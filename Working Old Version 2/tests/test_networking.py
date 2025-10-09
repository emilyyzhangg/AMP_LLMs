import pytest
from networking import ping_host, check_port_open

def test_ping_host_success(monkeypatch):
    # Skip actual pinging for test safety
    monkeypatch.setattr("subprocess.run", lambda *a, **kw: type("Mock", (), {"returncode": 0})())
    assert ping_host("localhost") is True

def test_check_port_open(monkeypatch):
    # Simulate port open
    def mock_create_connection(*args, **kwargs):
        class DummySocket:
            def __enter__(self): return self
            def __exit__(self, exc_type, exc_val, exc_tb): pass
        return DummySocket()
    monkeypatch.setattr("socket.create_connection", mock_create_connection)
    assert check_port_open("localhost", 22) is True
