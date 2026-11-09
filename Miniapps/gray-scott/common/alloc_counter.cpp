// Test-only allocation counter (#25), linked only with GS_COUNT_ALLOCATIONS.
//
// Replaces the global operator new/delete family and wraps malloc, calloc
// and realloc through glibc's __libc_* entry points, counting calls and
// requested bytes with relaxed atomics. Frees are not counted: the check is
// "did this region allocate", not a leak tracker. glibc-specific (Linux).

#include "alloc_count.hpp"

#include <atomic>
#include <cstdlib>
#include <new>

extern "C" void *__libc_malloc(std::size_t);
extern "C" void *__libc_calloc(std::size_t, std::size_t);
extern "C" void *__libc_realloc(void *, std::size_t);
extern "C" void __libc_free(void *);

namespace
{
std::atomic<std::uint64_t> g_calls{0};
std::atomic<std::uint64_t> g_bytes{0};
// Plain integers, initialised to zero before any code runs, so they are
// safe to touch from inside malloc during thread start-up.
thread_local std::uint64_t t_calls = 0;
thread_local std::uint64_t t_bytes = 0;

inline void note(std::size_t n)
{
    g_calls.fetch_add(1, std::memory_order_relaxed);
    g_bytes.fetch_add(n, std::memory_order_relaxed);
    t_calls++;
    t_bytes += n;
}

void *counted_new(std::size_t n)
{
    note(n);
    if (void *p = __libc_malloc(n ? n : 1))
        return p;
    throw std::bad_alloc();
}
} // namespace

std::uint64_t gs_alloc_calls() { return g_calls.load(std::memory_order_relaxed); }
std::uint64_t gs_alloc_bytes() { return g_bytes.load(std::memory_order_relaxed); }
std::uint64_t gs_alloc_calls_this_thread() { return t_calls; }
std::uint64_t gs_alloc_bytes_this_thread() { return t_bytes; }
bool gs_alloc_counting_enabled() { return true; }

extern "C" void *malloc(std::size_t n)
{
    note(n);
    return __libc_malloc(n);
}
extern "C" void *calloc(std::size_t n, std::size_t s)
{
    note(n * s);
    return __libc_calloc(n, s);
}
extern "C" void *realloc(void *p, std::size_t n)
{
    note(n);
    return __libc_realloc(p, n);
}
extern "C" void free(void *p) { __libc_free(p); }

void *operator new(std::size_t n) { return counted_new(n); }
void *operator new[](std::size_t n) { return counted_new(n); }
void *operator new(std::size_t n, const std::nothrow_t &) noexcept
{
    note(n);
    return __libc_malloc(n ? n : 1);
}
void *operator new[](std::size_t n, const std::nothrow_t &) noexcept
{
    note(n);
    return __libc_malloc(n ? n : 1);
}
void operator delete(void *p) noexcept { __libc_free(p); }
void operator delete[](void *p) noexcept { __libc_free(p); }
void operator delete(void *p, std::size_t) noexcept { __libc_free(p); }
void operator delete[](void *p, std::size_t) noexcept { __libc_free(p); }
