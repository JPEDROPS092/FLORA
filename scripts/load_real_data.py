#!/usr/bin/env python3
"""Load FLORA with real public data and run the analyses, so every screen has something real to show.

    python scripts/load_real_data.py --workdir results            # data, diversity, statistics, ML, reports
    python scripts/load_real_data.py --workdir results --llm      # also the LLM operator's analyses (needs a model in Modelos de IA)

One project per study (MGnify, EMBL-EBI), downloaded and ingested through the same code the app uses. Re-running is safe:
existing projects are reused and only missing steps are redone. Nothing outside ``--workdir`` is written.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

STUDIES = [
    {
        "accession": "MGYS00005810",
        "name": "Continuum do Amazonas: rio → pluma oceânica",
        "question": "A comunidade microbiana do Rio Amazonas difere da pluma que entra no Atlântico tropical?",
        "description": "MGnify MGYS00005810 (PRJNA237344): 83 amostras de água do Rio Amazonas e da pluma no Atlântico oeste tropical.",
        "group": "environment_biome",
        "llm": ["Compare o rio com a pluma oceânica: faça o gráfico da composição por filo, teste a diversidade alfa e beta e mostre quais táxons mais diferem. Interprete com ressalvas.",
                "Mostre o mapa das amostras deste estudo e diga como a diversidade muda com o ambiente."],
    },
    {
        "accession": "MGYS00005779",
        "name": "Solo da Amazônia colombiana: uso da terra",
        "question": "Como floresta, regeneração e pastagem mudam a comunidade microbiana do solo e da serapilheira?",
        "description": "MGnify MGYS00005779 (PRJEB44163): 64 amostras de solo e serapilheira em Belén e Solano (Caquetá, Colômbia).",
        "group": "land_cover",
        "llm": ["Compare floresta, regeneração e pastagem: composição por filo, diversidade alfa e beta, e os táxons diferenciais entre floresta e pastagem. Interprete com ressalvas."],
    },
    {
        "accession": "MGYS00001352",
        "name": "Desmatamento na Amazônia: floresta × área desmatada",
        "question": "O que o desmatamento de curto prazo muda no microbioma do solo amazônico?",
        "description": "MGnify MGYS00001352: 18 amostras de solo (floresta e áreas recém-desmatadas) em três sítios do Brasil (NIOO-KNAW).",
        "group": "land_cover",
        "llm": ["Compare floresta e área desmatada: gráficos, testes de diversidade e táxons diferenciais. Fale do tamanho da amostra."],
    },
    {
        "accession": "MGYS00006055",
        "name": "Lagos naturais: estação seca × chuvosa",
        "question": "A comunidade dos lagos naturais muda entre a estação seca e a chuvosa?",
        "description": "MGnify MGYS00006055: 19 amostras de lagos naturais (Vale Technological Institute), 9 na seca e 10 na chuvosa.",
        "group": "environment_feature",
        "llm": ["Compare a estação seca e a chuvosa nestes lagos: composição, diversidade e testes. Interprete com ressalvas."],
    },
]


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def step(label: str, fn, *a, **kw):
    """Run one step; a failure is reported and skipped so one study cannot block the rest."""
    started = time.time()
    try:
        out = fn(*a, **kw)
        log(f"  ok   {label} ({time.time() - started:.1f}s)")
        return out
    except Exception as exc:  # noqa: BLE001 - this is a batch loader: report and continue
        log(f"  FAIL {label}: {str(exc)[:160]}")
        return None


def project_for(state, study) -> object:
    for p in state.projects.list():
        if p.name == study["name"]:
            return p
    return state.projects.create(study["name"], study["question"], description=study["description"], organism="bacteria", marker="SSU rRNA", biome="Amazônia", kind="public")


def ingest(state, project, study) -> None:
    if project.stage == "ingested" and project.samples:
        log("  já ingerido")
        return
    job = state.sync.start(project.id, {"type": "mgnify", "accession": study["accession"], "params": {}})
    while True:
        job = state.sync.get(job["id"], project.id)
        if job["status"] in {"completed", "failed", "cancelled"}:
            break
        time.sleep(1.5)
    if job["status"] != "completed":
        raise RuntimeError(job.get("error") or job["status"])
    log(f"  {job['result'].get('summary', 'concluído')}")


def analyses(state, project, study) -> dict:
    from flora.ui.handlers import analysis, explore, ml, report, viz

    group = study["group"]
    pipe = state.pipeline
    out: dict = {"project": project.name, "group_by": group}
    schema = explore.get_schema(state)
    out["counts"], out["reads"] = schema["counts"], schema["reads"]
    levels = next((c["values"] for c in schema["group_columns"] if c["name"] == group), [])
    out["groups"] = {v["value"]: v["count"] for v in levels}
    depth = max(int(schema["reads"].get("min", 100) * 0.95), 10)

    step("diversidade alfa (salva no banco)", pipe.compute_diversity, sampling_depth=depth)
    step("matriz beta (salva no banco)", viz.viz_beta_heatmap, state, {"metric": ["bray_curtis"], "normalize": ["tss"], "max_samples": ["60"]})
    out["qc"] = step("QC", analysis.get_qc, state, {"min_reads": [str(max(depth // 2, 10))]})
    out["rarefaction"] = step("rarefação", analysis.get_rarefaction, state, {"group_by": [group]})
    out["alpha"] = step("estatística alfa", analysis.get_alpha_stats, state, {"group_by": [group]})
    out["beta"] = {m: step(f"PERMANOVA/PERMDISP ({m})", analysis.get_beta_stats, state, {"group_by": [group], "metric": [m], "permutations": ["999"]}) for m in ("bray_curtis", "aitchison")}
    names = sorted(out["groups"], key=lambda g: -out["groups"][g])
    a, b = (names[0], names[1]) if len(names) >= 2 else ("", "")
    if a and b:
        out["differential"] = step(f"abundância diferencial ({b} vs {a})", analysis.get_volcano, state, {"group_by": [group], "rank": ["genus"], "a": [a], "b": [b]})
    out["mixs"] = step("MIxS", analysis.get_mixs, state)
    for model in ("random_forest", "xgboost"):
        res = step(f"ML {model}", ml.classify, state, {"model": model, "target_column": group, "split": "auto", "cv_folds": 3, "seed": 42, "normalize": "clr"})
        if res:
            e = res["experiment"]
            out.setdefault("ml", {})[model] = {"accuracy": e["accuracy"], "f1_macro": e["f1_macro"], "train_n": e["train_n"], "test_n": e["test_n"]}
    step("relatório HTML", report.generate_report, state, {"title": study["name"], "group_by": group, "output_path": "relatorio.html"})
    return out


def operator(state, study, questions: list[str]) -> None:
    from flora.llm import SettingsStore
    from flora.ui.handlers import llm as handler

    if not SettingsStore(state.workdir).load().enabled:
        log("  LLM desativado em Modelos de IA: pulando as análises do operador")
        return
    for question in questions:
        history = [{"role": "user", "content": question}]
        for _ in range(4):  # follow the operator's turns; reading tools never need approval
            res = step(f"operador: {question[:60]}…", handler.agent, state, {"messages": history})
            if not res or res["pending"]:
                break
            history += res["messages"]
            if res["text"]:
                log(f"    → {res['text'][:110].replace(chr(10), ' ')}…")
                break


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--workdir", default="results")
    ap.add_argument("--llm", action="store_true", help="run the LLM operator's analyses too")
    ap.add_argument("--only", help="accession to load (default: all)")
    args = ap.parse_args()

    from flora.ui.cli import ui_config
    from flora.ui.server import create_app

    workdir = Path(args.workdir)
    _, _, state = create_app(config=ui_config(None), workdir=workdir)
    summary, first = [], None
    for study in STUDIES:
        if args.only and study["accession"] != args.only:
            continue
        log(f"{study['accession']}  {study['name']}")
        project = project_for(state, study)
        state.projects.set_active(project.id)
        first = first or project.id
        if step("download + ingestão", ingest, state, project, study) is None and state.projects.get(project.id).stage != "ingested":
            continue
        result = analyses(state, state.projects.get(project.id), study)
        if args.llm:
            operator(state, study, study["llm"])
        (Path(state.projects.dir(project.id)) / "analises.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), "utf-8")
        summary.append({"project": project.name, "id": project.id, "samples": result["counts"]["samples"], "features": result["counts"]["asvs"], "ml": result.get("ml")})
    if first:
        state.projects.set_active(first)
    log("pronto.")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
