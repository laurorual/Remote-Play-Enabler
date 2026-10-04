from __future__ import annotations

import os
import logging
import shutil
import subprocess
import sys


logger = logging.getLogger("remote_play_enabler.steam")


RETROARCH_STEAM_APP_ID = "1118310"
RETROARCH_RUN_URL = f"steam://run/{RETROARCH_STEAM_APP_ID}"
RETROARCH_INSTALL_URL = f"steam://install/{RETROARCH_STEAM_APP_ID}"


class SteamLaunchError(RuntimeError):
    pass


def _open_steam_url(url: str) -> None:
    """Open a steam:// URL through Steam on Windows or Linux."""
    logger.info("Opening Steam URL: %s", url)
    if sys.platform == "win32":
        try:
            os.startfile(url)  # type: ignore[attr-defined]
            logger.debug("Steam URL passed to Windows URL handler.")
            return
        except OSError as exc:
            raise SteamLaunchError(
                "Windows could not open the Steam URL. Make sure Steam is installed "
                "and its URL protocol is registered."
            ) from exc

    if sys.platform.startswith("linux"):
        steam = shutil.which("steam")
        if steam:
            try:
                logger.debug("Launching Steam URL through executable: %s", steam)
                subprocess.Popen(
                    [steam, url],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
                return
            except OSError:
                pass

        # Useful for Flatpak/package layouts where steam:// is registered but
        # no `steam` executable is exposed in PATH.
        xdg_open = shutil.which("xdg-open")
        if xdg_open:
            try:
                logger.debug("Launching Steam URL through xdg-open: %s", xdg_open)
                subprocess.Popen(
                    [xdg_open, url],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
                return
            except OSError:
                pass

        raise SteamLaunchError(
            "Could not find Steam or a handler for steam:// URLs on this Linux system."
        )

    raise SteamLaunchError(
        "Opening Steam URLs is currently supported on Windows and Linux only."
    )


def launch_retroarch_via_steam() -> None:
    """Launch the Steam version of RetroArch through Steam."""
    _open_steam_url(RETROARCH_RUN_URL)


def install_retroarch_via_steam() -> None:
    """Ask Steam to install the Steam version of RetroArch."""
    _open_steam_url(RETROARCH_INSTALL_URL)
