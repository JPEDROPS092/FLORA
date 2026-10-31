"""FLORA — Earth Microbiome Project analysis and documentation exporter.

Runs the EMP pipeline with the local dataset in ``data/raw/emp``, generates
interactive HTML plus static PNG figures, and writes a Markdown report under
``docs/`` for downstream academic reporting.
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import polars as pl
from sklearn.model_selection import train_test_split

from flora.db.connection import FloraDB
from flora.db.ingestion import ingest_biom, ingest_metadata, ingest_taxonomy
from flora.db.schema import initialize_schema
from flora.diversity.alpha import compute_alpha_diversity
from flora.diversity.beta import compute_beta_diversity
from flora.feature_engineering.normalization import clr_transform
from flora.feature_engineering.reduction import compute_pcoa
from flora.feature_engineering.selection import filter_by_prevalence
from flora.ml.classification.classifier import MicrobiomeClassifier
from flora.ml.explainability.shap_analysis import SHAPAnalyzer
from flora.reports.html_report import FLORAReport
from flora.viz.diversity_plots import (
    plot_alpha_diversity,
    plot_beta_diversity_heatmap,
    plot_pcoa,
)
from flora.viz.ml_plots import (
    plot_confusion_matrix,
    plot_feature_importance,
    plot_roc_curve,
)
from flora.viz.taxonomy_plots import plot_taxonomy_barplot, plot_taxonomy_heatmap

DATA_DIR = Path("data/raw/emp")
RESULTS = Path("results")
DOCS_DIR = Path("docs")
DOCS_ASSETS = DOCS_DIR / "assets" / "emp"
PARQUET_DIR = RESULTS / "parquet"
METADATA = DATA_DIR / "metadata.tsv"
ASV_TABLE = DATA_DIR / "asv_table.tsv"
BIOM_TABLE = DATA_DIR / "emp_deblur_150bp.release1.biom"
TAXONOMY = DATA_DIR / "taxonomy.tsv"
DB_PATH = RESULTS / "emp_flora.duckdb"
REPORT_OUT = RESULTS / "emp_report.html"
MARKDOWN_OUT = DOCS_DIR / "emp_report.md"

TARGET_COL = "empo_3"
KEEP_CLASSES = {"Plant surface", "Soil (non-saline)", "Animal proximal gut"}
SAMPLING_DEPTH = 5000
CLR_PREVALENCE = 0.05
CV_FOLDS = 3
TEST_SIZE = 0.25
RANDOM_STATE = 42


def main() -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    DOCS_ASSETS.mkdir(parents=True, exist_ok=True)
    PARQUET_DIR.mkdir(parents=True, exist_ok=True)

    if DB_PATH.exists():
        DB_PATH.unlink()

    print("FLORA — EMP Analysis")
    print("=" * 50)

    print("\n[1/8] Ingesting data...")
    db = FloraDB.connect(str(DB_PATH))
    initialize_schema(db)
    n_samples = ingest_metadata(db, METADATA, parquet_dir=PARQUET_DIR)
    metadata_df = pl.read_csv(METADATA, separator="\t", infer_schema_length=10000)
    n_obs = ingest_biom(
        db,
        BIOM_TABLE,
        filter_sample_ids=metadata_df["sample_id"].to_list(),
        parquet_dir=PARQUET_DIR,
    )
    n_tax = ingest_taxonomy(db, TAXONOMY, parquet_dir=PARQUET_DIR)
    db.create_views()
    print(f"  Samples: {n_samples}  |  ASV obs: {n_obs}  |  Taxonomy rows: {n_tax}")

    print("\n[2/8] Building matrices...")
    wide = db.pivot_asv(normalize=None)
    clr = filter_by_prevalence(clr_transform(wide), min_prevalence=CLR_PREVALENCE)
    n_features = len(clr.columns) - 1
    sample_totals = wide.with_columns(
        pl.sum_horizontal(pl.exclude("sample_id")).alias("total_reads")
    ).select(["sample_id", "total_reads"])
    print(f"  Samples: {len(clr)}  |  Features after filter: {n_features}")

    print("\n[3/8] Preparing labels...")
    meta = db.query(
        f"""
        SELECT s.sample_id, m.value AS {TARGET_COL}
        FROM samples s
        LEFT JOIN sample_metadata m
               ON s.sample_id = m.sample_id AND m.key = '{TARGET_COL}'
        """
    ).to_polars()
    meta_filtered = meta.filter(pl.col(TARGET_COL).is_in(list(KEEP_CLASSES)))
    clr_labeled = clr.join(
        meta_filtered.select(["sample_id", TARGET_COL]),
        on="sample_id",
        how="inner",
    )
    class_counts = (
        clr_labeled[TARGET_COL]
        .value_counts()
        .rename({TARGET_COL: "class"})
        .sort("count", descending=True)
    )
    print(f"  Samples after class filter: {len(clr_labeled)}")
    for row in class_counts.iter_rows(named=True):
        print(f"    {row['class']}: {row['count']}")

    print("\n[4/8] Train/test split...")
    df_pd = clr_labeled.to_pandas()
    train_pd, test_pd = train_test_split(
        df_pd,
        test_size=TEST_SIZE,
        stratify=df_pd[TARGET_COL],
        random_state=RANDOM_STATE,
    )
    train_df = pl.from_pandas(train_pd)
    test_df = pl.from_pandas(test_pd)
    print(f"  Train: {len(train_df)}  |  Test: {len(test_df)}")

    print("\n[5/8] Training classifier...")
    clf = MicrobiomeClassifier(
        model="xgboost",
        target_column=TARGET_COL,
        random_state=RANDOM_STATE,
        n_jobs=1,
        mlflow_tracking_uri=None,
    )
    result = clf.fit(train_df, test_df, cv_folds=CV_FOLDS)
    print(f"  Accuracy : {result.accuracy:.4f}")
    print(f"  F1-macro : {result.f1_macro:.4f}")
    print(f"  ROC-AUC  : {result.roc_auc:.4f}" if result.roc_auc is not None else "  ROC-AUC  : N/A")

    print("\n[6/8] Computing explainability and diversity...")
    shap_result = None
    shap_analyzer = None
    try:
        shap_analyzer = SHAPAnalyzer(model=result.model, feature_names=result.feature_names)
        shap_result = shap_analyzer.explain(test_df.select(["sample_id"] + result.feature_names))
    except Exception as exc:
        print(f"  SHAP unavailable in current environment: {exc}")

    alpha_df = compute_alpha_diversity(
        wide,
        metrics=["shannon", "observed_features", "chao1", "simpson"],
        sampling_depth=SAMPLING_DEPTH,
    )
    beta_df = compute_beta_diversity(wide, metric="bray_curtis")
    pcoa_long = compute_pcoa(clr.drop(TARGET_COL, strict=False), metric="braycurtis", n_components=3)
    print(f"  Alpha samples: {len(alpha_df)}  |  Beta distances: {len(beta_df)}")

    print("\n[7/8] Generating figures...")
    pcoa_meta = pcoa_long.join(meta_filtered.select(["sample_id", TARGET_COL]), on="sample_id", how="left")
    alpha_meta = alpha_df.join(meta_filtered.select(["sample_id", TARGET_COL]), on="sample_id", how="left")
    taxon_agg = db.aggregate_by_taxon(level="phylum", group_by=TARGET_COL)
    genus_sample_abundance = db.query(
        """
        SELECT
            a.sample_id,
            COALESCE(t.genus, 'Unclassified') AS genus,
            SUM(a.abundance) AS abundance
        FROM asv a
        LEFT JOIN taxonomy t USING(feature_id)
        GROUP BY a.sample_id, COALESCE(t.genus, 'Unclassified')
        """
    ).to_polars()
    top_taxa = (
        taxon_agg.group_by("phylum")
        .agg(pl.col("mean_abundance").sum().alias("mean_abundance"))
        .sort("mean_abundance", descending=True)
        .head(15)
    )

    figures = {
        "pcoa_braycurtis": plot_pcoa(
            pcoa_meta,
            metadata_df=pcoa_meta,
            color_by=TARGET_COL,
            title="Bray-Curtis PCoA — EMP",
        ),
        "alpha_shannon": plot_alpha_diversity(alpha_meta, metric="shannon", group_by=TARGET_COL),
        "alpha_chao1": plot_alpha_diversity(alpha_meta, metric="chao1", group_by=TARGET_COL),
        "beta_heatmap": plot_beta_diversity_heatmap(beta_df, metric="bray_curtis", cluster=True),
        "taxonomy_barplot": plot_taxonomy_barplot(taxon_agg, level="phylum", group_by=TARGET_COL),
        "taxonomy_heatmap": plot_taxonomy_heatmap(
            genus_sample_abundance,
            level="genus",
            top_n=20,
        ),
        "roc_curve": plot_roc_curve(result),
        "confusion_matrix": plot_confusion_matrix(
            result.y_true,
            result.y_pred,
            label_names=list(result.label_encoder.classes_),
        ),
        "feature_importance": plot_feature_importance(result.feature_importances, top_n=20),
    }
    if shap_analyzer is not None and shap_result is not None:
        figures["shap_summary"] = shap_analyzer.summary_plot(shap_result, max_display=20)
    saved_assets = {name: save_figure(name, fig) for name, fig in figures.items()}
    static_assets = save_static_figures(
        pcoa_meta=pcoa_meta,
        alpha_meta=alpha_meta,
        beta_df=beta_df,
        top_taxa=top_taxa,
        genus_sample_abundance=genus_sample_abundance,
        class_counts=class_counts,
        result=result,
        shap_result=shap_result,
    )

    print("\n[8/8] Building report outputs...")
    report = FLORAReport(title="FLORA — Earth Microbiome Project Analysis")
    report.add_metrics(
        "Dataset Summary",
        {
            "Samples (total)": n_samples,
            "Samples (ML subset)": len(clr_labeled),
            "ASV observations": n_obs,
            "Taxonomy rows": n_tax,
            "Features after prevalence filter": n_features,
            "Sampling depth": SAMPLING_DEPTH,
        },
    )
    report.add_metrics(
        "Model Summary",
        {
            "Target column": TARGET_COL,
            "Model": "XGBoost",
            "Accuracy": round(result.accuracy, 4),
            "F1-macro": round(result.f1_macro, 4),
            "ROC-AUC": "N/A" if result.roc_auc is None else round(result.roc_auc, 4),
            "CV folds": CV_FOLDS,
        },
    )
    report.add_text("Classification Report", result.classification_report_str)
    report.add_plot("PCoA", figures["pcoa_braycurtis"])
    report.add_plot("Taxonomic Composition", figures["taxonomy_barplot"])
    report.add_plot("Taxonomy Heatmap", figures["taxonomy_heatmap"])
    report.add_plot("Shannon Diversity", figures["alpha_shannon"])
    report.add_plot("Chao1 Richness", figures["alpha_chao1"])
    report.add_plot("Beta Diversity Heatmap", figures["beta_heatmap"])
    report.add_plot("ROC Curve", figures["roc_curve"])
    report.add_plot("Confusion Matrix", figures["confusion_matrix"])
    report.add_plot("Feature Importance", figures["feature_importance"])
    report.add_table("Class Distribution", class_counts)
    report.add_table("Top Phyla", top_taxa)
    if shap_result is not None and "shap_summary" in figures:
        report.add_plot("SHAP Summary", figures["shap_summary"])
        report.add_table("Top Features by SHAP", shap_result.mean_abs_shap.head(20))
    report.add_table(
        "Alpha Diversity Table",
        alpha_meta.sort("shannon", descending=True),
        max_rows=89,
    )
    html_out = report.save(REPORT_OUT)

    summary = {
        "samples_total": n_samples,
        "samples_ml": len(clr_labeled),
        "asv_observations": n_obs,
        "taxonomy_rows": n_tax,
        "features_after_filter": n_features,
        "train_samples": len(train_df),
        "test_samples": len(test_df),
        "accuracy": result.accuracy,
        "f1_macro": result.f1_macro,
        "roc_auc": result.roc_auc,
        "mean_reads_per_sample": float(sample_totals["total_reads"].mean()),
        "median_reads_per_sample": float(sample_totals["total_reads"].median()),
        "max_reads_per_sample": float(sample_totals["total_reads"].max()),
        "min_reads_per_sample": float(sample_totals["total_reads"].min()),
        "top_feature": None if shap_result is None else shap_result.mean_abs_shap["feature"][0],
        "top_feature_shap": None if shap_result is None else float(shap_result.mean_abs_shap["mean_abs_shap"][0]),
    }
    write_markdown_report(
        summary=summary,
        class_counts=class_counts,
        alpha_meta=alpha_meta,
        top_taxa=top_taxa,
        top_features=None if shap_result is None else shap_result.mean_abs_shap.head(20),
        saved_assets=saved_assets,
        static_assets=static_assets,
        html_report=html_out,
    )

    print(f"  HTML report: {html_out}")
    print(f"  Markdown report: {MARKDOWN_OUT}")
    print(f"  Static assets: {DOCS_ASSETS}")
    db.close()


def save_figure(name: str, fig: object) -> dict[str, str | None]:
    html_path = DOCS_ASSETS / f"{name}.html"
    png_path = DOCS_ASSETS / f"{name}.png"
    fig.write_html(str(html_path))

    png_rel = None
    try:
        fig.write_image(str(png_path), width=1600, height=900, scale=2)
        png_rel = f"assets/emp/{png_path.name}"
    except Exception:
        png_rel = None

    return {
        "html": f"assets/emp/{html_path.name}",
        "png": png_rel,
    }


def write_markdown_report(
    *,
    summary: dict[str, float | int | str | None],
    class_counts: pl.DataFrame,
    alpha_meta: pl.DataFrame,
    top_taxa: pl.DataFrame,
    top_features: pl.DataFrame | None,
    saved_assets: dict[str, dict[str, str | None]],
    static_assets: dict[str, str],
    html_report: Path,
) -> None:
    alpha_summary = alpha_meta.select(
        pl.col("shannon").mean().alias("mean_shannon"),
        pl.col("shannon").median().alias("median_shannon"),
        pl.col("chao1").mean().alias("mean_chao1"),
        pl.col("simpson").mean().alias("mean_simpson"),
    )

    lines = [
        "# EMP Analysis Report",
        "",
        "Relatorio gerado automaticamente pela pipeline FLORA com os dados locais em `data/raw/emp`.",
        "",
        "## Resumo Executivo",
        "",
        f"- Amostras totais ingeridas: **{summary['samples_total']}**",
        f"- Amostras usadas no modelo: **{summary['samples_ml']}**",
        f"- Observacoes ASV carregadas: **{summary['asv_observations']:,}**",
        f"- Taxonomias carregadas: **{summary['taxonomy_rows']:,}**",
        f"- Features apos filtro de prevalencia: **{summary['features_after_filter']:,}**",
        f"- Acuracia no teste: **{summary['accuracy']:.4f}**",
        f"- F1-macro no teste: **{summary['f1_macro']:.4f}**",
        f"- ROC-AUC: **{'N/A' if summary['roc_auc'] is None else f'{summary['roc_auc']:.4f}'}**",
        f"- Leitura media por amostra: **{summary['mean_reads_per_sample']:.1f}**",
        (
            "- Top feature por SHAP: **"
            f"{summary['top_feature']}** ({summary['top_feature_shap']:.4f})"
            if summary["top_feature"] is not None and summary["top_feature_shap"] is not None
            else "- SHAP nao foi exportado porque a instalacao local do pacote `shap` esta incompativel com o ambiente atual."
        ),
        "",
        f"Relatorio interativo completo: [`{html_report}`](../results/{html_report.name})",
        "",
        "## Distribuicao de Classes",
        "",
    ]
    lines.extend(markdown_table(class_counts.rename({"class": "Classe", "count": "Amostras"})))
    lines.extend(
        [
            "",
            "## Diversidade",
            "",
            f"- Shannon medio: **{alpha_summary['mean_shannon'][0]:.4f}**",
            f"- Shannon mediano: **{alpha_summary['median_shannon'][0]:.4f}**",
            f"- Chao1 medio: **{alpha_summary['mean_chao1'][0]:.2f}**",
            f"- Simpson medio: **{alpha_summary['mean_simpson'][0]:.4f}**",
            "",
            "## Top Filos",
            "",
        ]
    )
    lines.extend(markdown_table(top_taxa.rename({"phylum": "Phylum", "mean_abundance": "Abundancia media"})))
    if top_features is not None:
        lines.extend(
            [
                "",
                "## Top Features por SHAP",
                "",
            ]
        )
        lines.extend(markdown_table(top_features.rename({"feature": "Feature", "mean_abs_shap": "Mean |SHAP|"})))
    lines.extend(
        [
            "",
            "## Figuras",
            "",
        ]
    )

    figure_order = [
        ("PCoA Bray-Curtis", "pcoa_braycurtis"),
        ("Shannon por Classe", "alpha_shannon"),
        ("Chao1 por Classe", "alpha_chao1"),
        ("Heatmap de Beta Diversidade", "beta_heatmap"),
        ("Composicao Taxonomica por Classe", "taxonomy_barplot"),
        ("Heatmap Taxonomico", "taxonomy_heatmap"),
        ("ROC", "roc_curve"),
        ("Matriz de Confusao", "confusion_matrix"),
        ("Importancia de Features", "feature_importance"),
    ]
    if "shap_summary" in saved_assets:
        figure_order.append(("Resumo SHAP", "shap_summary"))
    for title, key in figure_order:
        asset = saved_assets[key]
        lines.append(f"### {title}")
        lines.append("")
        image_path = asset["png"] or static_assets.get(key)
        if image_path:
            lines.append(f"![{title}]({image_path})")
            lines.append("")
        lines.append(f"[Abrir versao interativa]({asset['html']})")
        lines.append("")

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


def save_static_figures(
    *,
    pcoa_meta: pl.DataFrame,
    alpha_meta: pl.DataFrame,
    beta_df: pl.DataFrame,
    top_taxa: pl.DataFrame,
    genus_sample_abundance: pl.DataFrame,
    class_counts: pl.DataFrame,
    result: object,
    shap_result: object | None,
) -> dict[str, str]:
    os.environ.setdefault("MPLCONFIGDIR", "/tmp/mplconfig")

    import matplotlib.pyplot as plt

    assets: dict[str, str] = {}

    def _save(name: str) -> str:
        path = DOCS_ASSETS / f"{name}.png"
        plt.tight_layout()
        plt.savefig(path, dpi=200, bbox_inches="tight")
        plt.close()
        rel = f"assets/emp/{path.name}"
        assets[name] = rel
        return rel

    class_df = class_counts.to_pandas()
    plt.figure(figsize=(8, 4.5))
    plt.bar(class_df["class"], class_df["count"], color=["#3f7d20", "#d08c00", "#8c3a2b"])
    plt.title("Class Distribution")
    plt.ylabel("Samples")
    plt.xticks(rotation=20, ha="right")
    _save("class_distribution")

    taxa_df = top_taxa.to_pandas().head(12).sort_values("mean_abundance")
    plt.figure(figsize=(9, 5.5))
    plt.barh(taxa_df["phylum"], taxa_df["mean_abundance"], color="#0b7285")
    plt.title("Top Phyla by Mean Abundance")
    plt.xlabel("Mean abundance")
    _save("taxonomy_barplot")

    alpha_pd = alpha_meta.drop_nulls(TARGET_COL).to_pandas()
    labels = list(alpha_pd[TARGET_COL].dropna().unique())
    data = [alpha_pd.loc[alpha_pd[TARGET_COL] == label, "shannon"].values for label in labels]
    plt.figure(figsize=(8.5, 5))
    plt.boxplot(data, tick_labels=labels, patch_artist=True)
    plt.title("Shannon Diversity by Class")
    plt.ylabel("Shannon")
    plt.xticks(rotation=20, ha="right")
    _save("alpha_shannon")

    data_chao1 = [alpha_pd.loc[alpha_pd[TARGET_COL] == label, "chao1"].values for label in labels]
    plt.figure(figsize=(8.5, 5))
    plt.boxplot(data_chao1, tick_labels=labels, patch_artist=True)
    plt.title("Chao1 Richness by Class")
    plt.ylabel("Chao1")
    plt.xticks(rotation=20, ha="right")
    _save("alpha_chao1")

    pcoa_pd = pcoa_meta.pivot(index="sample_id", on="component", values="value", aggregate_function="first").to_pandas()
    pcoa_pd = pcoa_pd.rename(columns={"1": "PC1", "2": "PC2", "3": "PC3"})
    if TARGET_COL in pcoa_meta.columns:
        class_map = pcoa_meta.select(["sample_id", TARGET_COL]).unique().to_pandas()
        pcoa_pd = pcoa_pd.merge(class_map, on="sample_id", how="left")
    plt.figure(figsize=(8, 6))
    for label in pcoa_pd[TARGET_COL].dropna().unique():
        sub = pcoa_pd[pcoa_pd[TARGET_COL] == label]
        plt.scatter(sub["PC1"], sub["PC2"], label=label, alpha=0.8, s=36)
    plt.title("PCoA Bray-Curtis")
    plt.xlabel("PC1")
    plt.ylabel("PC2")
    plt.legend(frameon=False)
    _save("pcoa_braycurtis")

    beta_pd = beta_df.to_pandas()
    sample_ids = sorted(set(beta_pd["sample_a"]).union(beta_pd["sample_b"]))
    idx = {sample_id: i for i, sample_id in enumerate(sample_ids)}
    matrix = np.zeros((len(sample_ids), len(sample_ids)), dtype=float)
    for row in beta_pd.itertuples(index=False):
        i = idx[row.sample_a]
        j = idx[row.sample_b]
        matrix[i, j] = row.distance
        matrix[j, i] = row.distance
    plt.figure(figsize=(7, 6))
    plt.imshow(matrix, cmap="viridis", aspect="auto")
    plt.colorbar(label="Bray-Curtis distance")
    plt.title("Beta Diversity Heatmap")
    plt.xlabel("Sample index")
    plt.ylabel("Sample index")
    _save("beta_heatmap")

    genus_pd = genus_sample_abundance.to_pandas()
    top_genera = (
        genus_pd.groupby("genus", as_index=False)["abundance"]
        .sum()
        .sort_values("abundance", ascending=False)
        .head(20)["genus"]
        .tolist()
    )
    genus_pivot = (
        genus_pd[genus_pd["genus"].isin(top_genera)]
        .pivot_table(index="sample_id", columns="genus", values="abundance", fill_value=0.0)
    )
    if len(genus_pivot) > 0:
        mat = genus_pivot.to_numpy(dtype=float)
        row_sums = mat.sum(axis=1, keepdims=True)
        mat = np.divide(mat, row_sums, out=np.zeros_like(mat), where=row_sums != 0)
        plt.figure(figsize=(11, 6))
        plt.imshow(mat, cmap="magma", aspect="auto")
        plt.colorbar(label="Relative abundance")
        plt.title("Top Genera Heatmap")
        plt.xlabel("Genus")
        plt.ylabel("Sample")
        plt.xticks(range(len(genus_pivot.columns)), genus_pivot.columns, rotation=90, fontsize=7)
        plt.yticks([])
        _save("taxonomy_heatmap")

    cm = result.label_encoder.classes_
    y_true = np.asarray(result.y_true)
    y_pred = np.asarray(result.y_pred)
    counts = np.zeros((len(cm), len(cm)), dtype=float)
    index = {label: i for i, label in enumerate(cm)}
    for truth, pred in zip(y_true, y_pred, strict=False):
        counts[index[truth], index[pred]] += 1
    row_sums = counts.sum(axis=1, keepdims=True)
    norm = np.divide(counts, row_sums, out=np.zeros_like(counts), where=row_sums != 0)
    plt.figure(figsize=(6.5, 5.5))
    plt.imshow(norm, cmap="Blues", aspect="auto")
    plt.colorbar(label="Proportion")
    plt.xticks(range(len(cm)), cm, rotation=25, ha="right")
    plt.yticks(range(len(cm)), cm)
    plt.title("Confusion Matrix")
    plt.xlabel("Predicted")
    plt.ylabel("True")
    _save("confusion_matrix")

    fi = result.feature_importances.to_pandas().head(15).sort_values("importance")
    plt.figure(figsize=(10, 6))
    plt.barh(fi["feature"], fi["importance"], color="#495057")
    plt.title("Top Feature Importances")
    plt.xlabel("Importance")
    _save("feature_importance")

    if result.y_proba is not None and len(cm) > 1:
        plt.figure(figsize=(6.5, 5.5))
        from sklearn.metrics import auc, roc_curve
        from sklearn.preprocessing import label_binarize

        y_bin = label_binarize(result.y_true, classes=cm)
        for i, label in enumerate(cm):
            fpr, tpr, _ = roc_curve(y_bin[:, i], result.y_proba[:, i])
            plt.plot(fpr, tpr, label=f"{label} (AUC={auc(fpr, tpr):.2f})")
        plt.plot([0, 1], [0, 1], linestyle="--", color="gray")
        plt.title("ROC Curves")
        plt.xlabel("False Positive Rate")
        plt.ylabel("True Positive Rate")
        plt.legend(frameon=False, fontsize=8)
        _save("roc_curve")

    if shap_result is not None:
        shap_df = shap_result.mean_abs_shap.to_pandas().head(15).sort_values("mean_abs_shap")
        plt.figure(figsize=(10, 6))
        plt.barh(shap_df["feature"], shap_df["mean_abs_shap"], color="#7f5539")
        plt.title("Top SHAP Features")
        plt.xlabel("Mean |SHAP|")
        _save("shap_summary")

    return assets


if __name__ == "__main__":
    main()
