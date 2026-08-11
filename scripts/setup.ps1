$ErrorActionPreference = "Stop"

$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    $python = Get-Command py -ErrorAction SilentlyContinue
}
if (-not $python) {
    throw "Python 3.11 or newer is required. Install Python, then run this script again."
}

& $python.Source -m venv .venv
& .\.venv\Scripts\python.exe -m pip install --upgrade "pip>=26.1.2"
& .\.venv\Scripts\python.exe -m pip install -e ".[dev]"

Write-Output "Gateway environment is ready. Run .\scripts\start.ps1"
