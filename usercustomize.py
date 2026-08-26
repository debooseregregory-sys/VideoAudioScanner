"""Startup enhancements for VideoAudioScanner.

This module leaves scanning, matching and deletion logic untouched. It only
adds a visible group-view action to the already existing duplicate finder.
"""

try:
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import (
        QApplication, QDialog, QFrame, QHBoxLayout, QLabel, QPushButton,
        QScrollArea, QVBoxLayout, QWidget,
    )
except Exception:
    QTimer = None
    QApplication = None


def _install_group_view():
    try:
        from duplicate_finder import DuplicateFinderWindow, VideoPreviewDialog
    except Exception:
        return

    if getattr(DuplicateFinderWindow, "_kid_acid_group_view_installed", False):
        return

    original_build_ui = DuplicateFinderWindow._build_ui

    def build_ui_with_group_view(self):
        original_build_ui(self)

        try:
            root = self.centralWidget()
            root_layout = root.layout()
            if root_layout is None:
                return

            actions_layout = root_layout.itemAt(root_layout.count() - 1).layout()
            if actions_layout is None:
                return

            button = QPushButton("▦  GROEPSWEERGAVE — DUPLICATEN VERGELIJKEN")
            button.setObjectName("groupViewButton")
            button.setMinimumHeight(42)
            button.setStyleSheet("""
                QPushButton#groupViewButton {
                    background: #315f9e;
                    border: 1px solid #5686c4;
                    border-radius: 7px;
                    padding: 9px 18px;
                    font-size: 13px;
                    font-weight: 700;
                    color: white;
                }
                QPushButton#groupViewButton:hover { background: #3b70b8; }
            """)
            button.setToolTip("Bekijk gevonden duplicaten per groep met de beste versie bovenaan.")
            button.clicked.connect(lambda: _show_groups(self))
            actions_layout.insertWidget(0, button)
            self._kid_acid_group_button = button
        except Exception:
            return

    DuplicateFinderWindow._build_ui = build_ui_with_group_view
    DuplicateFinderWindow._kid_acid_group_view_installed = True


def _show_groups(window):
    rows = list(getattr(window, "rows", []) or [])
    dialog = QDialog(window)
    dialog.setWindowTitle("VideoAudioScanner — Duplicaatgroepen")
    dialog.resize(1250, 780)

    outer = QVBoxLayout(dialog)
    title = QLabel("DUPLICAATGROEPEN")
    title.setStyleSheet("font-size: 26px; font-weight: 800; color: white;")
    outer.addWidget(title)

    if not rows:
        message = QLabel(
            "Er zijn nog geen duplicaten om te tonen.\n\n"
            "Kies eerst een map en start een duplicatenscan."
        )
        message.setStyleSheet("font-size: 16px; color: #aeb5c0; padding: 40px;")
        outer.addWidget(message)
        close = QPushButton("Sluiten")
        close.clicked.connect(dialog.close)
        outer.addWidget(close)
        dialog.exec()
        return

    groups = {}
    for row in rows:
        groups.setdefault(row.group, []).append(row)

    summary = QLabel(
        f"{len(groups)} duplicaatgroepen • {len(rows)} bestanden • "
        f"{sum(r.info.size for r in rows if r.recommended_delete) / (1024 ** 3):.2f} GB aanbevolen ruimtewinst"
    )
    summary.setStyleSheet("color: #9ca5b3; font-size: 14px; padding-bottom: 8px;")
    outer.addWidget(summary)

    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    content = QWidget()
    content_layout = QVBoxLayout(content)
    content_layout.setSpacing(14)

    for group_no in sorted(groups):
        members = sorted(groups[group_no], key=lambda r: (not r.recommended_delete, -r.info.size))
        card = QFrame()
        card.setStyleSheet("QFrame { background: #1b1f25; border: 1px solid #343a44; border-radius: 10px; }")
        card_layout = QVBoxLayout(card)

        exact = any(r.info.video_hash for r in members)
        header = QHBoxLayout()
        group_label = QLabel(f"DUPLICAATGROEP {group_no:03d}")
        group_label.setStyleSheet("font-size: 17px; font-weight: 800; color: white;")
        kind = QLabel("◆ EXACT DUPLICAAT" if exact else "◈ VERMOEDELIJKE MATCH")
        kind.setStyleSheet("font-weight: 700; color: #8eb7ef;")
        header.addWidget(group_label)
        header.addStretch(1)
        header.addWidget(kind)
        card_layout.addLayout(header)

        for row in members:
            info = row.info
            item = QHBoxLayout()
            status = QLabel("★ BEWAREN" if not row.recommended_delete else "● VERWIJDEREN")
            status.setMinimumWidth(135)
            status.setStyleSheet(
                "font-weight: 800; color: #8fd19e;" if not row.recommended_delete
                else "font-weight: 800; color: #e58b91;"
            )
            details = QLabel(
                f"{info.name}\n"
                f"{info.resolution}  •  {info.bitrate_text}  •  {info.duration_text}  •  "
                f"{info.video_codec}/{info.audio_codec}  •  {info.fps} FPS  •  {info.size / (1024 ** 3):.2f} GB\n"
                f"Match: {row.similarity}%  —  {row.reason}"
            )
            details.setWordWrap(True)
            details.setStyleSheet("color: #d5dae1; padding: 5px;")
            view = QPushButton("▶ Bekijk")
            view.clicked.connect(lambda checked=False, path=info.path: _preview(window, path))
            item.addWidget(status)
            item.addWidget(details, 1)
            item.addWidget(view)
            card_layout.addLayout(item)

        content_layout.addWidget(card)

    content_layout.addStretch(1)
    scroll.setWidget(content)
    outer.addWidget(scroll, 1)

    close = QPushButton("Sluiten")
    close.clicked.connect(dialog.close)
    outer.addWidget(close)

    dialog.setStyleSheet("""
        QDialog, QWidget { background: #101216; color: #e8eaed; }
        QPushButton { background: #292e36; border: 1px solid #3c424c; border-radius: 6px; padding: 8px 13px; }
        QPushButton:hover { background: #353b45; }
    """)
    dialog.exec()


def _preview(window, path):
    try:
        from duplicate_finder import VideoPreviewDialog
        preview = VideoPreviewDialog(path, window)
        if not hasattr(window, "_kid_acid_group_previews"):
            window._kid_acid_group_previews = []
        window._kid_acid_group_previews.append(preview)
        preview.show()
    except Exception:
        pass


def _apply_branding():
    if QApplication is None:
        return
    app = QApplication.instance()
    if app is None:
        return
    for window in app.topLevelWidgets():
        credit = window.findChild(QLabel, "credit")
        if credit is not None:
            credit.setText("MADE BY KID ACID\nVIDEOAUDIOSCANNER")
            credit.adjustSize()


if QTimer is not None:
    _install_group_view()
    QTimer.singleShot(0, _apply_branding)
    QTimer.singleShot(300, _apply_branding)
