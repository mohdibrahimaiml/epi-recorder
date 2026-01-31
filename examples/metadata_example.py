"""
Example showing EPI Recorder metadata features
"""

from epi_recorder import record


@record(
    goal="Demonstrate metadata features",
    notes="This example shows how to add metadata to EPI recordings",
    metrics={"demo_score": 0.95, "execution_time": 1.2},
    approved_by="example@company.com",
    metadata_tags=["example", "metadata", "demo"]
)
def main():
    """Main function demonstrating metadata usage."""
    print("🚀 EPI Recorder Metadata Example")
    print("=" * 40)
    
    # Simulate some AI work
    print("🤖 Simulating AI workflow...")
    
    # Task 1: Data processing
    print("📋 Task 1: Data Processing")
    data = list(range(100))
    processed = [x * 2 for x in data]
    print(f"   Processed {len(data)} items")
    
    # Task 2: Model inference
    print("📋 Task 2: Model Inference")
    predictions = [x > 50 for x in processed]
    accuracy = sum(predictions) / len(predictions)
    print(f"   Accuracy: {accuracy:.2%}")
    
    # Task 3: Result generation
    print("📋 Task 3: Result Generation")
    results = {
        "total_items": len(data),
        "processed_items": len(processed),
        "predictions_made": len(predictions),
        "accuracy": accuracy
    }
    
    print("✅ Workflow completed successfully!")
    print("=" * 40)
    print("✨ Metadata captured:")
    print("   • Goal: Demonstrate metadata features")
    print("   • Notes: This example shows how to add metadata to EPI recordings")
    print("   • Metrics: demo_score=0.95, execution_time=1.2")
    print("   • Approved by: example@company.com")
    print("   • Tags: example, metadata, demo")
    
    return results


def context_manager_example():
    """Example using context manager with metadata."""
    print("\n🔄 Context Manager Example")
    print("=" * 40)
    
    # Fix: Need to call record() properly as a context manager
    with record(
        "context_manager_test.epi",  # Need to provide a path
        goal="Context manager metadata test",
        notes="Testing the context manager approach",
        metrics={"context_score": 0.88},
        approved_by="context@example.com",
        metadata_tags=["context-manager", "test"]
    ):
        print("🔧 Running workflow with context manager...")
        result = sum(range(10))
        print(f"   Result: {result}")
        print("✅ Context manager workflow completed!")


if __name__ == "__main__":
    # Run decorator example
    main_result = main()
    
    # Run context manager example
    context_manager_example()
    
    print("\n🎉 Both examples completed!")
    print("📁 Check ./epi-recordings/ for the generated .epi files")
    print("👀 Use 'epi ls' to see the metadata in the listing")
    print("👁️  Use 'epi view <filename>' to see metadata in the viewer")


