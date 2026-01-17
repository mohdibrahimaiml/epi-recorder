import subprocess
import sys

print("STARTING DIRECT STRESS TEST", flush=True)
for i in range(1, 6):
    print(f"\n--- ITERATION {i}/5 ---", flush=True)
    subprocess.run([sys.executable, "-m", "pip", "install", "epi-recorder", "--force-reinstall", "--no-cache-dir"], check=False)
    print(f"--- COMPLETED ITERATION {i} ---", flush=True)
print("DONE", flush=True)
