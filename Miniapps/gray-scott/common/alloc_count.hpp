#pragma once
//
// Allocation counting for the zero-copy checks (#25).
//
// gs_alloc_calls() and gs_alloc_bytes() return the number of heap
// allocations (operator new, malloc, calloc, realloc) and the bytes they
// requested since the process started, across all threads. They return 0
// unless the executable was built with GS_COUNT_ALLOCATIONS=ON, which links
// common/alloc_counter.cpp (a test-only replacement of the global allocation
// functions). Default builds pay nothing.

#include <cstdint>

std::uint64_t gs_alloc_calls();
std::uint64_t gs_alloc_bytes();
// The same, counting only allocations made by the calling thread. Regions
// of our own code are measured with these, so a logger or MPI progress
// thread allocating at the same moment does not show up in them.
std::uint64_t gs_alloc_calls_this_thread();
std::uint64_t gs_alloc_bytes_this_thread();
bool gs_alloc_counting_enabled();

// Allocations made by this thread between construction and delta().
struct AllocSnapshot
{
    std::uint64_t calls = gs_alloc_calls_this_thread();
    std::uint64_t bytes = gs_alloc_bytes_this_thread();
    std::uint64_t delta_calls() const { return gs_alloc_calls_this_thread() - calls; }
    std::uint64_t delta_bytes() const { return gs_alloc_bytes_this_thread() - bytes; }
};

// Allocations made by every thread (a backend's worker threads included).
struct ProcessAllocSnapshot
{
    std::uint64_t calls = gs_alloc_calls();
    std::uint64_t bytes = gs_alloc_bytes();
    std::uint64_t delta_calls() const { return gs_alloc_calls() - calls; }
    std::uint64_t delta_bytes() const { return gs_alloc_bytes() - bytes; }
};
