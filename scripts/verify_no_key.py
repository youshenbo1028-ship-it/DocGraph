"""安全检查：确认本地的 API Key 未被误打包进 exe / 前端资源 / 仓库。

- exe / web/dist：严格门槛，命中即 FAIL（这是最需要防的泄漏点）
- 仓库已跟踪文件：仅在密钥长度 >= 16（真实密钥长度）时检查，
  避免把测试夹具里的短假 key（如 sk-test）误判为泄漏

退出码：0 = 通过；1 = 检出密钥泄漏。
用作发布前检查：scripts\selftest.ps1 会调用本脚本，配合 release 产物使用。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from docgraph.core.settings import get_api_key

ROOT = Path(__file__).resolve().parent.parent
EXE = ROOT / "release" / "DocGraph.exe"
DIST = ROOT / "web" / "dist"
MIN_REAL_KEY_LEN = 16  # 低于该长度视为测试/占位，不做仓库泄漏判定

key = get_api_key()
key_checks: list[tuple[str, bool]] = []  # (label, passed)
failures: list[str] = []

if not key:
    print("[check] 未配置 API Key，跳过泄漏检查")
    print("RESULT: PASS（无密钥）")
    sys.exit(0)

kb = key.encode("utf-8")
variants = {kb, key.lower().encode("utf-8"), key.upper().encode("utf-8")}
print(f"[info] 当前 Key 长度={len(key)}（前4后3：{key[:4]}...{key[-3:]}）")


def scan_file(path: Path, label: str, strict: bool) -> None:
    if not path.exists():
        print(f"[{label}] 不存在，跳过")
        return
    try:
        data = path.read_bytes()
        found = any(v in data for v in variants)
    except OSError as e:
        print(f"[{label}] 读取失败: {e}")
        found = False
    if found:
        failures.append(f"{label} 检测到 Key")
        print(f"[{label}] 含 Key: YES  -> FAIL")
    else:
        print(f"[{label}] 含 Key: NO")


# 1) exe
scan_file(EXE, "exe", strict=True)
# 2) web/dist
dist_hits = []
for f in DIST.rglob("*"):
    if f.is_file():
        try:
            d = f.read_bytes()
            if any(v in d for v in variants):
                dist_hits.append(str(f.name))
        except OSError:
            pass
if dist_hits:
    failures.append(f"web/dist 检出 Key: {dist_hits[:5]}")
    print(f"[web/dist] 含 Key 文件数: {len(dist_hits)} -> FAIL {dist_hits[:5]}")
else:
    print("[web/dist] 含 Key 文件数: 0")

# 3) 仓库已跟踪文件（真实密钥长度才判定；测试夹具的短假 key 不计）
if len(key) >= MIN_REAL_KEY_LEN:
    r = subprocess.run(
        ["git", "grep", "-l", "-i", "-F", "--", key],
        capture_output=True, text=True, cwd=str(ROOT), timeout=90,
    )
    files = [l for l in r.stdout.splitlines() if l.strip()]
    if files:
        failures.append(f"仓库检出 Key: {files[:5]}")
        print(f"[repo] 含 Key 文件数: {len(files)} -> FAIL {files[:5]}")
    else:
        print("[repo] 含 Key 文件数: 0")
else:
    print(f"[repo] 跳过（Key 长度 {len(key)} < {MIN_REAL_KEY_LEN}，视为测试/占位）")

# 4) 设置文件明文
from docgraph.core import settings

for p in (settings.settings_path(), ROOT / "settings.json"):
    if p.exists() and kb in p.read_bytes():
        failures.append(f"设置文件含 Key 明文: {p.name}")
        print(f"[settings:{p.name}] 含 Key 明文 -> FAIL")
    elif p.exists():
        print(f"[settings:{p.name}] 含 Key 明文: NO")

print()
if failures:
    print("RESULT: FAIL")
    for f in failures:
        print("  -", f)
    sys.exit(1)
print("RESULT: PASS")
sys.exit(0)
