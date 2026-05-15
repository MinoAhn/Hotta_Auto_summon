$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $Root ".venv\Scripts\python.exe"

if (!(Test-Path $Python)) {
    python -m venv (Join-Path $Root ".venv")
}

& $Python -m pip install -r (Join-Path $Root "requirements.txt")
$env:PYTHONPATH = Join-Path $Root "src"
& $Python -m auto_summon
