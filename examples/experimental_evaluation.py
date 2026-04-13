"""Experimental evaluation for FLORA with baselines, robustness and interpretation."""

from __future__ import annotations

import logging
from pathlib import Path

import biom
import numpy as np
import polars as pl

from flora.feature_engineering.selection import select_by_importance
from flora.ml import (
    map_top_features_to_taxonomy,
    run_classification_benchmark,
    run_prevalence_sensitivity,
    run_rarefaction_sensitivity,
    summarize_taxonomic_signal,
)

DATA_DIR = Path("data/raw/emp")
RESULTS_DIR = Path("results/benchmark")
DOCS_DIR = Path("docs")
MARKDOWN_OUT = DOCS_DIR / "experimental_evaluation.md"

TARGET_COL = "empo_3"
KEEP_CLASSES = {"Plant surface", "Soil (non-saline)", "Animal proximal gut"}
SECONDARY_TARGET = "empo_2"
RANDOM_STATE = 42


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
    )
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    print("FLORA experimental evaluation")
    print("=" * 40)
    print("[1/6] Loading EMP data...")

    emp_wide = pl.read_csv(DATA_DIR / "asv_table.tsv", separator="\t", infer_schema_length=1000)
    emp_metadata = pl.read_csv(DATA_DIR / "metadata.tsv", separator="\t", infer_schema_length=10000)
    taxonomy_df = pl.read_csv(DATA_DIR / "taxonomy.tsv", separator="\t", infer_schema_length=1000)

    labels_df = (
        emp_metadata
        .select(["sample_id", TARGET_COL])
        .filter(pl.col(TARGET_COL).is_in(list(KEEP_CLASSES)))
    )
    emp_wide = emp_wide.join(labels_df.select("sample_id"), on="sample_id", how="inner")

    print("[2/6] Building second real dataset from raw EMP metadata + BIOM...")
    broad_wide, broad_labels = load_emp_broad_dataset()

    print("[3/6] Running EMP benchmark suite...")
    benchmark_emp = run_classification_benchmark(
        emp_wide,
        labels_df,
        dataset_name="EMP",
        target_column=TARGET_COL,
        normalizations=["raw", "tss", "clr"],
        models=["majority", "random_forest", "xgboost", "svm"],
        prevalence_threshold=0.05,
        cv_splits=5,
        cv_repeats=2,
        random_state=RANDOM_STATE,
        tune_models=["random_forest", "xgboost"],
        tuning_trials=6,
    )

    print("[4/6] Running second real benchmark suite...")
    benchmark_broad = run_classification_benchmark(
        broad_wide,
        broad_labels,
        dataset_name="EMP_Broad",
        target_column=SECONDARY_TARGET,
        normalizations=["raw", "tss", "clr"],
        models=["majority", "random_forest", "xgboost"],
        prevalence_threshold=0.05,
        cv_splits=4,
        cv_repeats=2,
        random_state=RANDOM_STATE,
    )

    print("[5/6] Running robustness analyses...")
    rarefaction_sensitivity = run_rarefaction_sensitivity(
        emp_wide,
        labels_df,
        dataset_name="EMP",
        target_column=TARGET_COL,
        depths=[3000, 5000, 8000, 10000],
        normalization="clr",
        model="xgboost",
        prevalence_threshold=0.05,
        cv_splits=4,
        cv_repeats=2,
        random_state=RANDOM_STATE,
    )

    prevalence_sensitivity = run_prevalence_sensitivity(
        emp_wide,
        labels_df,
        dataset_name="EMP",
        target_column=TARGET_COL,
        thresholds=[0.01, 0.03, 0.05, 0.10, 0.15],
        normalization="clr",
        model="xgboost",
        cv_splits=4,
        cv_repeats=2,
        random_state=RANDOM_STATE,
    )

    print("[6/6] Exporting biological interpretation and reports...")
    print("  - Computing feature importance mapping...")
    importance_input = emp_wide.join(labels_df, on="sample_id", how="inner")
    _, importance_df = select_by_importance(
        importance_input,
        labels=importance_input[TARGET_COL],
        task="classification",
        n_features=20,
        random_state=RANDOM_STATE,
    )
    mapped_taxonomy = map_top_features_to_taxonomy(importance_df, taxonomy_df, top_n=20)
    taxonomic_signal = summarize_taxonomic_signal(mapped_taxonomy, level="phylum")

    summary = pl.concat([benchmark_emp.summary, benchmark_broad.summary], how="diagonal")
    folds = pl.concat([benchmark_emp.fold_metrics, benchmark_broad.fold_metrics], how="diagonal")

    summary.write_csv(RESULTS_DIR / "benchmark_summary.csv")
    folds.write_csv(RESULTS_DIR / "benchmark_fold_metrics.csv")
    rarefaction_sensitivity.write_csv(RESULTS_DIR / "rarefaction_sensitivity.csv")
    prevalence_sensitivity.write_csv(RESULTS_DIR / "prevalence_sensitivity.csv")
    mapped_taxonomy.write_csv(RESULTS_DIR / "top_features_taxonomy.csv")
    taxonomic_signal.write_csv(RESULTS_DIR / "taxonomic_signal.csv")

    write_markdown(
        summary=summary,
        rarefaction=rarefaction_sensitivity,
        prevalence=prevalence_sensitivity,
        mapped_taxonomy=mapped_taxonomy,
        taxonomic_signal=taxonomic_signal,
        tuned_params={**benchmark_emp.tuned_params, **benchmark_broad.tuned_params},
    )

    print("Experimental evaluation completed.")
    print(f"Summary: {RESULTS_DIR / 'benchmark_summary.csv'}")
    print(f"Markdown: {MARKDOWN_OUT}")


