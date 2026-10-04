from __future__ import annotations

import os
import logging
import shutil
import sys
from datetime import datetime
from pathlib import Path

from .linker import LinkError


logger = logging.getLogger("remote_play_enabler.retroarch")


def prepare_retroarch_folder(retroarch_dir: Path) -> Path | None:
    logger.info("Preparing RetroArch folder: %s", retroarch_dir)
    """
    Move the current RetroArch contents to a sibling backup directory.

    Unlike the original Bash script, this does not permanently delete the
    installation contents. The selected RetroArch directory itself remains
    in place and becomes the managed container used by Remote Play Enabler.
    """
    retroarch_dir = retroarch_dir.resolve()
    if not retroarch_dir.is_dir():
        raise LinkError(f"RetroArch folder does not exist: {retroarch_dir}")

    items = list(retroarch_dir.iterdir())
    if not items:
        logger.info("RetroArch folder is already empty; no backup needed.")
        return None

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = retroarch_dir.parent / f"{retroarch_dir.name}.rpe-backup-{stamp}"
    backup.mkdir(parents=False, exist_ok=False)

    moved: list[tuple[Path, Path]] = []
    try:
        for item in items:
            target = backup / item.name
            shutil.move(str(item), str(target))
            moved.append((item, target))
    except Exception as exc:
        # Best-effort rollback.
        for original, backed_up in reversed(moved):
            try:
                if backed_up.exists():
                    shutil.move(str(backed_up), str(original))
            except Exception:
                pass
        try:
            backup.rmdir()
        except OSError:
            pass
        raise LinkError(f"Could not prepare RetroArch folder: {exc}") from exc

    logger.info("RetroArch backup created: %s (%d item(s) moved)", backup, len(moved))
    return backup


def find_retroarch_backups(retroarch_dir: Path) -> list[Path]:
    """Return backup folders created for this exact RetroArch installation.

    Backup directory names contain a sortable timestamp, so newest backups are
    returned first. The function intentionally checks sibling directories only;
    a similarly named folder elsewhere on disk is never considered evidence
    that this installation is prepared.
    """
    try:
        retroarch_dir = retroarch_dir.resolve()
    except OSError:
        retroarch_dir = retroarch_dir.absolute()

    parent = retroarch_dir.parent
    prefix = f"{retroarch_dir.name}.rpe-backup-"

    try:
        candidates = [
            child
            for child in parent.iterdir()
            if child.is_dir() and child.name.startswith(prefix)
        ]
    except OSError:
        logger.exception("Could not scan for RetroArch backups next to %s", retroarch_dir)
        return []

    # YYYYMMDD-HHMMSS makes name order chronological. Name is also more stable
    # than directory mtime, which may change when files are inspected/moved.
    candidates.sort(key=lambda path: path.name, reverse=True)
    logger.debug(
        "Detected RetroArch backup candidate(s) for %s: %s",
        retroarch_dir,
        [str(x) for x in candidates],
    )
    return candidates


def detect_retroarch_backup(
    retroarch_dir: Path,
    preferred_backup: Path | None = None,
) -> Path | None:
    """Find the backup that indicates a RetroArch folder is already prepared.

    A still-valid backup recorded in config wins. If config is stale or was
    reset, sibling ``*.rpe-backup-*`` folders are used as a recovery mechanism.
    When more than one exists, the newest timestamped backup is selected and a
    warning is written to the log.
    """
    try:
        retroarch_dir = retroarch_dir.resolve()
    except OSError:
        retroarch_dir = retroarch_dir.absolute()

    prefix = f"{retroarch_dir.name}.rpe-backup-"

    if preferred_backup is not None:
        try:
            preferred = preferred_backup.resolve()
        except OSError:
            preferred = preferred_backup.absolute()

        if (
            preferred.is_dir()
            and preferred.parent == retroarch_dir.parent
            and preferred.name.startswith(prefix)
        ):
            logger.debug("Using configured RetroArch backup: %s", preferred)
            return preferred

    backups = find_retroarch_backups(retroarch_dir)
    if not backups:
        return None

    if len(backups) > 1:
        logger.warning(
            "Multiple RetroArch backups were found for %s; using newest: %s | all=%s",
            retroarch_dir,
            backups[0],
            [str(x) for x in backups],
        )

    return backups[0]


