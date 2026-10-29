from datetime import time

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.elexon_client import ElexonClient
from app.main import create_app
from app.store import DataStore
from tests import fake_elexon
from tests.fixtures import make_rows


@pytest.fixture
def settings(tmp_path, monkeypatch):
    monkeypatch.setenv("CACHE_PATH", str(tmp_path / "cache.json"))
    monkeypatch.setenv("AUTO_REFRESH_ON_START", "false")
    get_settings.cache_clear()
    yield get_settings()
    get_settings.cache_clear()


@pytest.fixture
def raw():
    return make_rows()


@pytest.fixture
def store_with_fixture(settings, monkeypatch, raw):
    """Full pipeline: ElexonClient -> fake Elexon endpoints (test fixture) -> DataStore."""
    monkeypatch.setattr(fake_elexon, "_A", raw[0])
    monkeypatch.setattr(fake_elexon, "_F", raw[1])
    client = ElexonClient("http://fake", http=TestClient(fake_elexon.app, base_url="http://fake"),
                          sleep=lambda s: None)
    store = DataStore(settings, client)
    assert store.refresh()
    return store


@pytest.fixture
def api(settings, store_with_fixture):
    return TestClient(create_app(settings, store_with_fixture))
