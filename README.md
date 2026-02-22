# ProveNuance2

Minimal project scaffold configured for:
- `py` (Windows Python launcher)
- `git` workflow

## Requirements
- Git installed
- Python launcher available as `py`

## Quick start
```powershell
.\scripts\bootstrap.ps1
.\.venv\Scripts\Activate.ps1
```

## Manual setup (optional)
```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
```

If pip bootstrap fails on your machine, use:
```powershell
py -3.13 -m venv .venv --without-pip
```

## pip recovery
When `.venv` exists but has no `pip`:
```powershell
.\scripts\install-pip.ps1 -VenvPath .venv
```

Optional fallback with online bootstrap:
```powershell
.\scripts\install-pip.ps1 -VenvPath .venv -UseGetPip
```

## Git
Repository is initialized with:
- `.gitignore` for Python, venv, IDE and OS artifacts
- `main` default branch
