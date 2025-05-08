#!/usr/bin/env python3
import os
import subprocess
import time
import sys
from datetime import datetime

def create_timestamp_dir():
    """Create a timestamped directory for this test run"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    results_dir = f"results_{timestamp}"
    os.makedirs(results_dir, exist_ok=True)
    return results_dir

def run_script(script_name, results_dir):
    """Run a script and capture its output"""
    print(f"\n{'='*50}")
    print(f"Running {script_name}...")
    print(f"{'='*50}")
    
    # Full path to the script
    script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), script_name)
    
    # Make sure the script is executable
    try:
        os.chmod(script_path, 0o755)  # rwxr-xr-x
    except Exception as e:
        print(f"Warning: Could not make {script_name} executable: {e}")
    
    # Create a log file for this script's output
    log_file = os.path.join(results_dir, f"{os.path.splitext(script_name)[0]}_output.log")
    
    try:
        # Run the script and capture output
        process = subprocess.run(
            [script_path], 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE,
            text=True,
            timeout=60  # 1 minute timeout
        )
        
        # Save the output to the log file
        with open(log_file, 'w') as f:
            f.write(f"STDOUT:\n{process.stdout}\n\n")
            f.write(f"STDERR:\n{process.stderr}\n\n")
            f.write(f"Return code: {process.returncode}\n")
        
        # Also display the output to the console
        print(process.stdout)
        if process.stderr:
            print("ERRORS:", file=sys.stderr)
            print(process.stderr, file=sys.stderr)
        
        print(f"Output saved to {log_file}")
        return process.returncode == 0
        
    except subprocess.TimeoutExpired:
        with open(log_file, 'w') as f:
            f.write(f"ERROR: Script timed out after 60 seconds\n")
        print(f"ERROR: {script_name} timed out after 60 seconds")
        return False
    except Exception as e:
        with open(log_file, 'w') as f:
            f.write(f"ERROR: Failed to run script: {e}\n")
        print(f"ERROR: Failed to run {script_name}: {e}")
        return False

def main():
    # Get all Python scripts in the current directory
    current_dir = os.path.dirname(os.path.abspath(__file__))
    scripts = [f for f in os.listdir(current_dir) 
               if f.endswith('.py') and f != 'run_all_tests.py' and not f.startswith('_')]
    
    if not scripts:
        print("No test scripts found in the directory!")
        return
    
    print(f"Found {len(scripts)} test scripts to run:")
    for script in scripts:
        print(f"  - {script}")
    
    # Create results directory
    results_dir = create_timestamp_dir()
    print(f"\nTest results will be saved in: {results_dir}")
    
    # Run each script
    results = {}
    for script in scripts:
        success = run_script(script, results_dir)
        results[script] = "Success" if success else "Failed"
        
        # Move any output files from the script to the results directory
        for output_file in os.listdir(current_dir):
            if (output_file.endswith(('.html', '.txt', '.json')) and 
                not output_file.endswith('.py') and
                not os.path.isdir(output_file)):
                try:
                    dest_path = os.path.join(results_dir, output_file)
                    os.rename(output_file, dest_path)
                    print(f"Moved {output_file} to {results_dir}/")
                except Exception as e:
                    print(f"Could not move {output_file}: {e}")
        
        # Short pause between tests
        time.sleep(1)
    
    # Summary
    print("\n" + "="*50)
    print("TEST SUMMARY")
    print("="*50)
    for script, status in results.items():
        print(f"{script}: {status}")
    print("\nAll test results and outputs have been saved to the directory:")
    print(f"{os.path.abspath(results_dir)}")

if __name__ == "__main__":
    main()