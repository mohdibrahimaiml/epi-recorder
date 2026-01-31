"""
EPI CLI Chat - Interactive evidence querying with AI.

Allows users to ask natural language questions about their .epi evidence files.
"""

import json
import os
import warnings
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
import google.api_core.exceptions

from epi_core.container import EPIContainer


console = Console()


def load_steps_from_epi(epi_path: Path) -> list:
    """Load steps from an .epi file."""
    import tempfile
    
    temp_dir = Path(tempfile.mkdtemp())
    extracted = EPIContainer.unpack(epi_path, temp_dir)
    
    steps_file = extracted / "steps.jsonl"
    if not steps_file.exists():
        return []
    
    steps = []
    with open(steps_file, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                steps.append(json.loads(line))
    
    return steps


def chat(
    epi_file: Path = typer.Argument(..., help="Path to .epi file to chat with"),
    query: str = typer.Option(None, "--query", "-q", help="Single question (non-interactive mode)"),
    model: str = typer.Option("gemini-2.0-flash", "--model", "-m", help="Gemini model to use")
):
    """
    Chat with your evidence file using AI.
    
    Ask natural language questions about what happened in your recording.
    
    Examples:
        epi chat my_recording.epi                    # Interactive mode
        epi chat my_recording.epi -q "What happened?"  # Single question
    """
    # Resolve path
    if not epi_file.exists():
        # Try epi-recordings directory
        recordings_dir = Path("./epi-recordings")
        potential_path = recordings_dir / f"{epi_file.stem}.epi"
        if potential_path.exists():
            epi_file = potential_path
        else:
            console.print(f"[red]Error:[/red] File not found: {epi_file}")
            raise typer.Exit(1)
    
    # Check for API key
    api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if not api_key:
        console.print(Panel(
            "[yellow]No API key found![/yellow]\n\n"
            "Set your Google AI API key:\n"
            "  [cyan]set GOOGLE_API_KEY=your-key-here[/cyan]  (Windows)\n"
            "  [cyan]export GOOGLE_API_KEY=your-key-here[/cyan]  (Mac/Linux)\n\n"
            "Get a free key at: [link]https://makersuite.google.com/app/apikey[/link]",
            title="[!] API Key Required",
            border_style="yellow"
        ))
        raise typer.Exit(1)
    
    # Load the .epi file
    console.print(f"\n[dim]Loading evidence from:[/dim] {epi_file}")
    
    try:
        manifest = EPIContainer.read_manifest(epi_file)
        steps = load_steps_from_epi(epi_file)
    except Exception as e:
        console.print(f"[red]Error loading .epi file:[/red] {e}")
        raise typer.Exit(1)
    
    # Initialize Gemini
    try:
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            import google.generativeai as genai
            
        genai.configure(api_key=api_key)
        ai_model = genai.GenerativeModel(model)
    except ImportError:
        console.print(Panel(
            "[red]Google Generative AI package not installed![/red]\n\n"
            "Install it with:\n"
            "  [cyan]pip install google-generativeai[/cyan]",
            title="[X] Missing Dependency",
            border_style="red"
        ))
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error initializing Gemini:[/red] {e}")
        raise typer.Exit(1)
    
    # Build context
    context = f"""You are an expert assistant analyzing an EPI evidence recording file.
    
The recording contains cryptographically signed, tamper-proof evidence of an AI workflow execution.

Recording metadata:
- Created: {manifest.created_at}
- Goal: {manifest.goal or 'Not specified'}
- Command: {manifest.cli_command or 'Not specified'}
- Workflow ID: {manifest.workflow_id}
- Total steps: {len(steps)}

Here are the recorded steps (this is the timeline of events):
{json.dumps(steps[:50], indent=2, default=str)[:8000]}

When answering questions:
1. Be specific and cite step indices when relevant
2. Distinguish between LLM requests, responses, and other events
3. If asked about security, note that API keys are automatically redacted
4. Keep answers concise but informative
"""

    # Start chat session
    chat_session = ai_model.start_chat(history=[])
    
    # Display header
    console.print()
    console.print(Panel(
        f"[bold cyan]EPI Evidence Chat[/bold cyan]\n\n"
        f"[dim]File:[/dim] {epi_file.name}\n"
        f"[dim]Steps:[/dim] {len(steps)}\n"
        f"[dim]Model:[/dim] {model}\n\n"
        f"Ask questions about this evidence recording.\n"
        f"Type [yellow]exit[/yellow] or [yellow]quit[/yellow] to end the session.",
        border_style="cyan"
    ))
    console.print()
    
    # Non-interactive mode: answer single question and exit
    if query:
        try:
            full_prompt = f"{context}\n\nUser question: {query}"
            response = chat_session.send_message(full_prompt)
            console.print("[bold green]AI:[/bold green]")
            console.print(Markdown(response.text))
            return
        except Exception as e:
            console.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(1)
    
    # Interactive chat loop
    while True:
        try:
            question = Prompt.ask("[bold cyan]You[/bold cyan]")
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Goodbye![/dim]")
            break
        
        if question.lower() in ('exit', 'quit', 'q'):
            console.print("[dim]Goodbye![/dim]")
            break
        
        if not question.strip():
            continue
        
        # Send to Gemini with context
        try:
            full_prompt = f"{context}\n\nUser question: {question}"
            response = chat_session.send_message(full_prompt)
            
            console.print()
            console.print("[bold green]AI:[/bold green]")
            console.print(Markdown(response.text))
            console.print()
            
        except google.api_core.exceptions.ResourceExhausted:
            console.print(Panel(
                "[yellow]API Quota Exceeded[/yellow]\n\n"
                "You have hit the rate limit for the Gemini API (free tier).\n"
                "Please wait a minute before trying again.",
                title="[!] Rate Limit",
                border_style="yellow"
            ))
        except google.api_core.exceptions.NotFound:
            console.print(f"[red]Error:[/red] The model '{model}' was not found. Try using a different model with --model.")
        except google.api_core.exceptions.InvalidArgument as e:
            console.print(f"[red]Error:[/red] Invalid argument: {e}")
        except Exception as e:
            console.print(f"[red]Error:[/red] {e}")
            console.print("[dim]Try asking a different question.[/dim]")
            console.print()


