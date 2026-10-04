from __future__ import annotations

import logging
import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .steam import SteamLaunchError, install_retroarch_via_steam


class HelpDialog(QDialog):
    def __init__(self, logger: logging.Logger, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.logger = logger
        self.setWindowTitle("How To — Remote Play Enabler")
        self.resize(680, 480)

        title = QLabel("<h2>How to use Remote Play Enabler</h2>")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.pages = QStackedWidget()
        self.pages.addWidget(self._requirements_page())
        self.pages.addWidget(self._setup_page())
        self.pages.addWidget(self._play_page())

        self.page_label = QLabel()
        self.page_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.back_btn = QPushButton("← Back")
        self.next_btn = QPushButton("Next →")
        close_btn = QPushButton("Close")
        install_btn = QPushButton("Install RetroArch on Steam")
        install_btn.setToolTip("Open Steam and start installation of RetroArch (AppID 1118310)")

        self.back_btn.clicked.connect(self._back)
        self.next_btn.clicked.connect(self._next)
        close_btn.clicked.connect(self.accept)
        install_btn.clicked.connect(self._install_retroarch)

        nav = QHBoxLayout()
        nav.addWidget(self.back_btn)
        nav.addWidget(self.next_btn)
        nav.addStretch(1)
        nav.addWidget(install_btn)
        nav.addWidget(close_btn)

        layout = QVBoxLayout(self)
        layout.addWidget(title)
        layout.addWidget(self.pages, 1)
        layout.addWidget(self.page_label)
        layout.addLayout(nav)

        self.pages.currentChanged.connect(self._refresh_nav)
        self._refresh_nav()

    @staticmethod
    def _page(html: str) -> QWidget:
        widget = QWidget()
        label = QLabel(html)
        label.setWordWrap(True)
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        layout = QVBoxLayout(widget)
        layout.setContentsMargins(18, 10, 18, 10)
        layout.addWidget(label)
        layout.addStretch(1)
        return widget

    def _requirements_page(self) -> QWidget:
        linux_note = ""
        if sys.platform.startswith("linux"):
            linux_note = (
                "<p><b>Linux requirement:</b> RetroArch must be configured to run through "
                "<b>Proton</b> in Steam. Open RetroArch's <i>Properties → Compatibility</i>, "
                "enable <i>Force the use of a specific Steam Play compatibility tool</i>, and "
                "select Proton (Proton Experimental is a good default).</p>"
            )
        else:
            linux_note = (
                "<p><b>If you later use the app on Linux:</b> RetroArch must be configured "
                "to run through Proton in Steam.</p>"
            )

        return self._page(
            "<h3>1. Requirements</h3>"
            "<p>Remote Play Enabler requires <b>RetroArch installed through Steam</b>. "
            "The Steam version is used as the Remote Play Together bridge; a standalone "
            "RetroArch installation will not work for this purpose.</p>"
            + linux_note
            + "<p>You can use the <b>Install RetroArch on Steam</b> button below to ask "
            "Steam to start the installation.</p>"
            "<p><b>Tip:</b> Keep Steam running while configuring and launching games.</p>"
        )

    def _setup_page(self) -> QWidget:
        return self._page(
            "<h3>2. First-time setup</h3>"
            "<p><b>1.</b> Click <b>Choose RetroArch Folder…</b> and select the Steam RetroArch "
            "installation folder. The safest way to find it is Steam → RetroArch → Manage → "
            "Browse local files.</p>"
            "<p><b>2.</b> Click <b>Prepare / Backup RetroArch</b>. The app moves RetroArch's "
            "original files to a backup folder next to the installation instead of deleting them.</p>"
            "<p><b>3.</b> Click <b>Add Game…</b>, choose the game's folder, review the automatically "
            "detected name, and select its executable. Use <b>Other…</b> if the executable is in "
            "a subfolder.</p>"
            "<p><b>4.</b> Select the game in the list and click <b>Enable</b>. The app then creates "
            "the links needed for Steam to see that game as RetroArch.</p>"
            "<p>On Windows, the app prefers hardlinks and directory junctions. If a symbolic link "
            "is required and Windows needs elevation, you will receive a single UAC prompt.</p>"
        )

    def _play_page(self) -> QWidget:
        return self._page(
            "<h3>3. Playing and restoring RetroArch</h3>"
            "<p>After enabling a game, click <b>Start Game</b>. The app asks <b>Steam</b> to launch "
            "RetroArch (AppID 1118310); it does not run the executable from the RetroArch folder "
            "directly. You can then use Steam's Remote Play Together controls as usual.</p>"
            "<p>To switch games, select another saved game and click <b>Enable</b>. The links from "
            "the previous game are cleaned up first.</p>"
            "<p>When you want to use normal RetroArch again, click <b>Restore RetroArch</b>. "
            "The active game is disabled, the app-managed links are removed, and the original "
            "RetroArch files are moved back from the backup.</p>"
            "<p>To use Remote Play Enabler again afterward, simply run <b>Prepare / Backup "
            "RetroArch</b> again and enable a game.</p>"
        )

    def _refresh_nav(self) -> None:
        index = self.pages.currentIndex()
        count = self.pages.count()
        self.page_label.setText(f"Page {index + 1} of {count}")
        self.back_btn.setEnabled(index > 0)
        self.next_btn.setEnabled(index < count - 1)

    def _back(self) -> None:
        self.pages.setCurrentIndex(max(0, self.pages.currentIndex() - 1))

    def _next(self) -> None:
        self.pages.setCurrentIndex(min(self.pages.count() - 1, self.pages.currentIndex() + 1))

    def _install_retroarch(self) -> None:
        try:
            install_retroarch_via_steam()
        except SteamLaunchError as exc:
            self.logger.exception("Could not open RetroArch installation through Steam")
            QMessageBox.critical(self, "Could not open Steam", str(exc))
            return

        self.logger.info("Requested RetroArch installation through Steam")
        QMessageBox.information(
            self,
            "Steam opened",
            "Steam was asked to start the RetroArch installation.",
        )
