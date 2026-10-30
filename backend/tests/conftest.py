"""Test setup: every test run uses a throwaway database, never the real one."""

import os
import tempfile
from pathlib import Path

import pytest

_TMP = Path(tempfile.mkdtemp(prefix="shadowmap-test-"))
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP / 'test.db'}"  # must be set before the app is imported


@pytest.fixture
def tmp_db_url(tmp_path):
    return f"sqlite:///{tmp_path / 'persist.db'}"
