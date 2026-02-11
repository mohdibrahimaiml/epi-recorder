"""
Agent Analytics Engine for EPI Recorder

Analyzes agent performance across multiple .epi runs.
Provides insights on success rates, costs, errors, and trends.

Usage:
    from epi_recorder.analytics import AgentAnalytics
    
    analytics = AgentAnalytics("./production_runs")
    print(analytics.success_rate_over_time())
    print(analytics.cost_trends())
    print(analytics.error_patterns())
"""

import json
import zipfile
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
import pandas as pd
from collections import defaultdict, Counter

try:
    import matplotlib.pyplot as plt
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False


class AgentAnalytics:
    """
    Analyze agent performance across multiple .epi artifacts.
    
    Metrics tracked:
    - Success rate over time
    - Average steps per run
    - Cost per run (if available)
    - Error patterns and frequencies
    - Tool usage distribution
    - LLM call counts
    """
    
    def __init__(self, artifact_dir: str):
        """
        Initialize analytics from directory of .epi files.
        
        Args:
            artifact_dir: Path to directory containing .epi files
        """
        self.artifact_dir = Path(artifact_dir)
        if not self.artifact_dir.exists():
            raise ValueError(f"Directory not found: {artifact_dir}")
        
        self.artifacts = self._load_all_artifacts()
        if not self.artifacts:
            raise ValueError(f"No .epi files found in {artifact_dir}")
        
        self.df = self._to_dataframe()
    
    def _load_all_artifacts(self) -> List[Dict[str, Any]]:
        """Load and parse all .epi files in directory"""
        artifacts = []
        
        for epi_file in self.artifact_dir.glob("*.epi"):
            try:
                artifact = self._parse_artifact(epi_file)
                if artifact:
                    artifacts.append(artifact)
            except Exception as e:
                print(f"Warning: Failed to parse {epi_file.name}: {e}")
                continue
        
        return artifacts
    
    def _parse_artifact(self, epi_path: Path) -> Optional[Dict[str, Any]]:
        """
        Parse a single .epi file and extract metrics.
        
        Returns:
            Dictionary with artifact metadata and metrics
        """
        try:
            with zipfile.ZipFile(epi_path, 'r') as zf:
                # Read manifest
                manifest_data = json.loads(zf.read('manifest.json').decode('utf-8'))
                
                # Read steps
                steps = []
                try:
                    steps_data = zf.read('steps.jsonl').decode('utf-8')
                    for line in steps_data.strip().split('\n'):
                        if line:
                            steps.append(json.loads(line))
                except KeyError:
                    pass  # No steps file
                
                # Extract metrics
                return self._extract_metrics(epi_path, manifest_data, steps)
                
        except Exception as e:
            print(f"Error parsing {epi_path.name}: {e}")
            return None
    
    def _extract_metrics(
        self, 
        epi_path: Path, 
        manifest: Dict, 
        steps: List[Dict]
    ) -> Dict[str, Any]:
        """Extract all metrics from artifact"""
        
        # Determine success (no errors in steps)
        errors = [s for s in steps if 'error' in s.get('kind', '').lower()]
        success = len(errors) == 0 and len(steps) > 0
        
        # Count LLM calls
        llm_calls = len([s for s in steps if 'llm' in s.get('kind', '')])
        
        # Count tool calls
        tool_calls = len([s for s in steps if 'tool' in s.get('kind', '')])
        
        # Calculate cost (if available in metadata)
        cost = 0.0
        if 'metrics' in manifest and isinstance(manifest['metrics'], dict):
            cost = float(manifest['metrics'].get('cost', 0.0))
        
        # Calculate duration
        duration = None
        if steps and len(steps) >= 2:
            try:
                start = datetime.fromisoformat(steps[0]['timestamp'].replace('Z', '+00:00'))
                end = datetime.fromisoformat(steps[-1]['timestamp'].replace('Z', '+00:00'))
                duration = (end - start).total_seconds()
            except (KeyError, ValueError):
                pass
        
        # Parse timestamp
        timestamp = datetime.fromisoformat(
            manifest['created_at'].replace('Z', '+00:00')
        )
        
        return {
            'filename': epi_path.name,
            'run_id': manifest.get('workflow_id', 'unknown'),
            'timestamp': timestamp,
            'success': success,
            'steps': len(steps),
            'duration': duration,
            'cost': cost,
            'errors': len(errors),
            'error_details': [
                {
                    'type': e.get('kind', 'unknown'),
                    'message': e.get('content', {}).get('error', 'No message')
                } 
                for e in errors
            ],
            'llm_calls': llm_calls,
            'tool_calls': tool_calls,
            'goal': manifest.get('goal', ''),
            'tags': manifest.get('tags', []),
            'cli_command': manifest.get('cli_command', ''),
        }
    
    def _to_dataframe(self) -> pd.DataFrame:
        """Convert artifacts to pandas DataFrame for analysis"""
        records = []
        
        for artifact in self.artifacts:
            records.append({
                'filename': artifact['filename'],
                'run_id': artifact['run_id'],
                'timestamp': artifact['timestamp'],
                'success': artifact['success'],
                'steps': artifact['steps'],
                'duration': artifact['duration'],
                'cost': artifact['cost'],
                'errors': artifact['errors'],
                'llm_calls': artifact['llm_calls'],
                'tool_calls': artifact['tool_calls'],
                'goal': artifact['goal'],
            })
        
        df = pd.DataFrame(records)
        df = df.sort_values('timestamp')
        return df
    
    # ==================== Analysis Methods ====================
    
    def success_rate_over_time(
        self, 
        window: str = '7D', 
        min_periods: int = 1
    ) -> pd.Series:
        """
        Calculate rolling success rate over time.
        
        Args:
            window: Rolling window size (e.g., '1D', '7D', '30D')
            min_periods: Minimum observations in window
            
        Returns:
            Pandas Series with rolling success rate (0.0 to 1.0)
        """
        df = self.df.set_index('timestamp')
        return df['success'].rolling(window, min_periods=min_periods).mean()
    
    def cost_trends(self, freq: str = 'D') -> pd.DataFrame:
        """
        Analyze cost trends over time.
        
        Args:
            freq: Aggregation frequency ('D'=daily, 'W'=weekly, 'M'=monthly)
            
        Returns:
            DataFrame with sum, mean, median, std of costs
        """
        df = self.df.copy()
        df['date'] = pd.to_datetime(df['timestamp']).dt.to_period(freq)
        
        grouped = df.groupby('date')['cost'].agg([
            ('total', 'sum'),
            ('average', 'mean'),
            ('median', 'median'),
            ('std', 'std'),
            ('count', 'count')
        ])
        
        return grouped
    
    def error_patterns(self, top_n: int = 10) -> Dict[str, int]:
        """
        Identify most common error types.
        
        Args:
            top_n: Return top N error types
            
        Returns:
            Dictionary of error_type -> count, sorted by frequency
        """
        error_counts = Counter()
        
        for artifact in self.artifacts:
            for error in artifact['error_details']:
                error_counts[error['type']] += 1
        
        return dict(error_counts.most_common(top_n))
    
    def tool_usage_distribution(self, top_n: int = 10) -> Dict[str, int]:
        """
        Analyze which tools are used most frequently.
        
        Args:
            top_n: Return top N tools
            
        Returns:
            Dictionary of tool_name -> count
        """
        tool_counts = Counter()
        
        for epi_file in self.artifact_dir.glob("*.epi"):
            try:
                with zipfile.ZipFile(epi_file, 'r') as zf:
                    steps_data = zf.read('steps.jsonl').decode('utf-8')
                    for line in steps_data.strip().split('\n'):
                        if not line:
                            continue
                        step = json.loads(line)
                        if step.get('kind', '').startswith('tool.'):
                            tool_name = step.get('content', {}).get('name', 'unknown')
                            tool_counts[tool_name] += 1
            except Exception:
                continue
        
        return dict(tool_counts.most_common(top_n))
    
    def performance_summary(self) -> Dict[str, Any]:
        """
        Generate overall performance summary.
        
        Returns:
            Dictionary with key performance metrics
        """
        return {
            'total_runs': len(self.df),
            'success_rate': self.df['success'].mean() * 100,
            'total_cost': self.df['cost'].sum(),
            'avg_cost_per_run': self.df['cost'].mean(),
            'avg_steps_per_run': self.df['steps'].mean(),
            'avg_duration': self.df['duration'].mean(),
            'total_llm_calls': self.df['llm_calls'].sum(),
            'total_tool_calls': self.df['tool_calls'].sum(),
            'error_rate': (self.df['errors'] > 0).mean() * 100,
            'date_range': {
                'first': self.df['timestamp'].min().isoformat(),
                'last': self.df['timestamp'].max().isoformat(),
            }
        }
    
    def compare_periods(
        self, 
        period1_start: datetime, 
        period1_end: datetime,
        period2_start: datetime,
        period2_end: datetime
    ) -> Dict[str, Dict[str, float]]:
        """
        Compare metrics between two time periods.
        
        Returns:
            Dictionary with metrics for each period and % change
        """
        df = self.df
        
        period1 = df[(df['timestamp'] >= period1_start) & (df['timestamp'] < period1_end)]
        period2 = df[(df['timestamp'] >= period2_start) & (df['timestamp'] < period2_end)]
        
        def calc_change(v1, v2):
            if v1 == 0:
                return 0.0
            return ((v2 - v1) / v1) * 100
        
        p1_success = period1['success'].mean()
        p2_success = period2['success'].mean()
        
        p1_cost = period1['cost'].mean()
        p2_cost = period2['cost'].mean()
        
        p1_duration = period1['duration'].mean()
        p2_duration = period2['duration'].mean()
        
        return {
            'success_rate': {
                'period1': p1_success * 100,
                'period2': p2_success * 100,
                'change_pct': calc_change(p1_success, p2_success)
            },
            'avg_cost': {
                'period1': p1_cost,
                'period2': p2_cost,
                'change_pct': calc_change(p1_cost, p2_cost)
            },
            'avg_duration': {
                'period1': p1_duration,
                'period2': p2_duration,
                'change_pct': calc_change(p1_duration, p2_duration)
            }
        }
    
    def generate_report(self, output_path: Optional[str] = None) -> str:
        """
        Generate comprehensive HTML report.
        
        Args:
            output_path: Where to save report (default: analytics_report.html)
            
        Returns:
            Path to generated report
        """
        if output_path is None:
            output_path = self.artifact_dir / "analytics_report.html"
        else:
            output_path = Path(output_path)
        
        summary = self.performance_summary()
        errors = self.error_patterns()
        tools = self.tool_usage_distribution()
        
        html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Agent Performance Report</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 40px; background: #f5f5f5; }}
        .container {{ max-width: 1200px; margin: 0 auto; background: white; padding: 30px; border-radius: 8px; }}
        h1 {{ color: #333; border-bottom: 3px solid #4CAF50; padding-bottom: 10px; }}
        h2 {{ color: #555; margin-top: 30px; }}
        .metric {{ display: inline-block; margin: 10px 20px; }}
        .metric-value {{ font-size: 32px; font-weight: bold; color: #4CAF50; }}
        .metric-label {{ font-size: 14px; color: #777; }}
        table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
        th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }}
        th {{ background: #4CAF50; color: white; }}
        tr:hover {{ background: #f5f5f5; }}
        .success {{ color: #4CAF50; }}
        .error {{ color: #f44336; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🤖 Agent Performance Report</h1>
        <p>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        
        <h2>📊 Overview</h2>
        <div class="metric">
            <div class="metric-value">{summary['total_runs']}</div>
            <div class="metric-label">Total Runs</div>
        </div>
        <div class="metric">
            <div class="metric-value success">{summary['success_rate']:.1f}%</div>
            <div class="metric-label">Success Rate</div>
        </div>
        <div class="metric">
            <div class="metric-value">${summary['avg_cost_per_run']:.3f}</div>
            <div class="metric-label">Avg Cost/Run</div>
        </div>
        <div class="metric">
            <div class="metric-value">{summary['avg_steps_per_run']:.1f}</div>
            <div class="metric-label">Avg Steps</div>
        </div>
        
        <h2>🔍 Error Patterns</h2>
        <table>
            <tr><th>Error Type</th><th>Count</th></tr>
"""
        
        for error_type, count in errors.items():
            html += f"            <tr><td>{error_type}</td><td class='error'>{count}</td></tr>\n"
        
        if not errors:
            html += "            <tr><td colspan='2'>No errors found ✅</td></tr>\n"
        
        html += """
        </table>
        
        <h2>🛠️ Tool Usage</h2>
        <table>
            <tr><th>Tool Name</th><th>Usage Count</th></tr>
"""
        
        for tool_name, count in tools.items():
            html += f"            <tr><td>{tool_name}</td><td>{count}</td></tr>\n"
        
        if not tools:
            html += "            <tr><td colspan='2'>No tool usage tracked</td></tr>\n"
        
        html += """
        </table>
        
        <h2>📈 Metrics</h2>
        <ul>
            <li><strong>Total Cost:</strong> ${:.2f}</li>
            <li><strong>Total LLM Calls:</strong> {:,}</li>
            <li><strong>Total Tool Calls:</strong> {:,}</li>
            <li><strong>Error Rate:</strong> {:.1f}%</li>
            <li><strong>Avg Duration:</strong> {:.1f}s</li>
        </ul>
    </div>
</body>
</html>
""".format(
            summary['total_cost'],
            summary['total_llm_calls'],
            summary['total_tool_calls'],
            summary['error_rate'],
            summary['avg_duration'] or 0.0
        )
        
        output_path.write_text(html, encoding='utf-8')
        return str(output_path)
    
    def __repr__(self) -> str:
        return f"<AgentAnalytics: {len(self.artifacts)} runs from {self.artifact_dir}>"
