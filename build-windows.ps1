$ErrorActionPreference = "Stop"

if (-not (Test-Path ".venv-build")) {
    py -m venv .venv-build
}

& .\.venv-build\Scripts\python.exe -m pip install --upgrade pip
& .\.venv-build\Scripts\python.exe -m pip install -r requirements.txt -r requirements-build.txt

if (Test-Path "build") { Remove-Item -Recurse -Force "build" }
if (Test-Path "dist") { Remove-Item -Recurse -Force "dist" }

& .\.venv-build\Scripts\python.exe -m PyInstaller --clean --noconfirm RemotePlayEnabler.spec

Write-Host ""
Write-Host "Build complete:"
Write-Host "  dist\RemotePlayEnabler.exe"
