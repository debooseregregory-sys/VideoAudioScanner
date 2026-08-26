"""Load application patches automatically when running the source tree with Python."""
try:
    from duplicate_fixes import install_fixes
    install_fixes()
except Exception:
    # Never prevent the main scanner from starting because an optional patch failed.
    pass
