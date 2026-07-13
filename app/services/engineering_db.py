from __future__ import annotations

import re
from collections import defaultdict

import psycopg2
from psycopg2 import sql
from psycopg2.extras import RealDictCursor

from app.core.config import get_settings
from app.schemas.engineering_db import (
    ColumnSchema,
    EngineeringDbLookupResult,
    EngineeringDbRecord,
    EngineeringDbSchemaCatalog,
    EngineeringDbSchemaContextMatch,
    EngineeringDbSchemaContextResult,
    TableRelationship,
    TableSchema,
)

TEXT_TYPES = {"text", "character varying", "character", "citext"}
DISPLAY_COLUMN_CANDIDATES = (
    "name",
    "title",
    "part_number",
    "part_no",
    "sku",
    "label",
    "description",
    "id",
)
NOTES_COLUMN_CANDIDATES = ("notes_path", "notes", "note_path", "documentation_path")
TOKEN_RE = re.compile(r"[a-z0-9]+")


def get_db_connection():
    settings = get_settings()
    return psycopg2.connect(
        dbname=settings.db_name,
        user=settings.db_user,
        password=settings.db_password,
        host=settings.db_host,
        port=settings.db_port,
    )


def _tokenize(value: str) -> set[str]:
    return set(TOKEN_RE.findall((value or "").lower()))


def _join_reason_parts(parts: list[str]) -> str:
    filtered = [part for part in parts if part]
    return "; ".join(filtered) if filtered else "General engineering DB lookup fallback."


def get_engineering_db_schema_catalog() -> EngineeringDbSchemaCatalog:
    settings = get_settings()
    columns_sql = """
    SELECT
        c.table_name,
        c.column_name,
        c.data_type,
        c.is_nullable,
        EXISTS (
            SELECT 1
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name
             AND tc.table_schema = kcu.table_schema
             AND tc.table_name = kcu.table_name
            WHERE tc.constraint_type = 'PRIMARY KEY'
              AND tc.table_schema = c.table_schema
              AND tc.table_name = c.table_name
              AND kcu.column_name = c.column_name
        ) AS is_primary_key
    FROM information_schema.columns c
    JOIN information_schema.tables t
      ON c.table_schema = t.table_schema
     AND c.table_name = t.table_name
    WHERE c.table_schema = %s
      AND t.table_type = 'BASE TABLE'
    ORDER BY c.table_name, c.ordinal_position;
    """
    relationships_sql = """
    SELECT
        tc.table_name AS from_table,
        kcu.column_name AS from_column,
        ccu.table_name AS to_table,
        ccu.column_name AS to_column
    FROM information_schema.table_constraints tc
    JOIN information_schema.key_column_usage kcu
      ON tc.constraint_name = kcu.constraint_name
     AND tc.table_schema = kcu.table_schema
    JOIN information_schema.constraint_column_usage ccu
      ON ccu.constraint_name = tc.constraint_name
     AND ccu.table_schema = tc.table_schema
    WHERE tc.constraint_type = 'FOREIGN KEY'
      AND tc.table_schema = %s
    ORDER BY tc.table_name, kcu.column_name;
    """

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(columns_sql, (settings.db_schema,))
        column_rows = cur.fetchall()
        cur.execute(relationships_sql, (settings.db_schema,))
        relationship_rows = cur.fetchall()
        cur.close()
        conn.close()
    except Exception as exc:
        return EngineeringDbSchemaCatalog(ok=False, schema_name=settings.db_schema, error=str(exc))

    relationships = [
        TableRelationship(
            from_table=from_table,
            from_column=from_column,
            to_table=to_table,
            to_column=to_column,
        )
        for from_table, from_column, to_table, to_column in relationship_rows
    ]

    relationships_by_table: dict[str, list[TableRelationship]] = defaultdict(list)
    for relationship in relationships:
        relationships_by_table[relationship.from_table].append(relationship)

    tables: list[TableSchema] = []
    current_table_name = None
    current_columns: list[ColumnSchema] = []

    def flush_table(table_name: str | None, columns: list[ColumnSchema]) -> None:
        if not table_name:
            return
        primary_key_columns = [column.name for column in columns if column.is_primary_key]
        searchable_columns = [
            column.name for column in columns if column.data_type in TEXT_TYPES
        ]
        notes_columns = [
            column.name for column in columns if column.name.lower() in NOTES_COLUMN_CANDIDATES
        ]
        display_columns = [
            candidate
            for candidate in DISPLAY_COLUMN_CANDIDATES
            if any(column.name.lower() == candidate for column in columns)
        ]
        tables.append(
            TableSchema(
                table_name=table_name,
                columns=list(columns),
                primary_key_columns=primary_key_columns,
                searchable_columns=searchable_columns,
                notes_columns=notes_columns,
                display_columns=display_columns,
                foreign_keys=relationships_by_table.get(table_name, []),
            )
        )

    for table_name, column_name, data_type, is_nullable, is_primary_key in column_rows:
        if current_table_name is None:
            current_table_name = table_name
        if table_name != current_table_name:
            flush_table(current_table_name, current_columns)
            current_table_name = table_name
            current_columns = []

        is_foreign_key = any(
            relationship.from_table == table_name and relationship.from_column == column_name
            for relationship in relationships
        )
        current_columns.append(
            ColumnSchema(
                name=column_name,
                data_type=data_type,
                is_nullable=(is_nullable == "YES"),
                is_primary_key=is_primary_key,
                is_foreign_key=is_foreign_key,
            )
        )

    flush_table(current_table_name, current_columns)

    return EngineeringDbSchemaCatalog(
        ok=True,
        schema_name=settings.db_schema,
        tables=tables,
        relationships=relationships,
    )


