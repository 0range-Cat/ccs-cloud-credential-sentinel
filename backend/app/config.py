"""应用配置：环境变量前缀 CCS_，支持 backend/.env。"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    app_name: str = "云上凭据泄露自动化检测与响应系统"
    app_version: str = "0.1.0"

    data_dir: Path = REPO_ROOT / "data"
    db_url: str = ""  # 空则默认 sqlite:///data/app.db

    master_key: str = ""     # CCS_MASTER_KEY：优先于 data/master.key 密钥文件
    access_token: str = ""   # CCS_ACCESS_TOKEN：可选单用户访问保护
    static_dir: str = ""     # CCS_STATIC_DIR：容器内前端产物目录（默认 frontend/dist）

    workers: int = 2
    scheduler_tick_seconds: int = 20
    background: bool = True   # CCS_BACKGROUND=false 时禁用调度器与验证线程（测试用）
    display_timezone: str = "Asia/Shanghai"

    # 默认预算（可在来源配置中覆盖）
    max_items_per_run: int = 2000
    max_bytes_per_run: int = 512 * 1024 * 1024
    max_seconds_per_run: int = 1800
    max_file_bytes: int = 1024 * 1024
    max_context_chars: int = 4096

    model_config = SettingsConfigDict(env_prefix="CCS_", env_file=".env", extra="ignore")

    def resolved_db_url(self) -> str:
        if self.db_url:
            return self.db_url
        self.data_dir.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{(self.data_dir / 'app.db').as_posix()}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
