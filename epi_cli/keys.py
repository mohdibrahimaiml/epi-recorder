"""
EPI CLI keys compatibility layer and presentation helpers.
"""

from rich.console import Console
from rich.table import Table

from epi_core.keys import KeyManager

console = Console()


def generate_default_keypair_if_missing(console_output: bool = True) -> bool:
    """
    Generate default key pair if it doesn't exist (frictionless first run).

    Args:
        console_output: Whether to print console messages

    Returns:
        bool: True if key was generated, False if already exists
    """
    key_manager = KeyManager()

    if key_manager.has_default_key():
        return False

    private_path, public_path = key_manager.generate_keypair("default")

    if console_output:
        console.print("\n[bold green]Welcome to EPI![/bold green]")
        console.print("\n[dim]Generated default Ed25519 key pair for signing:[/dim]")
        console.print(f"  [cyan]Private:[/cyan] {private_path}")
        console.print(f"  [cyan]Public:[/cyan]  {public_path}")
        console.print("\n[dim]Your .epi files will be automatically signed for authenticity.[/dim]\n")

    return True


def print_keys_table(keys: list[dict[str, str]]) -> None:
    """
    Print a formatted table of keys using Rich.

    Args:
        keys: List of key information dicts
    """
    if not keys:
        console.print("[yellow]No keys found. Generate with: epi keys generate[/yellow]")
        return

    table = Table(title="EPI Key Pairs", show_header=True, header_style="bold magenta")
    table.add_column("Name", style="cyan")
    table.add_column("Private Key", style="green")
    table.add_column("Public Key", style="blue")

    for key in keys:
        private_status = "[Y]" if key["has_private"] else "[N]"
        public_status = "[Y]" if key["has_public"] else "[N]"

        table.add_row(
            key["name"],
            f"{private_status} {key['private_path']}",
            f"{public_status} {key['public_path']}",
        )

    console.print(table)
