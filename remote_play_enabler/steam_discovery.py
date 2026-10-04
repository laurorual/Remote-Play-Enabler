from __future__ import annotations

import logging
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path


logger = logging.getLogger("remote_play_enabler.steam_discovery")
RETROARCH_APP_ID = "1118310"


@dataclass(frozen=True)
class RetroArchInstall:
    steam_root: Path
    library_root: Path
    retroarch_path: Path
    source: str


def _unique_existing_dirs(paths: list[Path]) -> list[Path]:
    result: list[Path] = []
    seen: set[str] = set()

    for path in paths:
        try:
            candidate = path.expanduser().resolve()
        except OSError:
            candidate = path.expanduser()

        key = str(candidate).casefold()
        if key in seen or not candidate.is_dir():
            continue

        seen.add(key)
        result.append(candidate)

    return result


def _windows_steam_roots() -> list[Path]:
    candidates: list[Path] = []

    try:
        import winreg

        registry_values = [
            (winreg.HKEY_CURRENT_USER, r"Software\\Valve\\Steam", "SteamPath"),
            (winreg.HKEY_CURRENT_USER, r"Software\\Valve\\Steam", "SteamExe"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\\WOW6432Node\\Valve\\Steam", "InstallPath"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\\Valve\\Steam", "InstallPath"),
        ]

        for hive, key_name, value_name in registry_values:
            try:
                with winreg.OpenKey(hive, key_name) as key:
                    value, _ = winreg.QueryValueEx(key, value_name)
                candidate = Path(str(value))
                if value_name == "SteamExe":
                    candidate = candidate.parent
                candidates.append(candidate)
            except OSError:
                pass
    except Exception:
        logger.exception("Could not query the Windows registry for Steam.")

    if os.environ.get("PROGRAMFILES(X86)"):
        candidates.append(Path(os.environ["PROGRAMFILES(X86)"]) / "Steam")
    if os.environ.get("PROGRAMFILES"):
        candidates.append(Path(os.environ["PROGRAMFILES"]) / "Steam")

    return _unique_existing_dirs(candidates)


def _linux_steam_roots() -> list[Path]:
    home = Path.home()
    return _unique_existing_dirs([
        home / ".local/share/Steam",
        home / ".steam/steam",
        home / ".steam/root",
        # Flatpak Steam
        home / ".var/app/com.valvesoftware.Steam/data/Steam",
        home / ".var/app/com.valvesoftware.Steam/.local/share/Steam",
    ])


def default_steam_roots() -> list[Path]:
    roots = _windows_steam_roots() if sys.platform == "win32" else _linux_steam_roots()
    logger.debug("Steam roots found: %s", [str(x) for x in roots])
    return roots


def _library_paths_from_vdf(path: Path) -> list[Path]:
    if not path.is_file():
        return []

    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        logger.exception("Could not read Steam library configuration: %s", path)
        return []

    result: list[Path] = []
    # We only need quoted `path` values from libraryfolders.vdf.
    for match in re.finditer(r'^\s*"path"\s*"([^"]+)"\s*$', text, flags=re.MULTILINE):
        raw = match.group(1).replace(r"\\", "\\")
        result.append(Path(raw))
    return result


def steam_library_roots(steam_root: Path) -> list[Path]:
    candidates = [steam_root]
    candidates.extend(
        _library_paths_from_vdf(steam_root / "steamapps" / "libraryfolders.vdf")
    )
    libraries = _unique_existing_dirs(candidates)
    logger.debug(
        "Steam libraries for %s: %s",
        steam_root,
        [str(x) for x in libraries],
    )
    return libraries


def _install_dir_from_manifest(manifest: Path) -> str | None:
    if not manifest.is_file():
        return None

    try:
        text = manifest.read_text(encoding="utf-8", errors="replace")
    except OSError:
        logger.exception("Could not read Steam manifest: %s", manifest)
        return None

    match = re.search(r'^\s*"installdir"\s*"([^"]+)"\s*$', text, flags=re.MULTILINE)
    return match.group(1) if match else None


def find_retroarch_installations() -> list[RetroArchInstall]:
    found: list[RetroArchInstall] = []
    seen: set[str] = set()

    for steam_root in default_steam_roots():
        for library_root in steam_library_roots(steam_root):
            steamapps = library_root / "steamapps"
            manifest = steamapps / f"appmanifest_{RETROARCH_APP_ID}.acf"
            install_dir = _install_dir_from_manifest(manifest)

            if install_dir:
                retroarch = steamapps / "common" / install_dir
                source = f"Steam manifest: {manifest}"
            else:
                # Fallback for an unusual/older Steam layout where the manifest
                # is unavailable but the standard RetroArch folder exists.
                retroarch = steamapps / "common" / "RetroArch"
                source = f"Standard Steam library path: {library_root}"

            if not retroarch.is_dir():
                continue

            try:
                retroarch = retroarch.resolve()
            except OSError:
                pass

            key = str(retroarch).casefold()
            if key in seen:
                continue

            seen.add(key)
            found.append(
                RetroArchInstall(
                    steam_root=steam_root,
                    library_root=library_root,
                    retroarch_path=retroarch,
                    source=source,
                )
            )
            logger.info("Detected Steam RetroArch installation: %s", retroarch)

    if not found:
        logger.info("No Steam RetroArch installation was detected automatically.")

    return found
