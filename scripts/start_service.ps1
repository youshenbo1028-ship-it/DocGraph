# DocGraph 本地服务版启动器（v0.6）
# 用法: pwsh -ExecutionPolicy Bypass -File scripts/start_service.ps1
# 流程: 启动 Docker 服务(PG/Neo4j/Weaviate) -> 迁移 SQLite 数据(首次/幂等) -> 启动后端(PG) -> 打开浏览器
param(
    [switch]$NoMigrate,   # 跳过数据迁移
    [switch]$NoDocker     # 跳过 Docker 服务（自行启动 PG 时使用）
)
$ErrorActionPreference = "Continue"
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root
$env:DOCGRAPH_DATABASE_URL = "postgresql://docgraph:docgraph@127.0.0.1:5432/docgraph_meta"

Write-Host ""
Write-Host "========== DocGraph 本地服务版 ==========" -ForegroundColor Cyan

if (-not $NoDocker) {
    Write-Host "[1/3] 启动 Docker 服务（PostgreSQL / Neo4j / Weaviate）..." -ForegroundColor Cyan
    docker compose up -d
    $h = ""
    for ($i = 0; $i -lt 40; $i++) {
        $h = docker inspect --format "{{.State.Health.Status}}" docgraph-pg 2>$null
        if ($h -eq "healthy") { break }
        Start-Sleep -Seconds 3
    }
    if ($h -ne "healthy") { Write-Host "  PostgreSQL 未就绪，请检查 docker compose ps" -ForegroundColor Red; exit 1 }
    Write-Host "  PostgreSQL 就绪 (5432)" -ForegroundColor Green
}

if (-not $NoMigrate) {
    Write-Host "[2/3] 迁移 SQLite 数据 -> PostgreSQL（幂等，已有数据可跳过）..." -ForegroundColor Cyan
    & .\.venv\Scripts\python.exe scripts\migrate_sqlite_to_pg.py
}

Write-Host "[3/3] 启动 DocGraph 后端并打开浏览器..." -ForegroundColor Cyan
Start-Process "http://127.0.0.1:8765"
Write-Host ""
Write-Host "  访问: http://127.0.0.1:8765  （Ctrl+C 停止后端）" -ForegroundColor Green
Write-Host "  Neo4j 控制台: http://127.0.0.1:7474 (neo4j/docgraph123)" -ForegroundColor DarkGray
Write-Host "  Weaviate: http://127.0.0.1:8080" -ForegroundColor DarkGray
Write-Host "==========================================" -ForegroundColor Cyan
& .\.venv\Scripts\python.exe -m uvicorn docgraph.server.app:app --host 127.0.0.1 --port 8765
