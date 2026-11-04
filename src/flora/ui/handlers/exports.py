"""Downloads of the loaded dataset in open formats: TSV and BIOM (feature table + taxonomy)."""

from __future__ import annotations

import io

import numpy as np

from flora.ui.http import RawResponse, UiHttpError

_FORMATS = {"features_tsv", "taxonomy_tsv", "metadata_tsv", "biom"}
_TAX = ("kingdom", "phylum", "class", "order", "family", "genus", "species")


def _q(params: dict | None, key: str, default: str = "") -> str:
    values = (params or {}).get(key)
    return values[0] if values else default


def _project_slug(state) -> str:
    active = state.projects.active_id()
    return active or "flora"


def export_dataset(state, params: dict | None = None):
    fmt = _q(params, "format", "features_tsv")
    if fmt not in _FORMATS:
        raise UiHttpError(f"Formato desconhecido: {fmt}. Use {', '.join(sorted(_FORMATS))}.", code="invalid_format")
    db = state.db
    wide = db.pivot_asv(normalize=None)
    if wide.is_empty() and fmt != "metadata_tsv":
        raise UiHttpError("Não há dados ingeridos para exportar.", code="empty_feature_matrix")
    slug = _project_slug(state)

    if fmt == "features_tsv":
        buf = io.StringIO()
        wide.write_csv(buf, separator="\t")
        return RawResponse(buf.getvalue().encode(), "text/tab-separated-values; charset=utf-8", f"{slug}_feature_table.tsv")
    if fmt == "taxonomy_tsv":
        buf = io.StringIO()
        db.query("SELECT feature_id, kingdom, phylum, class, \"order\", family, genus, species, confidence FROM taxonomy ORDER BY feature_id").to_polars().write_csv(buf, separator="\t")
        return RawResponse(buf.getvalue().encode(), "text/tab-separated-values; charset=utf-8", f"{slug}_taxonomy.tsv")
    if fmt == "metadata_tsv":
        buf = io.StringIO()
        db.query("SELECT * FROM samples ORDER BY sample_id").to_polars().write_csv(buf, separator="\t")
        return RawResponse(buf.getvalue().encode(), "text/tab-separated-values; charset=utf-8", f"{slug}_metadata.tsv")

    from biom import Table

    samples = wide["sample_id"].to_list()
    features = [c for c in wide.columns if c != "sample_id"]
    matrix = wide.drop("sample_id").to_numpy().astype(float).T  # features x samples, as BIOM expects
    tax = {r["feature_id"]: [r[c] or "" for c in _TAX] for r in db.query(f"SELECT feature_id, {', '.join(f'"{c}"' for c in _TAX)} FROM taxonomy").to_polars().iter_rows(named=True)}
    observation_metadata = [{"taxonomy": tax.get(f, [])} for f in features]
    table = Table(np.asarray(matrix), features, samples, observation_metadata=observation_metadata)
    return RawResponse(table.to_json("FLORA").encode(), "application/json", f"{slug}.biom")
