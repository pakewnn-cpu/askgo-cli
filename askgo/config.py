"""Configuration: load .env, apply CLI overrides. Nothing is hardcoded.

Environment variables (see .env.example):
    ASKGO_BASE_URL      site base URL           (default https://askgo.co)
    ASKGO_DEFAULT_MODEL default model name       (default "")
    ASKGO_HEADLESS      "1"/"0" headless mode    (default 1)
    ASKGO_TIMEOUT_MS    per-step timeout in ms   (default 60000)
    ASKGO_STATE_FILE    saved login state path   (default ./.askgo/storage_state.json)
    ASKGO_MEDIA_DIR     where media is saved     (default ./media)
    ASKGO_DEBUG_DIR     where debug screenshots  (default ./debug)
    ASKGO_SERVE_URL     CDP endpoint for serve   (default http://127.0.0.1:9222)
    ASKGO_USER_AGENT    optional user agent override
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv(path: str | Path) -> None:
    """Minimal .env loader (no external dependency). Does not override real env."""
    p = Path(path)
    if not p.exists():
        return
    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        line = line.removeprefix("export ")
        if "=" not in line:
            continue
        key, val = line.split("=", 1)
        key = key.strip()
        val = val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
            val = val[1:-1]
        os.environ.setdefault(key, val)


@dataclass
class Config:
    base_url: str = "https://askgo.co"
    default_model: str = ""
    headless: bool = True
    timeout_ms: int = 60000
    state_file: Path = Path(".askgo/storage_state.json")
    auth_state_file: Path = Path(".askgo/auth_state.json")
    media_dir: Path = Path("media")
    debug_dir: Path = Path("debug")
    serve_url: str = "http://127.0.0.1:9222"
    user_agent: str = ""
    login_timeout_s: int = 600
    new_session: bool = False
    save_media: bool = True
    use_serve: bool = False

    @classmethod
    def from_env(cls, env_file: str | Path = ".env") -> Config:
        _load_dotenv(env_file)
        g = os.environ.get
        cfg = cls(
            base_url=g("ASKGO_BASE_URL", "https://askgo.co").rstrip("/"),
            default_model=g("ASKGO_DEFAULT_MODEL", ""),
            headless=str(g("ASKGO_HEADLESS", "1")).lower() in ("1", "true", "yes"),
            timeout_ms=int(g("ASKGO_TIMEOUT_MS", "60000")),
            state_file=Path(g("ASKGO_STATE_FILE", ".askgo/storage_state.json")),
            auth_state_file=Path(g("ASKGO_AUTH_STATE_FILE", ".askgo/auth_state.json")),
            media_dir=Path(g("ASKGO_MEDIA_DIR", "media")),
            debug_dir=Path(g("ASKGO_DEBUG_DIR", "debug")),
            serve_url=g("ASKGO_SERVE_URL", "http://127.0.0.1:9222"),
            user_agent=g("ASKGO_USER_AGENT", ""),
            login_timeout_s=int(g("ASKGO_LOGIN_TIMEOUT_S", "600")),
        )
        cfg.ensure_dirs()
        return cfg

    def ensure_dirs(self) -> None:
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.media_dir.mkdir(parents=True, exist_ok=True)
        self.debug_dir.mkdir(parents=True, exist_ok=True)
