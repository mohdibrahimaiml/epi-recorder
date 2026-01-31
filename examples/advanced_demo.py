import time
import random
import json
from pathlib import Path
from epi_recorder import record

# Simulate a typical AI workflow
def run_investor_demo():
    print("Starting EPI Investor Demo...")
    
    # 1. Setup Context
    print("Loading model weights (simulated)...")
    time.sleep(0.5)
    
    # 2. Record the 'critical' workflow
    # This context manager captures everything: inputs, outputs, code, and environment
    with record("investor_pitch.epi", 
                workflow_name="EPI-001: Investor Validation", 
                goal="Prove EPI works for any AI workflow",
                tags=["investor-demo", "mvp", "v2.0"]) as session:
        
        print("Initializing AI Agent...")
        # Simulate AI processing
        prompts = [
            "Analyze market trends for AI safety",
            "Predict adoption rates for 2025"
        ]
        
        results = []
        for i, prompt in enumerate(prompts):
            print(f"   Step {i+1}: Processing prompt '{prompt}'...")
            # Simulate variable latency
            time.sleep(0.3) 
            
            # Simulate non-deterministic output
            confidence = 0.85 + (random.random() * 0.14)
            result = {
                "prompt": prompt,
                "response": f"Analysis complete. Trend is POSITIVE. Confidence: {confidence:.2%}",
                "tokens": 150 + random.randint(0, 50)
            }
            results.append(result)
            
            # Log the step explicitly (optional, since auto-capture works too)
            session.log_step("model_inference", result)
            
        # 3. Create an artifact
        print("Saving analysis report...")
        report_data = {
            "summary": "EPI makes AI workflows transparent and verifiable.",
            "timestamp": time.time(),
            "data": results
        }
        
        with open("final_analysis.json", "w") as f:
            json.dump(report_data, f, indent=2)
            
        # Log the file artifact
        session.log_artifact(Path("final_analysis.json"))
        
        print("Workflow Complete!")

if __name__ == "__main__":
    run_investor_demo()


