param(
    [string]$PythonVersion = "3.13"
)

$ErrorActionPreference = "Stop"

if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
    throw "Python launcher 'py' was not found in PATH."
}

Write-Host "Creating virtual environment with py -$PythonVersion ..."
py -$PythonVersion -m venv .venv

if ($LASTEXITCODE -ne 0) {
    Write-Warning "venv creation with bundled pip failed. Retrying without pip ..."
    if (Test-Path ".venv") {
        Remove-Item -Recurse -Force ".venv" -ErrorAction SilentlyContinue
    }
    py -$PythonVersion -m venv .venv --without-pip
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to create .venv with py -$PythonVersion."
    }
}

cmd /c ".\.venv\Scripts\python.exe -m pip --version >NUL 2>&1"
$pipAvailable = ($LASTEXITCODE -eq 0)

if ($pipAvailable) {
    Write-Host "Upgrading pip inside .venv ..."
    & ".\.venv\Scripts\python.exe" -m pip install --upgrade pip
}
else {
    Write-Warning "pip is not available in this virtual environment."
    Write-Warning "You can still use python from .venv; install pip separately if needed."
    Write-Host "Run: .\scripts\install-pip.ps1 -VenvPath .venv"
}

Write-Host "Done. Activate with: .\.venv\Scripts\Activate.ps1"
