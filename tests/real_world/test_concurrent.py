import threading
import time
from epi_recorder import record

def agent_task(name, thread_id):
    """Simulates one agent in a crew"""
    with record(workflow_name=f"concurrent_agent_{thread_id}"):
        print(f"[{name}] Starting...")
        
        # Simulate work
        for i in range(3):
            time.sleep(0.3)  # Reduced sleep for faster testing
            print(f"[{name}] Step {i}")
            
            # Simulate LLM call (without actually calling API)
            print(f"[{name}] Simulated LLM call for step {i}")
        
        print(f"[{name}] Done!")

# Launch 5 threads simultaneously (like CrewAI)
threads = []
for i in range(5):
    t = threading.Thread(target=agent_task, args=(f"Agent-{i}", i))
    threads.append(t)

print("Launching 5 concurrent agents...")
for t in threads:
    t.start()

for t in threads:
    t.join()

print("All agents complete!")


