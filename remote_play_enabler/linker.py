from __future__ import annotations

import ctypes
import json
import logging
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from .models import Game, ManagedEntry


logger = logging.getLogger("remote_play_enabler.linker")


class LinkError(RuntimeError):
    pass


@dataclass
class PlannedLink:
    source: Path
    destination: Path
    source_is_dir: bool
    preferred_kind: str
    requires_elevation: bool = False


def _same_windows_volume(a: Path, b: Path) -> bool:
    return a.drive.casefold() == b.drive.casefold() and bool(a.drive)


def _unity_data_source(game_dir: Path, executable_path: Path) -> Path | None:
    """Find a Unity *_Data directory, preferring one next to the chosen executable."""
    exe_stem = executable_path.stem.casefold()

    search_dirs = [executable_path.parent]
    if executable_path.parent != game_dir:
        search_dirs.append(game_dir)

    for directory in search_dirs:
        exact = [
            p for p in directory.iterdir()
            if p.is_dir() and p.name.casefold() == f"{exe_stem}_data"
        ]
        if len(exact) == 1:
            return exact[0]

        candidates = [
            p for p in directory.iterdir()
            if p.is_dir() and p.name.casefold().endswith("_data")
        ]
        if len(candidates) == 1:
            return candidates[0]

    return None


def _matching_pck_source(executable_path: Path) -> Path | None:
    """Return a .pck next to the executable with the same basename.

    Godot projects commonly require the PCK filename to match the executable
    filename. Because the selected executable is exposed as retroarch.exe, the
    matching PCK must be exposed as retroarch.pck as well.
    """
    parent = executable_path.parent
    expected_name = f"{executable_path.stem}.pck".casefold()

    try:
        matches = [
            child
            for child in parent.iterdir()
            if child.is_file() and child.name.casefold() == expected_name
        ]
    except OSError:
        logger.exception("Could not scan for PCK next to %s", executable_path)
        return None

    if len(matches) == 1:
        logger.info("Detected matching PCK sidecar: %s", matches[0])
        return matches[0]

    if len(matches) > 1:
        logger.warning(
            "Multiple matching PCK sidecars found next to %s; using %s",
            executable_path,
            matches[0],
        )
        return matches[0]

    logger.debug("No matching PCK sidecar found next to %s", executable_path)
    return None


def _planned_link(source: Path, destination: Path, windows_symlink_allowed: bool | None) -> tuple[PlannedLink, bool | None]:
    is_dir = source.is_dir()

    if sys.platform == "win32":
        if is_dir:
            preferred = "junction"
            elevated = False
        elif _same_windows_volume(source, destination):
            preferred = "hardlink"
            elevated = False
        else:
            preferred = "symlink"
            if windows_symlink_allowed is None:
                windows_symlink_allowed = can_create_unprivileged_file_symlink(destination.parent)
            elevated = not windows_symlink_allowed
    else:
        preferred = "symlink"
        elevated = False

    return (
        PlannedLink(
            source=source,
            destination=destination,
            source_is_dir=is_dir,
            preferred_kind=preferred,
            requires_elevation=elevated,
        ),
        windows_symlink_allowed,
    )


