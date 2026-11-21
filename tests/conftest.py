"""Shared fixtures. Tests are offline: no network, no API keys, no LLM calls."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from o2j.spec import load_specs  # noqa: E402

TRAIN = ROOT / "data" / "train"
DOCTYPES = ROOT / "config" / "doctypes"


@pytest.fixture(scope="session")
def specs():
    return load_specs(DOCTYPES)


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """Fail loudly if anything tries to open a socket to a remote host."""
    import socket

    real_connect = socket.socket.connect

    def guarded(self, address, *a, **kw):
        host = address[0] if isinstance(address, tuple) else address
        if isinstance(host, str) and host not in ("127.0.0.1", "localhost", "::1") and not host.startswith("/"):
            raise RuntimeError(f"network access attempted in tests: {address!r}")
        return real_connect(self, address, *a, **kw)

    monkeypatch.setattr(socket.socket, "connect", guarded)
