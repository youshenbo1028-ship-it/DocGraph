# 开发与打包脚本

## 开发模式

```bash
# 1) 后端依赖
pip install -e ".[dev]"

# 2) 前端
cd web && npm install && npm run dev

# 3) 桌面壳（另一终端，指向 http://127.0.0.1:5173）
python -m app.main
```

## 打包单文件 exe（FR-901）

```powershell
powershell -ExecutionPolicy Bypass -File scripts/build_exe.ps1
# 产物: dist/DocGraph.exe
```

> TODO(M1): 构建脚本就绪后补齐 WebView2 运行时检测与体积优化（PRD 7.5）。
