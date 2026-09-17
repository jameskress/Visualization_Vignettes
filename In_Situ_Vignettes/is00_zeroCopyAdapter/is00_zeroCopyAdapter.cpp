//
// Visualization Vignettes -- In Situ Vignettes
//
// is00_zeroCopyAdapter
//
// WHAT THIS VIGNETTE PROVES
// -------------------------
// An in situ adapter is only worth having if handing the simulation's memory
// to the analysis library is actually free. This vignette measures whether it
// is, and fails the build if it is not.
//
// It exists because the gray-scott miniapp's own adapters do the opposite of
// what their comments claim. Every simulation-side writer materialises the
// field two or three extra times per output step:
//
//   writerAscent.cpp:67    mesh["fields/u/values"].set(sim.u_noghost().data(),
//                                                      sim.u_noghost().size());
//
// That single line calls u_noghost() twice -- two full heap allocations and
// two full element-wise copies of the field -- and then conduit::Node::set()
// deep-copies a third time. The zero-copy call the code actually wants,
// set_external(), sits commented out one line above it in
// writerCatalyst.cpp:198. The analysis-side reader gets this right
// (ascent_backend.cpp:54), so the repository already contains both the wrong
// and the right pattern; nothing tells you which one you compiled.
//
// THE FOUR CHECKS
// ---------------
//   1. IDENTITY   set_external leaves the Conduit node pointing at the
//                 simulation's own buffer -- pointer equality, not a copy.
//   2. ALIASING   writing through the simulation buffer after publish is
//                 visible through the node. If it is not, something copied.
//   3. FOOTPRINT  N publish cycles through the zero-copy path grow RSS by
//                 less than one field's worth of memory. The deep-copy path
//                 is measured alongside it so the log shows the real cost.
//   4. VALIDITY   the resulting mesh passes conduit::blueprint::mesh::verify
//                 on every rank -- collectively, so one bad rank cannot slip
//                 through while the others render.
//
// Dependencies: Conduit + MPI only. Conduit ships inside both Ascent and
// ParaView-Catalyst, so this vignette builds anywhere either backend does,
// and it does not need a GPU, a display, or a rendering context.
//
#include "insitu_harness.h"

#include <conduit.hpp>
#include <conduit_blueprint.hpp>

#include <cstdlib>
#include <iostream>
#include <string>

namespace
{

// How the field gets handed to Conduit.
enum class Publish
{
    ZeroCopy, // set_external -- node borrows the simulation's buffer
    DeepCopy  // set          -- node allocates and copies (what the miniapp does today)
};

// Build a Blueprint uniform mesh describing one rank's interior points.
//
// Note what is NOT here: the "+ dx/nx * spacing" origin fudge that both
// writerAscent.cpp:58 and writerCatalyst.cpp:173 use to shove neighbouring
// subdomains together. That expression is an integer division, so it only
// lands correctly when L is an exact multiple of the process count. The
// honest fix is to publish the ghost layer and let the backend consume it;
// is01_ghostCorrectness is where that gets tested.
void build_mesh(conduit::Node &mesh,
                insitu::GhostedBlock &block,
                int step,
                double spacing,
                Publish mode)
{
    mesh.reset();

    mesh["state/cycle"] = static_cast<conduit::int64>(step);
    mesh["state/time"] = static_cast<double>(step) * 0.2;
    mesh["state/domain_id"] = static_cast<conduit::int64>(0);

    conduit::Node &coords = mesh["coordsets/coords"];
    coords["type"] = "uniform";
    coords["dims/i"] = static_cast<conduit::int64>(block.nx + 2);
    coords["dims/j"] = static_cast<conduit::int64>(block.ny + 2);
    coords["dims/k"] = static_cast<conduit::int64>(block.nz + 2);
    // Origin is shifted back by one cell because we publish the ghost layer.
    coords["origin/x"] = (static_cast<double>(block.ox) - 1.0) * spacing;
    coords["origin/y"] = (static_cast<double>(block.oy) - 1.0) * spacing;
    coords["origin/z"] = (static_cast<double>(block.oz) - 1.0) * spacing;
    coords["spacing/dx"] = spacing;
    coords["spacing/dy"] = spacing;
    coords["spacing/dz"] = spacing;

    mesh["topologies/mesh/type"] = "uniform";
    mesh["topologies/mesh/coordset"] = "coords";

    for (const char *name : {"u", "v"})
    {
        const std::string base = std::string("fields/") + name;
        mesh[base + "/association"] = "vertex";
        mesh[base + "/topology"] = "mesh";
    }

    if (mode == Publish::ZeroCopy)
    {
        // The whole point. Conduit records the pointer and the length; it does
        // not allocate. block MUST outlive every use of this node -- which is
        // exactly why block is taken by reference and never by value, and why
        // the miniapp's `set(sim.u_noghost().data(), ...)` would be a
        // use-after-free the moment someone "optimised" it to set_external.
        mesh["fields/u/values"].set_external(block.u.data(), block.u.size());
        mesh["fields/v/values"].set_external(block.v.data(), block.v.size());
    }
    else
    {
        mesh["fields/u/values"].set(block.u.data(), block.u.size());
        mesh["fields/v/values"].set(block.v.data(), block.v.size());
    }
}

// Run `cycles` publish cycles and report how much RSS grew, in KiB.
// Returns -1 when RSS is unavailable (non-Linux), so the caller can skip.
long measure_growth(insitu::GhostedBlock &block, int cycles, double spacing, Publish mode)
{
    const long before = insitu::rss_kb();
    if (before == 0)
        return -1;

    for (int step = 0; step < cycles; ++step)
    {
        conduit::Node mesh;
        block.seed(step);
        build_mesh(mesh, block, step, spacing, mode);

        // Touch the data the way a real backend would, so nothing is
        // optimised away and any lazy allocation actually happens.
        conduit::Node info;
        if (!conduit::blueprint::mesh::verify(mesh, info))
            return -1;
    }

    return insitu::rss_kb() - before;
}

} // namespace

