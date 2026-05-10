"""从 .env 加载环境变量（原 config/settings 逻辑），供 model/factory 等使用。"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

from utils.path import get_project_root


def _load_dotenv() -> None:
    """
    加载项目根与当前工作目录下的 ``.env``（若存在）。

    - 项目根 ``.env`` 使用 ``override=True``，覆盖系统里可能存在的空同名变量。
    - 当前目录 ``.env`` 使用 ``override=False``，仅在变量仍缺失时补全（便于从子目录启动时兜底）。
    """
    try:
        paths: list[Path] = []
        try:
            root = get_project_root()
            p0 = root / ".env"
            if p0.is_file():
                paths.append(p0)
        except Exception:
            pass
        p1 = Path.cwd() / ".env"
        if p1.is_file():
            try:
                if not paths or p1.resolve() != paths[0].resolve():
                    paths.append(p1)
            except Exception:
                paths.append(p1)
        if paths:
            load_dotenv(paths[0], override=True)
            for extra in paths[1:]:
                load_dotenv(extra, override=False)
        else:
            load_dotenv()
    except ImportError:
        pass


_env_config: Optional["EnvConfig"] = None


def _sanitize_api_key_value(val: Optional[str]) -> Optional[str]:
    """去掉 BOM、首尾空白、成对引号（.env 手误常见导致 401）。"""
    if val is None:
        return None
    s = str(val).strip()
    if s.startswith("\ufeff"):
        s = s.lstrip("\ufeff").strip()
    if len(s) >= 2:
        if (s[0] == s[-1] == '"') or (s[0] == s[-1] == "'"):
            s = s[1:-1].strip()
    return s or None


class EnvConfig:
    """从 .env 读取的环境配置"""

    def __init__(self) -> None:
        _load_dotenv()
        # 统一使用 APIKEY（按 openai / gemini / qwen / deepseek 顺序）
        self.OPENAI_APIKEY: Optional[str] = os.environ.get("OPENAI_APIKEY") or None
        self.GEMINI_APIKEY: Optional[str] = os.environ.get("GEMINI_APIKEY") or None
        qwen = _sanitize_api_key_value(os.environ.get("QWEN_APIKEY"))
        dash = _sanitize_api_key_value(os.environ.get("DASHSCOPE_APIKEY"))
        # 通义与 DashScope 常用同一密钥，任填其一即可
        if not qwen:
            qwen = dash
        if not dash:
            dash = qwen
        self.QWEN_APIKEY: Optional[str] = qwen
        self.DASHSCOPE_APIKEY: Optional[str] = dash
        self.DEEPSEEK_APIKEY: Optional[str] = os.environ.get("DEEPSEEK_APIKEY") or None
        self.KIMI_APIKEY: Optional[str] = os.environ.get("KIMI_APIKEY") or None
        self.BOCHA_API_KEY: Optional[str] = os.environ.get("BOCHA_API_KEY") or None
        self.NETINSIGHT_USER: Optional[str] = os.environ.get("NETINSIGHT_USER") or None
        self.NETINSIGHT_PASS: Optional[str] = os.environ.get("NETINSIGHT_PASS") or None

    def get_api_key(self, env_var_name: str) -> Optional[str]:
        """根据配置中的 api_key_env 取对应 API Key。"""
        raw = os.environ.get(env_var_name) or getattr(self, env_var_name, None)
        if (raw or "").strip():
            return _sanitize_api_key_value(str(raw))
        if env_var_name == "QWEN_APIKEY":
            alt = os.environ.get("DASHSCOPE_APIKEY") or getattr(self, "DASHSCOPE_APIKEY", None)
            return _sanitize_api_key_value(str(alt) if alt is not None else None)
        if env_var_name == "DASHSCOPE_APIKEY":
            alt = os.environ.get("QWEN_APIKEY") or getattr(self, "QWEN_APIKEY", None)
            return _sanitize_api_key_value(str(alt) if alt is not None else None)
        return None


def get_env_config() -> EnvConfig:
    """获取单例 EnvConfig，首次调用时加载 .env。"""
    global _env_config
    if _env_config is None:
        _env_config = EnvConfig()
    return _env_config


def reload_env_config() -> EnvConfig:
    """丢弃缓存并重新从当前 ``os.environ`` 构建配置（供在 ``load_dotenv(override=True)`` 之后使用）。"""
    global _env_config
    _env_config = None
    return get_env_config()
