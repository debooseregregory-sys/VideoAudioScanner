from pathlib import Path
import re

FILE = Path('video_library.py')
text = FILE.read_text(encoding='utf-8-sig')

# Selection state
if 'self.selected_paths: set[str]' not in text:
    text = text.replace(
        '        self.selected_path = ""\n',
        '        self.selected_path = ""\n        self.selected_paths: set[str] = set()\n        self.selection_anchor = ""\n',
        1,
    )

# Replace the entire VideoCard class to remove the duplicate mousePressEvent
# and pass keyboard modifiers to the window selection handler.
start = text.index('class VideoCard(QFrame):')
end = text.index('\ndef format_size(', start)
video_card = '''class VideoCard(QFrame):
    def __init__(self, item, select_callback, open_callback, parent=None):
        super().__init__(parent)
        self.item = item
        self.select_callback = select_callback
        self.open_callback = open_callback
        self.setObjectName("libraryCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumSize(250, 250)
        self.setMaximumWidth(360)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(7)

        self.preview = QLabel("Preview laden…")
        self.preview.setObjectName("libraryPreview")
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setFixedHeight(145)
        layout.addWidget(self.preview)

        title = QLabel(item.name)
        title.setObjectName("libraryTitle")
        title.setWordWrap(True)
        title.setToolTip(item.path)
        layout.addWidget(title)

        meta = QLabel(f"{item.extension.upper().lstrip('.')}  •  {format_size(item.size)}")
        meta.setObjectName("libraryMeta")
        layout.addWidget(meta)

        self.status_label = QLabel()
        self.status_label.setObjectName("libraryStatusBadge")
        self.update_status()
        layout.addWidget(self.status_label)

        path_label = QLabel(str(Path(item.path).parent))
        path_label.setObjectName("libraryPath")
        path_label.setWordWrap(True)
        layout.addWidget(path_label, 1)

    def update_status(self):
        parts = []
        if self.item.favorite:
            parts.append("⭐ Favoriet")
        if self.item.watched:
            parts.append("✓ Bekeken")
        else:
            parts.append("○ Onbekeken")
        self.status_label.setText("   ".join(parts))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.select_callback(self.item.path, event.modifiers())
        super().mousePressEvent(event)

    def set_thumbnail(self, pixmap):
        if pixmap and not pixmap.isNull():
            self.preview.setText("")
            self.preview.setPixmap(pixmap.scaled(
                QSize(330, 145), Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation))
        else:
            self.preview.setText("▶")
            self.preview.setStyleSheet("font-size:42px;color:#5d8fd0;background:#0d1015;")

    def set_selected(self, selected):
        self.setProperty("selected", selected)
        self.style().unpolish(self)
        self.style().polish(self)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.open_callback(self.item.path)
        super().mouseDoubleClickEvent(event)

'''
text = text[:start] + video_card + text[end + 1:]

# Preserve multi-selection when cards are refreshed.
text = text.replace(
    '            card.set_selected(item.path == self.selected_path)\n',
    '            card.set_selected(item.path in self.selected_paths)\n',
)

