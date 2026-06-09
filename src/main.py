"""Thin entrypoint shim — keeps ``python3 src/main.py`` working.

The real application logic lives in the ``arduis`` package
(``arduis.main`` + ``arduis.window``). This shim only ensures ``src/`` is on
``sys.path`` and delegates to ``arduis.main.main`` (D-15: main.py stays as the
base entrypoint while the logic moves into the package).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from arduis.main import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
