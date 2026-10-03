# Build a windowed ScreenQuery.exe. Run this on Windows.
# On a Mac, use scripts/build-dmg.sh instead.
$ErrorActionPreference = "Stop"

if ($env:OS -ne "Windows_NT") {
    Write-Error "scripts/build-windows.ps1 builds ScreenQuery.exe. Run it on Windows. On a Mac, use scripts/build-dmg.sh."
    exit 1
}

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

python -m pip install -r requirements-build.txt

if (-not (Test-Path "frontend/dist/index.html")) {
    if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
        Write-Error "frontend/dist is missing. In frontend/, run: npm ci; npm run build"
        exit 1
    }
    Push-Location frontend
    npm ci
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    npm run build
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    Pop-Location
}

New-Item -ItemType Directory -Force -Path build | Out-Null
python -c "from screenquery.icon_art import draw_icon; draw_icon(256).save('build/icon.ico', format='ICO', sizes=[(16, 16), (32, 32), (48, 48), (256, 256)])"

python -m PyInstaller `
    --noconfirm `
    --clean `
    --windowed `
    --onefile `
    --name ScreenQuery `
    --icon build/icon.ico `
    --collect-submodules screenquery `
    --collect-submodules keyring `
    --collect-submodules pynput `
    --collect-submodules pystray `
    --hidden-import mss `
    --hidden-import PIL `
    --hidden-import webview `
    --hidden-import webview.platforms.winforms `
    --hidden-import webview.platforms.edgechromium `
    --hidden-import clr `
    --add-data "frontend/dist;frontend/dist" `
    screenquery/__main__.py

Write-Host "Built dist/ScreenQuery.exe"
