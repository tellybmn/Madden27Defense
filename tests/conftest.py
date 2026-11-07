"""Hard guarantee: no live network during tests."""
import socket

import pytest


@pytest.fixture(autouse=True)
def _block_network(monkeypatch):
    def guard(self, *a, **k):
        raise RuntimeError("network access attempted during offline tests")
    monkeypatch.setattr(socket.socket, "connect", guard)
    monkeypatch.setattr(socket.socket, "connect_ex", guard)
    monkeypatch.setattr(socket, "getaddrinfo", guard)
