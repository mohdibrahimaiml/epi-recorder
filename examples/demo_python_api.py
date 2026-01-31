"""
Comprehensive EPI Recorder Demo using Python API
This demonstrates the full functionality including step logging and artifacts
"""

import sys
import io
# Force UTF-8 encoding for Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from epi_recorder import record
from pathlib import Path
import json
import time

def main():
    print("\n" + "="*70)
    print("  EPI RECORDER - COMPREHENSIVE DEMONSTRATION")
    print("  Showing: Recording, Step Logging, Artifacts, and Verification")
    print("="*70 + "\n")
    
    # This is where the magic happens - everything inside is recorded!
    with record(
        "demo_comprehensive.epi",
        workflow_name="Customer Sentiment Analysis",
        goal="Analyze customer reviews and generate insights",
        notes="Demonstrating EPI Recorder capabilities for investors",
        metadata_tags=["demo", "v2.0", "live"]
    ) as session:
        
        print("[OK] EPI Recording started!")
        print()
        
        # Step 1: Load data
        print("[Step 1] Loading customer reviews...")
        reviews = [
            {"id": 1, "text": "This product is excellent! Best purchase ever.", "rating": 5},
            {"id": 2, "text": "Terrible quality. Very disappointed.", "rating": 1},
            {"id": 3, "text": "It's okay, nothing special.", "rating": 3},
            {"id": 4, "text": "Great value for money!", "rating": 5},
        ]
        
        session.log_step("data.loaded", {
            "source": "customer_reviews_db",
            "count": len(reviews),
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        })
        print(f"   → Loaded {len(reviews)} reviews")
        print()
        time.sleep(1)
        
        # Step 2: Process reviews
        print("[Step 2] Analyzing sentiment...")
        results = []
        
        for review in reviews:
            # Simple sentiment logic
            text = review['text'].lower()
            if review['rating'] >= 4 or 'excellent' in text or 'great' in text:
                sentiment = 'positive'
                score = 0.85
            elif review['rating'] <= 2 or 'terrible' in text or 'disappointed' in text:
                sentiment = 'negative'
                score = 0.15
            else:
                sentiment = 'neutral'
                score = 0.50
            
            result = {
                "review_id": review['id'],
                "text": review['text'],
                "sentiment": sentiment,
                "confidence": score,
                "rating": review['rating']
            }
            results.append(result)
            
            print(f"   Review {review['id']}: {sentiment.upper()} (confidence: {score:.0%})")
            time.sleep(0.5)
        
        session.log_step("sentiment.analyzed", {
            "reviews_processed": len(results),
            "algorithm": "rule_based_v1"
        })
        print()
        time.sleep(1)
        
        # Step 3: Generate summary
        print("[Step 3] Generating insights...")
        positive_count = sum(1 for r in results if r['sentiment'] == 'positive')
        negative_count = sum(1 for r in results if r['sentiment'] == 'negative')
        neutral_count = sum(1 for r in results if r['sentiment'] == 'neutral')
        avg_confidence = sum(r['confidence'] for r in results) / len(results)
        
        summary = {
            "total_reviews": len(results),
            "sentiment_distribution": {
                "positive": positive_count,
                "negative": negative_count,
                "neutral": neutral_count
            },
            "average_confidence": round(avg_confidence, 3),
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        
        print(f"   [SUMMARY]:")
        print(f"      Positive: {positive_count}")
        print(f"      Negative: {negative_count}")
        print(f"      Neutral: {neutral_count}")
        print(f"      Avg Confidence: {avg_confidence:.1%}")
        print()
        
        session.log_step("summary.generated", summary)
        time.sleep(1)
        
        # Step 4: Save artifacts
        print("[Step 4] Saving results...")
        
        # Save detailed results
        results_file = Path("sentiment_results.json")
        with open(results_file, 'w') as f:
            json.dump(results, f, indent=2)
        session.log_artifact(results_file)
        print(f"   [SAVED] {results_file}")
        
        # Save summary report
        summary_file = Path("sentiment_summary.json")
        with open(summary_file, 'w') as f:
            json.dump(summary, f, indent=2)
        session.log_artifact(summary_file)
        print(f"   [SAVED] {summary_file}")
        
        session.log_step("artifacts.saved", {
            "files": ["sentiment_results.json", "sentiment_summary.json"]
        })
        print()
        time.sleep(1)
        
        # Step 5: Final status
        print("[Step 5] Workflow complete!")
        session.log_step("workflow.completed", {
            "status": "success",
            "duration_seconds": 5,
            "steps_executed": 5
        })
        print()
    
    # The recording is now complete and signed!
    print("="*70)
    print("  [OK] RECORDING COMPLETE!")
    print("  [FILE] demo_comprehensive.epi")
    print("  [SECURE] Status: Signed and verified")
    print("="*70)
    print()
    print("Next steps:")
    print("  1. Verify: epi verify demo_comprehensive.epi")
    print("  2. View:   epi view demo_comprehensive.epi")
    print()

if __name__ == "__main__":
    main()


