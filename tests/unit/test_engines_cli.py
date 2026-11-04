"""``flora engines`` CLI, tools found in a connected environment's bin, and the persistent default database."""

from __future__ import annotations

import json
import os
import stat
import sys
from argparse import Namespace
from pathlib import Path

import pytest

from flora.engines import envs, registry
from flora.engines.cli import run_engines
from flora.ui.cli import ui_config


def _exe(path: Path, body: str = "#!/bin/sh\necho 1.2.3\n") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body)
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return path


@pytest.fixture()
def conda(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # discovery also looks in ./.engines, which exists in the real repository
    for var in ("CONDA_PREFIX", "CONDA_EXE"):
        monkeypatch.delenv(var, raising=False)
    root = tmp_path / "mm"
    monkeypatch.setenv("MAMBA_ROOT_PREFIX", str(root))
    monkeypatch.setenv("PATH", "/nonexistent")
    registry.configure({})
    for name, with_q2 in (("flora-engines", False), ("qiime2-amplicon", True)):
        prefix = root / "envs" / name
        _exe(prefix / "bin" / "python")
        if with_q2:
            _exe(prefix / "bin" / "qiime", f"#!{sys.executable}\nprint('q2cli 2024.10')\n")
            (prefix / "lib" / "python3.10" / "site-packages" / "qiime2").mkdir(parents=True)
        else:
            _exe(prefix / "bin" / "Rscript", f"#!{sys.executable}\nprint('4.3.1')\n")
            _exe(prefix / "bin" / "vsearch", f"#!{sys.executable}\nprint('vsearch v2.28')\n")
            (prefix / "lib" / "R" / "library" / "dada2").mkdir(parents=True)
    yield root
    registry.configure({})


def _args(action, workdir, **kw):
    base = dict(engines_action=action, workdir=str(workdir), json=False, env=None, qiime_env=None, r_env=None, qiime=None, python=None, rscript=None)
    return Namespace(**{**base, **kw})


def test_connect_two_environments_then_doctor_sees_tools_in_their_bin(conda, tmp_path, capsys):
    assert run_engines(_args("connect", tmp_path, r_env="flora-engines", qiime_env="qiime2-amplicon")) == 0
    saved = envs.load(tmp_path)
    assert saved["rscript"].endswith("flora-engines/bin/Rscript") and saved["qiime"].endswith("qiime2-amplicon/bin/qiime")
    capsys.readouterr()
    assert run_engines(_args("doctor", tmp_path, json=True)) == 0
    report = {e["id"]: e for e in json.loads(capsys.readouterr().out)["engines"]}
    assert report["qiime2"]["available"] and report["vsearch"]["available"]  # vsearch is only in the R env's bin, not on PATH
    assert registry.resolve_cmd(["vsearch", "--version"])[0].endswith("flora-engines/bin/vsearch")


def test_connect_requires_a_choice_when_several_environments_exist(conda, tmp_path, capsys):
    assert run_engines(_args("connect", tmp_path)) == 2
    err = capsys.readouterr().err
    assert "--env" in err and "flora-engines" in err and "qiime2-amplicon" in err
    assert run_engines(_args("connect", tmp_path, env="nope")) == 2
    assert envs.load(tmp_path) == {}


def test_connect_uses_the_only_environment_without_asking(conda, tmp_path):
    import shutil

    shutil.rmtree(conda / "envs" / "qiime2-amplicon")
    assert run_engines(_args("connect", tmp_path)) == 0
    assert "rscript" in envs.load(tmp_path)


def test_envs_lists_what_was_found(conda, tmp_path, capsys):
    run_engines(_args("envs", tmp_path))
    out = capsys.readouterr().out
    assert "flora-engines" in out and "DADA2 (R)" in out and "QIIME 2 API Python" in out


def test_doctor_reports_missing_tools_with_a_next_step(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("PATH", "/nonexistent")
    registry.configure({})
    run_engines(_args("doctor", tmp_path))
    out = capsys.readouterr().out
    assert "--" in out and "scripts/setup_engines.sh" in out


def test_ui_database_is_a_file_unless_memory_is_requested(tmp_path):
    assert ui_config(None).database.path == "flora.duckdb"
    assert ui_config(None, memory=True).database.path == ":memory:"
    cfg = tmp_path / "c.yaml"
    cfg.write_text("database:\n  path: custom.duckdb\n")
    assert ui_config(str(cfg)).database.path == "custom.duckdb"  # an explicit path is respected
    mem = tmp_path / "m.yaml"
    mem.write_text("database:\n  path: ':memory:'\n")
    assert ui_config(str(mem)).database.path == "flora.duckdb"
    assert ui_config(str(mem), memory=True).database.path == ":memory:"
