# Sanitizer runs (#13)

Build with the `host-cpu-asan` preset (AddressSanitizer and UndefinedBehaviorSanitizer):

`CMakeUserPresets.json.example` defines `my-host-asan` (it inherits
`host-cpu-asan` and adds your `VTK_DIR`); copy it as in the README's Build
section, or add that entry to your existing `CMakeUserPresets.json`.

```bash
cmake --preset my-host-asan && cmake --build --preset my-host-asan -j
tests/sanitizers/run_sanitized.sh build/my-host-asan 4                  # ranks; optional third argument: settings file
```

A clean run prints nothing from the sanitizers and exits 0. Use the no-output writer (the default settings file) so uninstrumented VTK stays out of the report.

What the script sets up, and why:

* `lsan.supp`: two leak suppressions, each naming the start-up function the leak comes from: `ompi_mpi_init` (Open MPI, PMIx and friends keep their start-up state until exit) and VTK's logger. A rule matches any frame of a leak's stack, so a library-wide rule like `leak:libmpi.so` would also hide an MPI communicator, datatype or buffer that our code forgets to free. A leak report that names one of our files is a real leak.
* `check_suppressions.sh`: builds `mpi_leak_probe.c`, which leaks an MPI datatype, an info object, an `MPI_Alloc_mem` buffer and a heap block on purpose, and checks that all four are still reported under `lsan.supp`. Run it after changing the suppressions.
* `dlclose_noop.c`, preloaded: Open MPI unloads its components at `MPI_Finalize`, after which their frames read `<unknown module>` and cannot be suppressed by name. Keeping libraries mapped until exit fixes the names.
* `fast_unwind_on_malloc=0`: the fast unwinder stops inside libc, hiding the Open MPI caller of small `strdup` leaks.

Checked 2026-11-08 on the workstation: 1, 2 and 4 ranks exit 0 with no reports, and `check_suppressions.sh` passes. The earlier library-wide rules hid three of the probe's four leaks (all but the heap block).
