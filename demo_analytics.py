"""
Demo script for Agent Analytics Engine

Shows how to use analytics to track agent performance over time.
"""

from epi_recorder.analytics import AgentAnalytics
from pathlib import Path

def demo_analytics():
    """Demonstrate analytics on existing .epi files"""
    
    print("🔍 EPI Agent Analytics Demo\n")
    print("=" * 60)
    
    # Find directory with .epi files
    current_dir = Path(".")
    epi_files = list(current_dir.glob("*.epi"))
    
    if not epi_files:
        print("❌ No .epi files found in current directory")
        print("\nTo generate test data, run:")
        print("  python test_ollama_integration.py --generate-data")
        return
    
    print(f"📂 Found {len(epi_files)} .epi files\n")
    
    # Initialize analytics
    try:
        analytics = AgentAnalytics(".")
        print(f"✅ Loaded {len(analytics.artifacts)} artifacts\n")
    except Exception as e:
        print(f"❌ Error loading analytics: {e}")
        return
    
    # Performance summary
    print("📊 PERFORMANCE SUMMARY")
    print("-" * 60)
    summary = analytics.performance_summary()
    
    print(f"Total Runs:        {summary['total_runs']}")
    print(f"Success Rate:      {summary['success_rate']:.1f}%")
    print(f"Avg Cost/Run:      ${summary['avg_cost_per_run']:.3f}")
    print(f"Avg Steps:         {summary['avg_steps_per_run']:.1f}")
    print(f"Total LLM Calls:   {summary['total_llm_calls']:,}")
    print(f"Total Tool Calls:  {summary['total_tool_calls']:,}")
    print(f"Error Rate:        {summary['error_rate']:.1f}%")
    print()
    
    # Error patterns
    print("🔴 ERROR PATTERNS")
    print("-" * 60)
    errors = analytics.error_patterns(top_n=5)
    if errors:
        for error_type, count in errors.items():
            print(f"  {error_type}: {count} occurrences")
    else:
        print("  ✅ No errors found!")
    print()
    
    # Tool usage
    print("🛠️  TOOL USAGE")
    print("-" * 60)
    tools = analytics.tool_usage_distribution(top_n=5)
    if tools:
        for tool_name, count in tools.items():
            print(f"  {tool_name}: {count} calls")
    else:
        print("  No tool usage tracked")
    print()
    
    # Cost trends
    print("💰 COST TRENDS (Daily)")
    print("-" * 60)
    try:
        cost_trends = analytics.cost_trends(freq='D')
        if not cost_trends.empty:
            print(cost_trends.to_string())
        else:
            print("  No cost data available")
    except Exception as e:
        print(f"  Could not calculate trends: {e}")
    print()
    
    # Generate HTML report
    print("📄 GENERATING HTML REPORT")
    print("-" * 60)
    try:
        report_path = analytics.generate_report()
        print(f"✅ Report saved to: {report_path}")
        print(f"\nOpen in browser:")
        print(f"  start {report_path}")
    except Exception as e:
        print(f"❌ Error generating report: {e}")
    
    print("\n" + "=" * 60)
    print("✅ Analytics demo complete!")

if __name__ == "__main__":
    demo_analytics()