def build_plan(game: Game, retroarch_dir: Path) -> list[PlannedLink]:
    logger.info("Building link plan for game: %s", game.name)
    logger.debug("Game path: %s | executable: %s | RetroArch: %s", game.path, game.executable, retroarch_dir)
    game_dir = Path(game.path).resolve()
    executable_rel = Path(game.executable)

    if executable_rel.is_absolute():
        raise LinkError("The saved executable path must be relative to the game folder.")

    executable_path = (game_dir / executable_rel).resolve()

    if not game_dir.is_dir():
        raise LinkError(f"Game folder does not exist: {game_dir}")
    try:
        executable_path.relative_to(game_dir)
    except ValueError as exc:
        raise LinkError("The executable must be inside the selected game folder.") from exc
    if not executable_path.is_file():
        raise LinkError(f"Executable does not exist: {executable_path}")
    if not retroarch_dir.is_dir():
        raise LinkError(f"RetroArch folder does not exist: {retroarch_dir}")

    unity_data = _unity_data_source(game_dir, executable_path)
    pck_source = _matching_pck_source(executable_path)
    plan: list[PlannedLink] = []
    windows_symlink_allowed: bool | None = None

    # Preserve the original behavior: expose every top-level game item inside
    # the RetroArch folder. If the executable/Data folder is itself top-level,
    # rename that link to the names RetroArch/Unity expect.
    for source in game_dir.iterdir():
        if source == executable_path:
            dest_name = "retroarch.exe"
        elif pck_source is not None and source == pck_source:
            dest_name = "retroarch.pck"
        elif unity_data is not None and source == unity_data:
            dest_name = "retroarch_Data"
        else:
            dest_name = source.name

        item, windows_symlink_allowed = _planned_link(
            source, retroarch_dir / dest_name, windows_symlink_allowed
        )
        plan.append(item)

    # "Other…" may point to an executable in a subdirectory. The top-level
    # directory is already exposed above; add a direct retroarch.exe link too.
    if executable_path.parent != game_dir:
        item, windows_symlink_allowed = _planned_link(
            executable_path, retroarch_dir / "retroarch.exe", windows_symlink_allowed
        )
        plan.append(item)

    # Godot games may require a .pck with the exact same basename as the
    # executable. Since the executable becomes retroarch.exe, expose its
    # matching sidecar as retroarch.pck.
    if pck_source is not None and pck_source.parent != game_dir:
        item, windows_symlink_allowed = _planned_link(
            pck_source, retroarch_dir / "retroarch.pck", windows_symlink_allowed
        )
        plan.append(item)

    # The Unity data folder normally sits next to the executable. If that is a
    # nested path, expose it directly as retroarch_Data as well.
    if unity_data is not None and unity_data.parent != game_dir:
        item, windows_symlink_allowed = _planned_link(
            unity_data, retroarch_dir / "retroarch_Data", windows_symlink_allowed
        )
        plan.append(item)

    for item in plan:
        logger.debug("Planned link: %s -> %s | kind=%s | dir=%s | elevation=%s", item.source, item.destination, item.preferred_kind, item.source_is_dir, item.requires_elevation)
    logger.info("Link plan ready: %d item(s), %d requiring elevation", len(plan), sum(1 for x in plan if x.requires_elevation))
    return plan


def can_create_unprivileged_file_symlink(destination_dir: Path) -> bool:
    if sys.platform != "win32":
        return True

    source_fd = None
    source_path = None
    link_path = None
    try:
        source_fd, raw_source = tempfile.mkstemp(prefix="rpe_probe_", dir=str(destination_dir))
        os.close(source_fd)
        source_fd = None
        source_path = Path(raw_source)
        link_path = destination_dir / f".rpe_symlink_probe_{os.getpid()}"
        os.symlink(source_path, link_path)
        return True
    except OSError:
        return False
    finally:
        if source_fd is not None:
            try:
                os.close(source_fd)
            except OSError:
                pass
        if link_path is not None:
            try:
                link_path.unlink(missing_ok=True)
            except OSError:
                pass
        if source_path is not None:
            try:
                source_path.unlink(missing_ok=True)
            except OSError:
                pass


def _create_windows_junction(source: Path, destination: Path) -> None:
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    result = subprocess.run(
        ["cmd.exe", "/d", "/c", "mklink", "/J", str(destination), str(source)],
        capture_output=True,
        text=True,
        creationflags=creationflags,
    )
    if result.returncode != 0:
        raise LinkError(
            f"Could not create junction {destination} -> {source}: "
            f"{(result.stderr or result.stdout).strip()}"
        )


