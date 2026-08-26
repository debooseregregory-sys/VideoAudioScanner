"""Load safe UI patches automatically when running the source tree with Python."""

try:
    import os
    from pathlib import Path
    import winsound
    from PySide6.QtCore import QUrl, QTimer
    from PySide6.QtWidgets import QMessageBox, QApplication
    import duplicate_finder

    # Install the existing duplicate-engine improvements first.
    from duplicate_fixes import install_fixes
    install_fixes()

    # Keep the preview dialog object, but completely detach its multimedia
    # source when it closes. QMediaPlayer can otherwise keep a Windows file
    # handle alive even after stop().
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

    def _install_delete_wrapper():
        # main.py calls its original imported install_fixes() after
        # sitecustomize, so re-apply our wrapper once the application has
        # finished constructing its main window.
        duplicate_finder.DuplicateFinderWindow.delete_selected = _delete_selected_with_release

    duplicate_finder.DuplicateFinderWindow.delete_selected = _delete_selected_with_release
    QTimer.singleShot(0, _install_delete_wrapper)
    QTimer.singleShot(250, _install_delete_wrapper)

    # Replace the old completion wrapper with one clear notification.
    _original_scan_finished = duplicate_finder.DuplicateFinderWindow.scan_finished

    def _scan_finished_with_notification(self, rows):
        _original_scan_finished(self, rows)
        candidates = list(rows)
        groups = len({getattr(row, "group", None) for row in candidates}) if candidates else 0
        recommended = [row for row in candidates if getattr(row, "recommended_delete", False)]
        bytes_to_reclaim = sum(getattr(row.info, "size", 0) for row in recommended)
        gib = bytes_to_reclaim / (1024 ** 3)

        try:
            # Use an actual audible Windows tone rather than relying only on
            # configurable system notification sounds.
            winsound.Beep(880, 180)
            winsound.Beep(1046, 180)
        except Exception:
            try:
                winsound.MessageBeep(winsound.MB_ICONINFORMATION)
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
    # Optional UI fixes must never prevent VideoAudioScanner from starting.
    pass