# Replace delete_selected with a single Windows Shell operation for all selected files.
pattern = re.compile(r'    def delete_selected\(self\):\n.*?(?=    def select_video\(self, path\):\n)', re.S)
new_delete = '''    def delete_selected(self):
        paths = [p for p in self.selected_paths if os.path.isfile(p)]
        if not paths:
            if self.selected_path and os.path.isfile(self.selected_path):
                paths = [self.selected_path]
            else:
                QMessageBox.warning(
                    self,
                    "Video verwijderen",
                    "Selecteer eerst één of meerdere geldige video's."
                )
                return

        names = [Path(p).name for p in paths]
        if len(paths) == 1:
            question = (
                "Weet je zeker dat je deze video naar de Windows Prullenbak wilt verplaatsen?"
                f"\\n\\n{names[0]}"
            )
        else:
            preview = "\\n".join(f"• {name}" for name in names[:12])
            if len(names) > 12:
                preview += f"\\n• … en nog {len(names) - 12} video's"
            question = (
                f"Weet je zeker dat je {len(paths):,} video's naar de Windows Prullenbak wilt verplaatsen?"
                f"\\n\\n{preview}"
            )

        answer = QMessageBox.question(
            self,
            "Naar Prullenbak",
            question,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        try:
            class SHFILEOPSTRUCT(ctypes.Structure):
                _fields_ = [
                    ("hwnd", ctypes.c_void_p),
                    ("wFunc", ctypes.c_uint),
                    ("pFrom", ctypes.c_wchar_p),
                    ("pTo", ctypes.c_wchar_p),
                    ("fFlags", ctypes.c_ushort),
                    ("fAnyOperationsAborted", ctypes.c_bool),
                    ("hNameMappings", ctypes.c_void_p),
                    ("lpszProgressTitle", ctypes.c_wchar_p),
                ]

            FO_DELETE = 0x0003
            FOF_ALLOWUNDO = 0x0040
            FOF_NOCONFIRMATION = 0x0010
            FOF_NOERRORUI = 0x0400
            FOF_SILENT = 0x0004

            source_list = "".join(str(Path(p)) + "\\0" for p in paths) + "\\0"
            op = SHFILEOPSTRUCT()
            op.wFunc = FO_DELETE
            op.pFrom = source_list
            op.fFlags = FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_NOERRORUI | FOF_SILENT

            result = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
            if result != 0 or op.fAnyOperationsAborted:
                raise OSError(
                    f"Windows kon de geselecteerde bestanden niet volledig naar de Prullenbak verplaatsen. Code: {result}"
                )

            for path in paths:
                self.db.delete_video(path)

            removed = set(paths)
            self.items = [item for item in self.items if item.path not in removed]
            self.selected_paths.clear()
            self.selected_path = ""
            self.selection_anchor = ""
            self.clear_details()
            self.refresh_cards()
            self.update_selection_ui()

            total = sum(item.size for item in self.items)
            self.stats.setText(f"{len(self.items):,} video's  •  {format_size(total)}")
            self.status.setText(f"🗑 {len(paths):,} video{'s' if len(paths) != 1 else ''} naar Prullenbak")

        except Exception as exc:
            QMessageBox.critical(
                self,
                "Video verwijderen",
                f"De geselecteerde video('s) konden niet naar de Prullenbak worden verplaatst.\\n\\n{exc}"
            )

'''
text, n = pattern.subn(new_delete, text, count=1)
if n != 1:
    raise RuntimeError('delete_selected niet gevonden')

# Replace select_video with Ctrl/Shift-aware selection.
pattern = re.compile(r'    def select_video\(self, path\):\n.*?(?=    def show_details\(self, path\):\n)', re.S)
new_select = '''    def update_selection_ui(self):
        count = len(self.selected_paths)
        self.delete_button.setEnabled(count > 0)
        self.delete_button.setText(
            f"🗑  Naar Prullenbak ({count:,})" if count > 1 else "🗑  Naar Prullenbak"
        )
        for p, card in self.card_by_path.items():
            card.set_selected(p in self.selected_paths)

    def select_video(self, path, modifiers=Qt.KeyboardModifier.NoModifier):
        if not os.path.isfile(path):
            return

        visible_paths = [item.path for item in self._visible_items()[:60]]
        ctrl = bool(modifiers & Qt.KeyboardModifier.ControlModifier)
        shift = bool(modifiers & Qt.KeyboardModifier.ShiftModifier)

        if shift and self.selection_anchor in visible_paths:
            start = visible_paths.index(self.selection_anchor)
            end = visible_paths.index(path)
            lo, hi = sorted((start, end))
            self.selected_paths.update(visible_paths[lo:hi + 1])
        elif ctrl:
            if path in self.selected_paths:
                self.selected_paths.remove(path)
            else:
                self.selected_paths.add(path)
            self.selection_anchor = path
        else:
            self.selected_paths = {path}
            self.selection_anchor = path

        if path in self.selected_paths:
            self.selected_path = path
        elif self.selected_paths:
            self.selected_path = next(iter(self.selected_paths))
        else:
            self.selected_path = ""

        if self.selected_path:
            self.show_details(self.selected_path)
        else:
            self.clear_details()

        self.update_selection_ui()

'''
text, n = pattern.subn(new_select, text, count=1)
if n != 1:
    raise RuntimeError('select_video niet gevonden')

# Clear multi-selection on a fresh scan.
text = text.replace(
    '        self.selected_path = ""\n        self.clear_details()\n        self.refresh_cards()\n',
    '        self.selected_path = ""\n        self.selected_paths.clear()\n        self.selection_anchor = ""\n        self.clear_details()\n        self.refresh_cards()\n',
    1,
)

FILE.write_text(text, encoding='utf-8-sig')
print('OK: multi-select aangepast in video_library.py')
print('Ctrl+klik = meerdere | Shift+klik = reeks | gewone klik = één')
print('Start daarna: python .\\video_suite.py')
