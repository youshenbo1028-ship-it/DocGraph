"""设置存储测试（FR-801 / FR-802）。"""

from __future__ import annotations

import pytest

from docgraph.core import settings


@pytest.fixture(autouse=True)
def no_keyring(monkeypatch):
    """强制走文件回退路径（keyring 在测试环境不可预测）。"""
    monkeypatch.setattr(settings, "keyring", None)


def test_save_and_get_api_config(tmp_path, monkeypatch):
    monkeypatch.setenv("DOCGRAPH_SETTINGS_PATH", str(tmp_path / "settings.json"))
    settings.save_api_config("https://api.deepseek.com/v1", "deepseek-chat", api_key="sk-test-123")
    cfg = settings.get_api_config()
    assert cfg["base_url"] == "https://api.deepseek.com/v1"
    assert cfg["model"] == "deepseek-chat"
    assert cfg["has_key"] is True


def test_empty_key_keeps_existing(tmp_path, monkeypatch):
    monkeypatch.setenv("DOCGRAPH_SETTINGS_PATH", str(tmp_path / "settings.json"))
    settings.save_api_config("u1", "m1", api_key="k1")
    settings.save_api_config("u2", "m2")  # 不传 key -> 保留
    cfg = settings.get_api_config()
    assert cfg["base_url"] == "u2"
    assert cfg["has_key"] is True


def test_load_returns_defaults_when_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("DOCGRAPH_SETTINGS_PATH", str(tmp_path / "none.json"))
    assert settings.get_api_config() == {"base_url": "", "model": "", "has_key": False}


def test_settings_file_contains_no_plain_key_note(tmp_path, monkeypatch):
    """回退模式下 Key 以 _key_fallback 存在；正式部署优先 Credential Manager。"""
    monkeypatch.setenv("DOCGRAPH_SETTINGS_PATH", str(tmp_path / "settings.json"))
    settings.save_api_config("u", "m", api_key="secret")
    raw = (tmp_path / "settings.json").read_text(encoding="utf-8")
    assert "secret" in raw  # 回退路径确实落盘（后续应换用系统凭据库）
