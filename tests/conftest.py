"""Gedeelde pytest fixtures."""
import os
import re
import shutil
import sys
import uuid
from pathlib import Path

import pytest

# Voeg project root toe aan sys.path zodat imports werken
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


@pytest.fixture
def workspace_tmp_path(request) -> Path:
    repo_root = Path(__file__).resolve().parents[1]
    root = repo_root / ".t"
    test_name = re.sub(r"[^A-Za-z0-9_.-]+", "-", request.node.name).strip("-") or "test"
    path = root / f"{test_name[:12]}-{uuid.uuid4().hex[:6]}"
    path.mkdir(parents=True, exist_ok=False)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)
