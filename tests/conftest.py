"""Tests never reach the real internet: online lookups are switched off unless a test fakes them."""
import pytest


@pytest.fixture(autouse=True)
def no_online_lookups(monkeypatch):
    from hush.library import service
    monkeypatch.setattr(service, "pick_providers", lambda settings: (None, None))
