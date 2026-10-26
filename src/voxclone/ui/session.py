"""Application session state management, UI stack, and system bootstrap lifecycle."""

from dataclasses import dataclass, field
from pathlib import Path
import sqlite3
from typing import Any

from rich.console import Console

from voxclone.config import AppConfig, get_config
from voxclone.logging_setup import log_event, setup_logging
from voxclone.services.settings_service import SettingsService
from voxclone.storage.db import connect
from voxclone.storage.files import ensure_data_layout
from voxclone.storage.migrate import apply_migrations
from voxclone.ui.components import make_console
from voxclone.ui.theme import Theme, get_theme


@dataclass
class SessionState:
    """Carries interactive runtime context across menu transitions and commands."""

    config: AppConfig
    conn: sqlite3.Connection
    theme: Theme
    console: Console

    selected_profile_id: str | None = None
    selected_profile_name: str | None = None
    last_job_id: str | None = None

    debug: bool = False
    plain: bool = False

    model_manager: Any = None
    model_service: Any = None
    profile_service: Any = None
    settings_snapshot: dict[str, Any] = field(default_factory=dict)


class ScreenStack:
    """LIFO stack tracking screen navigation history for back navigation."""

    def __init__(self) -> None:
        self._stack: list[str] = []

    def push(self, key: str) -> None:
        """Push a screen identifier onto the navigation stack."""
        self._stack.append(key)

    def pop(self) -> str | None:
        """Pop and return the previous screen identifier, or None if stack is empty."""
        if not self._stack:
            return None
        return self._stack.pop()

    def current(self) -> str | None:
        """Return the current screen identifier without removing it."""
        if not self._stack:
            return None
        return self._stack[-1]

    def clear(self) -> None:
        """Clear all entries from the screen stack."""
        self._stack.clear()


def bootstrap(debug: bool = False, plain: bool = False) -> SessionState:
    """Execute standard application initialization sequence.

    Lifecycle:
        1. Resolve application configuration.
        2. Ensure data directory layout on disk.
        3. Setup rotating JSONL logger.
        4. Establish SQLite connection with WAL/FK pragmas.
        5. Discover and apply pending schema migrations.
        6. Populate missing default application settings.
        7. Initialize Rich Console and UI Theme.
        8. Return configured SessionState.
    """
    config = get_config()
    is_plain = plain or config.plain_mode
    is_debug = debug or (config.log_level == "DEBUG")

    # 1. Prepare directory layout
    ensure_data_layout(config)

    # 2. Setup logging
    setup_logging(config)
    log_event("voxclone", "INFO", "app_bootstrap_started", debug=is_debug, plain=is_plain)

    # 3. Connect to database and apply migrations
    conn = connect(config.db_path)
    apply_migrations(conn, config.migrations_dir)

    # 4. Ensure settings defaults
    settings_svc = SettingsService(conn, config)
    settings_svc.ensure_defaults()
    settings_snapshot = {k: v.value for k, v in settings_svc.get_all().items()}

    # 5. UI Theme and Console
    theme = get_theme(plain=is_plain, no_color=config.no_color)
    console = make_console(theme=theme, plain=is_plain)

    # 6. Initialize Model Manager and Services
    from voxclone.engines.model_manager import ModelManager
    from voxclone.services.model_service import ModelService
    from voxclone.services.profile_service import ProfileService

    model_mgr = ModelManager(config=config, db_path=config.db_path)
    model_svc = ModelService(model_manager=model_mgr, db_path=config.db_path)
    profile_svc = ProfileService(db_path=config.db_path, profiles_dir=config.profiles_dir)

    state = SessionState(
        config=config,
        conn=conn,
        theme=theme,
        console=console,
        debug=is_debug,
        plain=is_plain,
        model_manager=model_mgr,
        model_service=model_svc,
        profile_service=profile_svc,
        settings_snapshot=settings_snapshot,
    )
    log_event("voxclone", "INFO", "app_bootstrap_completed")
    return state


def close(state: SessionState) -> None:
    """Release model manager resources, close database connection, and flush logs."""
    try:
        if state.model_manager:
            state.model_manager.close()
    except Exception:
        pass

    try:
        if state.conn:
            state.conn.close()
    except Exception:
        pass
    log_event("voxclone", "INFO", "app_session_closed")
