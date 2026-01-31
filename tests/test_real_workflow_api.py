"""
Real AI Workflow Test - Python API
Simulates a complete AI workflow with LLM calls and data processing
"""
from epi_recorder import record
from pathlib import Path
import json
import time

print("="*70)
print("TESTING EPI-RECORDER WITH REAL AI WORKFLOW - PYTHON API")
print("="*70)
print()

# Test 1: Simple AI workflow with decorator
print("[TEST 1] Simple AI Workflow with Decorator")
print("-"*70)

@record(
    goal="Analyze customer sentiment",
    metrics={"accuracy": 0.92, "latency_ms": 250},
    metadata_tags=["production", "sentiment-analysis", "v1.0"]
)
def analyze_customer_feedback():
    """Simulated AI sentiment analysis workflow"""
    print("  Processing customer feedback...")
    
    # Simulate API call (would be real OpenAI/etc in production)
    feedback = "This product is amazing! Best purchase ever."
    
    # Simulate AI processing
    time.sleep(0.3)
    
    result = {
        "sentiment": "positive",
        "confidence": 0.95,
        "keywords": ["amazing", "best"],
        "recommendation": "promote_review"
    }
    
    print(f"  Analysis complete: {result['sentiment']} ({result['confidence']})")
    return result

result = analyze_customer_feedback()
print(f"[OK] Workflow completed: {result}")
print()

# Test 2: Context manager with artifacts
print("[TEST 2] AI Workflow with Artifacts and Manual Logging")
print("-"*70)

with record(
    "ai_pipeline_test.epi",
    goal="Complete AI data pipeline",
    metrics={"total_cost": 0.15, "items_processed": 100}
) as session:
    print("  Step 1: Fetching data...")
    # Simulate data fetch
    data = {"users": 100, "requests": 500}
    
    session.log_step("data.fetched", {
        "source": "api.example.com",
        "records": data["users"]
    })
    
    print("  Step 2: Processing with AI...")
    time.sleep(0.2)
    
    # Simulate AI processing
    session.log_step("ai.processing", {
        "model": "gpt-4",
        "operation": "classification",
        "batch_size": 100
    })
    
    print("  Step 3: Saving results...")
    # Create output artifact
    output_file = Path("ai_results.json")
    output_file.write_text(json.dumps({
        "processed": 100,
        "success_rate": 0.98,
        "timestamp": time.time()
    }, indent=2))
    
    # Log the artifact
    session.log_artifact(output_file)
    
    print("  Step 4: Finalizing...")
    session.log_step("pipeline.complete", {
        "status": "success",
        "duration_seconds": 0.5
    })

print("[OK] Pipeline completed with artifacts")
print()

# Test 3: Multi-step workflow showing all features
print("[TEST 3] Advanced Workflow - All Features")
print("-"*70)

@record(
    goal="Train and evaluate ML model",
    notes="Testing with hyperparameter optimization",
    metrics={
        "train_accuracy": 0.96,
        "val_accuracy": 0.94,
        "epochs": 10,
        "learning_rate": 0.001
    },
    approved_by="data_scientist@company.com",
    metadata_tags=["ml", "training", "experiment-42"]
)
def train_model_workflow():
    """Complete ML training workflow"""
    print("  Initializing model...")
    
    # Simulate training
    for epoch in range(3):
        print(f"  Epoch {epoch+1}/3...")
        time.sleep(0.1)
    
    print("  Evaluating model...")
    time.sleep(0.1)
    
    model_metrics = {
        "final_loss": 0.023,
        "accuracy": 0.96,
        "f1_score": 0.95
    }
    
    print(f"  Training complete: {model_metrics}")
    return model_metrics

result = train_model_workflow()
print(f"[OK] Model trained: accuracy = {result['accuracy']}")
print()

# Cleanup
if Path("ai_results.json").exists():
    Path("ai_results.json").unlink()

print("="*70)
print("PYTHON API TEST COMPLETE")
print("="*70)
print()
print("Check ./epi-recordings/ for generated .epi files")
print("Next: Test with CLI commands")


