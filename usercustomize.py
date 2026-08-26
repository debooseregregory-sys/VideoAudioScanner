"""Optional startup branding for VideoAudioScanner.

Python loads usercustomize automatically during normal interpreter startup.
This file only styles the existing top-right credit label; it does not alter
scan, duplicate detection, preview, or delete behaviour.
"""

try:
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication, QLabel
except Exception:
    QTimer = None
    QApplication = None
    QLabel = None


def _apply_kid_acid_branding():
    if QApplication is None:
        return
    app = QApplication.instance()
    if app is None:
        return
    for window in app.topLevelWidgets():
        credit = window.findChild(QLabel, "credit")
        if credit is None:
            continue
        credit.setText("MADE BY KID ACID\nVIDEOAUDIOSCANNER")
        credit.setStyleSheet("""
            QLabel#credit {
                color: #f5f7fa;
                font-size: 19px;
                font-weight: 800;
                letter-spacing: 1px;
                padding: 9px 16px;
                background: #11141a;
                border: 1px solid #596171;
                border-radius: 8px;
            }
        """)
        credit.setToolTip("VideoAudioScanner • Made by Kid Acid")
        credit.adjustSize()


if QTimer is not None:
    QTimer.singleShot(0, _apply_kid_acid_branding)
    QTimer.singleShot(300, _apply_kid_acid_branding)
