"""Release internal video preview handles before moving files to the Windows Recycle Bin."""

from pathlib import Path

from PySide6.QtCore import QUrl

import duplicate_finder as df


_original_install_fixes = df.install_fixes


def _release_previews(window, paths):
    wanted = {str(Path(path).resolve()).casefold() for path in paths}
    remaining = []
    for preview in list(getattr(window, "preview_windows", [])):
        try:
            source = getattr(preview, "_preview_path", "")
            if source and str(Path(source).resolve()).casefold() in wanted:
                player = getattr(preview, "player", None)
                if player is not None:
                    player.stop()
                    player.setSource(QUrl())
                    player.setVideoOutput(None)
                    player.setAudioOutput(None)
                preview.close()
                preview.deleteLater()
            else:
                remaining.append(preview)
        except Exception:
            # A preview that cannot be queried must not prevent deletion of other files.
            try:
                preview.close()
            except Exception:
                pass
    window.preview_windows = remaining


def _delete_selected_with_release(self):
    paths = []
    for row in range(self.table.rowCount()):
        item = self.table.item(row, 0)
        if item and item.checkState() == df.Qt.CheckState.Checked:
            path = item.data(df.Qt.ItemDataRole.UserRole)
            if path and Path(path).is_file():
                paths.append(str(path))

    if not paths:
        return self._original_delete_selected()

    # Close only previews belonging to files that are actually being deleted.
    # This releases QMediaPlayer/FFmpeg file handles before SHFileOperation runs.
    _release_previews(self, paths)
    return self._original_delete_selected()


def apply():
    """Wrap duplicate_fixes installation so the lock-safe delete stays installed."""
    if getattr(df, "_lock_fix_installed", False):
        return

    def wrapped_install_fixes():
        _original_install_fixes()
        current = df.DuplicateFinderWindow.delete_selected
        if current is not _delete_selected_with_release:
            _delete_selected_with_release._original_delete_selected = current
            df.DuplicateFinderWindow.delete_selected = _delete_selected_with_release
            # Keep a direct reference for the wrapper; it is also useful if install_fixes runs again.
            _delete_selected_with_release._original_delete_selected = current

    df.install_fixes = wrapped_install_fixes
    wrapped_install_fixes()
    df._lock_fix_installed = True
