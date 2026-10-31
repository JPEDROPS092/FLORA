"""Reusable SQL helper functions for UI endpoints."""

from __future__ import annotations

import re

_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_SAMPLE_COLUMNS = {"biome", "location", "latitude", "longitude", "sequencing_depth"}


def validate_identifier(name: str, *, field: str) -> str:
    """Validate a SQL identifier used by visualization endpoints."""
    if not name or not _SAFE_IDENTIFIER.match(name):
        raise ValueError(f"Invalid {field}: '{name}'")
    return name


def taxonomy_expr(level: str) -> str:
    """Return the safe taxonomy SQL expression for a given level."""
    level = validate_identifier(level, field="taxonomy level")
    return 't."order"' if level == "order" else f"t.{level}"


def group_projection(group_by: str | None) -> tuple[str, str, str]:
    """Return select/join fragments for optional grouping."""
    if not group_by:
        return "", "", ""

    group_by = validate_identifier(group_by, field="group_by")
    if group_by in _SAMPLE_COLUMNS:
        return f", s.{group_by} AS {group_by}", "", group_by

    join = f"""
    LEFT JOIN (
        SELECT sample_id, value AS {group_by}
        FROM sample_metadata
        WHERE key = '{group_by}'
    ) grp ON a.sample_id = grp.sample_id
    """
    return f", grp.{group_by} AS {group_by}", join, group_by


def fetch_sample_taxonomy_profile(db, level: str):
    """Return sample-level taxonomy abundance profile."""
    expr = taxonomy_expr(level)
    sql = f"""
    SELECT
        a.sample_id,
        COALESCE(NULLIF({expr}, ''), 'Unassigned') AS {level},
        SUM(a.abundance) AS abundance
    FROM asv a
    LEFT JOIN taxonomy t USING(feature_id)
    GROUP BY a.sample_id, {level}
    ORDER BY a.sample_id, abundance DESC
    """
    return db.query(sql).to_polars()


def fetch_taxonomy_hierarchy(db, group_by: str | None, top_n: int):
    """Return lineage hierarchy used by sunburst/tree endpoints."""
    select_group, join_group, group_name = group_projection(group_by)
    group_cols = f", {group_name}" if group_name else ""
    sql = f"""
    WITH lineage AS (
        SELECT
            COALESCE(NULLIF(t.kingdom, ''), 'Unassigned') AS kingdom,
            COALESCE(NULLIF(t.phylum, ''), 'Unassigned') AS phylum,
            COALESCE(NULLIF(t.class, ''), 'Unassigned') AS class,
            COALESCE(NULLIF(t."order", ''), 'Unassigned') AS "order",
            COALESCE(NULLIF(t.family, ''), 'Unassigned') AS family,
            COALESCE(NULLIF(t.genus, ''), 'Unassigned') AS genus,
            COALESCE(NULLIF(t.species, ''), 'Unassigned') AS species
            {select_group},
            SUM(a.abundance) AS abundance
        FROM asv a
        LEFT JOIN taxonomy t USING(feature_id)
        JOIN samples s USING(sample_id)
        {join_group}
        GROUP BY kingdom, phylum, class, "order", family, genus, species{group_cols}
    ),
    ranked AS (
        SELECT *, ROW_NUMBER() OVER (ORDER BY abundance DESC) AS rn
        FROM lineage
    )
    SELECT * EXCLUDE (rn)
    FROM ranked
    WHERE rn <= {int(top_n)}
    ORDER BY abundance DESC
    """
    return db.query(sql).to_polars()
