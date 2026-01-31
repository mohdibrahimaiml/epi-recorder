"""
EPI CLI - Main entry point for python -m epi_cli

This allows users to run the CLI even if 'epi' is not in PATH:
    python -m epi_cli run script.py
    python -m epi_cli view recording.epi
    etc.
"""
from epi_cli.main import cli_main

if __name__ == "__main__":
    cli_main()


