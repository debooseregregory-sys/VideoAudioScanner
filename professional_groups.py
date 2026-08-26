from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QVBoxLayout, QWidget,
)


def _label(text: str, object_name: str = "") -> QLabel:
    label = QLabel(text)
    if object_name:
        label.setObjectName(object_name)
    label.setWordWrap(True)
    return label


class DuplicateGroupsDialog(QDialog):
    def __init__(self, owner, rows):
        super().__init__(owner)
        self.owner = owner
        self.setWindowTitle("VideoAudioScanner — Professioneel duplicatenoverzicht")
        self.resize(1450, 850)
        self.setStyleSheet("""
            QDialog { background:#0d1014; color:#edf0f4; }
            QFrame#groupCard { background:#171b21; border:1px solid #343b46; border-radius:14px; }
            QLabel#groupTitle { color:#ffffff; font-size:18px; font-weight:800; }
            QLabel#exact { color:#8bd5a8; font-weight:800; }
            QLabel#keep { color:#8fd0ff; font-weight:800; }
            QLabel#remove { color:#ff9a9a; font-weight:800; }
            QLabel#meta { color:#aeb6c2; font-size:12px; }
            QLabel#score { color:#ffffff; font-size:22px; font-weight:900; }
            QPushButton { background:#292f38; color:#f0f2f5; border:1px solid #424a56; border-radius:7px; padding:8px 13px; }
            QPushButton:hover { background:#373f4a; }
        """)
        outer = QVBoxLayout(self)
        header = QHBoxLayout()
        title = _label("DUPLICATE GROUPS", "groupTitle")
        subtitle = _label(f"{len(rows)} dubbele bestanden • vergelijk de aanbevolen versies", "meta")
        header.addWidget(title)
        header.addStretch(1)
        header.addWidget(subtitle)
        outer.addLayout(header)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        grid = QGridLayout(content)
        grid.setContentsMargins(4, 8, 4, 8)
        grid.setSpacing(14)
        groups = {}
        for row in rows:
            groups.setdefault(row.group, []).append(row)
        for index, (group_no, candidates) in enumerate(sorted(groups.items())):
            card = self._make_group(group_no, candidates)
            grid.addWidget(card, index, 0)
        grid.setRowStretch(len(groups), 1)
        scroll.setWidget(content)
        outer.addWidget(scroll, 1)
        close = QPushButton("Sluiten")
        close.clicked.connect(self.close)
        outer.addWidget(close, 0, Qt.AlignmentFlag.AlignRight)

    def _make_group(self, group_no, candidates):
        card = QFrame()
        card.setObjectName("groupCard")
        layout = QVBoxLayout(card)
        top = QHBoxLayout()
        exact = all(c.info.video_hash for c in candidates) and len({c.info.video_hash for c in candidates}) == 1
        top.addWidget(_label(f"DUPLICAATGROEP {group_no:03d}", "groupTitle"))
        top.addStretch(1)
        top.addWidget(_label("◆ EXACT DUPLICAAT" if exact else "◈ VERMOEDELIJKE MATCH", "exact" if exact else "meta"))
        layout.addLayout(top)
        columns = QHBoxLayout()
        for candidate in candidates:
            columns.addWidget(self._make_candidate(candidate), 1)
        layout.addLayout(columns)
        return card

    def _make_candidate(self, candidate):
        box = QFrame()
        layout = QVBoxLayout(box)
        keep = not candidate.recommended_delete
        status = "★ BEWAREN" if keep else "● VERWIJDEREN"
        status_label = _label(status, "keep" if keep else "remove")
        layout.addWidget(status_label)
        name = _label(candidate.info.name, "groupTitle")
        name.setMaximumHeight(52)
        layout.addWidget(name)
        score = 100 if keep and candidate.similarity >= 100 else max(0, min(100, candidate.similarity))
        layout.addWidget(_label(f"{score}/100", "score"))
        meta = (
            f"Resolutie: {candidate.info.resolution}\n"
            f"Bitrate: {candidate.info.bitrate_text}\n"
            f"Duur: {candidate.info.duration_text}\n"
            f"Video: {candidate.info.video_codec} • Audio: {candidate.info.audio_codec}\n"
            f"FPS: {candidate.info.fps} • Container: {candidate.info.container}\n"
            f"Grootte: {candidate.info.size / (1024**3):.2f} GB\n"
            f"Match: {candidate.similarity}%\n"
            f"Waarom: {candidate.reason}"
        )
        layout.addWidget(_label(meta, "meta"))
        view = QPushButton("▶ Bekijk video")
        view.clicked.connect(lambda _=False, p=candidate.info.path: self.owner.preview_row_for_path(p))
        layout.addWidget(view)
        return box


def install(owner_class):
    original_build = owner_class._build_ui
    def build(self):
        original_build(self)
        button = QPushButton("▦ Groepsweergave")
        button.setToolTip("Bekijk duplicaten per groep met duidelijke BEWAREN/VERWIJDEREN-keuzes")
        button.clicked.connect(self.show_professional_groups)
        # Place beside the existing preview action without touching scanner logic.
        actions = self.centralWidget().layout().itemAt(self.centralWidget().layout().count() - 1)
        if actions and actions.layout():
            actions.layout().insertWidget(1, button)
    owner_class._build_ui = build
    original_scan = owner_class.scan_finished
    def scan(self, rows):
        original_scan(self, rows)
    owner_class.scan_finished = scan
    def show(self):
        if not getattr(self, "rows", None):
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.information(self, "Groepsweergave", "Voer eerst een scan uit.")
            return
        self._groups_dialog = DuplicateGroupsDialog(self, self.rows)
        self._groups_dialog.show()
        self._groups_dialog.raise_()
        self._groups_dialog.activateWindow()
    owner_class.show_professional_groups = show
    def preview_path(self, path):
        for row, candidate in enumerate(self.rows):
            if candidate.info.path == path:
                self.preview_row(row)
                return
    owner_class.preview_row_for_path = preview_path
