$ErrorActionPreference = "Continue"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
Write-Host "=== Python environment ==="
if (Test-Path $ProjectPython) {
    & $ProjectPython --version
    & $ProjectPython -c "import manim, rdkit, pydantic; print('Manim', manim.__version__); print('RDKit', rdkit.__version__); print('Pydantic', pydantic.__version__)"
} else {
    Write-Host "MISSING: $ProjectPython"
}

Write-Host "`n=== DeepSeek ==="
if ($env:DEEPSEEK_API_KEY) {
    Write-Host "DEEPSEEK_API_KEY = SET (value hidden)"
} else {
    Write-Host "DEEPSEEK_API_KEY = MISSING"
}
Write-Host "model = $(if ($env:DEEPSEEK_MODEL) { $env:DEEPSEEK_MODEL } else { 'deepseek-v4-flash' })"
