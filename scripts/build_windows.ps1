# Build Anonymizer.exe + a Windows installer (via Inno Setup).
#
# Run from the repo root in PowerShell: .\scripts\build_windows.ps1
# Requires: the project venv set up per README.md, plus
#   uv pip install -r requirements-build.txt
# For the installer step: Inno Setup (https://jrsoftware.org/isinfo.php),
# with its compiler (ISCC.exe) on PATH — if it's missing, this script still
# produces the raw dist\Anonymizer\ folder, just skips the installer.
#
# NOTE: this script mirrors the macOS build (scripts/build_macos.sh) but has
# not been run on an actual Windows machine — there is no Windows environment
# available to verify it in. Please report back if a step doesn't match
# reality on your machine; see CLAUDE.md's packaging notes for the platform
# quirks this needed to account for.

$ErrorActionPreference = "Stop"

Set-Location (Join-Path $PSScriptRoot "..")

if (-not (Test-Path ".venv")) {
    Write-Error "No .venv found — run the Setup steps in README.md first."
    exit 1
}

& .\.venv\Scripts\Activate.ps1

Write-Host "==> Running PyInstaller..."
pyinstaller --clean --noconfirm anonymizer.spec

$distDir = "dist\Anonymizer"
if (-not (Test-Path $distDir)) {
    Write-Error "Expected PyInstaller output at $distDir but it's missing."
    exit 1
}

$iscc = Get-Command "ISCC.exe" -ErrorAction SilentlyContinue
if ($null -eq $iscc) {
    Write-Host ""
    Write-Host "Inno Setup (ISCC.exe) not found on PATH — skipping installer build."
    Write-Host "The unpacked app is ready at $distDir\Anonymizer.exe (run it directly,"
    Write-Host "or install Inno Setup and re-run this script for a proper installer)."
    exit 0
}

Write-Host "==> Building installer with Inno Setup..."
& $iscc.Source "scripts\anonymizer-installer.iss"

Write-Host ""
Write-Host "Done: $distDir\Anonymizer.exe and dist\Anonymizer-Setup.exe"
Write-Host "Note: the installer is unsigned — Windows SmartScreen will warn on"
Write-Host "first run ('Windows protected your PC') until it accumulates enough"
Write-Host "reputation, or until it's signed with a code-signing certificate."
