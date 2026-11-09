/* Leaks on purpose, to check that lsan.supp hides only start-up leaks (#13).
 * Each function leaks one kind of resource that miniapp code could forget
 * to free. check_suppressions.sh expects every one to be reported. */
#include <mpi.h>
#include <stdlib.h>

static void leak_datatype(void)
{
    MPI_Datatype t;
    MPI_Type_vector(4, 2, 8, MPI_DOUBLE, &t);
    MPI_Type_commit(&t);
}

static void leak_info(void)
{
    MPI_Info info;
    MPI_Info_create(&info);
    MPI_Info_set(info, "key", "value");
}

static void leak_mpi_buffer(void)
{
    void *b;
    MPI_Alloc_mem(4096, MPI_INFO_NULL, &b);
}

static void leak_heap(void)
{
    void *p = malloc(4242);
    (void)p;
}

int main(int argc, char **argv)
{
    int provided;
    MPI_Init_thread(&argc, &argv, MPI_THREAD_MULTIPLE, &provided);
    leak_datatype();
    leak_info();
    leak_mpi_buffer();
    leak_heap();
    MPI_Finalize();
    return 0;
}
