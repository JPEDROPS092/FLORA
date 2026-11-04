"""Turn MGnify's processed SSU taxonomy table into FLORA's ``asv_table.tsv`` + ``taxonomy.tsv``.

MGnify publishes, per study, a TSV with one row per taxonomic lineage (``sk__Bacteria;k__;p__...``)
and one column per analysis (an assembly ``ERZ…`` or run ``ERR…`` accession). FLORA needs samples as rows,
so the analysis columns are mapped to sample accessions and summed when a sample has several analyses.

These features are **taxonomic profiles**, not ASVs: they come from MGnify's own pipeline and have no sequences.
"""

from __future__ import annotations

import csv
import io
import logging
from pathlib import Path

logger = logging.getLogger("flora.io.mgnify_tables")

_RANKS = (("sk__", "kingdom"), ("k__", None), ("p__", "phylum"), ("c__", "class"), ("o__", "order"), ("f__", "family"), ("g__", "genus"), ("s__", "species"))
_TAX_COLUMNS = ["feature_id", "kingdom", "phylum", "class", "order", "family", "genus", "species"]


def parse_lineage(lineage: str) -> dict[str, str]:
    """``sk__Archaea;k__;p__X;c__`` -> ``{kingdom: Archaea, phylum: X, ...}`` (empty ranks stay empty)."""
    out = {name: "" for name in _TAX_COLUMNS[1:]}
    for part in lineage.split(";"):
        part = part.strip()
        for prefix, rank in _RANKS:
            if rank and part.startswith(prefix):
                out[rank] = part[len(prefix):].replace("_", " ").strip() if rank == "species" else part[len(prefix):]
                break
    return out


def convert_ssu_table(
    text: str,
    column_to_sample: dict[str, str],
    output_dir: Path,
) -> dict[str, str]:
    """Write ``asv_table.tsv`` (samples x features) and ``taxonomy.tsv``; return their paths.

    Columns not found in *column_to_sample* are kept under their own name, so nothing is silently dropped.
    Raises ``ValueError`` when the table has no usable rows.
    """
    reader = csv.reader(io.StringIO(text), delimiter="\t")
    header = next(reader, None)
    if not header or len(header) < 2:
        raise ValueError("MGnify table has no sample columns")
    columns = header[1:]
    samples = [column_to_sample.get(col, col) for col in columns]
    order = list(dict.fromkeys(samples))

    features: list[tuple[str, dict[str, str], dict[str, float]]] = []
    for row in reader:
        if not row or not row[0].strip():
            continue
        counts: dict[str, float] = {}
        for sample, raw in zip(samples, row[1:], strict=False):
            try:
                value = float(raw)
            except ValueError:
                continue
            if value:
                counts[sample] = counts.get(sample, 0.0) + value
        if counts:
            features.append((f"MGN_{len(features) + 1:05d}", parse_lineage(row[0]), counts))
    if not features:
        raise ValueError("MGnify table has no features with counts")

    output_dir.mkdir(parents=True, exist_ok=True)
    asv_path, tax_path = output_dir / "asv_table.tsv", output_dir / "taxonomy.tsv"
    with open(asv_path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, delimiter="\t", lineterminator="\n")
        writer.writerow(["sample_id", *[f[0] for f in features]])
        for sample in order:
            writer.writerow([sample, *[int(f[2].get(sample, 0)) if float(f[2].get(sample, 0)).is_integer() else f[2].get(sample, 0) for f in features]])
    with open(tax_path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, delimiter="\t", lineterminator="\n")
        writer.writerow(_TAX_COLUMNS)
        for fid, tax, _ in features:
            writer.writerow([fid, *[tax[c] for c in _TAX_COLUMNS[1:]]])
    logger.info("MGnify tables written: %d samples x %d features", len(order), len(features))
    return {"asv_table": str(asv_path), "taxonomy": str(tax_path)}


def analysis_sample_map(analyses: list[dict]) -> dict[str, str]:
    """Map every accession an analysis can be labelled with (assembly, run, analysis id) to its sample."""
    mapping: dict[str, str] = {}
    for analysis in analyses:
        rels = analysis.get("relationships") or {}

        def rel(name: str) -> str:
            data = (rels.get(name) or {}).get("data")
            return data.get("id", "") if isinstance(data, dict) else ""

        sample = rel("sample")
        if not sample:
            continue
        for key in (rel("assembly"), rel("run"), analysis.get("id", "")):
            if key:
                mapping[key] = sample
    return mapping
