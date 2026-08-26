"""Load safe UI patches automatically when running the source tree with Python."""

try:
    import os
    from pathlib import Path
    import winsound
    from PySide6.QtCore import QUrl, QTimer, Qt
    from PySide6.QtWidgets import QMessageBox, QApplication, QFrame, QLabel, QHBoxLayout, QVBoxLayout
    import duplicate_finder

    from duplicate_fixes import install_fixes
    install_fixes()

    # --- Reliable preview release before Windows recycle-bin operations ---
    _original_preview_init = duplicate_finder.VideoPreviewDialog.__init__
    _original_preview_close = duplicate_finder.VideoPreviewDialog.closeEvent

    def _preview_init(self, path, parent=None):
        self._vas_preview_path = str(Path(path).resolve())
        _original_preview_init(self, path, parent)

    def _preview_close(self, event):
        try:
            self.player.stop()
            self.player.setSource(QUrl())
            self.player.setVideoOutput(None)
            self.player.setAudioOutput(None)
        except Exception:
            pass
        try:
            _original_preview_close(self, event)
        finally:
            try:
                self.player.deleteLater()
            except Exception:
                pass

    duplicate_finder.VideoPreviewDialog.__init__ = _preview_init
    duplicate_finder.VideoPreviewDialog.closeEvent = _preview_close

    _base_delete_selected = duplicate_finder.DuplicateFinderWindow.delete_selected

    def _delete_selected_with_release(self):
        paths = []
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item and item.checkState() == duplicate_finder.Qt.CheckState.Checked:
                path = item.data(duplicate_finder.Qt.ItemDataRole.UserRole)
                if path and os.path.isfile(path):
                    paths.append(str(Path(path).resolve()))

        wanted = {path.casefold() for path in paths}
        for preview in list(getattr(self, "preview_windows", [])):
            preview_path = str(getattr(preview, "_vas_preview_path", "")).casefold()
            if preview_path and preview_path in wanted:
                try:
                    preview.close()
                except Exception:
                    pass

        try:
            QApplication.processEvents()
        except Exception:
            pass
        return _base_delete_selected(self)

    duplicate_finder.DuplicateFinderWindow.delete_selected = _delete_selected_with_release

    def _install_delete_wrapper():
        duplicate_finder.DuplicateFinderWindow.delete_selected = _delete_selected_with_release

    QTimer.singleShot(0, _install_delete_wrapper)
    QTimer.singleShot(250, _install_delete_wrapper)

    # --- Professional, clearly visible dashboard ---
    _original_build_ui = duplicate_finder.DuplicateFinderWindow._build_ui

    def _professional_build_ui(self):
        _original_build_ui(self)
        root = self.centralWidget()
        layout = root.layout() if root else None
        if layout is None:
            return

        dashboard = QFrame()
        dashboard.setObjectName("duplicateDashboard")
        dash_layout = QHBoxLayout(dashboard)
        dash_layout.setContentsMargins(14, 10, 14, 10)
        dash_layout.setSpacing(10)

        self._vas_group_value = QLabel("0")
        self._vas_files_value = QLabel("0")
        self._vas_recommended_value = QLabel("0")
        self._vas_space_value = QLabel("0 GB")
        for value in (self._vas_group_value, self._vas_files_value, self._vas_recommended_value, self._vas_space_value):
            value.setObjectName("dashValue")
            value.setAlignment(Qt.AlignmentFlag.AlignCenter)

        cards = [
            ("DUPLICAATGROEPEN", self._vas_group_value),
            ("DUBBELE BESTANDEN", self._vas_files_value),
            ("AANBEVOLEN", self._vas_recommended_value),
            ("RUIMTEWINST", self._vas_space_value),
        ]
        for caption, value in cards:
            card = QFrame()
            card.setObjectName("dashCard")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(10, 7, 10, 7)
            label = QLabel(caption)
            label.setObjectName("dashCaption")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            card_layout.addWidget(label)
            card_layout.addWidget(value)
            dash_layout.addWidget(card, 1)

        layout.insertWidget(1, dashboard)
        self.setStyleSheet(self.styleSheet() + """
            QFrame#duplicateDashboard { background: #0d1015; border: 1px solid #3b4350; border-radius: 12px; }
            QFrame#dashCard { background: #191e26; border: 1px solid #303844; border-radius: 9px; }
            QLabel#dashCaption { color: #8f99a8; font-size: 10px; font-weight: 800; letter-spacing: 1px; }
            QLabel#dashValue { color: #ffffff; font-size: 25px; font-weight: 900; padding: 2px; }
        """)

    duplicate_finder.DuplicateFinderWindow._build_ui = _professional_build_ui

    # --- Professional duplicate group comparison ---
    from professional_groups import install as install_professional_groups
    install_professional_groups(duplicate_finder.DuplicateFinderWindow)

    # --- Completion popup + audible notification ---
    _original_scan_finished = duplicate_finder.DuplicateFinderWindow.scan_finished

    def _scan_finished_with_notification(self, rows):
        _original_scan_finished(self, rows)
        candidates = list(rows)
        groups = len({getattr(row, "group", None) for row in candidates}) if candidates else 0
        recommended = [row for row in candidates if getattr(row, "recommended_delete", False)]
        bytes_to_reclaim = sum(getattr(row.info, "size", 0) for row in recommended)
        gib = bytes_to_reclaim / (1024 ** 3)

        try:
            winsound.Beep(880, 180)
            winsound.Beep(1046, 180)
        except Exception:
            try:
                winsound.MessageBeep(winsound.MB_ICONINFORMATION)
            except Exception:
                pass

        try:
            self._vas_group_value.setText(str(groups))
            self._vas_files_value.setText(str(len(candidates)))
            self._vas_recommended_value.setText(str(len(recommended)))
            self._vas_space_value.setText(f"{gib:.2f} GB")
        except Exception:
            pass

        if candidates:
            text = (
                "De analyse van de dubbele video's is volledig klaar.\n\n"
                f"Duplicaatgroepen: {groups}\n"
                f"Dubbele bestanden: {len(candidates)}\n"
                f"Automatisch geselecteerd: {len(recommended)}\n"
                f"Mogelijke ruimtewinst: {gib:.2f} GB\n\n"
                "De beste versies zijn niet geselecteerd.\n"
                "Exacte duplicaten en vermoedelijke duplicaten staan in de lijst."
            )
        else:
            text = "De analyse van de dubbele video's is volledig klaar.\n\nGeen dubbele video's gevonden."
        QMessageBox.information(self, "🎬 Analyse voltooid", text)

    duplicate_finder.DuplicateFinderWindow.scan_finished = _scan_finished_with_notification

except Exception:
    pass
