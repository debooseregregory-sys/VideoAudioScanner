"""Optional startup branding for VideoAudioScanner.

The duplicate-group interface lives directly in duplicate_finder.py. This
module only keeps the existing optional branding and does not modify scan,
matching, preview, or recycle-bin behaviour.
"""

try:
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication, QLabel
except Exception:
    QTimer = None
    QApplication = None
    QLabel = None


def _apply_branding():
    if QApplication is None or QLabel is None:
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
    QTimer.singleShot(0, _apply_branding)
    QTimer.singleShot(300, _apply_branding)
