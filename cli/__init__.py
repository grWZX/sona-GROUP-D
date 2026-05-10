"""CLI 模块：提供命令行交互界面。"""

from __future__ import annotations

from pathlib import Path


def _preload_project_dotenv() -> None:
    """在任何子模块（含 agent / model）导入前注入项目根 .env，避免 Key 未进 os.environ。"""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    root = Path(__file__).resolve().parent.parent
    env_path = root / ".env"
    if env_path.is_file():
        load_dotenv(env_path, override=True)


_preload_project_dotenv()

from cli.main import main

__all__ = ["main"]
