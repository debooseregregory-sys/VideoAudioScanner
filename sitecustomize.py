"""Load application patches automatically when running the source tree with Python."""
try:
    from duplicate_fixes import install_fixes
    install_fixes()

    # Add a clear completion notification without changing the existing scan
    # engine or the main application file.
    import winsound
    from PySide6.QtWidgets import QMessageBox
    import duplicate_finder

    _original_scan_finished = duplicate_finder.DuplicateFinderWindow.scan_finished

    def _scan_finished_with_notification(self, rows):
        _original_scan_finished(self, rows)
        count = len(rows)
        groups = len({getattr(row, "group", None) for row in rows}) if rows else 0
        try:
            winsound.MessageBeep(winsound.MB_ICONINFORMATION)
        except Exception:
            pass
        if count:
            text = (
                "De analyse is volledig klaar.\n\n"
                f"Duplicaat-kandidaten: {count}\n"
                f"Duplicaatgroepen: {groups}\n\n"
                "De resultaten staan nu in de lijst."
            )
        else:
            text = "De analyse is volledig klaar.\n\nEr zijn geen dubbele video's gevonden."
        QMessageBox.information(self, "Analyse voltooid", text)

    duplicate_finder.DuplicateFinderWindow.scan_finished = _scan_finished_with_notification

    # Release QMediaPlayer handles before selected duplicate files are sent to
    # the Windows Recycle Bin. This prevents Windows error 32 after previewing.
    from duplicate_delete_lock_fix import apply as apply_delete_lock_fix
    apply_delete_lock_fix()
except Exception:
    # Never prevent the main scanner from starting because an optional patch failed.
    pass
