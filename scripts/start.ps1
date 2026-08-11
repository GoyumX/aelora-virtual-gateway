$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath ".\.venv\Scripts\aelora-virtual-gateway.exe")) {
    throw "The virtual environment is not ready. Run .\scripts\setup.ps1 first."
}

& .\.venv\Scripts\aelora-virtual-gateway.exe