def _create_normal_link(item: PlannedLink) -> ManagedEntry:
    logger.debug("Creating link: %s -> %s using %s", item.source, item.destination, item.preferred_kind)
    if item.destination.exists() or item.destination.is_symlink():
        raise LinkError(f"Destination already exists: {item.destination}")

    if sys.platform == "win32":
        if item.preferred_kind == "hardlink":
            os.link(item.source, item.destination)
            return ManagedEntry(str(item.destination), "hardlink")

        if item.preferred_kind == "junction":
            try:
                _create_windows_junction(item.source, item.destination)
                return ManagedEntry(str(item.destination), "junction")
            except LinkError:
                # A directory symlink is the last non-destructive fallback.
                try:
                    os.symlink(item.source, item.destination, target_is_directory=True)
                    return ManagedEntry(str(item.destination), "symlink_dir")
                except OSError as exc:
                    raise LinkError(
                        f"Could not create junction or directory symlink for {item.source}: {exc}"
                    ) from exc

        os.symlink(item.source, item.destination, target_is_directory=item.source_is_dir)
        return ManagedEntry(
            str(item.destination),
            "symlink_dir" if item.source_is_dir else "symlink_file",
        )

    os.symlink(item.source, item.destination, target_is_directory=item.source_is_dir)
    return ManagedEntry(
        str(item.destination),
        "symlink_dir" if item.source_is_dir else "symlink_file",
    )


def remove_managed_entry(entry: ManagedEntry) -> None:
    logger.debug("Removing managed entry: %s | kind=%s", entry.destination, entry.kind)
    path = Path(entry.destination)

    # Windows may briefly deny deletion while shell/AV/indexing components are
    # inspecting a freshly-created executable. Retry transient sharing/access
    # failures instead of immediately aborting the whole cleanup.
    attempts = 8 if sys.platform == "win32" else 1
    delay = 0.20

    for attempt in range(1, attempts + 1):
        try:
            if entry.kind == "junction" and sys.platform == "win32":
                if path.exists():
                    os.rmdir(path)
                return

            if path.is_symlink() or path.exists():
                path.unlink()
            return

        except FileNotFoundError:
            return

        except OSError as exc:
            winerror = getattr(exc, "winerror", None)
            retryable = (
                sys.platform == "win32"
                and winerror in {5, 32, 33}
                and attempt < attempts
            )

            if not retryable:
                raise

            logger.warning(
                "Windows temporarily refused to remove %s (WinError %s). "
                "Retrying %d/%d...",
                path,
                winerror,
                attempt,
                attempts,
            )
            time.sleep(delay)


def cleanup_entries(entries: list[ManagedEntry]) -> None:
    logger.info("Cleaning %d managed link(s)", len(entries))
    errors: list[str] = []
    for entry in reversed(entries):
        try:
            remove_managed_entry(entry)
        except OSError as exc:
            errors.append(f"{entry.destination}: {exc}")
    if errors:
        raise LinkError("Some managed links could not be removed:\n" + "\n".join(errors))


def _self_launch_parts() -> tuple[str, list[str]]:
    if getattr(sys, "frozen", False):
        return sys.executable, []
    script = Path(sys.argv[0]).resolve()
    return sys.executable, [str(script)]


def _windows_quote_args(args: list[str]) -> str:
    return subprocess.list2cmdline(args)


class SHELLEXECUTEINFOW(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.c_ulong),
        ("fMask", ctypes.c_ulong),
        ("hwnd", ctypes.c_void_p),
        ("lpVerb", ctypes.c_wchar_p),
        ("lpFile", ctypes.c_wchar_p),
        ("lpParameters", ctypes.c_wchar_p),
        ("lpDirectory", ctypes.c_wchar_p),
        ("nShow", ctypes.c_int),
        ("hInstApp", ctypes.c_void_p),
        ("lpIDList", ctypes.c_void_p),
        ("lpClass", ctypes.c_wchar_p),
        ("hkeyClass", ctypes.c_void_p),
        ("dwHotKey", ctypes.c_ulong),
        ("hIconOrMonitor", ctypes.c_void_p),
        ("hProcess", ctypes.c_void_p),
    ]