def retroarch_leftovers(retroarch_dir: Path) -> list[Path]:
    """Return items currently left inside the prepared RetroArch folder."""
    retroarch_dir = retroarch_dir.resolve()
    if not retroarch_dir.is_dir():
        raise LinkError(f"RetroArch folder does not exist: {retroarch_dir}")
    items = list(retroarch_dir.iterdir())
    logger.debug("RetroArch leftovers in %s: %s", retroarch_dir, [x.name for x in items])
    return items


def _is_windows_junction(path: Path) -> bool:
    if sys.platform != "win32":
        return False
    is_junction = getattr(path, "is_junction", None)
    if is_junction is None:
        return False
    try:
        return bool(is_junction())
    except OSError:
        return False


def _remove_item_safely(path: Path) -> None:
    """Delete one item without traversing symlinks or Windows junctions."""
    if path.is_symlink():
        path.unlink()
        return

    if _is_windows_junction(path):
        os.rmdir(path)
        return

    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()


def clear_retroarch_leftovers(retroarch_dir: Path) -> None:
    logger.warning("Deleting all remaining items from prepared RetroArch folder: %s", retroarch_dir)
    """Permanently remove every remaining item inside RetroArch.

    This is intentionally separate from restore_retroarch_folder so the GUI
    must obtain explicit user confirmation before destructive cleanup.
    """
    leftovers = retroarch_leftovers(retroarch_dir)
    errors: list[str] = []

    for item in leftovers:
        try:
            _remove_item_safely(item)
        except Exception as exc:
            errors.append(f"{item.name}: {exc}")

    if errors:
        raise LinkError(
            "Some remaining RetroArch files could not be deleted:\n\n"
            + "\n".join(f"• {line}" for line in errors)
        )


def restore_retroarch_folder(retroarch_dir: Path, backup_dir: Path) -> None:
    logger.info("Restoring RetroArch from %s to %s", backup_dir, retroarch_dir)
    """Restore a previously created RetroArch backup safely.

    The caller must remove managed game links first. This function still
    refuses to overwrite unexpected items; the GUI may explicitly clear them
    first after asking the user.
    """
    retroarch_dir = retroarch_dir.resolve()
    backup_dir = backup_dir.resolve()

    if not retroarch_dir.is_dir():
        raise LinkError(f"RetroArch folder does not exist: {retroarch_dir}")
    if not backup_dir.is_dir():
        raise LinkError(f"RetroArch backup does not exist: {backup_dir}")

    leftovers = retroarch_leftovers(retroarch_dir)
    if leftovers:
        names = "\n".join(f"• {item.name}" for item in leftovers[:15])
        if len(leftovers) > 15:
            names += f"\n• …and {len(leftovers) - 15} more"
        raise LinkError(
            "The RetroArch folder still contains files that would be overwritten:\n\n"
            f"{names}"
        )

    backup_items = list(backup_dir.iterdir())
    if not backup_items:
        raise LinkError("The RetroArch backup folder is empty. Nothing was restored.")

    moved: list[tuple[Path, Path]] = []
    try:
        for item in backup_items:
            destination = retroarch_dir / item.name
            if destination.exists() or destination.is_symlink():
                raise LinkError(f"Restore destination already exists: {destination}")
            shutil.move(str(item), str(destination))
            moved.append((item, destination))
    except Exception as exc:
        # Put already-restored items back in the backup if something fails.
        for original, restored in reversed(moved):
            try:
                if restored.exists() or restored.is_symlink():
                    shutil.move(str(restored), str(original))
            except Exception:
                pass
        if isinstance(exc, LinkError):
            raise
        raise LinkError(f"Could not restore RetroArch: {exc}") from exc

    logger.info("RetroArch restore completed: %d item(s) restored", len(moved))

    try:
        backup_dir.rmdir()
    except OSError:
        # The restore itself succeeded; a leftover backup directory is harmless.
        pass
