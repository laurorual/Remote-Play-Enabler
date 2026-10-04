from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .steam_discovery import RetroArchInstall, find_retroarch_installations


class RetroArchSelectionDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Choose Steam RetroArch")
        self.resize(720, 420)

        self._selected_path: Path | None = None
        self._installs: list[RetroArchInstall] = []

        intro = QLabel(
            "Remote Play Enabler will search Steam's standard locations and all "
            "Steam Libraries registered in Steam."
        )
        intro.setWordWrap(True)

        self.status = QLabel()
        self.status.setWordWrap(True)

        self.list_widget = QListWidget()
        self.list_widget.itemDoubleClicked.connect(lambda _: self._accept_detected())
        self.list_widget.itemSelectionChanged.connect(self._update_ok)

        self.scan_btn = QPushButton("Scan Again")
        self.scan_btn.clicked.connect(self.scan)

        self.manual_btn = QPushButton("Choose Manually…")
        self.manual_btn.clicked.connect(self.choose_manually)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok
        )
        self.buttons.accepted.connect(self._accept_detected)
        self.buttons.rejected.connect(self.reject)

        ok = self.buttons.button(QDialogButtonBox.StandardButton.Ok)
        if ok is not None:
            ok.setText("Use Selected")
            ok.setEnabled(False)

        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addWidget(self.status)
        layout.addWidget(self.list_widget, 1)
        layout.addWidget(self.scan_btn)
        layout.addWidget(self.manual_btn)
        layout.addWidget(self.buttons)

        self.scan()

    @property
    def selected_path(self) -> Path | None:
        return self._selected_path

    def _update_ok(self) -> None:
        ok = self.buttons.button(QDialogButtonBox.StandardButton.Ok)
        if ok is not None:
            ok.setEnabled(bool(self.list_widget.selectedItems()))

    def scan(self) -> None:
        self.list_widget.clear()
        self._installs = find_retroarch_installations()

        if not self._installs:
            self.status.setText(
                "<b>No Steam RetroArch installation was found automatically.</b><br>"
                "Use <i>Choose Manually…</i> below to select it yourself."
            )
            return

        count = len(self._installs)
        self.status.setText(
            f"Found <b>{count}</b> Steam RetroArch installation"
            + ("." if count == 1 else "s.")
        )

        for index, install in enumerate(self._installs):
            item = QListWidgetItem(
                f"{install.retroarch_path}\nSteam Library: {install.library_root}"
            )
            item.setData(Qt.ItemDataRole.UserRole, index)
            item.setToolTip(install.source)
            self.list_widget.addItem(item)

        if self.list_widget.count():
            self.list_widget.setCurrentRow(0)

    def _accept_detected(self) -> None:
        selected = self.list_widget.selectedItems()
        if not selected:
            return

        index = int(selected[0].data(Qt.ItemDataRole.UserRole))
        self._selected_path = self._installs[index].retroarch_path
        self.accept()

    def choose_manually(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self,
            "Select the Steam RetroArch folder",
        )
        if not folder:
            return

        path = Path(folder)
        if not path.is_dir():
            QMessageBox.warning(self, "Invalid folder", "The selected folder does not exist.")
            return

        self._selected_path = path
        self.accept()
