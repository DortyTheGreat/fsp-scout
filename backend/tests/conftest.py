import os
import sys
import tempfile
from pathlib import Path

import pytest

_tmp = Path(tempfile.mkdtemp()) / "test.db"
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_tmp}")
os.environ["LLM_PROVIDER"] = "none"
os.environ["DEMO_MODE"] = "true"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "fsp-mock"))

from fastapi.testclient import TestClient  # noqa: E402

from app.core.db import Base, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    Base.metadata.drop_all(engine)
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def fsp_mock():
    import main as fsp_main  # fsp-mock/main.py

    from app.services.fsp.client import FspClient, set_fsp_client
    mock_client = TestClient(fsp_main.app, base_url="http://localhost:8001")
    set_fsp_client(FspClient(http=mock_client))
    yield mock_client
    set_fsp_client(None)