def get_engineering_db_table_schema(table_name: str) -> TableSchema | None:
    catalog = get_engineering_db_schema_catalog()
    if not catalog.ok:
        return None
    for table in catalog.tables:
        if table.table_name == table_name:
            return table
    return None


def retrieve_engineering_db_schema_context(
    query: str,
    max_tables: int = 5,
) -> EngineeringDbSchemaContextResult:
    catalog = get_engineering_db_schema_catalog()
    if not catalog.ok:
        return EngineeringDbSchemaContextResult(
            ok=False,
            query=query,
            guidance="Unable to retrieve engineering DB schema context.",
            error=catalog.error,
        )

    query_tokens = _tokenize(query)
    matches: list[EngineeringDbSchemaContextMatch] = []

    for table in catalog.tables:
        table_tokens = _tokenize(table.table_name.replace("_", " "))
        column_tokens = _tokenize(" ".join(column.name.replace("_", " ") for column in table.columns))
        searchable_tokens = _tokenize(" ".join(table.searchable_columns))

        table_overlap = len(query_tokens & table_tokens)
        column_overlap = len(query_tokens & column_tokens)
        searchable_overlap = len(query_tokens & searchable_tokens)
        score = (table_overlap * 4) + (column_overlap * 2) + searchable_overlap

        if score == 0 and query_tokens:
            continue

        related_tables = sorted(
            {
                relationship.to_table
                for relationship in catalog.relationships
                if relationship.from_table == table.table_name
            }
            | {
                relationship.from_table
                for relationship in catalog.relationships
                if relationship.to_table == table.table_name
            }
        )
        reason_parts = []
        if table_overlap:
            reason_parts.append("table name overlaps the user query")
        if column_overlap:
            reason_parts.append("column names overlap the user query")
        if table.notes_columns:
            reason_parts.append("table includes note references")
        if related_tables:
            reason_parts.append(f"related to {', '.join(related_tables[:3])}")

        matches.append(
            EngineeringDbSchemaContextMatch(
                table_name=table.table_name,
                score=score,
                reason=_join_reason_parts(reason_parts),
                searchable_columns=table.searchable_columns,
                notes_columns=table.notes_columns,
                related_tables=related_tables,
            )
        )

    if not matches:
        fallback_tables = catalog.tables[:max_tables]
        matches = [
            EngineeringDbSchemaContextMatch(
                table_name=table.table_name,
                score=0,
                reason="Fallback suggestion because no strong schema match was found.",
                searchable_columns=table.searchable_columns,
                notes_columns=table.notes_columns,
                related_tables=sorted(
                    {
                        relationship.to_table
                        for relationship in catalog.relationships
                        if relationship.from_table == table.table_name
                    }
                ),
            )
            for table in fallback_tables
        ]

    matches.sort(key=lambda item: (-item.score, item.table_name))
    selected_matches = matches[:max_tables]
    selected_table_names = {item.table_name for item in selected_matches}
    selected_relationships = [
        relationship
        for relationship in catalog.relationships
        if relationship.from_table in selected_table_names or relationship.to_table in selected_table_names
    ]

    return EngineeringDbSchemaContextResult(
        ok=True,
        query=query,
        suggested_tables=selected_matches,
        relationships=selected_relationships,
        guidance=(
            "Use the suggested tables to scope engineering-db-lookup first. "
            "Only read a note if the DB result is incomplete or a notes path is explicitly useful."
        ),
    )


def _pick_display_column(table: TableSchema) -> str | None:
    for candidate in table.display_columns:
        if candidate in {column.name for column in table.columns}:
            return candidate
    if table.primary_key_columns:
        return table.primary_key_columns[0]
    if table.columns:
        return table.columns[0].name
    return None


def _normalize_candidate_tables(
    candidate_tables: list[str] | None,
    catalog: EngineeringDbSchemaCatalog,
) -> list[TableSchema]:
    if candidate_tables:
        allowed = {table_name.strip() for table_name in candidate_tables if table_name.strip()}
        return [table for table in catalog.tables if table.table_name in allowed]
    return catalog.tables