def _run_elevated_windows(args: list[str]) -> int:
    if sys.platform != "win32":
        raise LinkError("Elevation helper is Windows-only.")

    SEE_MASK_NOCLOSEPROCESS = 0x00000040
    SW_SHOWNORMAL = 1
    INFINITE = 0xFFFFFFFF

    exe, prefix = _self_launch_parts()
    params = _windows_quote_args(prefix + args)

    info = SHELLEXECUTEINFOW()
    info.cbSize = ctypes.sizeof(info)
    info.fMask = SEE_MASK_NOCLOSEPROCESS
    info.lpVerb = "runas"
    info.lpFile = exe
    info.lpParameters = params
    info.nShow = SW_SHOWNORMAL

    shell32 = ctypes.windll.shell32
    kernel32 = ctypes.windll.kernel32

    if not shell32.ShellExecuteExW(ctypes.byref(info)):
        error = ctypes.windll.kernel32.GetLastError()
        raise LinkError(f"Administrator permission was not granted (Windows error {error}).")

    try:
        kernel32.WaitForSingleObject(info.hProcess, INFINITE)
        exit_code = ctypes.c_ulong()
        if not kernel32.GetExitCodeProcess(info.hProcess, ctypes.byref(exit_code)):
            raise LinkError("Could not read the elevated helper exit code.")
        return int(exit_code.value)
    finally:
        kernel32.CloseHandle(info.hProcess)


def _apply_elevated_symlinks(items: list[PlannedLink]) -> list[ManagedEntry]:
    payload_dir = Path(tempfile.mkdtemp(prefix="rpe_elevated_"))
    plan_file = payload_dir / "plan.json"
    result_file = payload_dir / "result.json"

    payload = {
        "items": [
            {
                "source": str(x.source),
                "destination": str(x.destination),
                "source_is_dir": x.source_is_dir,
            }
            for x in items
        ],
        "result_file": str(result_file),
    }
    plan_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    try:
        code = _run_elevated_windows(["--elevated-apply", str(plan_file)])
        if code != 0:
            detail = ""
            if result_file.exists():
                try:
                    detail = json.loads(result_file.read_text(encoding="utf-8")).get("error", "")
                except Exception:
                    pass
            raise LinkError(detail or f"Elevated helper failed with exit code {code}.")

        if not result_file.exists():
            raise LinkError("Elevated helper did not return a result.")

        result = json.loads(result_file.read_text(encoding="utf-8"))
        if not result.get("ok"):
            raise LinkError(str(result.get("error", "Unknown elevated helper error.")))

        return [
            ManagedEntry(str(x.destination), "symlink_dir" if x.source_is_dir else "symlink_file")
            for x in items
        ]
    finally:
        shutil.rmtree(payload_dir, ignore_errors=True)


def elevated_apply(plan_file: Path) -> int:
    try:
        payload = json.loads(plan_file.read_text(encoding="utf-8"))
        result_file = Path(payload["result_file"])
        created: list[Path] = []

        for raw in payload["items"]:
            source = Path(raw["source"])
            destination = Path(raw["destination"])
            source_is_dir = bool(raw["source_is_dir"])

            if destination.exists() or destination.is_symlink():
                raise LinkError(f"Destination already exists: {destination}")

            os.symlink(source, destination, target_is_directory=source_is_dir)
            created.append(destination)

        result_file.write_text(json.dumps({"ok": True}), encoding="utf-8")
        return 0
    except Exception as exc:
        try:
            result_file = Path(payload["result_file"])  # type: ignore[name-defined]
            result_file.write_text(json.dumps({"ok": False, "error": str(exc)}), encoding="utf-8")
        except Exception:
            pass
        return 1


def apply_plan(plan: list[PlannedLink]) -> list[ManagedEntry]:
    logger.info("Applying link plan with %d item(s)", len(plan))
    created: list[ManagedEntry] = []

    # Preflight: never overwrite an unexpected file/folder.
    conflicts = [
        str(item.destination)
        for item in plan
        if item.destination.exists() or item.destination.is_symlink()
    ]
    if conflicts:
        raise LinkError(
            "The following destinations already exist and were not modified:\n"
            + "\n".join(conflicts)
        )

    normal = [x for x in plan if not x.requires_elevation]
    elevated = [x for x in plan if x.requires_elevation]

    try:
        for item in normal:
            created.append(_create_normal_link(item))

        if elevated:
            created.extend(_apply_elevated_symlinks(elevated))

        logger.info("Link plan applied successfully. Created %d managed entry/entries.", len(created))
        return created
    except Exception:
        logger.exception("Link plan failed; attempting rollback")
        try:
            cleanup_entries(created)
        except Exception:
            pass
        raise
