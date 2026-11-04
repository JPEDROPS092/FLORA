"""``flora engines``: check and connect QIIME 2, DADA2 and the other external tools from the terminal."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from flora.engines import envs, registry


def add_engines_parser(sub) -> None:
    cmd = sub.add_parser("engines", help="Check and connect QIIME 2, DADA2 and other external tools")
    actions = cmd.add_subparsers(dest="engines_action", required=True)
    for name, text in (("doctor", "Show which tools FLORA can use, with versions and install hints"),
                       ("envs", "List conda environments that contain QIIME 2 or DADA2"),
                       ("connect", "Save the environment FLORA should use")):
        p = actions.add_parser(name, help=text)
        p.add_argument("--workdir", default="results", help="Working directory (holds engines.json)")
    doctor = actions.choices["doctor"]
    doctor.add_argument("--json", action="store_true", help="Machine-readable output")
    connect = actions.choices["connect"]
    connect.add_argument("--env", help="One environment for QIIME 2 and R")
    connect.add_argument("--qiime-env", help="Environment with QIIME 2")
    connect.add_argument("--r-env", help="Environment with R / DADA2")
    connect.add_argument("--qiime", help="Path to the qiime executable")
    connect.add_argument("--python", help="Path to the Python of the QIIME 2 environment")
    connect.add_argument("--rscript", help="Path to Rscript")


def _apply(workdir: str) -> None:
    registry.configure(envs.load(Path(workdir)))


def run_engines(args: argparse.Namespace) -> int:
    workdir = Path(args.workdir)
    if args.engines_action == "envs":
        found = envs.discover()
        for e in found:
            tags = [t for t, ok in (("QIIME 2 CLI", e["qiime"]), ("QIIME 2 API Python", e["qiime2_python_api"]), ("DADA2 (R)", e["dada2_r_package"])) if ok]
            print(f"{e['name']:<32} {e['prefix']}  [{', '.join(tags)}]")
        if not found:
            print("Nenhum ambiente com QIIME 2 ou DADA2 encontrado. Veja scripts/setup_engines.sh.")
        return 0
    if args.engines_action == "connect":
        try:
            saved = envs.connect(workdir, env=args.env, qiime_env=args.qiime_env, r_env=args.r_env, qiime=args.qiime, python=args.python, rscript=args.rscript)
        except envs.EnvError as exc:
            print(f"Erro: {exc}", file=sys.stderr)
            return 2
        for key, value in saved.items():
            print(f"{key:<8} {value}")
        print(f"Salvo em {workdir / envs.CONFIG_NAME}")
        return 0
    _apply(args.workdir)
    report = registry.detect_all(fresh=True)
    if args.json:
        print(json.dumps({"config": envs.load(workdir), "engines": report}, ensure_ascii=False, indent=2))
        return 0
    for e in report:
        mark = "OK " if e["available"] else "-- "
        print(f"{mark}{e['name']:<18} {e['version'] or e['install']}")
    missing = [e for e in report if not e["available"]]
    if missing:
        print(f"\n{len(missing)} ferramenta(s) ausente(s). Para instalar num ambiente conda: scripts/setup_engines.sh")
    return 0
