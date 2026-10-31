"""Smoke tests for the ``flora ui`` bootstrap path."""

from __future__ import annotations

from flora.ui.server import create_app, run_server


class DummyServer:
    """Test double for ``HTTPServer`` used by run_server smoke tests."""

    def __init__(self, address, handler_cls):
        self.address = address
        self.handler_cls = handler_cls
        self.closed = False
        self.served = False

    def serve_forever(self):
        self.served = True
        raise KeyboardInterrupt

    def server_close(self):
        self.closed = True


def test_create_app_returns_server_components(tmp_path):
    server_cls, handler_cls, state = create_app(workdir=tmp_path)

    assert server_cls is not None
    assert handler_cls is not None
    assert state.workdir == tmp_path


def test_run_server_smoke(monkeypatch, tmp_path, capsys):
    created: dict[str, object] = {}

    def fake_setup_logging(*, level: str, **_kwargs):
        created["log_level"] = level

    def fake_install_buffer_handler():
        created["buffer_handler"] = True

    def fake_http_server(address, handler_cls):
        server = DummyServer(address, handler_cls)
        created["server"] = server
        return server

    monkeypatch.setattr("flora.ui.server.setup_logging", fake_setup_logging)
    monkeypatch.setattr("flora.ui.server._install_buffer_handler", fake_install_buffer_handler)
    monkeypatch.setattr("flora.ui.server.HTTPServer", fake_http_server)

    run_server(
        host="127.0.0.1",
        port=8765,
        workdir=tmp_path,
        open_browser=False,
        log_level="INFO",
    )

    output = capsys.readouterr().out
    server = created["server"]

    assert created["log_level"] == "INFO"
    assert created["buffer_handler"] is True
    assert isinstance(server, DummyServer)
    assert server.address == ("127.0.0.1", 8765)
    assert server.served is True
    assert server.closed is True
    assert "FLORA Web Interface running at: http://127.0.0.1:8765" in output
