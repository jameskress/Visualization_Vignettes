/* Preloaded for sanitizer runs only (#13). Open MPI unloads its components at
 * MPI_Finalize, which leaves LeakSanitizer unable to name the frames of the
 * memory those components keep until exit ("<unknown module>"), so they could
 * not be suppressed by library name. Keeping every library mapped until exit
 * fixes the names; nothing is loaded or unloaded differently otherwise.
 * Build: cc -shared -fPIC -o dlclose_noop.so dlclose_noop.c */
int dlclose(void *handle)
{
    (void)handle;
    return 0;
}