def load_emp_broad_dataset(min_nonzero_samples: int = 20) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Create a second real dataset from the larger EMP raw metadata subset."""
    raw_meta = pl.read_csv(DATA_DIR / "emp_metadata_raw.tsv", separator="\t", infer_schema_length=10000)
    raw_meta = raw_meta.rename({"#SampleID": "sample_id"})
    biom_table = biom.load_table(str(DATA_DIR / "emp_deblur_150bp.release1.biom"))
    biom_ids = set(map(str, biom_table.ids(axis="sample")))

    labels = (
        raw_meta
        .filter(pl.col("sample_id").is_in(list(biom_ids)))
        .select(["sample_id", SECONDARY_TARGET])
        .drop_nulls()
    )

    sample_ids = labels["sample_id"].to_list()
    subset = biom_table.filter(sample_ids, axis="sample", inplace=False)
    matrix = subset.matrix_data.tocsc()
    keep_features = np.asarray(matrix.getnnz(axis=1)).ravel() >= min_nonzero_samples
    matrix = matrix[keep_features, :].transpose().toarray().astype(float)
    feature_ids = np.asarray(subset.ids(axis="observation"))[keep_features]
    ordered_sample_ids = [str(s) for s in subset.ids(axis="sample")]

    columns = {"sample_id": ordered_sample_ids}
    for idx, feature_id in enumerate(feature_ids):
        columns[str(feature_id)] = matrix[:, idx].tolist()
    feature_df = pl.DataFrame(columns)
    label_df = labels.filter(pl.col("sample_id").is_in(ordered_sample_ids))
    return feature_df, label_df


def write_markdown(
    *,
    summary: pl.DataFrame,
    rarefaction: pl.DataFrame,
    prevalence: pl.DataFrame,
    mapped_taxonomy: pl.DataFrame,
    taxonomic_signal: pl.DataFrame,
    tuned_params: dict[str, dict[str, object]],
) -> None:
    best_emp = (
        summary
        .filter(pl.col("dataset") == "EMP")
        .sort("f1_macro_mean", descending=True)
        .head(6)
    )
    best_broad = (
        summary
        .filter(pl.col("dataset") == "EMP_Broad")
        .sort("f1_macro_mean", descending=True)
        .head(6)
    )

    lines = [
        "# Experimental Evaluation",
        "",
        "## Hypothesis",
        "",
        "> A normalizacao composicional CLR melhora a separacao entre classes ambientais e o desempenho preditivo em relacao a abundancias brutas.",
        "",
        "## Biological Ingestion Protocol",
        "",
        "- controle de qualidade: trimming, remocao de primers/adaptadores e filtragem por qualidade;",
        "- denoising: inferencia de variantes por DADA2/QIIME2 quando a origem e FASTQ;",
        "- geracao de ASVs: remocao de quimeras e construcao da tabela de abundancia;",
        "- taxonomia: associacao de ASVs a ranks taxonomicos por classificador supervisionado;",
        "- ingestao analitica: carga de `metadata`, `asv_table`/BIOM e `taxonomy` no DuckDB;",
        "- modelagem: transformacao `raw`, `TSS` ou `CLR`, filtro por prevalencia e benchmarking supervisionado.",
        "",
        "## Experimental Design",
        "",
        "- datasets: EMP focado (subconjunto curado) e EMP_Broad (1.139 amostras reais do metadata bruto com overlap no BIOM);",
        "- modelos: baseline majoritario, Random Forest, XGBoost e SVM;",
        "- normalizacoes: raw, TSS e CLR;",
        "- metricas: accuracy, balanced_accuracy, f1_macro e roc_auc;",
        "- validacao: RepeatedStratifiedKFold com media, desvio padrao e IC aproximado de 95%;",
        "- robustez: sensibilidade a profundidade de rarefacao e filtro de prevalencia.",
        "",
        "## Benchmark Summary — EMP",
        "",
    ]
    lines.extend(markdown_table(best_emp.select([
        "normalization", "model", "accuracy_mean", "balanced_accuracy_mean", "f1_macro_mean", "roc_auc_mean", "n_features"
    ])))
    lines.extend([
        "",
        "## Benchmark Summary — Second Real Dataset",
        "",
    ])
    lines.extend(markdown_table(best_broad.select([
        "normalization", "model", "accuracy_mean", "balanced_accuracy_mean", "f1_macro_mean", "roc_auc_mean", "n_features"
    ])))
    lines.extend([
        "",
        "## Rarefaction Sensitivity",
        "",
    ])
    lines.extend(markdown_table(rarefaction.select([
        "sampling_depth", "accuracy_mean", "balanced_accuracy_mean", "f1_macro_mean", "roc_auc_mean", "n_features"
    ])))
    lines.extend([
        "",
        "## Prevalence Sensitivity",
        "",
    ])
    lines.extend(markdown_table(prevalence.select([
        "prevalence_threshold", "accuracy_mean", "balanced_accuracy_mean", "f1_macro_mean", "roc_auc_mean", "n_features"
    ])))
    lines.extend([
        "",
        "## Biological Interpretation",
        "",
        "### Top Features Mapped to Taxonomy",
        "",
    ])
    lines.extend(markdown_table(mapped_taxonomy.select([
        "feature_id", "importance", "phylum", "genus", "species"
    ]).head(15)))
    lines.extend([
        "",
        "### Dominant Phyla Among Top Features",
        "",
    ])
    lines.extend(markdown_table(taxonomic_signal.head(10)))
    lines.extend([
        "",
        "## Tuned Models",
        "",
    ])
    for key, value in sorted(tuned_params.items()):
        lines.append(f"- `{key}`: `{value}`")

    with open(MARKDOWN_OUT, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))


def markdown_table(df: pl.DataFrame) -> list[str]:
    headers = [str(col) for col in df.columns]
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for row in df.iter_rows():
        cells = []
        for value in row:
            if isinstance(value, float):
                cells.append(f"{value:.4f}")
            else:
                cells.append(str(value))
        lines.append("| " + " | ".join(cells) + " |")
    return lines


if __name__ == "__main__":
    main()
