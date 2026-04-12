@echo off
setlocal
set "SCRIPT_DIR=%~dp0"
set "VENV_PYTHON=%SCRIPT_DIR%.venv\Scripts\python.exe"

if exist "%VENV_PYTHON%" (
  "%VENV_PYTHON%" -m epi_cli.main %*
  exit /b %ERRORLEVEL%
)

python -m epi_cli.main %*
exit /b %ERRORLEVEL%
