# Agent Analytics Engine

The Agent Analytics Engine provides powerful insights into agent performance across multiple runs.

## Installation

Analytics is included with EPI Recorder v2.4.0+:

```bash
pip install epi-recorder
```

## Quick Start

```python
from epi_recorder import AgentAnalytics

# Analyze all .epi files in a directory
analytics = AgentAnalytics("./production_runs")

# Get performance summary
summary = analytics.performance_summary()
print(f"Success Rate: {summary['success_rate']:.1f}%")
print(f"Avg Cost: ${summary['avg_cost_per_run']:.3f}")

# Generate HTML report
analytics.generate_report("report.html")
```

## Features

### 📊 Performance Metrics

Track key performance indicators:
- Success rate over time
- Average cost per run
- Steps per execution
- LLM/tool call counts
- Error rates

```python
summary = analytics.performance_summary()
# Returns:
# {
#     'total_runs': 100,
#     'success_rate': 95.5,
#     'avg_cost_per_run': 0.023,
#     'avg_steps_per_run': 12.3,
#     'total_llm_calls': 450,
#     'error_rate': 4.5
# }
```

### 📈 Trend Analysis

Analyze performance over time:

```python
# Rolling success rate (7-day window)
success_rate = analytics.success_rate_over_time(window='7D')

# Daily cost trends
cost_trends = analytics.cost_trends(freq='D')
print(cost_trends)
# Shows: total, average, median, std per day
```

### 🔍 Error Analysis

Identify most common failure modes:

```python
errors = analytics.error_patterns(top_n=10)
# Returns: {'llm.error': 23, 'tool.timeout': 12, ...}
```

### 🛠️ Tool Usage

See which tools are used most:

```python
tools = analytics.tool_usage_distribution(top_n=10)
# Returns: {'search': 145, 'calculator': 89, ...}
```

### ⚖️ Period Comparison

Compare two time periods:

```python
from datetime import datetime, timedelta

now = datetime.now()
week_ago = now - timedelta(days=7)
two_weeks_ago = now - timedelta(days=14)

comparison = analytics.compare_periods(
    period1_start=two_weeks_ago,
    period1_end=week_ago,
    period2_start=week_ago,
    period2_end=now
)

print(f"Success rate change: {comparison['success_rate']['change_pct']:.1f}%")
print(f"Cost change: {comparison['avg_cost']['change_pct']:.1f}%")
```

### 📄 HTML Reports

Generate comprehensive reports:

```python
report_path = analytics.generate_report("weekly_report.html")
# Opens in browser: detailed metrics, charts, error tables
```

## Use Cases

### 1. A/B Testing Prompts

```python
# Tag runs with version
with record("test.epi", tags=["prompt_v1"]):
    # Run agent with version 1

with record("test.epi", tags=["prompt_v2"]):
    # Run agent with version 2

# Compare
analytics = AgentAnalytics(".")
# Filter by tags and compare metrics
```

### 2. Cost Monitoring

```python
# Alert on cost spikes
cost_trends = analytics.cost_trends(freq='D')
if cost_trends['total'].iloc[-1] > cost_trends['total'].iloc[-7] * 2:
    send_alert("Cost doubled in last week!")
```

### 3. Regression Detection

```python
# Track success rate
success_rate = analytics.success_rate_over_time(window='7D')
if success_rate.iloc[-1] < 0.8:
    send_alert("Success rate dropped below 80%!")
```

### 4. Performance Dashboards

```python
# Generate weekly reports
import schedule

def generate_weekly_report():
    analytics = AgentAnalytics("./production_runs")
    analytics.generate_report(f"reports/week_{datetime.now().strftime('%Y%m%d')}.html")

schedule.every().monday.at("09:00").do(generate_weekly_report)
```

## API Reference

### `AgentAnalytics(artifact_dir: str)`

Initialize analytics from directory of .epi files.

**Methods:**

- `performance_summary() -> Dict` - Overall performance metrics
- `success_rate_over_time(window='7D') -> pd.Series` - Rolling success rate
- `cost_trends(freq='D') -> pd.DataFrame` - Cost aggregation over time
- `error_patterns(top_n=10) -> Dict` - Most common error types
- `tool_usage_distribution(top_n=10) -> Dict` - Tool call frequencies
- `compare_periods(...) -> Dict` - Compare two time ranges
- `generate_report(output_path='report.html') -> str` - Create HTML report

## Example Workflow

```python
from epi_recorder import record, AgentAnalytics, wrap_openai
from openai import OpenAI

# 1. Record agent runs
client = wrap_openai(OpenAI())

for i in range(10):
    with record(f"run_{i}.epi", goal=f"Test {i}"):
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "user", "content": f"Task {i}"}]
        )

# 2. Analyze performance
analytics = AgentAnalytics(".")

# 3. View metrics
summary = analytics.performance_summary()
print(f"Completed {summary['total_runs']} runs")
print(f"Success rate: {summary['success_rate']:.1f}%")
print(f"Total cost: ${summary['total_cost']:.2f}")

# 4. Identify issues
errors = analytics.error_patterns()
if errors:
    print("Top errors:", errors)

# 5. Generate report
analytics.generate_report("performance_report.html")
```

## Requirements

- Python 3.11+
- pandas
- epi-recorder

## License

MIT
