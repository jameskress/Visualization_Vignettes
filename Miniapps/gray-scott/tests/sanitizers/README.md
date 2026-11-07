# Sanitizer runs (#13)

Build with the `host-cpu-asan` preset (AddressSanitizer and UndefinedBehaviorSanitizer):

```bash
cmake --preset my-host-asan && cmake --build --preset my-host-asan -j   # your user preset inheriting host-cpu-asan
tests/sanitizers/run_sanitized.sh build/my-host-asan 4                  # ranks; optional third argument: settings file
```

A clean run prints nothing from the sanitizers and exits 0. Use the no-output writer (the default settings file) so uninstrumented VTK stays out of the report.

What the script sets up, and why:

* `lsan.supp`: leak suppressions for libraries that keep memory until exit (Open MPI, PMIx, VTK's logger). Each entry says why. None covers miniapp code; a leak report that names one of our files is a real leak.
* `dlclose_noop.c`, preloaded: Open MPI unloads its components at `MPI_Finalize`, after which their frames read `<unknown module>` and cannot be suppressed by name. Keeping libraries mapped until exit fixes the names.
* `fast_unwind_on_malloc=0`: the fast unwinder stops inside libc, hiding the Open MPI caller of small `strdup` leaks.

Checked 2026-11-07 on the workstation: 1, 2 and 4 ranks exit 0 with no reports; a deliberate 4242-byte leak in a test program is still reported with its file and line under the same settings.
