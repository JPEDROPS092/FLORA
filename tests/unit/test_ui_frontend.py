"""Tests for frontend asset resolution and strict Angular-only behavior."""

import pytest

from flora.ui import frontend


def test_spa_root_dir_uses_build_dir(monkeypatch, tmp_path):
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    (app_dir / "index.html").write_text("<html>angular</html>", encoding="utf-8")
    monkeypatch.setattr(frontend, "SPA_BUILD_DIR", app_dir)

    assert frontend.spa_root_dir() == app_dir
    assert frontend.has_built_frontend() is True
    assert frontend.load_index_html() == "<html>angular</html>"


def test_frontend_mode_defaults_to_missing_build(monkeypatch, tmp_path):
    monkeypatch.setattr(frontend, "SPA_BUILD_DIR", tmp_path / "app")

    assert frontend.has_built_frontend() is False
    assert frontend.frontend_mode() == "missing-build"


def test_resolve_frontend_asset_returns_file_when_build_exists(monkeypatch, tmp_path):
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    asset = app_dir / "main.js"
    (app_dir / "index.html").write_text("<html></html>", encoding="utf-8")
    asset.write_text("console.log('flora');", encoding="utf-8")

    monkeypatch.setattr(frontend, "SPA_BUILD_DIR", app_dir)

    resolved = frontend.resolve_frontend_asset("/main.js")

    assert resolved is not None
    assert resolved.path == asset
    assert resolved.content_type == "text/javascript"
    assert resolved.binary is False


def test_resolve_frontend_asset_blocks_path_traversal(monkeypatch, tmp_path):
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    (app_dir / "index.html").write_text("<html></html>", encoding="utf-8")

    monkeypatch.setattr(frontend, "SPA_BUILD_DIR", app_dir)

    assert frontend.resolve_frontend_asset("/../secret.txt") is None


def test_should_serve_spa_index_for_client_route(monkeypatch, tmp_path):
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    (app_dir / "index.html").write_text("<html></html>", encoding="utf-8")

    monkeypatch.setattr(frontend, "SPA_BUILD_DIR", app_dir)

    assert frontend.should_serve_spa_index("/overview") is True
    assert frontend.should_serve_spa_index("/assets/main.js") is False


def test_spa_root_dir_prefers_browser_subdirectory(monkeypatch, tmp_path):
    app_dir = tmp_path / "app"
    browser_dir = app_dir / "browser"
    browser_dir.mkdir(parents=True)
    (browser_dir / "index.html").write_text("<html></html>", encoding="utf-8")

    monkeypatch.setattr(frontend, "SPA_BUILD_DIR", app_dir)

    assert frontend.spa_root_dir() == browser_dir


def test_load_index_html_reads_built_spa(monkeypatch, tmp_path):
    app_dir = tmp_path / "app"
    browser_dir = app_dir / "browser"
    browser_dir.mkdir(parents=True)
    (browser_dir / "index.html").write_text("<html>angular</html>", encoding="utf-8")

    monkeypatch.setattr(frontend, "SPA_BUILD_DIR", app_dir)

    assert frontend.load_index_html() == "<html>angular</html>"


def test_load_index_html_raises_when_build_is_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(frontend, "SPA_BUILD_DIR", tmp_path / "app")

    with pytest.raises(frontend.FrontendNotBuiltError):
        frontend.load_index_html()
