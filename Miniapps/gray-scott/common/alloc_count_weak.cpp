// Fallbacks used when the allocation counter is not linked (#25).
#include "alloc_count.hpp"

__attribute__((weak)) std::uint64_t gs_alloc_calls() { return 0; }
__attribute__((weak)) std::uint64_t gs_alloc_bytes() { return 0; }
__attribute__((weak)) std::uint64_t gs_alloc_calls_this_thread() { return 0; }
__attribute__((weak)) std::uint64_t gs_alloc_bytes_this_thread() { return 0; }
__attribute__((weak)) bool gs_alloc_counting_enabled() { return false; }
