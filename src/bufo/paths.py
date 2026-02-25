"""XDG path helpers and project-scoped storage roots."""

from __future__ import annotations

from hashlib import sha1
from pathlib import Path

from platformdirs import PlatformDirs

APP_NAME = "bufo"
APP_AUTHOR = "bitnom"


def dirs() -> PlatformDirs:
    return PlatformDirs(appname=APP_NAME, appauthor=APP_AUTHOR, roaming=False)


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def config_root() -> Path:
    return ensure_dir(Path(dirs().user_config_path))


def state_root() -> Path:
    return ensure_dir(Path(dirs().user_state_path))


def data_root() -> Path:
    return ensure_dir(Path(dirs().user_data_path))


def settings_path() -> Path:
    return config_root() / "settings.json"


def custom_agents_dir() -> Path:
    return ensure_dir(config_root() / "agents")


def session_db_path() -> Path:
    return state_root() / "sessions.sqlite3"


def project_identity(project_root: Path) -> str:
    normalized = str(project_root.expanduser().resolve())
    digest = sha1(normalized.encode("utf-8"), usedforsecurity=False).hexdigest()[:12]
    leaf = project_root.name or "root"
    return f"{leaf}-{digest}"


def project_data_dir(project_root: Path) -> Path:
    return ensure_dir(data_root() / "projects" / project_identity(project_root))
