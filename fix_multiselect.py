from __future__ import annotations

from pathlib import Path

TARGET = Path(__file__).resolve().parent / "video_library.py"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise RuntimeError(f"Kan onderdeel niet vinden: {label}")
    return text.replace(old, new, 1)


def main():
    if not TARGET.exists():
        raise SystemExit(f"Bestand niet gevonden: {TARGET}")

    text = TARGET.read_text(encoding="utf-8")
    backup = TARGET.with_name("video_library.py.before_multiselect")
    backup.write_text(text, encoding="utf-8")

    # ctypes is required by the existing Windows recycle-bin implementation.
    if "import ctypes\n" not in text:
        text = replace_once(
            text,
            "import hashlib\n",
            "import ctypes\nimport hashlib\n",
            "ctypes import",
        )

    # Keep the existing single selected_path for details, and add a set/list for bulk selection.
    text = replace_once(
        text,
        '        self.selected_path = ""\n',
        '        self.selected_path = ""\n        self.selected_paths: list[str] = []\n        self.selection_anchor = ""\n',
        "selection state",
    )

    # VideoCard receives the complete mouse event so Ctrl/Shift selection can be handled by the window.
    text = replace_once(
        text,
        '        self.select_callback = select_callback\n        self.open_callback = open_callback\n',
        '        self.select_callback = select_callback\n        self.open_callback = open_callback\n',
        "card callbacks",
    )

    old_press = '''    def mousePressEvent(self, event):\n        if event.button() == Qt.MouseButton.LeftButton:\n            self.select_callback(self.item.path)\n        super().mousePressEvent(event)\n'''
    new_press = '''    def mousePressEvent(self, event):\n        if event.button() == Qt.MouseButton.LeftButton:\n            self.select_callback(self.item.path, event.modifiers())\n        super().mousePressEvent(event)\n'''
    if old_press in text:
        text = replace_once(text, old_press, new_press, "VideoCard mousePressEvent")
    else:
        raise RuntimeError("Kan VideoCard.mousePressEvent niet vinden")

    # Add bulk delete button next to the scan button.
    old_controls = '''        controls.addWidget(self.scan_button)\n        self.search = QLineEdit()\n'''
    new_controls = '''        controls.addWidget(self.scan_button)\n        self.delete_button = QPushButton("🗑  Naar Prullenbak")\n        self.delete_button.setEnabled(False)\n        self.delete_button.clicked.connect(self.delete_selected)\n        controls.addWidget(self.delete_button)\n        self.selection_label = QLabel("0 geselecteerd")\n        self.selection_label.setObjectName("librarySubtitle")\n        controls.addWidget(self.selection_label)\n        self.search = QLineEdit()\n'''
    text = replace_once(text, old_controls, new_controls, "bulk delete controls")

    # Replace the old single-file delete method with a multi-selection version.
    start = text.find("    def delete_selected(self):\n")
    if start < 0:
        raise RuntimeError("delete_selected() niet gevonden")
    end = text.find("    def select_video(", start)
    if end < 0:
        raise RuntimeError("select_video() niet gevonden na delete_selected()")

    delete_method = '''    def delete_selected(self):\n        paths = [p for p in self.selected_paths if os.path.isfile(p)]\n        if not paths and self.selected_path and os.path.isfile(self.selected_path):\n            paths = [self.selected_path]\n\n        if not paths:\n            QMessageBox.warning(\n                self,\n                "Video verwijderen",\n                "Selecteer eerst één of meer geldige video's.",\n            )\n            return\n\n        names = [Path(p).name for p in paths]\n        if len(names) == 1:\n            question = (\n                "Weet je zeker dat je deze video naar de Windows Prullenbak wilt "\n                f"verplaatsen?\\n\\n{names[0]}"\n            )\n        else:\n            preview = "\\n".join(f"• {name}" for name in names[:12])\n            if len(names) > 12:\n                preview += f"\\n• … en nog {len(names) - 12} video's"\n            question = (\n                f"Weet je zeker dat je {len(names):,} video's naar de Windows "\n                f"Prullenbak wilt verplaatsen?\\n\\n{preview}"\n            )\n\n        answer = QMessageBox.question(\n            self,\n            "Naar Prullenbak",\n            question,\n            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,\n            QMessageBox.StandardButton.No,\n        )\n        if answer != QMessageBox.StandardButton.Yes:\n            return\n\n        failed = []\n        moved = []\n\n        class SHFILEOPSTRUCT(ctypes.Structure):\n            _fields_ = [\n                ("hwnd", ctypes.c_void_p),\n                ("wFunc", ctypes.c_uint),\n                ("pFrom", ctypes.c_wchar_p),\n                ("pTo", ctypes.c_wchar_p),\n                ("fFlags", ctypes.c_ushort),\n                ("fAnyOperationsAborted", ctypes.c_bool),\n                ("hNameMappings", ctypes.c_void_p),\n                ("lpszProgressTitle", ctypes.c_wchar_p),\n            ]\n\n        FO_DELETE = 0x0003\n        FOF_ALLOWUNDO = 0x0040\n        FOF_NOCONFIRMATION = 0x0010\n        FOF_NOERRORUI = 0x0400\n        FOF_SILENT = 0x0004\n\n        for path in paths:\n            try:\n                op = SHFILEOPSTRUCT()\n                op.wFunc = FO_DELETE\n                op.pFrom = path + "\\0\\0"\n                op.fFlags = FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_NOERRORUI | FOF_SILENT\n                result = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))\n                if result != 0 or op.fAnyOperationsAborted:\n                    raise OSError(f"Windows foutcode: {result}")\n                moved.append(path)\n            except Exception:\n                failed.append(path)\n\n        for path in moved:\n            try:\n                self.db.delete_video(path)\n            except Exception:\n                pass\n\n        moved_set = set(moved)\n        self.items = [item for item in self.items if item.path not in moved_set]\n        self.selected_paths = [p for p in self.selected_paths if p not in moved_set]\n        self.selected_path = self.selected_paths[-1] if self.selected_paths else ""\n        self.selection_anchor = self.selected_path\n\n        self.clear_details()\n        self.refresh_cards()\n        self.update_selection_ui()\n\n        total = sum(item.size for item in self.items)\n        self.stats.setText(f"{len(self.items):,} video's  •  {format_size(total)}")\n\n        if failed:\n            QMessageBox.warning(\n                self,\n                "Verwijderen gedeeltelijk gelukt",\n                f"{len(moved):,} video's naar de Prullenbak verplaatst.\\n"\n                f"{len(failed):,} konden niet worden verplaatst.",\n            )\n            self.status.setText(\n                f"🗑 {len(moved):,} naar Prullenbak • {len(failed):,} mislukt"\n            )\n        else:\n            self.status.setText(f"🗑 {len(moved):,} video{'s' if len(moved) != 1 else ''} naar Prullenbak")\n\n    def update_selection_ui(self):\n        count = len(self.selected_paths)\n        if hasattr(self, "selection_label"):\n            self.selection_label.setText(f"{count:,} geselecteerd")\n        if hasattr(self, "delete_button"):\n            self.delete_button.setEnabled(count > 0)\n        for path, card in self.card_by_path.items():\n            card.set_selected(path in self.selected_paths)\n\n'''
    text = text[:start] + delete_method + text[end:]

    # Replace select_video with modifier-aware selection and keep detail display on the last selected item.
    start = text.find("    def select_video(")
    if start < 0:
        raise RuntimeError("select_video() niet gevonden")
    end = text.find("    def show_details(", start)
    if end < 0:
        raise RuntimeError("show_details() niet gevonden na select_video()")

    select_method = '''    def select_video(self, path, modifiers=Qt.KeyboardModifier.NoModifier):\n        if not os.path.isfile(path):\n            return\n\n        visible = [item.path for item in self._visible_items()]\n        if path not in visible:\n            visible.append(path)\n\n        if modifiers & Qt.KeyboardModifier.ShiftModifier and self.selection_anchor in visible:\n            a = visible.index(self.selection_anchor)\n            b = visible.index(path)\n            lo, hi = sorted((a, b))\n            self.selected_paths = visible[lo:hi + 1]\n        elif modifiers & Qt.KeyboardModifier.ControlModifier:\n            if path in self.selected_paths:\n                self.selected_paths.remove(path)\n            else:\n                self.selected_paths.append(path)\n            self.selection_anchor = path\n        else:\n            self.selected_paths = [path]\n            self.selection_anchor = path\n\n        self.selected_path = path if path in self.selected_paths else (self.selected_paths[-1] if self.selected_paths else "")\n        self.update_selection_ui()\n        if self.selected_path:\n            self.show_details(self.selected_path)\n\n'''
    text = text[:start] + select_method + text[end:]

    # If a refresh destroys selected cards, preserve only paths still in the current item list.
    old_refresh = '''        items = self._visible_items()\n        for index, item in enumerate(items):\n'''
    new_refresh = '''        items = self._visible_items()\n        valid = {item.path for item in items}\n        self.selected_paths = [p for p in self.selected_paths if p in valid]\n        if self.selected_path not in valid:\n            self.selected_path = self.selected_paths[-1] if self.selected_paths else ""\n        for index, item in enumerate(items):\n'''
    text = replace_once(text, old_refresh, new_refresh, "refresh selection preservation")

    # Ensure the UI is synchronized after cards are rebuilt.
    old_end = '''        self.status.setText(f"Weergave: {len(items):,} van {len(self.items):,} video's")\n'''
    new_end = '''        self.status.setText(f"Weergave: {len(items):,} van {len(self.items):,} video's")\n        self.update_selection_ui()\n'''
    text = replace_once(text, old_end, new_end, "refresh selection UI")

    # Initialize selection UI after construction if the matching widgets exist.
    old_build_end = '''        self.setCentralWidget(root)\n\n    def _apply_theme(self):\n'''
    new_build_end = '''        self.setCentralWidget(root)\n        self.update_selection_ui()\n\n    def _apply_theme(self):\n'''
    text = replace_once(text, old_build_end, new_build_end, "initial selection UI")

    TARGET.write_text(text, encoding="utf-8")
    print(f"OK: multi-select toegevoegd aan {TARGET}")
    print(f"Backup: {backup}")
    print("Gebruik Ctrl+klik voor meerdere video's en Shift+klik voor een reeks.")


if __name__ == "__main__":
    main()
