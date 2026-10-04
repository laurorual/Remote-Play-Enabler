from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any
import uuid


@dataclass
class Game:
    id: str
    name: str
    path: str
    executable: str

    @classmethod
    def create(cls, name: str, path: Path, executable: str) -> "Game":
        return cls(
            id=str(uuid.uuid4()),
            name=name.strip(),
            path=str(path.resolve()),
            executable=executable,
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Game":
        return cls(
            id=str(data["id"]),
            name=str(data["name"]),
            path=str(data["path"]),
            executable=str(data["executable"]),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ManagedEntry:
    destination: str
    kind: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ManagedEntry":
        return cls(destination=str(data["destination"]), kind=str(data["kind"]))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
