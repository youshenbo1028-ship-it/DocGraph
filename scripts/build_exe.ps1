# 打包单文件 exe（PyInstaller onefile，FR-901）
# 用法: powershell -ExecutionPolicy Bypass -File scripts/build_exe.ps1
$ErrorActionPreference = "Stop"

Set-Location (Split-Path $PSScriptRoot -Parent)

# 1. 构建前端静态资源
Push-Location web
npm install
npm run build
Pop-Location

# 2. 打包（TODO(M1): 补齐 hidden imports / datas / WebView2 运行时策略）
python -m PyInstaller `
  --name DocGraph `
  --onefile `
  --windowed `
  --add-data "web/dist;web/dist" `
  app/main.py

Write-Host "构建完成: dist/DocGraph.exe"
