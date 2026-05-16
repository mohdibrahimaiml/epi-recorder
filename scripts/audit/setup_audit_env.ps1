$ErrorActionPreference = "Stop"

Write-Host "Creating venv-editable..."
python -m venv venv-editable
.\venv-editable\Scripts\python.exe -m pip install --upgrade pip build
.\venv-editable\Scripts\pip.exe install -e .
Write-Host "Testing venv-editable CLI..."
.\venv-editable\Scripts\epi.exe --version
.\venv-editable\Scripts\epi.exe --help
.\venv-editable\Scripts\epi.exe verify --help

Write-Host "Building distributions..."
.\venv-editable\Scripts\python.exe -m build

Write-Host "Creating venv-wheel..."
python -m venv venv-wheel
.\venv-wheel\Scripts\python.exe -m pip install --upgrade pip
$wheel = Get-ChildItem -Path dist\*.whl | Select-Object -First 1
.\venv-wheel\Scripts\pip.exe install $wheel.FullName
Write-Host "Testing venv-wheel CLI..."
.\venv-wheel\Scripts\epi.exe --version
.\venv-wheel\Scripts\epi.exe --help

Write-Host "Creating venv-sdist..."
python -m venv venv-sdist
.\venv-sdist\Scripts\python.exe -m pip install --upgrade pip
$sdist = Get-ChildItem -Path dist\*.tar.gz | Select-Object -First 1
.\venv-sdist\Scripts\pip.exe install $sdist.FullName
Write-Host "Testing venv-sdist CLI..."
.\venv-sdist\Scripts\epi.exe --version
.\venv-sdist\Scripts\epi.exe --help

Write-Host "Phase 1 installation testing complete."
