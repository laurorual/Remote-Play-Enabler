from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .models import Game


OTHER_EXECUTABLE = "Other…"


class AddGameDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Add Game")
        self.resize(590, 195)

        self.path_edit = QLineEdit()
        self.name_edit = QLineEdit()
        self.exe_combo = QComboBox()
        self.exe_combo.setEditable(False)
        self.exe_combo.setPlaceholderText("Select executable")

        # Last real executable selection, used if the user opens "Other…" and cancels.
        self._last_executable = ""
        self.exe_combo.currentTextChanged.connect(self._executable_changed)

        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse_game_folder)

        path_row = QHBoxLayout()
        path_row.setContentsMargins(0, 0, 0, 0)
        path_row.addWidget(self.path_edit, 1)
        path_row.addWidget(browse)

        path_widget = QWidget()
        path_widget.setLayout(path_row)

        form = QFormLayout()
        form.addRow("Game folder:", path_widget)
        form.addRow("Name:", self.name_edit)
        form.addRow("Executable:", self.exe_combo)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Save
        )
        buttons.accepted.connect(self._validate)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addStretch(1)
        layout.addWidget(buttons)

    def _browse_game_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select game folder")
        if not folder:
            return

        self.path_edit.setText(folder)
        game_dir = Path(folder)

        # The folder name is a safe cross-platform automatic default. The field
        # remains editable so the user can correct storefront/version suffixes.
        self.name_edit.setText(game_dir.name)
        self._populate_executables(game_dir)

    def _populate_executables(self, game_dir: Path) -> None:
        executables: list[str] = []
        if game_dir.is_dir():
            if sys.platform == "win32":
                executables = sorted(
                    (x.name for x in game_dir.iterdir() if x.is_file() and x.suffix.lower() == ".exe"),
                    key=str.casefold,
                )
            else:
                # Windows games launched through Proton still use .exe on Linux.
                executables = sorted(
                    (
                        x.name
                        for x in game_dir.iterdir()
                        if x.is_file()
                        and (x.suffix.lower() == ".exe" or bool(x.stat().st_mode & 0o111))
                    ),
                    key=str.casefold,
                )

        self.exe_combo.blockSignals(True)
        self.exe_combo.clear()
        self.exe_combo.addItems(executables)
        self.exe_combo.addItem(OTHER_EXECUTABLE)
        self.exe_combo.blockSignals(False)

        self._last_executable = executables[0] if executables else ""
        if executables:
            self.exe_combo.setCurrentIndex(0)
        else:
            # Leave no item selected so choosing Other… emits a change signal.
            self.exe_combo.setCurrentIndex(-1)

    def _executable_changed(self, text: str) -> None:
        if not text:
            return
        if text == OTHER_EXECUTABLE:
            self._choose_other_executable()
        else:
            self._last_executable = text

    def _choose_other_executable(self) -> None:
        raw_folder = self.path_edit.text().strip()
        game_dir = Path(raw_folder).expanduser() if raw_folder else Path.home()

        if not game_dir.is_dir():
            QMessageBox.warning(self, "Game folder first", "Select the game folder before choosing another executable.")
            self._restore_last_executable()
            return

        file_filter = "Executables (*.exe);;All files (*)"
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Select game executable",
            str(game_dir),
            file_filter,
        )

        if not filename:
            self._restore_last_executable()
            return

        chosen = Path(filename).resolve()
        base = game_dir.resolve()

        try:
            relative = chosen.relative_to(base)
        except ValueError:
            QMessageBox.warning(
                self,
                "Executable outside game folder",
                "Choose an executable inside the selected game folder (it may be inside any subfolder).",
            )
            self._restore_last_executable()
            return

        relative_text = str(relative)

        # Add the custom path immediately before Other… so it remains selectable.
        existing_index = self.exe_combo.findText(relative_text, Qt.MatchFlag.MatchExactly)
        self.exe_combo.blockSignals(True)
        if existing_index < 0:
            other_index = self.exe_combo.findText(OTHER_EXECUTABLE, Qt.MatchFlag.MatchExactly)
            self.exe_combo.insertItem(max(other_index, 0), relative_text)
            existing_index = self.exe_combo.findText(relative_text, Qt.MatchFlag.MatchExactly)
        self.exe_combo.setCurrentIndex(existing_index)
        self.exe_combo.blockSignals(False)
        self._last_executable = relative_text

    def _restore_last_executable(self) -> None:
        self.exe_combo.blockSignals(True)
        if self._last_executable:
            index = self.exe_combo.findText(self._last_executable, Qt.MatchFlag.MatchExactly)
            if index >= 0:
                self.exe_combo.setCurrentIndex(index)
            else:
                self.exe_combo.setCurrentIndex(-1)
        else:
            self.exe_combo.setCurrentIndex(-1)
        self.exe_combo.blockSignals(False)

    def _validate(self) -> None:
        name = self.name_edit.text().strip()
        folder = Path(self.path_edit.text().strip()).expanduser()
        exe = self.exe_combo.currentText().strip()

        if not folder.is_dir():
            QMessageBox.warning(self, "Invalid folder", "The selected game folder does not exist.")
            return
        if not name:
            QMessageBox.warning(self, "Missing name", "Enter a name for the game.")
            return
        if not exe or exe == OTHER_EXECUTABLE or not (folder / exe).is_file():
            QMessageBox.warning(self, "Invalid executable", "Select a valid executable inside the game folder.")
            return

        self.accept()

    def game(self) -> Game:
        return Game.create(
            self.name_edit.text(),
            Path(self.path_edit.text()).expanduser(),
            self.exe_combo.currentText().strip(),
        )
