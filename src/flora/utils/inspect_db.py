"""
inspect_db.py  –  Inspeciona e documenta o schema do banco DuckDB do FLORA.

Por padrão inspeciona o arquivo:
  <raiz-do-projeto>/results/flora.duckdb

Uso:
  python inspect_db.py [--db caminho.duckdb] [--schemas main] [--sample-rows 5] [--out db.txt]
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

import duckdb

# Raiz do projeto: src/flora/utils/inspect_db.py -> parents[3] == raiz do FLORA
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_DB_PATH = _PROJECT_ROOT / "results" / "flora.duckdb"

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Inspeciona schema do banco DuckDB do FLORA")
    p.add_argument(
        "--db",
        default=str(_DEFAULT_DB_PATH),
        help=f"Caminho do arquivo .duckdb (default: {_DEFAULT_DB_PATH})",
    )
    p.add_argument(
        "--schemas",
        default="",
        help="Schemas a inspecionar, separados por vírgula (default: todos exceto information_schema/pg_catalog)",
    )
    p.add_argument(
        "--sample-rows",
        type=int,
        default=5,
        metavar="N",
        help="Quantas linhas de amostra por tabela (default: 5, 0 = desabilita)",
    )
    p.add_argument(
        "--out",
        default=str(Path(__file__).with_name("db.txt")),
        help="Arquivo de saída (default: db.txt no mesmo diretório)",
    )
    return p.parse_args()


# ---------------------------------------------------------------------------
# Output helper
# ---------------------------------------------------------------------------

class Reporter:
    def __init__(self) -> None:
        self._lines: list[str] = []

    def __call__(self, text: str = "") -> None:
        print(text)
        self._lines.append(text)

    def header(self, title: str) -> None:
        self(("=" * 80))
        self(f"  {title}")
        self(("=" * 80))

    def save(self, path: str) -> None:
        Path(path).write_text("\n".join(self._lines) + "\n", encoding="utf-8")
        print(f"\nSaída salva em: {path}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _qident(name: str) -> str:
    """Quote a DuckDB identifier (schema/table/column name)."""
    return '"' + str(name).replace('"', '""') + '"'


def _rows(con: duckdb.DuckDBPyConnection, sql: str, params: list | None = None) -> list[dict]:
    cur = con.execute(sql, params) if params else con.execute(sql)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def _format_row(row: dict) -> str:
    pairs = [f"{k}={v!r}" for k, v in row.items()]
    return "{ " + ", ".join(pairs) + " }"


def _excluded_schemas() -> tuple[str, ...]:
    return ("information_schema", "pg_catalog")


def _schema_clause(column: str, allowed_schemas: list[str]) -> tuple[str, list]:
    """Build a `WHERE`-fragment + params restricting rows to the chosen schemas."""
    if allowed_schemas:
        placeholders = ", ".join("?" for _ in allowed_schemas)
        return f"{column} IN ({placeholders})", list(allowed_schemas)
    placeholders = ", ".join("?" for _ in _excluded_schemas())
    return f"{column} NOT IN ({placeholders})", list(_excluded_schemas())


# ---------------------------------------------------------------------------
# Seções de inspeção
# ---------------------------------------------------------------------------

def section_tables(con, log: Reporter, allowed_schemas: list[str]) -> list[dict]:
    log()
    log.header("TABELAS NO BANCO")
    clause, params = _schema_clause("schema_name", allowed_schemas)
    tables = _rows(
        con,
        f"""
        SELECT schema_name, table_name
        FROM duckdb_tables()
        WHERE {clause}
        ORDER BY schema_name, table_name;
        """,
        params,
    )
    for t in tables:
        log(f"  {t['schema_name']}.{t['table_name']}")
    return tables


def section_columns(con, log: Reporter, tables: list[dict]) -> None:
    log()
    log.header("ESTRUTURA DAS TABELAS (Colunas, Tipos, Nullable, Default)")
    for t in tables:
        schema, table = t["schema_name"], t["table_name"]
        log(f"\n  --- {schema}.{table} ---")
        cols = _rows(
            con,
            """
            SELECT column_name, data_type, is_nullable, column_default, column_index
            FROM duckdb_columns()
            WHERE schema_name = ? AND table_name = ?
            ORDER BY column_index;
            """,
            [schema, table],
        )
        for c in cols:
            null = "NULL" if c["is_nullable"] else "NOT NULL"
            default = f" DEFAULT {c['column_default']}" if c["column_default"] else ""
            log(f"    {c['column_name']:40s} {c['data_type']:25s} {null:10s}{default}")


def section_primary_keys(con, log: Reporter, allowed_schemas: list[str]) -> list[dict]:
    log()
    log.header("PRIMARY KEYS")
    clause, params = _schema_clause("schema_name", allowed_schemas)
    pks = _rows(
        con,
        f"""
        SELECT schema_name, table_name, constraint_column_names
        FROM duckdb_constraints()
        WHERE constraint_type = 'PRIMARY KEY' AND {clause}
        ORDER BY schema_name, table_name;
        """,
        params,
    )
    if not pks:
        log("  (Nenhuma primary key encontrada)")
        return pks
    for pk in pks:
        log(f"\n  {pk['schema_name']}.{pk['table_name']}:")
        for col in pk["constraint_column_names"]:
            log(f"    PK -> {col}")
    return pks


_FK_RE = re.compile(
    r"FOREIGN\s+KEY\s*\(([^)]+)\)\s*REFERENCES\s+([\w.\"]+)\s*\(([^)]+)\)",
    re.IGNORECASE,
)


def section_foreign_keys(con, log: Reporter, allowed_schemas: list[str]) -> list[dict]:
    log()
    log.header("FOREIGN KEYS (RELACIONAMENTOS)")
    clause, params = _schema_clause("schema_name", allowed_schemas)
    fks = _rows(
        con,
        f"""
        SELECT schema_name, table_name, constraint_column_names, constraint_text
        FROM duckdb_constraints()
        WHERE constraint_type = 'FOREIGN KEY' AND {clause}
        ORDER BY schema_name, table_name;
        """,
        params,
    )
    parsed: list[dict] = []
    if not fks:
        log("  (Nenhuma foreign key encontrada)")
        return parsed

    for fk in fks:
        m = _FK_RE.search(fk["constraint_text"] or "")
        ref_table = m.group(2).strip('"') if m else "?"
        ref_cols = m.group(3) if m else "?"
        fk_cols = ", ".join(fk["constraint_column_names"])
        log(
            f"  {fk['schema_name']}.{fk['table_name']}.({fk_cols})"
            f"  -->  {ref_table}({ref_cols})"
        )
        for col in fk["constraint_column_names"]:
            parsed.append({"fk_schema": fk["schema_name"], "fk_table": fk["table_name"], "fk_column": col})
    return parsed


def section_indexes(con, log: Reporter, allowed_schemas: list[str]) -> list[dict]:
    log()
    log.header("INDEXES")
    clause, params = _schema_clause("schema_name", allowed_schemas)
    idxs = _rows(
        con,
        f"""
        SELECT schema_name, table_name, index_name, is_unique, is_primary, sql
        FROM duckdb_indexes()
        WHERE {clause}
        ORDER BY schema_name, table_name, index_name;
        """,
        params,
    )
    if not idxs:
        log("  (Nenhum índice encontrado)")
        return idxs
    for idx in idxs:
        kind = "PRIMARY" if idx["is_primary"] else ("UNIQUE" if idx["is_unique"] else "INDEX")
        log(f"  {idx['schema_name']}.{idx['table_name']}  |  {idx['index_name']}  [{kind}]")
        if idx["sql"]:
            log(f"    {idx['sql']}")
    return idxs


def section_enums(con, log: Reporter, allowed_schemas: list[str]) -> None:
    log()
    log.header("TIPOS ENUM (USER-DEFINED)")
    clause, params = _schema_clause("schema_name", allowed_schemas)
    try:
        rows = _rows(
            con,
            f"""
            SELECT schema_name, type_name, labels
            FROM duckdb_types()
            WHERE logical_type = 'ENUM'
              AND labels IS NOT NULL
              AND database_name = current_database()
              AND {clause}
            ORDER BY schema_name, type_name;
            """,
            params,
        )
    except duckdb.Error as exc:
        log(f"  (Não foi possível consultar tipos ENUM: {exc})")
        return
    if not rows:
        log("  (Nenhum enum encontrado)")
        return
    for r in rows:
        values = ", ".join(r["labels"]) if r["labels"] else ""
        log(f"  {r['schema_name']}.{r['type_name']}:  {values}")


def section_row_counts(con, log: Reporter, tables: list[dict]) -> dict[str, int]:
    log()
    log.header("CONTAGEM DE REGISTROS POR TABELA")
    counts: dict[str, int] = {}
    for t in tables:
        schema, table = t["schema_name"], t["table_name"]
        qualified = f"{_qident(schema)}.{_qident(table)}"
        n = con.execute(f"SELECT COUNT(*) FROM {qualified}").fetchone()[0]
        counts[f"{schema}.{table}"] = n
        log(f"  {schema}.{table:45s}  {n:>8,} rows")
    return counts


def section_sample_data(con, log: Reporter, tables: list[dict], n_rows: int) -> None:
    if n_rows <= 0:
        return
    log()
    log.header(f"AMOSTRA DE DADOS ({n_rows} LINHAS POR TABELA)")
    for t in tables:
        schema, table = t["schema_name"], t["table_name"]
        log(f"\n  --- {schema}.{table} ---")
        qualified = f"{_qident(schema)}.{_qident(table)}"
        try:
            rows = _rows(con, f"SELECT * FROM {qualified} LIMIT {int(n_rows)}")
            if not rows:
                log("    (sem registros)")
                continue
            for i, row in enumerate(rows, start=1):
                log(f"    [{i}] {_format_row(row)}")
        except duckdb.Error as ex:
            log(f"    [ERRO] {ex}")


# ---------------------------------------------------------------------------
# Seção de diagnóstico / alertas
# ---------------------------------------------------------------------------

def section_diagnostics(
    con,
    log: Reporter,
    tables: list[dict],
    fks: list[dict],
    indexes: list[dict],
    pks: list[dict],
) -> None:
    log()
    log.header("DIAGNÓSTICO / ALERTAS")
    warnings: list[str] = []

    # --- 1) Índices duplicados (mesma tabela + mesma definição) -------------
    idx_by_table: dict[str, list[dict]] = defaultdict(list)
    for idx in indexes:
        key = f"{idx['schema_name']}.{idx['table_name']}"
        idx_by_table[key].append(idx)

    for tkey, tidxs in idx_by_table.items():
        seen: dict[str, str] = {}
        for idx in tidxs:
            sig = idx["sql"] or idx["index_name"]
            try:
                sig = sig.split("(", 1)[1].rstrip(")")
            except IndexError:
                pass
            if sig in seen:
                warnings.append(
                    f"  [INDICE DUPLICADO] {tkey}: índices '{seen[sig]}' e "
                    f"'{idx['index_name']}' parecem cobrir as mesmas colunas ({sig})"
                )
            else:
                seen[sig] = idx["index_name"]

    # --- 2) Colunas *_id sem FK declarada -----------------------------------
    # Ignora colunas que são a própria PK (de coluna única) da tabela: nesse
    # caso a coluna define a identidade da entidade, não referencia outra.
    fk_cols = {(f["fk_schema"], f["fk_table"], f["fk_column"]) for f in fks}
    own_single_pk_cols = {
        (pk["schema_name"], pk["table_name"], pk["constraint_column_names"][0])
        for pk in pks
        if len(pk["constraint_column_names"]) == 1
    }
    for t in tables:
        schema, table = t["schema_name"], t["table_name"]
        cols = _rows(
            con,
            """
            SELECT column_name, is_nullable
            FROM duckdb_columns()
            WHERE schema_name = ? AND table_name = ?
              AND column_name LIKE '%_id'
              AND column_name != 'id'
            ORDER BY column_name;
            """,
            [schema, table],
        )
        for c in cols:
            key = (schema, table, c["column_name"])
            if key not in fk_cols and key not in own_single_pk_cols:
                nullable = "(nullable)" if c["is_nullable"] else "(NOT NULL)"
                warnings.append(
                    f"  [FK AUSENTE] {schema}.{table}.{c['column_name']} {nullable} "
                    f"parece ser FK mas não tem constraint declarada"
                )

    # --- Exibe resultados ---------------------------------------------------
    if warnings:
        log(f"\n  {len(warnings)} alerta(s) encontrado(s):\n")
        for w in warnings:
            log(w)
    else:
        log("\n  Nenhum alerta encontrado.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    args = _parse_args()
    allowed_schemas = [s.strip() for s in args.schemas.split(",") if s.strip()]
    log = Reporter()

    db_path = Path(args.db)
    if not db_path.exists():
        sys.exit(f"ERRO: arquivo DuckDB não encontrado: {db_path}")

    try:
        con = duckdb.connect(database=str(db_path), read_only=True)
    except duckdb.Error as exc:
        sys.exit(f"ERRO ao conectar ao banco: {exc}")

    try:
        log.header(f"BANCO: {db_path}")
        tables  = section_tables(con, log, allowed_schemas)
        section_columns(con, log, tables)
        pks     = section_primary_keys(con, log, allowed_schemas)
        fks     = section_foreign_keys(con, log, allowed_schemas)
        indexes = section_indexes(con, log, allowed_schemas)
        section_enums(con, log, allowed_schemas)
        section_row_counts(con, log, tables)
        section_sample_data(con, log, tables, args.sample_rows)
        section_diagnostics(con, log, tables, fks, indexes, pks)

        log()
        log.header("DONE")
    finally:
        con.close()
        log.save(args.out)


if __name__ == "__main__":
    main()
