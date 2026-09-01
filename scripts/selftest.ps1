# DocGraph 自动化自测（用户交互 + 关键流程）
# 用法: powershell -ExecutionPolicy Bypass -File scripts/selftest.ps1
# 覆盖: 后端 pytest / 前端 tsc+vite / 种子数据 / 后端 API / Playwright UI 交互
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root

$selftestData = Join-Path $root ".selftest-data"
if (Test-Path $selftestData) { Remove-Item -Recurse -Force $selftestData }
$env:DOCGRAPH_USER_DATA = $selftestData
$env:DOCGRAPH_SETTINGS_PATH = Join-Path $selftestData "settings.json"
$env:UV_CACHE_DIR = Join-Path $root ".uv-cache"

function Step($label) { Write-Host ""; Write-Host "== $label ==" -ForegroundColor Cyan }

# 预检：释放 8765 端口与残留进程，避免"新代码未生效"类问题（如 405）
Step "0/6 预检：释放端口/清理残留进程"
Get-Process -Name DocGraph -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
$conn = Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue
if ($conn) { $conn | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue } }
Start-Sleep -Seconds 2
$c = Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue
if ($c) { Write-Host "FAIL: 端口 8765 仍被占用" -ForegroundColor Red; exit 1 }
Write-Host "PASS: 端口 8765 空闲" -ForegroundColor Green

Step "1/6 后端测试 (pytest)"
& .\.venv\Scripts\python.exe -m pytest tests\ --no-header -q
if ($LASTEXITCODE -ne 0) { Write-Host "FAIL: pytest" -ForegroundColor Red; exit 1 }
Write-Host "PASS: pytest" -ForegroundColor Green

Step "2/6 前端类型检查 + 构建"
Push-Location web
& node node_modules\typescript\bin\tsc --noEmit
if ($LASTEXITCODE -ne 0) { Pop-Location; Write-Host "FAIL: tsc" -ForegroundColor Red; exit 1 }
& node node_modules\vite\bin\vite.js build
if ($LASTEXITCODE -ne 0) { Pop-Location; Write-Host "FAIL: vite build" -ForegroundColor Red; exit 1 }
Pop-Location
Write-Host "PASS: 前端构建" -ForegroundColor Green

Step "3/6 种子数据（文档+图谱+证据，隔离目录）"
& .\.venv\Scripts\python.exe scripts\seed_test_project.py
if ($LASTEXITCODE -ne 0) { Write-Host "FAIL: seed" -ForegroundColor Red; exit 1 }
Write-Host "PASS: seed" -ForegroundColor Green

Step "4/6 启动后端并做 API 冒烟"
$server = Start-Job -ScriptBlock {
    param($r, $data)
    Set-Location $r
    $env:DOCGRAPH_USER_DATA = $data
    $env:DOCGRAPH_SETTINGS_PATH = Join-Path $data "settings.json"
    $env:UV_CACHE_DIR = Join-Path $r ".uv-cache"
    & .\.venv\Scripts\python.exe -m uvicorn docgraph.server.app:app --host 127.0.0.1 --port 8765 --log-level warning
} -ArgumentList $root, $selftestData
Start-Sleep -Seconds 6
try {
    & .\.venv\Scripts\python.exe -c @"
import json, urllib.request
def get(u):
    with urllib.request.urlopen('http://127.0.0.1:8765'+u, timeout=10) as r: return json.load(r)
h = get('/api/health'); assert h['status']=='ok', h
active = get('/api/projects/active'); assert active['project'], active
assert active['documents'], '无文档'
graph = get('/api/projects/'+active['project']['id']+'/graph')
assert graph['nodes'], '图谱无节点'
eid = graph['nodes'][0]['data']['id']
detail = get('/api/projects/'+active['project']['id']+'/entities/'+eid)
assert detail.get('evidence'), '实体无证据'
print('API_SMOKE_OK: hubs=', len(graph['nodes']), 'edges=', len(graph['edges']), 'evidence=', len(detail['evidence']))
"@
    if ($LASTEXITCODE -ne 0) { Write-Host "FAIL: API 冒烟" -ForegroundColor Red; exit 1 }
    Write-Host "PASS: API 冒烟" -ForegroundColor Green
} finally {
    Stop-Job $server -ErrorAction SilentlyContinue
    Remove-Job $server -Force -ErrorAction SilentlyContinue
}

Step "5/6 重新启动后端 + Playwright UI 交互"
$server = Start-Job -ScriptBlock {
    param($r, $data)
    Set-Location $r
    $env:DOCGRAPH_USER_DATA = $data
    $env:DOCGRAPH_SETTINGS_PATH = Join-Path $data "settings.json"
    $env:UV_CACHE_DIR = Join-Path $r ".uv-cache"
    & .\.venv\Scripts\python.exe -m uvicorn docgraph.server.app:app --host 127.0.0.1 --port 8765 --log-level warning
} -ArgumentList $root, $selftestData
Start-Sleep -Seconds 6
try {
    Push-Location web
    & npx playwright test 2>&1 | Select-Object -Last 40
    $code = $LASTEXITCODE
    Pop-Location
} finally {
    Stop-Job $server -ErrorAction SilentlyContinue
    Remove-Job $server -Force -ErrorAction SilentlyContinue
}
if ($code -ne 0) { Write-Host "FAIL: Playwright UI" -ForegroundColor Red; exit 1 }
Write-Host "PASS: Playwright UI" -ForegroundColor Green

Step "6/6 安全检查（API Key 未打包进产物）"
& .\.venv\Scripts\python.exe scripts\verify_no_key.py
if ($LASTEXITCODE -ne 0) { Write-Host "FAIL: 密钥安全检查——请勿将真实/占位 Key 打包进 exe 或提交入库" -ForegroundColor Red; exit 1 }
Write-Host "PASS: 密钥安全检查" -ForegroundColor Green

Write-Host ""; Write-Host "========== SELFTEST ALL PASS ==========" -ForegroundColor Green
