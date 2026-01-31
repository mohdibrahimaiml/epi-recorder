#!/usr/bin/env python3
"""
Complete example of using EPI Recorder from installation to viewing
"""

import openai
import tempfile
from pathlib import Path
import time

# Import EPI Recorder
from epi_recorder import record

def simulate_ai_workflow():
    """Simulate a complete AI workflow with EPI recording"""
    
    print("🤖 Starting AI Workflow with EPI Recording")
    print("=" * 50)
    
    # Create a temporary directory for our example
    with tempfile.TemporaryDirectory() as temp_dir:
        epi_file = Path(temp_dir) / "complete_example.epi"
        
        # Use EPI Recorder to capture the entire workflow
        with record(epi_file, workflow_name="Complete AI Example") as epi:
            print("📝 Recording started...")
            
            # Step 1: Data loading (custom step)
            epi.log_step("data.loading", {
                "dataset": "customer_reviews.csv",
                "rows": 10000,
                "columns": ["review_id", "product_id", "review_text", "rating", "timestamp"]
            })
            print("📊 Loaded dataset with 10,000 customer reviews")
            
            # Step 2: Data preprocessing (custom step)
            epi.log_step("data.preprocessing", {
                "steps": ["text cleaning", "tokenization", "sentiment labeling"],
                "cleaned_rows": 9850,  # Some rows removed due to quality issues
                "processing_time_seconds": 15.3
            })
            print("⚙️  Preprocessed text data")
            
            # Step 3: Model training simulation (custom step)
            epi.log_step("model.training", {
                "model_type": "sentiment_analysis_lstm",
                "epochs": 20,
                "batch_size": 64,
                "learning_rate": 0.001,
                "validation_accuracy": 0.92
            })
            print("🧠 Trained sentiment analysis model (92% validation accuracy)")
            time.sleep(1)  # Simulate processing time
            
            # Step 4: Simulate OpenAI API call (this would be automatically recorded)
            print("💬 Calling OpenAI API for review summarization...")
            
            # In a real scenario, you would make an actual API call:
            # response = openai.chat.completions.create(
            #     model="gpt-3.5-turbo",
            #     messages=[{"role": "user", "content": "Summarize: Great product, works perfectly"}]
            # )
            
            # For this example, we'll simulate the API call logging
            epi.log_llm_request("gpt-3.5-turbo", {
                "messages": [
                    {"role": "system", "content": "You are a helpful assistant that summarizes product reviews."},
                    {"role": "user", "content": "Please summarize this product review: 'This product exceeded my expectations. The quality is outstanding and it arrived earlier than expected. I would definitely recommend it to others.'"}
                ],
                "temperature": 0.7
            })
            
            # Simulate API response
            epi.log_llm_response({
                "model": "gpt-3.5-turbo",
                "choices": [{
                    "message": {
                        "role": "assistant",
                        "content": "Positive review highlighting excellent product quality and fast delivery, with a strong recommendation to others."
                    },
                    "finish_reason": "stop"
                }],
                "usage": {
                    "prompt_tokens": 85,
                    "completion_tokens": 32,
                    "total_tokens": 117
                },
                "latency_seconds": 1.42
            })
            
            # Step 5: Create an output artifact
            results_file = Path(temp_dir) / "sentiment_analysis_results.txt"
            with open(results_file, "w") as f:
                f.write("Sentiment Analysis Results\n")
                f.write("========================\n")
                f.write("Total Reviews Processed: 10,000\n")
                f.write("Positive: 6,500 (65%)\n")
                f.write("Neutral: 2,000 (20%)\n")
                f.write("Negative: 1,500 (15%)\n")
                f.write("\nTop Positive Keywords: quality, excellent, recommend, perfect\n")
                f.write("Top Negative Keywords: poor, broken, disappointed, waste\n")
            
            # Log the artifact
            epi.log_artifact(results_file)
            print("📄 Generated sentiment analysis report")
            
            # Step 6: Evaluation results (custom step)
            epi.log_step("evaluation.results", {
                "accuracy": 0.91,
                "precision": 0.89,
                "recall": 0.93,
                "f1_score": 0.91,
                "confusion_matrix": [[850, 50, 100], [30, 900, 70], [80, 120, 800]]
            })
            print("📈 Model evaluation completed")
        
        # Copy the EPI file to a permanent location
        import shutil
        final_epi_file = Path("my_complete_example.epi")
        shutil.copy2(epi_file, final_epi_file)
        print(f"\n✅ EPI recording completed: {final_epi_file.absolute()}")
        
        return final_epi_file

def verify_and_view(epi_file_path):
    """Verify the EPI file and view it in browser"""
    print("\n🔍 Verifying EPI file...")
    print("=" * 30)
    
    # In practice, you would run these commands in terminal:
    print(f"To verify the file, run:")
    print(f"  epi verify {epi_file_path}")
    
    print(f"\n🌐 To view in browser, run:")
    print(f"  epi view {epi_file_path}")
    
    print("\n📋 Verification output would look like:")
    print("""
  =========================================================
  ✅ EPI Verification Report
  =========================================================
    File: my_complete_example.epi
    Trust Level: HIGH
    Message: Cryptographically verified and integrity intact
    
    ✅ Integrity: Verified (8 files)
    ✅ Signature: Valid (key: default)
    
    Workflow ID: 550e8400-e29b-41d4-a716-446655440000
    Created: 2025-01-15T10:30:00Z
    Spec Version: 1.0-keystone
  =========================================================
    """)
    
    print("\n👀 Viewer would show:")
    print("  - Interactive timeline of all steps")
    print("  - LLM chat bubbles for API calls")
    print("  - Environment information")
    print("  - Generated artifacts")
    print("  - Trust badge indicating signed status")

def main():
    """Main function demonstrating complete EPI workflow"""
    print("EPI Recorder Complete Workflow Example")
    print("=====================================")
    
    print("\n[ ] STEP 1: INSTALLATION")
    print("-" * 25)
    print("Install EPI Recorder:")
    print("  pip install epi-recorder")
    
    print("\n[ ] STEP 2: RECORDING")
    print("-" * 20)
    epi_file = simulate_ai_workflow()
    
    print("\n[ ] STEP 3: VERIFICATION & VIEWING")
    print("-" * 32)
    verify_and_view(epi_file)
    
    print("\n[ ] COMPLETE WORKFLOW DEMONSTRATED!")
    print("-" * 35)
    print("1. Installed EPI Recorder")
    print("2. Recorded complete AI workflow")
    print("3. Verified integrity and authenticity")
    print("4. Viewed results in browser")
    
    print(f"\n📁 Your EPI file is ready: {epi_file}")
    print("   Run these commands in your terminal:")
    print(f"     epi verify {epi_file}")
    print(f"     epi view {epi_file}")

if __name__ == "__main__":
    main()