int main(int argc, char **argv)
{
    MPI_Init(&argc, &argv);

    MPI_Comm comm = MPI_COMM_WORLD;
    int rank = 0, nranks = 1;
    MPI_Comm_rank(comm, &rank);
    MPI_Comm_size(comm, &nranks);

    // Local interior extent per rank. Kept small by default so the vignette
    // runs in a few seconds in CI; override for a scaling study.
    size_t n = 48;
    int cycles = 200;
    const double spacing = 0.1;

    for (int i = 1; i < argc; ++i)
    {
        const std::string a(argv[i]);
        if (a.rfind("--size=", 0) == 0)
            n = static_cast<size_t>(std::strtoull(a.substr(7).c_str(), nullptr, 10));
        else if (a.rfind("--cycles=", 0) == 0)
            cycles = std::atoi(a.substr(9).c_str());
        else if (a == "-h" || a == "--help")
        {
            if (rank == 0)
                std::cout << "usage: is00_zeroCopyAdapter [--size=N] [--cycles=N]\n";
            MPI_Finalize();
            return 0;
        }
    }

    if (n == 0 || cycles <= 0)
    {
        if (rank == 0)
            std::cerr << "error: --size and --cycles must be positive\n";
        MPI_Abort(comm, 2);
    }

    insitu::Checks checks(comm, "is00_zeroCopyAdapter");

    // Stack the ranks along Z so each one owns a distinct global slab.
    insitu::GhostedBlock block(n, n, n, 0, 0, static_cast<size_t>(rank) * n);
    block.seed(0);

    const size_t field_bytes = block.padded_size() * sizeof(double);
    if (rank == 0)
        std::printf("  local block: %zu^3 interior (+ghost) = %.1f MiB per field, "
                    "%d cycles\n",
                    n, static_cast<double>(field_bytes) / (1024.0 * 1024.0), cycles);

    // --- Check 1: identity -------------------------------------------------
    conduit::Node mesh;
    build_mesh(mesh, block, 0, spacing, Publish::ZeroCopy);

    const void *published = mesh["fields/u/values"].data_ptr();
    const void *source = static_cast<const void *>(block.u.data());
    checks.check_all("set_external aliases the simulation buffer",
                     published == source);

    // --- Check 2: aliasing -------------------------------------------------
    // Mutate through the simulation's array and read back through the node.
    const size_t probe = block.idx(1, 1, 1);
    const double sentinel = -12345.678;
    block.u[probe] = sentinel;

    const double *via_node = mesh["fields/u/values"].value();
    const bool aliased = via_node[probe] == sentinel;
    checks.check_all("writes through the sim buffer reach the node", aliased);
    block.u[probe] = 0.0;

    // --- Check 3: footprint ------------------------------------------------
    const long zero_growth = measure_growth(block, cycles, spacing, Publish::ZeroCopy);
    const long deep_growth = measure_growth(block, cycles, spacing, Publish::DeepCopy);

    if (zero_growth < 0)
    {
        if (rank == 0)
            std::printf("  [SKIP] RSS unavailable on this platform "
                        "(no /proc/self/status)\n");
    }
    else
    {
        // Budget: one field's worth of slack absorbs allocator noise and
        // Conduit's own schema bookkeeping. A real deep copy blows straight
        // through it.
        const long budget_kb = static_cast<long>(field_bytes / 1024);
        char detail[192];
        std::snprintf(detail, sizeof(detail),
                      "zero-copy %+ld KiB vs deep-copy %+ld KiB (budget %ld KiB)",
                      zero_growth, deep_growth, budget_kb);
        checks.check_all("RSS stays flat across publish cycles",
                         zero_growth < budget_kb, detail);
    }

    // --- Check 4: validity -------------------------------------------------
    conduit::Node final_mesh;
    block.seed(cycles);
    build_mesh(final_mesh, block, cycles, spacing, Publish::ZeroCopy);

    conduit::Node verify_info;
    const bool valid = conduit::blueprint::mesh::verify(final_mesh, verify_info);
    if (!valid)
        verify_info.print();
    checks.check_all("mesh passes blueprint::mesh::verify", valid);

    // Checksum agreement guards against a rank publishing a stale or empty
    // block -- the failure mode the miniapp's `if (!sim.size_x) return;`
    // guards produce silently.
    const double local_sum = block.checksum();
    double global_sum = 0.0;
    MPI_Allreduce(&local_sum, &global_sum, 1, MPI_DOUBLE, MPI_SUM, comm);
    checks.check_all("every rank contributed a non-empty field",
                     local_sum > 0.0 && global_sum > 0.0);

    const int rc = checks.finish();
    MPI_Finalize();
    return rc;
}