def _select_attribute_columns(table: TableSchema) -> list[str]:
    preferred = []
    ignored = {"created_at", "updated_at"}
    for column in table.columns:
        name = column.name.lower()
        if name in ignored:
            continue
        if column.name in table.display_columns or column.name in table.primary_key_columns:
            preferred.append(column.name)
            continue
        if len(preferred) >= 6:
            continue
        preferred.append(column.name)
    return preferred[:8]


def engineering_db_lookup(
    query: str,
    candidate_tables: list[str] | None = None,
    max_tables: int = 5,
    max_rows_per_table: int = 5,
) -> EngineeringDbLookupResult:
    catalog = get_engineering_db_schema_catalog()
    if not catalog.ok:
        return EngineeringDbLookupResult(
            ok=False,
            query=query,
            guidance="Unable to query the engineering DB.",
            error=catalog.error,
        )

    scoped_catalog_tables = _normalize_candidate_tables(candidate_tables, catalog)
    if not scoped_catalog_tables:
        schema_context = retrieve_engineering_db_schema_context(query, max_tables=max_tables)
        if not schema_context.ok:
            return EngineeringDbLookupResult(
                ok=False,
                query=query,
                guidance="Unable to determine relevant tables for the engineering DB lookup.",
                error=schema_context.error,
            )
        scoped_names = [item.table_name for item in schema_context.suggested_tables]
        scoped_catalog_tables = [table for table in catalog.tables if table.table_name in scoped_names]
    else:
        scoped_names = [table.table_name for table in scoped_catalog_tables]

    wildcard = f"%{query}%"
    records: list[EngineeringDbRecord] = []

    try:
        conn = get_db_connection()
        for table in scoped_catalog_tables[:max_tables]:
            searchable_columns = table.searchable_columns or table.display_columns or table.primary_key_columns
            if not searchable_columns:
                continue

            where_parts = [
                sql.SQL("{}::text ILIKE %s").format(sql.Identifier(column_name))
                for column_name in searchable_columns
            ]
            score_parts = [
                sql.SQL("CASE WHEN {}::text ILIKE %s THEN 1 ELSE 0 END").format(sql.Identifier(column_name))
                for column_name in searchable_columns
            ]
            display_column = _pick_display_column(table)
            attribute_columns = _select_attribute_columns(table)
            query_sql = sql.SQL(
                "SELECT *, ({score}) AS jarvis_match_score "
                "FROM {table} "
                "WHERE {where_clause} "
                "ORDER BY jarvis_match_score DESC "
                "LIMIT %s"
            ).format(
                score=sql.SQL(" + ").join(score_parts),
                table=sql.Identifier(get_settings().db_schema, table.table_name),
                where_clause=sql.SQL(" OR ").join(where_parts),
            )

            params = [wildcard] * len(searchable_columns)
            params.extend([wildcard] * len(searchable_columns))
            params.append(max_rows_per_table)

            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute(query_sql, params)
            rows = cur.fetchall()
            cur.close()

            related_tables = sorted(
                {
                    relationship.to_table
                    for relationship in catalog.relationships
                    if relationship.from_table == table.table_name
                }
            )

            for row in rows:
                display_value = str(row.get(display_column) or table.table_name)
                key_attributes = {
                    column_name: row.get(column_name)
                    for column_name in attribute_columns
                    if column_name in row and row.get(column_name) is not None
                }
                notes_path = next(
                    (
                        row.get(column_name)
                        for column_name in table.notes_columns
                        if row.get(column_name)
                    ),
                    None,
                )
                summary_parts = [display_value]
                for key, value in list(key_attributes.items())[:3]:
                    if key == display_column:
                        continue
                    summary_parts.append(f"{key}={value}")

                records.append(
                    EngineeringDbRecord(
                        table_name=table.table_name,
                        entity_type=table.table_name,
                        display_name=display_value,
                        summary="; ".join(summary_parts),
                        key_attributes=key_attributes,
                        relationships=[
                            {"related_table": related_table, "relationship_type": "foreign-key"}
                            for related_table in related_tables[:5]
                        ],
                        notes_path=str(notes_path) if notes_path is not None else None,
                        confidence=float(row.get("jarvis_match_score", 0)),
                    )
                )
        conn.close()
    except Exception as exc:
        return EngineeringDbLookupResult(
            ok=False,
            query=query,
            scoped_tables=scoped_names,
            records=[],
            guidance="The engineering DB lookup failed before records could be returned.",
            error=str(exc),
        )

    records.sort(key=lambda item: (item.confidence or 0), reverse=True)

    return EngineeringDbLookupResult(
        ok=True,
        query=query,
        scoped_tables=scoped_names,
        records=records,
        guidance=(
            "Use the returned DB facts first. If a record includes notes_path and deeper context is needed, "
            "call read-note with that path."
        ),
    )
