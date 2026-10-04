from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from .models import Game, ManagedEntry


APP_DIR_NAME = "RemotePlayEnabler"


def app_data_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        path = base / APP_DIR_NAME
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
        path = base / "remote-play-enabler"
    path.mkdir(parents=True, exist_ok=True)
    return path


def log_dir() -> Path:
    path = app_data_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


class ConfigStore:
    def __init__(self) -> None:
        self.path = app_data_dir() / "config.json"
        self.data: dict[str, Any] = {
            "retroarch_path": "",
            "backup_path": "",
            "prepared": False,
            "active_game_id": "",
            "managed_entries": [],
            "games": [],
        }
        self.load()

    def load(self) -> None:
        if not self.path.exists():
            return
        try:
            saved = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return
        if isinstance(saved, dict):
            self.data.update(saved)

    def save(self) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.path)

    @property
    def retroarch_path(self) -> Path | None:
        value = str(self.data.get("retroarch_path", "")).strip()
        return Path(value) if value else None

    @retroarch_path.setter
    def retroarch_path(self, value: Path) -> None:
        self.data["retroarch_path"] = str(value.resolve())
        self.save()

    @property
    def backup_path(self) -> Path | None:
        value = str(self.data.get("backup_path", "")).strip()
        return Path(value) if value else None

    @backup_path.setter
    def backup_path(self, value: Path) -> None:
        self.data["backup_path"] = str(value.resolve())
        self.save()

    @property
    def prepared(self) -> bool:
        return bool(self.data.get("prepared", False))

    @prepared.setter
    def prepared(self, value: bool) -> None:
        self.data["prepared"] = bool(value)
        self.save()

    @property
    def active_game_id(self) -> str:
        return str(self.data.get("active_game_id", ""))

    @active_game_id.setter
    def active_game_id(self, value: str) -> None:
        self.data["active_game_id"] = value
        self.save()

    @property
    def games(self) -> list[Game]:
        return [Game.from_dict(x) for x in self.data.get("games", [])]

    def add_game(self, game: Game) -> None:
        games = self.games
        games.append(game)
        self.data["games"] = [g.to_dict() for g in games]
        self.save()

    def delete_game(self, game_id: str) -> None:
        self.data["games"] = [g.to_dict() for g in self.games if g.id != game_id]
        self.save()

    def game_by_id(self, game_id: str) -> Game | None:
        return next((g for g in self.games if g.id == game_id), None)

    @property
    def managed_entries(self) -> list[ManagedEntry]:
        return [ManagedEntry.from_dict(x) for x in self.data.get("managed_entries", [])]

    @managed_entries.setter
    def managed_entries(self, entries: list[ManagedEntry]) -> None:
        self.data["managed_entries"] = [e.to_dict() for e in entries]
        self.save()
