"""Test setup: every test run uses a throwaway database, never the real one."""

import os
import tempfile
from pathlib import Path

import pytest

_TMP = Path(tempfile.mkdtemp(prefix="shadowmap-test-"))
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP / 'test.db'}"  # must be set before the app is imported
os.environ["DATA_DIR"] = str(_TMP / "data")  # photos, uploads, frames: never the real backend/data folder
os.environ["START_WORKERS"] = "0"  # tests run video jobs directly instead of in the background
os.environ["SENTINEL_TOKEN"] = "test-sentinel-code"
os.environ["SENTINEL_ENFORCE_NIGHT"] = "false"  # security tests switch these rules on explicitly
os.environ["SENTINEL_ENFORCE_MOVING"] = "false"
os.environ["POLICE_TOKEN"] = "test-police-code"
# The general suite makes many requests from one test client; tests/test_rate_limits.py sets the agreed limits itself.
for _name in ("ROUTE_PER_MIN", "HELP_POINT_PER_MIN", "WALK_START_PER_MIN", "BRIEFING_PER_MIN", "REPORT_PER_HOUR", "MAP_PER_MIN",
              "WHERE_AM_I_PER_MIN"):
    os.environ[f"RATE_LIMIT_{_name}"] = "100000"


@pytest.fixture
def tmp_db_url(tmp_path):
    return f"sqlite:///{tmp_path / 'persist.db'}"
