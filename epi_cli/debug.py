"""
EPI Debug Command - AI-powered agent mistake detection.

Analyzes .epi recordings to find:
- Infinite loops
- Hallucinations
- Inefficiencies
- Repetitive patterns
"""

import json
from pathlib import Path
import typer
from rich.console import Console
from rich.panel import Panel

from epi_analyzer.detector import MistakeDetector

console = Console()
app = typer.Typer(name="debug", help="Debug AI agent recordings for mistakes")


@app.callback(invoke_without_command=True)
def debug(
    ctx: typer.Context,
    epi_file: Path = typer.Argument(..., help="Path to .epi recording file or directory"),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
    export: Path = typer.Option(None, "--export", help="Export report to file"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed analysis"),
):
    """
    Analyze agent execution for mistakes and inefficiencies.
    
    This command uses AI-powered analysis to detect:
    - Infinite loops (same tool called repeatedly)
    - Hallucinations (LLM confident but wrong)
    - Inefficiencies (excessive token usage)
    - Repetitive patterns (redundant work)
    
    Examples:
        epi debug agent_session.epi
        epi debug recording_dir/ --json
        epi debug agent.epi --export report.txt
    """
    console.print(f"🔍 Analyzing [cyan]{epi_file}[/cyan]...")
    
    try:
        # Run analysis
        detector = MistakeDetector(str(epi_file))
        mistakes = detector.analyze()
        
        # Prepare output
        if output_json:
            output = json.dumps(mistakes, indent=2)
        else:
            output = detector.get_summary()
            
            if verbose and mistakes:
                # Add detailed metrics for each mistake
                details = ["\n📊 Detailed Analysis:"]
                for i, m in enumerate(mistakes, 1):
                    details.append(f"\n{i}. {m.get('type')} (Step {m.get('step')})")
                    for key, value in m.items():
                        if key not in ['type', 'step']:
                            details.append(f"   {key}: {value}")
                output += "\n".join(details)
        
        # Display or export
        if export:
            export.write_text(output, encoding='utf-8')
            console.print(f"\n💾 Report saved to [green]{export}[/green]")
        else:
            console.print(f"\n{output}")
        
        # Show actionable summary if mistakes found
        if mistakes and not output_json:
            critical_count = sum(1 for m in mistakes if m.get('severity') == 'CRITICAL')
            if critical_count > 0:
                console.print(
                    Panel(
                        f"[bold red]⚠️  {critical_count} CRITICAL issue(s) detected![/bold red]\n\n"
                        "These issues can cause your agent to fail or waste resources.\n"
                        "Review the suggestions above to fix them.",
                        title="Action Required",
                        border_style="red"
                    )
                )
        
        # Exit code: 1 if critical mistakes found
        if any(m.get('severity') == 'CRITICAL' for m in mistakes):
            raise typer.Exit(code=1)
        
        console.print("\n✅ Analysis complete")
        
    except FileNotFoundError as e:
        console.print(f"[red]❌ File not found:[/red] {e}", err=True)
        raise typer.Exit(code=2)
    except Exception as e:
        console.print(f"[red]❌ Error analyzing file:[/red] {e}", err=True)
        if verbose:
            import traceback
            console.print(traceback.format_exc())
        raise typer.Exit(code=3)
