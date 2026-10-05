from __future__ import annotations

import gc
import hashlib
import logging
import sys
from pathlib import Path

from PySide6.QtCore import QFileInfo
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QFileIconProvider

from .config import app_data_dir
from .models import Game


logger = logging.getLogger("remote_play_enabler.icons")


def _cache_path(game: Game, executable: Path) -> Path:
    try:
        stat = executable.stat()
        fingerprint = f"{executable.resolve()}|{stat.st_mtime_ns}|{stat.st_size}"
    except OSError:
        fingerprint = str(executable)

    digest = hashlib.sha256(
        fingerprint.encode("utf-8", errors="replace")
    ).hexdigest()[:16]

    cache_dir = app_data_dir() / "icon-cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / f"{game.id}-{digest}.png"


def _extract_icon_to_png(executable: Path, output: Path) -> bool:
    """
    Extract the first Windows icon resource from a PE executable and normalize
    it to PNG.

    Resource objects are explicitly released before returning. This matters on
    Windows because the active RetroArch executable may be a hardlink to this
    same underlying file, and a lingering file handle can prevent that hardlink
    from being deleted.
    """
    logger.debug("Icon extraction started: %s", executable)

    try:
        from icoextract import IconExtractor, IconExtractorError
    except Exception:
        logger.exception(
            "Could not import icoextract. Install/update dependencies from requirements.txt."
        )
        return False

    try:
        from PIL import Image
    except Exception:
        logger.exception(
            "Could not import Pillow. Install/update dependencies from requirements.txt."
        )
        return False

    extractor = None
    icon_stream = None

    try:
        extractor = IconExtractor(str(executable))
        icon_stream = extractor.get_icon(num=0)
        logger.debug("icoextract returned the first icon group for: %s", executable)

        with Image.open(icon_stream) as image:
            selected = None
            sizes = []

            ico_reader = getattr(image, "ico", None)
            if ico_reader is not None and hasattr(ico_reader, "sizes"):
                try:
                    sizes = sorted(
                        ico_reader.sizes(),
                        key=lambda size: (size[0] * size[1], size[0], size[1]),
                        reverse=True,
                    )
                except Exception:
                    logger.exception(
                        "Could not enumerate embedded ICO sizes for %s",
                        executable,
                    )

            if sizes and ico_reader is not None and hasattr(ico_reader, "getimage"):
                chosen = sizes[0]
                logger.debug(
                    "Embedded icon sizes for %s: %s; using %s",
                    executable,
                    sizes,
                    chosen,
                )
                selected = ico_reader.getimage(chosen)
            else:
                logger.debug(
                    "ICO size enumeration unavailable for %s; using Pillow's default frame %s",
                    executable,
                    image.size,
                )
                selected = image.copy()

            selected = selected.convert("RGBA")

            if selected.width > 256 or selected.height > 256:
                resampling = getattr(Image, "Resampling", Image).LANCZOS
                selected.thumbnail((256, 256), resampling)

            output.parent.mkdir(parents=True, exist_ok=True)
            selected.save(output, format="PNG")

        logger.info("Extracted game icon: %s -> %s", executable, output)
        return True

    except IconExtractorError as exc:
        logger.warning(
            "No usable embedded icon could be extracted from %s: %s",
            executable,
            exc,
        )
        return False
    except Exception:
        logger.exception("Unexpected error while extracting icon from %s", executable)
        return False
    finally:
        # get_icon() normally returns an in-memory stream, but close it when the
        # object supports close(). Also drop the extractor explicitly rather
        # than relying on non-deterministic cleanup.
        if icon_stream is not None:
            try:
                close = getattr(icon_stream, "close", None)
                if close is not None:
                    close()
            except Exception:
                logger.exception("Could not close icon stream for %s", executable)

        icon_stream = None
        extractor = None

        # CPython normally releases these immediately, but this also clears any
        # cyclic object graphs from the PE/icon libraries before hardlink
        # cleanup can be attempted later.
        gc.collect()


def icon_for_game(game: Game) -> QIcon:
    executable = (Path(game.path) / game.executable).resolve()
    logger.debug("Loading icon for game '%s' from %s", game.name, executable)

    if not executable.is_file():
        logger.warning("Game executable does not exist while loading icon: %s", executable)
        return QIcon()

    cache = _cache_path(game, executable)

    if cache.exists():
        logger.debug("Using cached icon for '%s': %s", game.name, cache)
    else:
        logger.debug("No cached icon for '%s'; extracting from executable.", game.name)

        # Remove caches from older versions / changed executables for this game.
        cache_dir = cache.parent
        for pattern in (f"{game.id}-*.png", f"{game.id}-*.ico"):
            for old in cache_dir.glob(pattern):
                if old == cache:
                    continue
                try:
                    old.unlink()
                    logger.debug("Removed stale icon cache: %s", old)
                except OSError:
                    logger.exception("Could not remove stale icon cache: %s", old)

        _extract_icon_to_png(executable, cache)

    if cache.exists():
        icon = QIcon(str(cache))
        if not icon.isNull():
            logger.debug("Qt loaded extracted icon successfully for '%s'.", game.name)
            return icon
        logger.warning("Qt could not load extracted PNG icon: %s", cache)

    # QFileIconProvider asks the Windows shell for an executable's icon. Some
    # shell/icon handlers keep a file handle open longer than expected. Since
    # retroarch.exe can be a hardlink to this exact file, that can make Windows
    # refuse to delete the managed hardlink. Do not touch the EXE through the
    # shell on Windows; an empty icon is safer than holding the game file open.
    if sys.platform == "win32":
        logger.warning(
            "Embedded icon unavailable for '%s'; skipping Windows shell icon fallback "
            "to avoid locking the executable.",
            game.name,
        )
        return QIcon()

    logger.warning(
        "Falling back to the operating-system file icon for '%s' (%s).",
        game.name,
        executable,
    )
    fallback = QFileIconProvider().icon(QFileInfo(str(executable)))
    if fallback.isNull():
        logger.warning("Operating-system icon fallback was also null for %s", executable)
    return fallback
