import subprocess
import time
import sys
import concurrent.futures
import threading

# Configuration
TOTAL_ITERATIONS = 1000
CONCURRENT_WORKERS = 20  # Number of parallel installs

# Global counters
success_count = 0
fail_count = 0
completed_count = 0
lock = threading.Lock()
start_time = 0

def single_install(index):
    global success_count, fail_count, completed_count
    
    cmd = [sys.executable, "-m", "pip", "install", "epi-recorder", "--force-reinstall", "--no-cache-dir", "--quiet"]
    
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        with lock:
            success_count += 1
            result = "OK"
    except subprocess.CalledProcessError:
        with lock:
            fail_count += 1
            result = "FAIL"
    except Exception:
        with lock:
            fail_count += 1
            result = "ERROR"

    with lock:
        completed_count += 1
        elapsed = time.time() - start_time
        print(f"[{completed_count}/{TOTAL_ITERATIONS}] Worker {index} finished: {result} (Elapsed: {elapsed:.1f}s)")

def stress_test_parallel():
    global start_time
    print(f"Starting PARALLEL stress test: {TOTAL_ITERATIONS} iterations with {CONCURRENT_WORKERS} workers.")
    start_time = time.time()

    with concurrent.futures.ThreadPoolExecutor(max_workers=CONCURRENT_WORKERS) as executor:
        # Submit all tasks
        futures = [executor.submit(single_install, i) for i in range(TOTAL_ITERATIONS)]
        
        # Wait for all to complete
        concurrent.futures.wait(futures)

    total_time = time.time() - start_time
    print("\n" + "="*30)
    print("PARALLEL STRESS TEST COMPLETE")
    print(f"Total Iterations: {TOTAL_ITERATIONS}")
    print(f"Successful: {success_count}")
    print(f"Failed: {fail_count}")
    print(f"Total Time: {total_time:.2f}s")
    print(f"Average Time per Install: {total_time/TOTAL_ITERATIONS:.2f}s")
    print("="*30)

if __name__ == "__main__":
    stress_test_parallel()
