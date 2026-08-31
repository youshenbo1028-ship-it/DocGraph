"""设置持久化：API 配置 + API Key 安全存储（FR-801 / FR-802）。

- 所有用户数据存到稳定目录（默认 %LOCALAPPDATA%/DocGraph），不依赖程序启动目录；
- API Key 优先存 Windows Credential Manager（keyring），不可用回退配置文件；
- last_project_id 持久化，重启后恢复上一次项目。
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

try:
    import keyring
except Exception:  # keyring 依赖缺失或不可用
    keyring = None

_SERVICE = "docgraph"


def user_data_dir() -> Path:
    """稳定用户数据目录（环境变量 DOCGRAPH_USER_DATA 可覆盖，测试用）。"""
    env = os.environ.get("DOCGRAPH_USER_DATA")
    if env:
        return Path(env)
    local = os.environ.get("LOCALAPPDATA")
    if local:
        return Path(local) / "DocGraph"
    return Path(tempfile.gettempdir()) / "DocGraph"


def settings_path() -> Path:
    """设置文件路径：环境变量 DOCGRAPH_SETTINGS_PATH 可覆盖（测试用）。"""
    env = os.environ.get("DOCGRAPH_SETTINGS_PATH")
    if env:
        return Path(env)
    return user_data_dir() / "settings.json"


def load_settings() -> dict[str, Any]:
    p = settings_path()
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
    return {}


def _save_settings(cfg: dict[str, Any]) -> None:
    p = settings_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def save_api_config(base_url: str, model: str, api_key: str | None = None) -> None:
    """保存 API 配置；api_key 为空表示保留既有 Key。"""
    cfg = load_settings()
    api = cfg.setdefault("api", {})
    api["base_url"] = base_url
    api["model"] = model
    if api_key:
        if _store_key(api_key):
            api.pop("_key_fallback", None)  # 升级为安全存储后清理回退
        else:
            api["_key_fallback"] = api_key  # 非安全回退
    _save_settings(cfg)


def get_api_config() -> dict:
    """返回非敏感配置 + 是否已配置 Key（不返回 Key 本身）。"""
    cfg = load_settings().get("api", {})
    return {
        "base_url": cfg.get("base_url", ""),
        "model": cfg.get("model", ""),
        "has_key": bool(_read_key()),
    }


def get_api_key() -> str:
    """返回已存的 API Key（优先 keyring）。"""
    return _read_key()


def set_last_project_id(project_id: str) -> None:
    cfg = load_settings()
    cfg["last_project_id"] = project_id
    _save_settings(cfg)


def get_last_project_id() -> str:
    return load_settings().get("last_project_id", "")


def _store_key(key: str) -> bool:
    """尝试存入系统凭据库（keyring）；成功返回 True。"""
    if keyring is not None:
        try:
            keyring.set_password(_SERVICE, "api_key", key)
            return True
        except Exception:
            pass
    return False


def _read_key() -> str:
    if keyring is not None:
        try:
            key = keyring.get_password(_SERVICE, "api_key")
            if key:
                return key
        except Exception:
            pass
    return load_settings().get("api", {}).get("_key_fallback", "")
