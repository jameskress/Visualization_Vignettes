#include "analysis_backend_interface.h"
#include "ascent_backend.h"
#ifdef USE_CATALYST
#include "catalyst_backend.h"
#endif

#include <stdexcept>
#include <string>

// Factory function to create appropriate backend based on name
std::unique_ptr<AnalysisBackend> CreateBackend(const std::string &name, const BackendOptions &opts)
{
    if (name == "ascent")
    {
        return std::make_unique<AscentBackend>(opts);
    }
#ifdef USE_CATALYST
    else if (name == "catalyst" || name == "catalyst_insitu" || name == "catalyst_io")
    {
        return std::make_unique<CatalystBackend>(opts);
    }
#endif
    else
    {
        throw std::runtime_error("Unsupported backend type: " + name);
    }
    return nullptr;
}