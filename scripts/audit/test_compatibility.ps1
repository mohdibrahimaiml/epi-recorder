$ErrorActionPreference = "Stop"

Write-Host "--- Testing Python 3.11 ---"
py -3.11 -m venv venv-3.11
.\venv-3.11\Scripts\python.exe -m pip install --upgrade pip
.\venv-3.11\Scripts\pip.exe install -e ".[dev,test]"
.\venv-3.11\Scripts\epi.exe --version
# Run a targeted suite to ensure it works
.\venv-3.11\Scripts\pytest.exe tests/unit -q

Write-Host "--- Testing Typer/Click Min Versions (Python 3.12) ---"
.\venv-editable\Scripts\pip.exe install "typer==0.16.0" "click==8.1.0"
.\venv-editable\Scripts\epi.exe --version
.\venv-editable\Scripts\pytest.exe tests/test_all_cli_commands.py -q

Write-Host "--- Testing Typer/Click Max Versions (Python 3.12) ---"
.\venv-editable\Scripts\pip.exe install "typer==0.25.1" "click==8.1.8"
.\venv-editable\Scripts\epi.exe --version
.\venv-editable\Scripts\pytest.exe tests/test_all_cli_commands.py -q

Write-Host "Compatibility testing complete."
