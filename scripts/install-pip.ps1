param(
    [string]$VenvPath = ".venv",
    [switch]$UseGetPip
)

$ErrorActionPreference = "Stop"

$pythonExe = Join-Path $VenvPath "Scripts\python.exe"
if (-not (Test-Path $pythonExe)) {
    throw "Python executable not found: $pythonExe"
}

cmd /c "`"$pythonExe`" -m pip --version >NUL 2>&1"
if ($LASTEXITCODE -eq 0) {
    Write-Host "pip is already available in $VenvPath"
    exit 0
}

$root = (Resolve-Path ".").Path
$tmpRoot = Join-Path $root ".tmp"
$sessionTmp = Join-Path $tmpRoot ("pip-bootstrap-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force -Path $sessionTmp | Out-Null

$oldTemp = $env:TEMP
$oldTmp = $env:TMP
$env:TEMP = $sessionTmp
$env:TMP = $sessionTmp

$ensureLog = Join-Path $sessionTmp "ensurepip.log"
$ensured = $false

try {
    Write-Host "Trying ensurepip with isolated temp dir..."
    cmd /c "`"$pythonExe`" -m ensurepip --upgrade > `"$ensureLog`" 2>&1"
    $ensured = ($LASTEXITCODE -eq 0)
}
finally {
    $env:TEMP = $oldTemp
    $env:TMP = $oldTmp
}

if ($ensured) {
    Write-Host "ensurepip succeeded. Upgrading pip..."
    & $pythonExe -m pip install --upgrade pip
    Write-Host "pip installed successfully."
    exit 0
}

Write-Warning "ensurepip failed. Log: $ensureLog"

if ($UseGetPip) {
    $getPipPath = Join-Path $sessionTmp "get-pip.py"
    Write-Host "Downloading get-pip.py..."
    Invoke-WebRequest -UseBasicParsing -Uri "https://bootstrap.pypa.io/get-pip.py" -OutFile $getPipPath
    Write-Host "Running get-pip.py..."
    & $pythonExe $getPipPath
    cmd /c "`"$pythonExe`" -m pip --version >NUL 2>&1"
    if ($LASTEXITCODE -eq 0) {
        Write-Host "pip installed successfully via get-pip.py."
        exit 0
    }
}

Write-Error @"
pip is still unavailable.
Try one of:
1) Run terminal as Administrator and execute:
   .\scripts\install-pip.ps1 -VenvPath $VenvPath
2) Use online bootstrap:
   .\scripts\install-pip.ps1 -VenvPath $VenvPath -UseGetPip
"@
