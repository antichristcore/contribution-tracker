"""Кладёт корень репозитория на sys.path, чтобы тесты импортировали пакет
как `backend.app.*` независимо от того, откуда запущен pytest.

Тот же приём, что и в scripts/*.py — без него `pytest` (в отличие от
`python -m pytest`) не видит корень проекта.
"""

import sys
from pathlib import Path

ROOT = str(Path(__file__).resolve().parent)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
