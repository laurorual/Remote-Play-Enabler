from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import Qt, QSize, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from .config import ConfigStore
from .dialogs import AddGameDialog
from .game_icons import icon_for_game
from .help_dialog import HelpDialog
from .linker import LinkError, apply_plan, build_plan, cleanup_entries
from .models import Game
from .retroarch_dialog import RetroArchSelectionDialog
from .prepare import (
    clear_retroarch_leftovers,
    detect_retroarch_backup,
    prepare_retroarch_folder,
    restore_retroarch_folder,
    retroarch_leftovers,
)
from .steam import SteamLaunchError, launch_retroarch_via_steam


class MainWindow(QMainWindow):
    def __init__(self, store: ConfigStore, logger: logging.Logger) -> None:
        super().__init__()
        self.store = store
        self.logger = logger

        self.setWindowTitle("Remote Play Enabler")
        self.resize(760, 550)

        self.retroarch_label = QLabel()
        self.retroarch_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        choose_ra = QPushButton("Choose RetroArch Folder…")
        choose_ra.clicked.connect(self.choose_retroarch)

        self.prepare_btn = QPushButton("Prepare / Backup RetroArch")
        self.prepare_btn.clicked.connect(self.prepare_retroarch)

        self.restore_btn = QPushButton("Restore RetroArch")
        self.restore_btn.setToolTip("Restore the original Steam RetroArch files from the backup")
        self.restore_btn.clicked.connect(self.restore_retroarch)

        self.help_btn = QPushButton("How To")
        self.help_btn.setToolTip("Open the Remote Play Enabler usage guide")
        self.help_btn.clicked.connect(self.show_help)

        ra_buttons = QHBoxLayout()
        ra_buttons.addWidget(choose_ra)
        ra_buttons.addWidget(self.prepare_btn)
        ra_buttons.addWidget(self.restore_btn)
        ra_buttons.addStretch(1)
        ra_buttons.addWidget(self.help_btn)

        self.games = QListWidget()
        self.games.setIconSize(QSize(40, 40))
        self.games.setSpacing(2)
        self.games.itemSelectionChanged.connect(self._update_buttons)

        self.add_btn = QPushButton("Add Game…")
        self.enable_btn = QPushButton("Enable")
        self.disable_btn = QPushButton("Disable Active Game")
        self.delete_btn = QPushButton("Delete")

        self.start_btn = QPushButton("▶  Start Game")
        self.start_btn.setMinimumHeight(42)
        self.start_btn.setToolTip("Launch RetroArch through Steam (Steam AppID 1118310)")
        self.start_btn.setStyleSheet(
            "QPushButton {"
            "  background-color: #1b6ca8;"
            "  color: white;"
            "  font-weight: 600;"
            "  font-size: 14px;"
            "  padding: 8px 22px;"
            "  border-radius: 5px;"
            "}"
            "QPushButton:hover { background-color: #237fbd; }"
            "QPushButton:pressed { background-color: #15577f; }"
            "QPushButton:disabled { background-color: #555; color: #aaa; }"
        )

        self.add_btn.clicked.connect(self.add_game)
        self.enable_btn.clicked.connect(self.enable_selected)
        self.disable_btn.clicked.connect(self.disable_active)
        self.delete_btn.clicked.connect(self.delete_selected)
        self.start_btn.clicked.connect(self.start_game)

        actions = QHBoxLayout()
        actions.addWidget(self.add_btn)
        actions.addStretch(1)
        actions.addWidget(self.enable_btn)
        actions.addWidget(self.disable_btn)
        actions.addWidget(self.delete_btn)

        start_row = QHBoxLayout()
        start_row.addStretch(1)
        start_row.addWidget(self.start_btn, 2)
        start_row.addStretch(1)

        root = QWidget()
        layout = QVBoxLayout(root)
        layout.addWidget(QLabel("<b>Steam RetroArch folder</b>"))
        layout.addWidget(self.retroarch_label)
        layout.addLayout(ra_buttons)
        layout.addSpacing(12)
        layout.addWidget(QLabel("<b>Games</b>"))
        layout.addWidget(self.games, 1)
        layout.addLayout(actions)
        layout.addSpacing(8)
        layout.addLayout(start_row)

        self.setCentralWidget(root)
        self.setStatusBar(QStatusBar())

        # Reconcile config with the backup on disk. This also repairs state
        # saved by older versions that reset "prepared" after re-selecting
        # the same RetroArch installation.
        self._reconcile_retroarch_preparation_state()
        self.refresh()

    @staticmethod
    def _same_path(left: Path | None, right: Path | None) -> bool:
        if left is None or right is None:
            return False
        try:
            return left.resolve() == right.resolve()
        except OSError:
            return left.absolute() == right.absolute()

    def _reconcile_retroarch_preparation_state(self) -> None:
        """Recover prepared state from config and/or the on-disk backup.

        The config is useful for normal operation, while the backup directory is
        durable evidence that Prepare/Backup RetroArch already moved the real
        installation out of the way. Using both prevents a folder re-selection
        (or a stale config value) from making the app offer to prepare it twice.
        """
        ra = self.store.retroarch_path
        if ra is None or not ra.is_dir():
            return

        configured_backup = self.store.backup_path
        detected_backup = detect_retroarch_backup(ra, configured_backup)

        if detected_backup is not None:
            changed = (
                not self.store.prepared
                or configured_backup is None
                or not self._same_path(configured_backup, detected_backup)
            )

            self.store.data["prepared"] = True
            self.store.data["backup_path"] = str(detected_backup.resolve())
            if changed:
                self.store.save()
                self.logger.info(
                    "Recovered prepared RetroArch state from backup: %s",
                    detected_backup,
                )
            return

        # Rare edge case: an already-empty folder can be intentionally marked
        # prepared without producing a backup. Keep that config state instead
        # of incorrectly turning it back into an unprepared installation.
        if self.store.prepared and configured_backup is None:
            self.logger.debug(
                "RetroArch is marked prepared without a backup path; preserving config state: %s",
                ra,
            )
            return

        # If config explicitly points at a backup that disappeared, do NOT
        # silently offer to prepare the directory again. The folder may still
        # contain game links and preparing it again could back those up as if
        # they were the original RetroArch files. Preserve prepared=True and
        # let Restore report the missing backup instead.
        if self.store.prepared and configured_backup is not None:
            self.logger.warning(
                "RetroArch is marked prepared but its configured backup is missing: %s",
                configured_backup,
            )

    def refresh(self) -> None:
        ra = self.store.retroarch_path
        if ra:
            extra = " — prepared" if self.store.prepared else " — not prepared"
            self.retroarch_label.setText(f"{ra}{extra}")
        else:
            self.retroarch_label.setText("Not configured")

        selected_id = self._selected_game_id()
        self.games.clear()

        active_id = self.store.active_game_id
        for game in self.store.games:
            suffix = "   ● ACTIVE" if game.id == active_id else ""
            item = QListWidgetItem(f"{game.name}{suffix}\n{game.path}")
            item.setData(Qt.ItemDataRole.UserRole, game.id)
            icon = icon_for_game(game)
            if not icon.isNull():
                item.setIcon(icon)
            self.games.addItem(item)
            if game.id == selected_id:
                item.setSelected(True)

        active_game = self.store.game_by_id(active_id) if active_id else None
        self.statusBar().showMessage(
            f"Active: {active_game.name}" if active_game else "No active game"
        )
        self._update_buttons()

    def _selected_game_id(self) -> str | None:
        items = self.games.selectedItems()
        return str(items[0].data(Qt.ItemDataRole.UserRole)) if items else None

    def _selected_game(self) -> Game | None:
        game_id = self._selected_game_id()
        return self.store.game_by_id(game_id) if game_id else None

    def _update_buttons(self) -> None:
        game = self._selected_game()
        self.enable_btn.setEnabled(game is not None and game.id != self.store.active_game_id)
        self.delete_btn.setEnabled(game is not None)
        self.disable_btn.setEnabled(bool(self.store.active_game_id))
        self.start_btn.setEnabled(bool(self.store.active_game_id) and self.store.prepared)
        self.prepare_btn.setEnabled(bool(self.store.retroarch_path) and not self.store.prepared)
        backup = self.store.backup_path
        self.restore_btn.setEnabled(
            self.store.prepared and backup is not None and backup.is_dir()
        )

    def choose_retroarch(self) -> None:
        if self.store.active_game_id:
            QMessageBox.warning(
                self,
                "Active game",
                "Disable the active game before changing the RetroArch folder.",
            )
            return

        dialog = RetroArchSelectionDialog(self)
        if not dialog.exec():
            return

        path = dialog.selected_path
        if path is None:
            return

        previous_path = self.store.retroarch_path
        same_installation = self._same_path(previous_path, path)

        # A real backup on disk is the strongest evidence that this exact
        # RetroArch installation has already been prepared. Prefer the backup
        # already stored in config, but recover automatically from sibling
        # RetroArch.rpe-backup-* folders when necessary.
        preferred_backup = self.store.backup_path if same_installation else None
        detected_backup = detect_retroarch_backup(path, preferred_backup)

        self.store.data["retroarch_path"] = str(path.resolve())

        if detected_backup is not None:
            self.store.data["prepared"] = True
            self.store.data["backup_path"] = str(detected_backup.resolve())
            self.logger.info(
                "RetroArch folder selected and detected as already prepared: %s | backup=%s",
                path,
                detected_backup,
            )
        elif same_installation and self.store.prepared and self.store.backup_path is None:
            # Preserve the intentional no-backup state used when the selected
            # folder was already empty at preparation time.
            self.logger.info(
                "Re-selected prepared RetroArch folder with no backup required: %s",
                path,
            )
        elif same_installation and self.store.prepared:
            # Preserve a prepared state even if its expected backup is missing;
            # resetting it here could allow a dangerous second preparation.
            self.logger.warning(
                "Re-selected RetroArch folder is marked prepared, but no valid backup was found. "
                "Keeping prepared state to avoid preparing it twice: %s",
                path,
            )
        else:
            self.store.data["prepared"] = False
            self.store.data["backup_path"] = ""
            self.logger.info("RetroArch folder selected as unprepared: %s", path)

        self.store.save()
        self.refresh()

    def prepare_retroarch(self) -> None:
        ra = self.store.retroarch_path
        if ra is None:
            QMessageBox.warning(self, "RetroArch not configured", "Choose the Steam RetroArch folder first.")
            return
        if self.store.prepared:
            QMessageBox.information(self, "Already prepared", "This RetroArch folder is already marked as prepared.")
            return
        if self.store.active_game_id:
            QMessageBox.warning(self, "Active game", "Disable the active game first.")
            return

        answer = QMessageBox.question(
            self,
            "Prepare RetroArch",
            "Remote Play Enabler needs to temporarily use the RetroArch installation folder "
            "to link the selected game.\n\n"
            "The current RetroArch files will be safely moved to a backup folder next to the "
            "installation. You can restore them at any time using the ‘Restore RetroArch’ button.\n\n"
            "Prepare RetroArch now?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        try:
            backup = prepare_retroarch_folder(ra)
        except Exception as exc:
            self.logger.exception("RetroArch preparation failed")
            QMessageBox.critical(self, "Preparation failed", str(exc))
            return

        if backup is not None:
            self.store.backup_path = backup
            message = f"Original contents were moved to:\n{backup}"
            self.logger.info("RetroArch prepared. Backup: %s", backup)
        else:
            self.store.data["backup_path"] = ""
            self.store.save()
            message = "The selected RetroArch folder was already empty, so no backup was necessary."
            self.logger.info("RetroArch prepared. Folder was already empty.")

        self.store.prepared = True
        QMessageBox.information(self, "RetroArch prepared", message)
        self.refresh()

    def restore_retroarch(self) -> None:
        ra = self.store.retroarch_path
        backup = self.store.backup_path

        if ra is None:
            QMessageBox.warning(self, "RetroArch not configured", "Choose the Steam RetroArch folder first.")
            return
        if backup is None or not backup.is_dir():
            QMessageBox.warning(
                self,
                "Backup not found",
                "No valid RetroArch backup was found for this prepared installation.",
            )
            return

        active_game = self.store.game_by_id(self.store.active_game_id)
        active_note = (
            f"The active game “{active_game.name}” will be disabled first.\n\n"
            if active_game is not None
            else ""
        )
        answer = QMessageBox.question(
            self,
            "Restore RetroArch",
            active_note
            + "This will remove the links managed by Remote Play Enabler and restore the "
            "original RetroArch files from:\n\n"
            + str(backup)
            + "\n\nContinue?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        # Inspect the directory BEFORE removing the active game's managed links.
        # That lets “Open RetroArch Folder” truly do nothing except open the
        # folder: the active game remains active and no files are changed.
        try:
            current_items = retroarch_leftovers(ra)
        except Exception as exc:
            self.logger.exception("Could not inspect RetroArch folder before restore")
            QMessageBox.critical(self, "Restore failed", str(exc))
            return

        managed_paths = {
            str(Path(entry.destination).absolute())
            for entry in self.store.managed_entries
        }
        unexpected = [
            item
            for item in current_items
            if str(item.absolute()) not in managed_paths
        ]

        delete_unexpected = False
        if unexpected:
            names = "\n".join(f"• {item.name}" for item in unexpected[:12])
            if len(unexpected) > 12:
                names += f"\n• …and {len(unexpected) - 12} more"

            warning = QMessageBox(self)
            warning.setIcon(QMessageBox.Icon.Warning)
            warning.setWindowTitle("RetroArch folder contains extra files")
            warning.setText(
                "Files or folders that are not managed by Remote Play Enabler were found inside the RetroArch folder."
            )
            warning.setInformativeText(
                names
                + "\n\nChoose “Delete Files and Restore” to permanently delete these extra items and restore the original RetroArch backup, or open the folder to inspect it yourself."
            )
            delete_restore = warning.addButton(
                "Delete Files and Restore",
                QMessageBox.ButtonRole.DestructiveRole,
            )
            open_folder = warning.addButton(
                "Open RetroArch Folder",
                QMessageBox.ButtonRole.ActionRole,
            )
            warning.exec()

            clicked = warning.clickedButton()
            if clicked is open_folder:
                opened = QDesktopServices.openUrl(QUrl.fromLocalFile(str(ra.resolve())))
                if not opened:
                    QMessageBox.warning(
                        self,
                        "Could not open folder",
                        f"The folder could not be opened automatically:\n{ra}",
                    )
                self.logger.info("Opened RetroArch folder for manual inspection: %s", ra)
                return

            if clicked is not delete_restore:
                return

            delete_unexpected = True

        try:
            # Only after the user has chosen to proceed do we disable the active
            # game and remove links recorded as managed by this app.
            cleanup_entries(self.store.managed_entries)
            self.store.managed_entries = []
            self.store.active_game_id = ""
        except Exception as exc:
            self.logger.exception("RetroArch link cleanup failed before restore")
            self.refresh()
            QMessageBox.critical(self, "Restore failed", str(exc))
            return

        if delete_unexpected:
            try:
                # At this point the managed links are gone, so everything still
                # inside RetroArch is exactly what the user approved deleting.
                remaining = retroarch_leftovers(ra)
                clear_retroarch_leftovers(ra)
                self.logger.warning(
                    "User explicitly deleted %d leftover RetroArch item(s) before restore",
                    len(remaining),
                )
            except Exception as exc:
                self.logger.exception("Could not delete RetroArch leftovers")
                self.refresh()
                QMessageBox.critical(self, "Could not delete remaining files", str(exc))
                return

        try:
            restore_retroarch_folder(ra, backup)
        except Exception as exc:
            self.logger.exception("RetroArch restore failed")
            self.refresh()
            QMessageBox.critical(self, "Restore failed", str(exc))
            return

        self.store.prepared = False
        self.store.data["backup_path"] = ""
        self.store.save()

        self.logger.info("RetroArch restored from backup: %s", backup)
        QMessageBox.information(
            self,
            "RetroArch restored",
            "The original RetroArch files have been restored. You can now use RetroArch normally through Steam.",
        )
        self.refresh()

    def show_help(self) -> None:
        HelpDialog(self.logger, self).exec()

    def add_game(self) -> None:
        dlg = AddGameDialog(self)
        if dlg.exec():
            game = dlg.game()
            self.store.add_game(game)
            self.logger.info("Added game: %s (%s), executable: %s", game.name, game.path, game.executable)
            self.refresh()

    def enable_selected(self) -> None:
        game = self._selected_game()
        ra = self.store.retroarch_path
        if game is None:
            return
        if ra is None:
            QMessageBox.warning(self, "RetroArch not configured", "Choose the RetroArch folder first.")
            return
        if not self.store.prepared:
            QMessageBox.warning(
                self,
                "RetroArch not prepared",
                "Use “Prepare / Backup RetroArch” before enabling a game.",
            )
            return

        try:
            if self.store.active_game_id:
                cleanup_entries(self.store.managed_entries)
                self.store.managed_entries = []
                self.store.active_game_id = ""

            plan = build_plan(game, ra)
            elevated_count = sum(1 for x in plan if x.requires_elevation)

            if elevated_count:
                answer = QMessageBox.question(
                    self,
                    "Administrator permission required",
                    f"{elevated_count} file link(s) cannot use hardlinks because the game and "
                    "RetroArch are on different Windows volumes.\n\n"
                    "Windows will ask for administrator permission once to create the required "
                    "symbolic links. Continue?",
                )
                if answer != QMessageBox.StandardButton.Yes:
                    return

            created = apply_plan(plan)
            self.store.managed_entries = created
            self.store.active_game_id = game.id
            self.logger.info(
                "Enabled game: %s. Managed entries: %d",
                game.name,
                len(created),
            )
        except Exception as exc:
            self.logger.exception("Could not enable game")
            QMessageBox.critical(self, "Could not enable game", str(exc))
            return

        self.refresh()

    def disable_active(self) -> None:
        try:
            cleanup_entries(self.store.managed_entries)
        except LinkError as exc:
            self.logger.exception("Cleanup failed")
            QMessageBox.critical(self, "Cleanup failed", str(exc))
            return

        self.store.managed_entries = []
        self.store.active_game_id = ""
        self.logger.info("Active game disabled")
        self.refresh()

    def start_game(self) -> None:
        active_game = self.store.game_by_id(self.store.active_game_id)
        if active_game is None:
            return

        try:
            launch_retroarch_via_steam()
        except SteamLaunchError as exc:
            self.logger.exception("Could not launch RetroArch through Steam")
            QMessageBox.critical(self, "Could not start game", str(exc))
            return

        self.logger.info("Requested Steam launch for active game: %s", active_game.name)
        self.statusBar().showMessage(f"Starting {active_game.name} through Steam…", 5000)

    def delete_selected(self) -> None:
        game = self._selected_game()
        if game is None:
            return

        if game.id == self.store.active_game_id:
            QMessageBox.warning(self, "Active game", "Disable this game before deleting it.")
            return

        answer = QMessageBox.question(
            self,
            "Delete game",
            f"Remove “{game.name}” from the saved games list?\n\n"
            "The actual game files will not be changed.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        self.store.delete_game(game.id)
        self.logger.info("Deleted saved game: %s", game.name)
        self.refresh()
