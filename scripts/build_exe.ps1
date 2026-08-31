# 打包单文件 exe（PyInstaller onefile，FR-901）
# 用法: powershell -ExecutionPolicy Bypass -File scripts/build_exe.ps1
# 前置: .venv 已激活（uv venv --python 3.10 && uv pip install -e ".[dev]"）
$ErrorActionPreference = "Stop"

Set-Location (Split-Path $PSScriptRoot -Parent)

# 1. 构建前端静态资源
Push-Location web
npm install --no-audit --no-fund
npm run build
Pop-Location

# 2. 打包单文件 exe
python -m PyInstaller `
  --name DocGraph `
  --onefile `
  --windowed `
  --noconfirm `
  --paths src `
  --add-data "web/dist;web/dist" `
  --collect-all webview `
  --collect-all keyring `
  --hidden-import "webview.platforms.edgechromium" `
  --hidden-import "keyring.backends.Windows" `
  app/main.py

Write-Host "构建完成: dist/DocGraph.exe"
