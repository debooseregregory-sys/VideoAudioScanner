from __future__ import annotations

from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget, QMessageBox


def _label(text: str, object_name: str = "") -> QLabel:
    label = QLabel(text)
    if object_name:
        label.setObjectName(object_name)
    label.setWordWrap(True)
    return label


def _score(info) -> int:
    pixels = getattr(info, "width", 0) * getattr(info, "height", 0)
    bitrate = getattr(info, "bitrate", 0) or 0
    duration = max(getattr(info, "duration", 1.0), 1.0)
    raw = pixels / 2073600 * 55 + min(bitrate / 10000000, 1.0) * 30 + min((getattr(info, "size", 0) / duration) / 500000, 1.0) * 15
    return max(1, min(100, int(round(raw))))


class DuplicateGroupsDialog(QDialog):
    def __init__(self, owner, rows):
        super().__init__(owner)
        self.owner = owner
        self.setWindowTitle("VideoAudioScanner — Duplicaatgroepen")
        self.resize(1500, 880)
        self.setStyleSheet("""
            QDialog { background:#0d1014; color:#edf0f4; }
            QFrame#groupCard { background:#171b21; border:1px solid #3b4450; border-radius:14px; }
            QFrame#videoCard { background:#1d232c; border:1px solid #323b48; border-radius:10px; }
            QLabel#bigTitle { color:#ffffff; font-size:27px; font-weight:900; }
            QLabel#groupTitle { color:#ffffff; font-size:18px; font-weight:800; }
            QLabel#exact { color:#8bd5a8; font-weight:800; }
            QLabel#match { color:#f1cc7a; font-weight:800; }
            QLabel#keep { color:#8fd0ff; font-weight:900; }
            QLabel#remove { color:#ff9999; font-weight:900; }
            QLabel#meta { color:#aeb6c2; font-size:12px; }
            QLabel#score { color:#ffffff; font-size:24px; font-weight:900; }
            QPushButton { background:#29313c; color:#f0f2f5; border:1px solid #424c59; border-radius:7px; padding:9px 14px; }
            QPushButton:hover { background:#394350; }
        """)
        outer = QVBoxLayout(self)
        header = QHBoxLayout()
        header.addWidget(_label("DUPLICAATGROEPEN", "bigTitle"))
        header.addStretch(1)
        groups = {}
        for row in rows:
            groups.setdefault(row.group, []).append(row)
        header.addWidget(_label(f"{len(groups)} groepen  •  {len(rows)} bestanden", "meta"))
        outer.addLayout(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(4, 8, 4, 20)
        content_layout.setSpacing(16)
        for group_no in sorted(groups):
            content_layout.addWidget(self._make_group(group_no, groups[group_no]))
        content_layout.addStretch(1)
        scroll.setWidget(content)
        outer.addWidget(scroll, 1)
        close = QPushButton("Sluiten")
        close.clicked.connect(self.close)
        outer.addWidget(close, 0, Qt.AlignmentFlag.AlignRight)

    def _make_group(self, group_no, candidates):
        group_card = QFrame()
        group_card.setObjectName("groupCard")
        layout = QVBoxLayout(group_card)
        layout.setContentsMargins(18, 16, 18, 16)
        top = QHBoxLayout()
        top.addWidget(_label(f"DUPLICAATGROEP {group_no:03d}", "groupTitle"))
        top.addStretch(1)
        exact = all(bool(c.info.video_hash) for c in candidates) and len({c.info.video_hash for c in candidates}) == 1
        top.addWidget(_label("◆ EXACT DUPLICAAT" if exact else "◈ VERMOEDELIJKE MATCH", "exact" if exact else "match"))
        layout.addLayout(top)
        cards = QHBoxLayout()
        ordered = sorted(candidates, key=lambda c: (c.recommended_delete, -_score(c.info)))
        for candidate in ordered:
            cards.addWidget(self._make_candidate(candidate), 1)
        layout.addLayout(cards)
        return group_card

    def _make_candidate(self, candidate):
        info = candidate.info
        box = QFrame()
        box.setObjectName("videoCard")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(14, 14, 14, 14)
        keep = not candidate.recommended_delete
        layout.addWidget(_label("★ BEWAREN" if keep else "● VERWIJDEREN", "keep" if keep else "remove"))
        name = _label(info.name, "groupTitle")
        name.setMaximumHeight(54)
        layout.addWidget(name)
        layout.addWidget(_label(f"KWALITEIT  {_score(info)}/100", "score"))
        size_gb = info.size / (1024 ** 3)
        meta = (
            f"Resolutie:  {info.resolution or 'onbekend'}\n"
            f"Bitrate:    {info.bitrate_text or 'onbekend'}\n"
            f"Duur:       {info.duration_text or 'onbekend'}\n"
            f"Video:      {info.video_codec or 'onbekend'}\n"
            f"Audio:      {info.audio_codec or 'geen'}\n"
            f"FPS:        {info.fps or 'onbekend'}\n"
            f"Container:  {info.container or 'onbekend'}\n"
            f"Grootte:    {size_gb:.2f} GB\n"
            f"Overeenkomst: {candidate.similarity}%"
        )
        layout.addWidget(_label(meta, "meta"))
        layout.addWidget(_label(candidate.reason, "meta"))
        view = QPushButton("▶  BEKIJK VIDEO")
        view.clicked.connect(lambda _=False, p=info.path: self._preview(p))
        layout.addWidget(view)
        return box

    def _preview(self, path):
        try:
            from duplicate_finder import VideoPreviewDialog
            preview = VideoPreviewDialog(path, self.owner)
            if not hasattr(self.owner, "preview_windows"):
                self.owner.preview_windows = []
            self.owner.preview_windows.append(preview)
            preview.show()
            preview.raise_()
            preview.activateWindow()
        except Exception as exc:
            QMessageBox.warning(self, "Video bekijken", f"Kan de video niet openen:\n\n{exc}")


def _show_groups(self):
    rows = list(getattr(self, "rows", []))
    if not rows:
        QMessageBox.information(self, "Groepsweergave", "Voer eerst een duplicatenscan uit.")
        return
    dialog = DuplicateGroupsDialog(self, rows)
    self._professional_groups_dialog = dialog
    dialog.exec()


def install(owner_class):
    if getattr(owner_class, "_vas_groups_installed", False):
        return
    owner_class.show_professional_groups = _show_groups
    previous_build = owner_class._build_ui

    def build(self):
        previous_build(self)
        # Find the existing action row by looking for the delete button's layout.
        root_layout = self.centralWidget().layout()
        if not root_layout:
            return
        action_layout = None
        for i in range(root_layout.count()):
            item = root_layout.itemAt(i)
            if item and item.layout() and any(
                isinstance(item.layout().itemAt(j).widget(), QPushButton)
                and "Prullenbak" in item.layout().itemAt(j).widget().text()
                for j in range(item.layout().count())
                if item.layout().itemAt(j).widget()
            ):
                action_layout = item.layout()
                break
        if action_layout is None:
            action_layout = QHBoxLayout()
            root_layout.addLayout(action_layout)
        button = QPushButton("▦  GROEPSWEERGAVE")
        button.setObjectName("professionalGroupsButton")
        button.setMinimumHeight(40)
        button.setToolTip("Bekijk alle duplicaatgroepen met BEWAREN/VERWIJDEREN en kwaliteitsinformatie")
        button.clicked.connect(self.show_professional_groups)
        action_layout.insertWidget(1, button)
        self.setStyleSheet(self.styleSheet() + """
            QPushButton#professionalGroupsButton { background:#315f9e; border:1px solid #5b8fd0; font-weight:900; padding:10px 18px; }
            QPushButton#professionalGroupsButton:hover { background:#3d74bd; }
        """)

    owner_class._build_ui = build
    owner_class._vas_groups_installed = True
