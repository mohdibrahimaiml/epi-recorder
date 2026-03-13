"""
Minimal setup.py for backwards compatibility.
All project configuration is in pyproject.toml.

Note: pip install uses pyproject.toml + wheel builds — setup.py install
is not called by modern pip and PostInstallCommand hooks do not run.
File association registration is handled by epi_recorder/__init__.py
(on first import) and epi_cli/main.py (on first CLI use).
"""
from setuptools import setup

if __name__ == "__main__":
    setup()
