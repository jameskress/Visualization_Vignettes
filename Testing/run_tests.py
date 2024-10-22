import os
import subprocess
import shutil
import argparse

def find_executable(executable_name, env_var):
    """
    Find the executable for Visit or ParaView using an environment variable or system PATH.
    """
    executable_path = os.getenv(env_var)
    
    if executable_path:
        executable = os.path.join(executable_path, executable_name)
        if os.path.isfile(executable) and os.access(executable, os.X_OK):
            return executable
        else:
            raise ValueError(f"{env_var} is set but {executable_name} not found at {executable_path}")
    
    executable = shutil.which(executable_name)
    if executable:
        return executable
    
    raise ValueError(f"{executable_name} not found in system PATH or in {env_var}")

def run_local_visit(script_path, args, output_dir):
    """
    Run the Visit script locally and save logs in the output directory.
    """
    visit_exec = find_executable('visit', 'VISIT_PATH')
    
    cmd = [visit_exec, '-cli', '-nowin', '-s', script_path]
    cmd.extend(args)

    with open(os.path.join(output_dir, 'output.log'), 'w') as stdout_file, \
         open(os.path.join(output_dir, 'error.log'), 'w') as stderr_file:
        subprocess.run(cmd, stdout=stdout_file, stderr=stderr_file)
    
    print("Visit script executed locally.")

def run_local_paraview(script_path, args, output_dir):
    """
    Run the ParaView script locally using pvbatch and save logs in the output directory.
    """
    pvbatch_exec = find_executable('pvbatch', 'PARAVIEW_PATH')
    mpi_exec = find_executable('mpirun', 'MPI_EXEC_PATH')

    cmd = [mpi_exec, "-np", "1", "--bind-to", "none", pvbatch_exec, '--force-offscreen-rendering', script_path]
    cmd.extend(args)

    # Set OMP_NUM_THREADS to the desired number of threads
    env = os.environ.copy()  # Copy the current environment
    env['OMP_NUM_THREADS'] = '32'
    env['TBB_NUM_THREADS'] = '32'

    with open(os.path.join(output_dir, 'output.log'), 'w') as stdout_file, \
         open(os.path.join(output_dir, 'error.log'), 'w') as stderr_file:
        subprocess.run(cmd, stdout=stdout_file, stderr=stderr_file, env=env)

    print("ParaView script executed locally.")

def ensure_testing_directory(test_dir):
    """
    Ensure the 'Testing' directory exists in the test directory.
    """
    output_dir = os.path.join(test_dir, 'Testing')
    os.makedirs(output_dir, exist_ok=True)
    return output_dir

def find_test_script(test_dir):
    """
    Automatically find the test script in the directory.
    Exclude the run script itself and return the other Python script.
    """
    for file_name in os.listdir(test_dir):
        if file_name.endswith('.py') and file_name != 'run_script.py' and file_name != 'test_suite.py':
            return os.path.join(test_dir, file_name)
    
    raise FileNotFoundError("Test script not found in the directory.")

def main():
    parser = argparse.ArgumentParser(description="Run the local test script for a specific test directory.")
    parser.add_argument('test_dir', type=str, help="The test directory where the test script resides.")
    args = parser.parse_args()

    test_dir = args.test_dir
    output_dir = ensure_testing_directory(test_dir)

    # Automatically find the test script
    script_path = find_test_script(test_dir)

    # Determine the type of script based on its content
    if 'visit' in script_path.lower():
        run_local_visit(script_path, [], output_dir)
    elif 'paraview' in script_path.lower():
        run_local_paraview(script_path, [], output_dir)
    else:
        raise ValueError(f"Unknown script type for {script_path}")

if __name__ == "__main__":
    main()

