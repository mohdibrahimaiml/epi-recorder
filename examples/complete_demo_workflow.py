"""
Complete EPI Recorder Demonstration
From Installation to Viewing

This script demonstrates the entire user journey.
"""

import sys
import io
# Force UTF-8 encoding for Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import json
import time
from datetime import datetime

print("=" * 80)
print("  COMPLETE EPI RECORDER DEMONSTRATION")
print("  From Installation to Viewing")
print("=" * 80)
print()

# Simulate a real AI workflow: Text Summarization
print("[WORKFLOW] AI Text Summarization Tool")
print()

# Sample data
documents = [
    {
        "id": 1,
        "title": "Climate Change Report",
        "text": "Global temperatures have risen by 1.1 degrees Celsius since pre-industrial times. Scientists warn that immediate action is needed to prevent catastrophic consequences."
    },
    {
        "id": 2,
        "title": "AI in Healthcare",
        "text": "Artificial intelligence is revolutionizing medical diagnosis. Machine learning models can now detect diseases from medical images with 95% accuracy."
    },
    {
        "id": 3,
        "title": "Quantum Computing Breakthrough",
        "text": "Researchers have achieved quantum supremacy with a 127-qubit processor. This marks a significant milestone in the race to practical quantum computing."
    }
]

print(f"[STEP 1/5] Loading {len(documents)} documents...")
time.sleep(0.5)
print(f"            Loaded successfully!")
print()

print("[STEP 2/5] Analyzing text content...")
time.sleep(0.5)

summaries = []
for doc in documents:
    # Simple extractive summary (first sentence)
    sentences = doc['text'].split('. ')
    summary = sentences[0] + '.'
    
    word_count = len(doc['text'].split())
    summary_length = len(summary.split())
    compression_ratio = (1 - summary_length / word_count) * 100
    
    result = {
        "document_id": doc['id'],
        "title": doc['title'],
        "original_length": word_count,
        "summary": summary,
        "summary_length": summary_length,
        "compression": f"{compression_ratio:.1f}%"
    }
    summaries.append(result)
    
    print(f"            Document {doc['id']}: {doc['title']}")
    print(f"            -> {word_count} words compressed to {summary_length} words ({compression_ratio:.1f}% reduction)")
    time.sleep(0.3)

print()
print("[STEP 3/5] Generating insights...")
time.sleep(0.5)

total_original = sum(s['original_length'] for s in summaries)
total_summary = sum(s['summary_length'] for s in summaries)
avg_compression = (1 - total_summary / total_original) * 100

insights = {
    "total_documents": len(summaries),
    "total_original_words": total_original,
    "total_summary_words": total_summary,
    "average_compression": f"{avg_compression:.1f}%",
    "processing_date": datetime.now().isoformat()
}

print(f"            Total documents processed: {insights['total_documents']}")
print(f"            Original: {total_original} words -> Summary: {total_summary} words")
print(f"            Average compression: {avg_compression:.1f}%")
print()

print("[STEP 4/5] Saving results...")
time.sleep(0.5)

# Save summaries
summaries_file = "text_summaries.json"
with open(summaries_file, 'w') as f:
    json.dump(summaries, f, indent=2)
print(f"            Saved: {summaries_file}")

# Save insights
insights_file = "summary_insights.json"
with open(insights_file, 'w') as f:
    json.dump(insights, f, indent=2)
print(f"            Saved: {insights_file}")
print()

print("[STEP 5/5] Workflow complete!")
print()
print("=" * 80)
print("  SUMMARY")
print("=" * 80)
print(f"  Documents Processed:  {len(summaries)}")
print(f"  Words Reduced:        {total_original - total_summary}")
print(f"  Compression Rate:     {avg_compression:.1f}%")
print(f"  Files Generated:      2")
print("=" * 80)
print()
print("[SUCCESS] Text summarization workflow completed successfully!")
print()
