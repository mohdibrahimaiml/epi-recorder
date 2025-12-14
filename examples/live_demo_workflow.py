"""
Live Demo Workflow for EPI Recorder
This script demonstrates a realistic AI workflow that will be recorded.
"""

import json
import time
from datetime import datetime

def analyze_sentiment(text):
    """Simulate sentiment analysis"""
    # In a real scenario, this would call an AI API
    print(f"Analyzing sentiment for: '{text}'")
    time.sleep(0.5)
    
    # Simulate analysis
    if "great" in text.lower() or "excellent" in text.lower():
        sentiment = "positive"
        score = 0.92
    elif "bad" in text.lower() or "terrible" in text.lower():
        sentiment = "negative"
        score = 0.15
    else:
        sentiment = "neutral"
        score = 0.50
    
    return {
        "text": text,
        "sentiment": sentiment,
        "confidence": score,
        "timestamp": datetime.now().isoformat()
    }

def main():
    print("=" * 60)
    print("EPI RECORDER - LIVE DEMO WORKFLOW")
    print("=" * 60)
    print()
    
    # Sample customer reviews
    reviews = [
        "This product is great! Excellent quality.",
        "Terrible experience, would not recommend.",
        "It's okay, nothing special."
    ]
    
    results = []
    
    print("Analyzing customer reviews...")
    print()
    
    for i, review in enumerate(reviews, 1):
        print(f"Review {i}:")
        result = analyze_sentiment(review)
        results.append(result)
        print(f"  → Sentiment: {result['sentiment'].upper()}")
        print(f"  → Confidence: {result['confidence']:.2%}")
        print()
    
    # Save results
    output_file = "demo_analysis_results.json"
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"✅ Analysis complete! Results saved to {output_file}")
    print()
    
    # Summary
    positive_count = sum(1 for r in results if r['sentiment'] == 'positive')
    negative_count = sum(1 for r in results if r['sentiment'] == 'negative')
    neutral_count = sum(1 for r in results if r['sentiment'] == 'neutral')
    
    print("SUMMARY:")
    print(f"  Positive: {positive_count}")
    print(f"  Negative: {negative_count}")
    print(f"  Neutral: {neutral_count}")
    print()
    print("=" * 60)

if __name__ == "__main__":
    main()
