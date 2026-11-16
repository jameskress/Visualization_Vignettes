#include "adios_reader.h"
#include "analysis_backend_interface.h"
#include <numeric>
#include <algorithm>
#include <cctype>
#include <cmath>
#include <iostream>
#include <optional>
#include <stdexcept>
#include <array>
#include <chrono>
#include <climits>
#include <cstring>
#include <thread>

AdiosReader::AdiosReader(const BackendOptions &opts, PerfLogger &logger)
    : m_opts(opts), m_logger(logger), m_comm(opts.comm)
{
    // With the simulation's XML, the reader's engine parameters come from its
    // <io name="AnalysisInput"> block. Without it the reader had no way to get
    // any: ControlModule=epoll was set for the writer only, and a reader with
    // more than 1023 writers stays on select() and hangs (ADIOS2 #5272).
    if (m_opts.adios_config.empty())
        m_adios = std::make_unique<adios2::ADIOS>(m_comm);
    else
        m_adios = std::make_unique<adios2::ADIOS>(m_opts.adios_config, m_comm);
    m_io = std::make_unique<adios2::IO>(m_adios->DeclareIO("AnalysisInput"));
    if (m_opts.reader_shared_planes != "exchange" && m_opts.reader_shared_planes != "read")
        throw std::runtime_error("reader_shared_planes must be \"exchange\" or \"read\", not \"" +
                                 m_opts.reader_shared_planes + "\"");

    // A parameter the XML sets keeps the XML's value. BP5 matches parameter
    // names case-insensitively but SST matches them exactly (ADIOS2 2.11,
    // SstParamParser.cpp), so the XML's value is found in any case and
    // set again under the canonical name, which both engines read.
    const auto xml_params = m_io->Parameters();
    auto xml_value = [&xml_params](std::string key) -> std::optional<std::string> {
        const auto exact = xml_params.find(key);
        if (exact != xml_params.end())
            return exact->second;
        std::transform(key.begin(), key.end(), key.begin(),
                       [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
        for (const auto &kv : xml_params)
        {
            std::string k = kv.first;
            std::transform(k.begin(), k.end(), k.begin(),
                           [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
            if (k == key)
                return kv.second;
        }
        return std::nullopt;
    };

    if (m_opts.adios_verbose > 0)
        m_io->SetParameter("verbose", std::to_string(m_opts.adios_verbose));

    // The engine comes from the settings (or --engine), which also choose
    // the writer's, so the two always agree.
    m_io->SetEngine(m_opts.adios_engine);

    // Automatically set a short OpenTimeout for non-streaming engines.
    // This prevents the application from hanging indefinitely on corrupt/inaccessible files.
    // For SST, wait long enough for the simulation to start, which at scale
    // includes reading its checkpoint (ADIOS2's default of 60 s is too short, #78).
    // ADIOS2 matches engine names case-insensitively ("sst" is SST too).
    std::string engine = m_opts.adios_engine;
    std::transform(engine.begin(), engine.end(), engine.begin(),
                   [](unsigned char c) { return static_cast<char>(std::toupper(c)); });
    if (const auto xml_timeout = xml_value("OpenTimeoutSecs"))
    {
        m_io->SetParameter("OpenTimeoutSecs", *xml_timeout);
    }
    else if (engine != "SST" && engine != "EFFIS") // EFFIS is SST under another name
    {
        m_io->SetParameter("OpenTimeoutSecs", "5.0");
    }
    else
    {
        // SST takes whole seconds: round up, at least 1, within int range.
        const double t = std::min(std::max(std::ceil(m_opts.sst_open_timeout_s), 1.0), 2147483647.0);
        m_io->SetParameter("OpenTimeoutSecs", std::to_string(static_cast<int>(t)));
    }

    int rank = 0;
    MPI_Comm_rank(m_comm, &rank);
    if (rank == 0)
    {
        std::cout << "ADIOS2 reader parameters (" << engine << "):";
        for (const auto &kv : m_io->Parameters())
            std::cout << " " << kv.first << "=" << kv.second;
        std::cout << std::endl;
    }

    // A brick exchange reads the owned box through a memory selection.
    // SST honours that only with BP5 marshalling from ADIOS2 2.9.2 (the
    // FFS path and older BP5 put the values contiguously, at the wrong
    // places). Where that cannot be relied on, the whole run reads the
    // planes from the writers instead: it must be every reader or none,
    // or a neighbour would wait for a plane that is never sent. A slab
    // needs no memory selection.
    if (m_opts.reader_shared_planes == "exchange" && m_opts.read_decomposition == "brick" &&
        (engine == "SST" || engine == "EFFIS"))
    {
        bool honoured = true;
#if !defined(ADIOS2_VERSION) || ADIOS2_VERSION < 20902
        honoured = false;
#endif
        auto is_bp5 = [](std::string m) {
            std::transform(m.begin(), m.end(), m.begin(),
                           [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
            return m == "bp5";
        };
        if (const auto marshal = xml_value("MarshalMethod"))
            honoured = honoured && is_bp5(*marshal);
        // SST takes the read path from the writer's marshalling, which the
        // simulation sets in its <io name="SimulationOutput"> block of the
        // same XML; SST reads only the exact key (writerADIOS.cpp), and
        // without it marshals with BP5.
        if (!m_opts.adios_config.empty())
        {
            const auto writer_params = m_adios->DeclareIO("SimulationOutput").Parameters();
            const auto it = writer_params.find("MarshalMethod");
            if (it != writer_params.end())
                honoured = honoured && is_bp5(it->second);
        }
        if (!honoured)
        {
            m_opts.reader_shared_planes = "read";
            if (rank == 0)
                std::cout << "reader_shared_planes: exchange needs SST with BP5 marshalling and ADIOS2 2.9.2 "
                             "or later for a brick; reading the shared planes from the writers instead"
                          << std::endl;
        }
    }

    m_engine = std::make_unique<adios2::Engine>(m_io->Open(m_opts.adios_file, adios2::Mode::Read));

    ReadFidesAttributes(); // Read attributes and potentially update m_opts
}

AdiosReader::~AdiosReader()
{
    if (m_engine)
        m_engine->Close();
}

adios2::StepStatus AdiosReader::BeginStep()
{
    m_logger.start("ADIOS_Wait");
    float step_timeout = (m_opts.sst_wait_mode == "timeout") ? static_cast<float>(m_opts.sst_timeout_seconds) : -1.0f;
    const adios2::StepStatus status = m_engine->BeginStep(adios2::StepMode::Read, step_timeout);
    m_logger.stop("ADIOS_Wait");
    return status;
}

bool AdiosReader::NextStep()
{
    for (;;)
    {
        switch (BeginStep())
        {
        case adios2::StepStatus::OK:
            // Over SST, attributes arrive with the first step, after Open();
            // read the Fides origin and spacing again now (#42).
            if (!m_attributes_after_first_step)
            {
                ReadFidesAttributes();
                m_attributes_after_first_step = true;
            }
            return true;
        case adios2::StepStatus::EndOfStream:
            return false;
        case adios2::StepStatus::NotReady:
            // The timeout wait mode: the simulation is slower than the
            // timeout. Wait again; only EndOfStream ends the stream. A short
            // pause keeps a zero timeout from spinning a core.
            std::this_thread::sleep_for(std::chrono::milliseconds(10));
            continue;
        default:
            throw std::runtime_error("ADIOS2 BeginStep failed (StepStatus::OtherError)");
        }
    }
}

void AdiosReader::EndStep()
{
    m_logger.start("ADIOS_EndStep");
    m_engine->EndStep();
    m_logger.stop("ADIOS_EndStep");
    if (m_opts.reader_shared_planes == "exchange")
    {
        m_logger.start("Halo_Exchange");
        ExchangeSharedPlanes();
        m_logger.stop("Halo_Exchange");
    }
    m_pending_planes.clear();
}

// Each piece sends the first plane of its box along an axis to the piece
// before it on that axis, which stores it as its shared high plane. The axes
// go one at a time, slowest first, and each plane spans the extent already
// complete on the axes done so far, so a piece's corner and edge points
// arrive by way of its other neighbours. Neighbours along an axis have the
// same extents on every other axis, so both sides agree on every plane's
// size without asking. Empty pieces (more readers than planes) are the last
// along an axis and neither send nor receive.
void AdiosReader::ExchangeSharedPlanes()
{
    const size_t nd = m_parts.size();
    if (nd == 0 || nd > 3)
        return;
    const bool owns = !m_pending_planes.empty();
    const size_t off = 3 - nd;

    // One axis of a pending buffer's box for the plane along axis d:
    // complete on the axes already done, owned on the rest.
    auto extent = [&](const PendingPlanes &p, size_t d, size_t a) {
        return a == d ? size_t{1} : (a < d ? p.local_dims[a] : p.owned_dims[a]);
    };
    auto plane_bytes = [&](const PendingPlanes &p, size_t d) {
        size_t n = p.elem_size;
        for (size_t a = 0; a < nd; ++a)
            n *= extent(p, d, a);
        return n;
    };
    // Copies the plane at index `at` along axis d between the buffer and a
    // packed array, one run along the fastest axis at a time.
    auto copy_plane = [&](const PendingPlanes &p, size_t d, size_t at, char *flat, bool pack) {
        std::array<size_t, 3> L{1, 1, 1}, e{1, 1, 1}, lo{0, 0, 0};
        for (size_t a = 0; a < nd; ++a)
        {
            L[off + a] = p.local_dims[a];
            e[off + a] = extent(p, d, a);
        }
        lo[off + d] = at;
        const size_t run = e[2] * p.elem_size;
        for (size_t k = 0; k < e[0]; ++k)
            for (size_t j = 0; j < e[1]; ++j)
            {
                char *row = p.data + (((lo[0] + k) * L[1] + (lo[1] + j)) * L[2] + lo[2]) * p.elem_size;
                if (pack)
                    std::memcpy(flat, row, run);
                else
                    std::memcpy(row, flat, run);
                flat += run;
            }
    };
    auto rank_of = [&](size_t d, int delta) {
        int r = 0;
        for (size_t a = 0; a < nd; ++a)
            r = r * m_parts[a] + m_coords[a] + (a == d ? delta : 0);
        return r;
    };

    std::vector<char> &send_buf = m_send_planes, &recv_buf = m_recv_planes; // kept across steps
    for (size_t d = 0; d < nd; ++d)
    {
        const bool send = owns && m_coords[d] > 0;
        const bool recv = owns && m_pending_planes.front().shared_high[d];
        if (!send && !recv)
            continue;
        size_t total = 0;
        for (const PendingPlanes &p : m_pending_planes)
            total += plane_bytes(p, d);
        if (total > static_cast<size_t>(INT_MAX))
            throw std::runtime_error("shared plane exchange: a plane of " + std::to_string(total) +
                                     " bytes is too large for one MPI message; use reader_shared_planes \"read\"");
        const int tag = 7100 + static_cast<int>(d);
        MPI_Request reqs[2];
        int nreq = 0;
        if (recv)
        {
            recv_buf.resize(total);
            MPI_Irecv(recv_buf.data(), static_cast<int>(total), MPI_BYTE, rank_of(d, +1), tag, m_comm, &reqs[nreq++]);
        }
        if (send)
        {
            send_buf.resize(total);
            char *flat = send_buf.data();
            for (const PendingPlanes &p : m_pending_planes)
            {
                copy_plane(p, d, 0, flat, true);
                flat += plane_bytes(p, d);
            }
            MPI_Isend(send_buf.data(), static_cast<int>(total), MPI_BYTE, rank_of(d, -1), tag, m_comm, &reqs[nreq++]);
        }
        MPI_Waitall(nreq, reqs, MPI_STATUSES_IGNORE);
        if (recv)
        {
            char *flat = recv_buf.data();
            for (const PendingPlanes &p : m_pending_planes)
            {
                copy_plane(p, d, p.owned_dims[d], flat, false);
                flat += plane_bytes(p, d);
            }
        }
    }
}

size_t AdiosReader::CurrentStep() const
{
    return m_engine->CurrentStep();
}

const BackendOptions &AdiosReader::GetOptions() const
{
    return m_opts;
}

MPI_Comm AdiosReader::GetComm() const
{
    return m_comm;
}

double AdiosReader::TakeAllocFaults()
{
    const double f = m_alloc_faults;
    m_alloc_faults = 0.0;
    return f;
}

template <typename Vec>
size_t AdiosReader::productDims(const Vec &v)
{
    if (v.empty())
        return 0;
    size_t p = 1;
    for (auto &x : v)
        p *= static_cast<size_t>(x);
    return p;
}

void AdiosReader::ReadFidesAttributes()
{
    try
    {
        auto attr_o = m_io->InquireAttribute<double>("Fides_Origin");
        if (attr_o)
        {
            auto data = attr_o.Data();
            if (data.size() >= 3)
                m_opts.origin = {data[0], data[1], data[2]};
        }
    }
    catch (const std::exception &)
    { /* Ignore */
    }
    try
    {
        auto attr_s = m_io->InquireAttribute<double>("Fides_Spacing");
        if (attr_s)
        {
            auto data = attr_s.Data();
            if (data.size() >= 3)
                m_opts.spacing = {data[0], data[1], data[2]};
        }
    }
    catch (const std::exception &)
    { /* Ignore */
    }
}

// Method to read data in "preserve" block mode which returns the data to the reader just
// as it was written, with each rank getting a subset of the blocks.
// The blocks_out vector will contain one entry per block assigned to this rank,
// with the block's start indices, dimensions, and data buffer.
template <typename T>
size_t AdiosReader::ReadPreserve(const std::string &var_name, std::vector<BlockData<T>> &blocks_out)
{
    blocks_out.clear();
    if (var_name.empty())
        return 0;

    auto var = m_io->InquireVariable<T>(var_name);
    if (!var)
        return 0;

    int rank, size;
    MPI_Comm_rank(m_comm, &rank);
    MPI_Comm_size(m_comm, &size);

    auto adios_blocks = m_engine->BlocksInfo(var, m_engine->CurrentStep());
    for (size_t i = 0; i < adios_blocks.size(); ++i)
    {
        if (i % size == rank)
        {
            BlockData<T> block;
            block.start = adios_blocks[i].Start;
            block.dims = adios_blocks[i].Count;
            var.SetBlockSelection(i);
            size_t count = productDims(block.dims);
            block.buffer.resize(count);

            std::string timer_name = "ADIOS_Read_" + var_name;
            m_logger.start(timer_name);
            m_engine->Get(var, block.buffer.data(), adios2::Mode::Sync);
            m_logger.stop(timer_name);
            blocks_out.push_back(std::move(block));
        }
    }
    return adios_blocks.size();
}

// Method to read data in "repartition" mode which redistributes the data
// across ranks in a balanced manner. Each rank gets a contiguous slab of the
// global data. The buffer will contain the local data, and read_info will
// provide information about the global and local dimensions and offsets.
template <typename T>
void AdiosReader::ReadRepartition(const std::string &var_name, std::vector<T> &buffer, RepartitionInfo &read_info)
{
    if (var_name.empty())
    {
        buffer.clear();
        return;
    }
    // Read_Setup: the selection bookkeeping. Read_Alloc: sizing the buffer.
    // Both are inside the backends' Blueprint_Time (#103 follow-up).
    m_logger.start("Read_Setup");
    auto var = m_io->InquireVariable<T>(var_name);
    if (!var)
    {
        m_logger.stop("Read_Setup");
        // A named variable that is not in the stream is a settings or
        // writer mismatch: say so, rather than render empty data (#42).
        // (An empty name skips the field, above.)
        throw std::runtime_error("variable '" + var_name + "' is not in the ADIOS2 stream " + m_opts.adios_file);
    }

    int rank, size;
    MPI_Comm_rank(m_comm, &rank);
    MPI_Comm_size(m_comm, &size);

    read_info.global_dims = var.Shape();
    const size_t n_dims = read_info.global_dims.size();
    read_info.local_start.assign(n_dims, 0);
    read_info.local_dims = read_info.global_dims;
    read_info.owned_dims = read_info.global_dims;
    read_info.shared_high.assign(n_dims, false);

    // Ranks per axis, in ADIOS2's order (slowest first).
    std::vector<int> parts(n_dims, 1);
    if (n_dims > 0)
    {
        if (m_opts.read_decomposition == "brick" && n_dims == 3)
        {
            // The simulation's own split: MPI_Dims_create, with dims[0] along
            // x, the fastest axis (simulation/gray-scott.cpp). Splitting the
            // readers the same way lines a brick's owned box up with whole
            // writer blocks when every reader boundary falls on a writer boundary
            // (for example when L divides evenly by both counts on each axis).
            // The shared planes still reach into the next blocks.
            int dims[3] = {0, 0, 0};
            MPI_Dims_create(size, 3, dims);
            parts = {dims[2], dims[1], dims[0]}; // z, y, x
        }
        else
        {
            parts[0] = size; // slabs along the slowest axis
        }
    }

    // This rank's position in that grid, slowest axis first.
    std::vector<int> coords(n_dims, 0);
    {
        int remaining = rank;
        for (size_t d = n_dims; d-- > 0;)
        {
            coords[d] = remaining % parts[d];
            remaining /= parts[d];
        }
    }
    m_parts = parts;
    m_coords = coords;

    for (size_t d = 0; d < n_dims; ++d)
    {
        const size_t n = read_info.global_dims[d];
        const size_t p = static_cast<size_t>(parts[d]);
        const size_t c = static_cast<size_t>(coords[d]);
        const size_t base = n / p;
        const size_t remainder = n % p;
        read_info.local_start[d] = c * base + std::min(c, remainder);
        read_info.owned_dims[d] = base + (c < remainder ? 1 : 0);
        read_info.local_dims[d] = read_info.owned_dims[d];
        // Fetch one extra plane to close the physical gap between pieces:
        // every piece but the last along this axis, and only when it owns
        // something (more readers than planes leaves some with none).
        if (c != p - 1 && read_info.owned_dims[d] > 0 && read_info.local_start[d] + read_info.owned_dims[d] < n)
        {
            read_info.local_dims[d] += 1;
            read_info.shared_high[d] = true;
        }
    }

    // A rank that owns nothing along some axis reads nothing.
    for (size_t d = 0; d < n_dims; ++d)
        if (read_info.owned_dims[d] == 0)
        {
            std::fill(read_info.local_dims.begin(), read_info.local_dims.end(), 0);
            std::fill(read_info.owned_dims.begin(), read_info.owned_dims.end(), 0);
            std::fill(read_info.shared_high.begin(), read_info.shared_high.end(), false);
            break;
        }

    size_t local_count = productDims(read_info.local_dims);
    if (local_count > 0)
    {
        // Every piece with points takes part in the exchange, the last along
        // an axis too: it has no shared plane, but sends its first plane to
        // the piece before it.
        const bool exchange = m_opts.reader_shared_planes == "exchange" && n_dims <= 3;
        if (exchange)
        {
            // Read only the owned box from the writers, placed at the start
            // of the buffer; the shared planes come from the neighbours at
            // EndStep. With only the slowest axis shared (a slab) the owned
            // box is already a contiguous prefix of the buffer.
            var.SetSelection({read_info.local_start, read_info.owned_dims});
            bool prefix = true;
            for (size_t d = 1; d < n_dims; ++d)
                prefix = prefix && !read_info.shared_high[d];
            if (!prefix)
                var.SetMemorySelection({adios2::Dims(n_dims, 0), read_info.local_dims});
        }
        else
        {
            var.SetSelection({read_info.local_start, read_info.local_dims});
        }
        m_logger.stop("Read_Setup");
        m_logger.start("Read_Alloc");
        const double faults0 = ProcessMinorFaults();
        if (buffer.size() != local_count)
            buffer.resize(local_count);
        m_alloc_faults += ProcessMinorFaults() - faults0;
        m_logger.stop("Read_Alloc");

        // Deferred: the reads of a step complete together at EndStep(), one
        // round of communication with the writers instead of one per field
        // (ADIOS2 recommends this for SST). The buffer must not be touched
        // until then; every backend ends the step before using it (#42).
        std::string timer_name = "ADIOS_Read_" + var_name;
        m_logger.start(timer_name);
        m_engine->Get(var, buffer.data(), adios2::Mode::Deferred);
        m_logger.stop(timer_name);
        if (exchange)
            m_pending_planes.push_back({reinterpret_cast<char *>(buffer.data()), sizeof(T), read_info.local_dims,
                                        read_info.owned_dims, read_info.shared_high});
    }
    else
    {
        m_logger.stop("Read_Setup");
        buffer.clear();
    }
}

// Explicit template instantiations
template size_t AdiosReader::ReadPreserve<double>(const std::string &, std::vector<BlockData<double>> &);
template void AdiosReader::ReadRepartition<double>(const std::string &, std::vector<double> &, RepartitionInfo &);
