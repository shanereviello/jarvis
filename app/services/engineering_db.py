from __future__ import annotations

import re
from collections import defaultdict

import psycopg2
from psycopg2 import sql
from psycopg2.extras import RealDictCursor

from app.core.config import get_settings
from app.schemas.engineering_db import (
    ColumnSchema,
    EngineeringDbConnectionLookupResult,
    EngineeringDbConnectionRecord,
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
IDENTIFIER_COLUMN_CANDIDATES = (
    "component_id",
    "interface_id",
    "part_number",
    "part_no",
    "label",
    "name",
    "pin_number",
    "cable_id",
    "wire_id",
    "jack_a",
    "jack_b",
)


# These heuristics are the main place to customize the "knowledge map" of your DB.
# If your real schema uses different table meanings or naming patterns, edit the
# helper functions below rather than scattering special cases across the lookup code.
ENTITY_HINT_PATTERNS = {
    "component": ("component", "device", "board", "sensor", "controller", "connector"),
    "interface": ("interface", "port", "pinout", "pin"),
    "wire": ("wire", "termination", "signal", "jack"),
    "cable": ("cable", "harness", "assembly"),
}


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


def _describe_table_purpose(table_name: str, columns: list[ColumnSchema]) -> str:
    lower_name = table_name.lower()
    column_names = {column.name.lower() for column in columns}
    if "interface" in lower_name:
        return "Connection and interface endpoints associated with components."
    if "wire" in lower_name:
        return "Wire or termination data that describes point-to-point electrical connections."
    if "cable" in lower_name:
        return "Cable assemblies and bundle-level connection records."
    if "component" in lower_name:
        return "Component inventory records including names, labels, part numbers, and note paths."
    if "part_number" in column_names:
        return "Engineering part records keyed by part numbers and human-readable names."
    return "General engineering table containing searchable structured records."


def _infer_entity_type(table_name: str, columns: list[ColumnSchema]) -> str:
    # Customize this if your DB has table names that do not follow obvious naming patterns.
    lower_name = table_name.lower()
    column_names = {column.name.lower() for column in columns}
    for entity_type, patterns in ENTITY_HINT_PATTERNS.items():
        if any(pattern in lower_name for pattern in patterns):
            return entity_type
    if "part_number" in column_names:
        return "component"
    return "record"


def _infer_lookup_examples(table_name: str, columns: list[ColumnSchema]) -> list[str]:
    lower_name = table_name.lower()
    examples: list[str] = []
    if "component" in lower_name:
        examples.extend(["Raspberry Pi B4", "RPI4B", "XT60"])
    if "interface" in lower_name:
        examples.extend(["A2A1P2", "UART0", "GPIO-14"])
    if "wire" in lower_name:
        examples.extend(["W001", "24V sense wire"])
    if "cable" in lower_name:
        examples.extend(["W001", "camera harness"])
    if not examples and any(column.name.lower() == "part_number" for column in columns):
        examples.append("part number")
    return examples[:4]


def _infer_common_question_types(table_name: str, entity_type: str) -> list[str]:
    # Customize these prompts/examples to mirror how *you* naturally ask questions of each table.
    lower_name = table_name.lower()
    if entity_type == "component":
        return [
            "find component by name, label, or part number",
            "get component metadata and note path",
            "identify likely matching hardware record",
        ]
    if entity_type == "interface":
        return [
            "find interfaces belonging to a component",
            "look up interface pin or label details",
            "inspect interface notes or connection endpoints",
        ]
    if entity_type == "wire":
        return [
            "find where a wire terminates",
            "inspect wire purpose or endpoints",
            "trace point-to-point electrical connections",
        ]
    if entity_type == "cable":
        return [
            "find cable assembly records",
            "inspect a harness or cable purpose",
            "relate cable records to contained wire connections",
        ]
    return ["perform general engineering record lookup"]


def _infer_best_lookup_columns(
    columns: list[ColumnSchema],
    searchable_columns: list[str],
    display_columns: list[str],
    common_identifiers: list[str],
) -> list[str]:
    # This is one of the highest-value tuning points. If your DB has better "entry"
    # columns for each table, update the priority logic here.
    ordered: list[str] = []

    def add(column_name: str) -> None:
        if column_name and column_name not in ordered:
            ordered.append(column_name)

    for column_name in common_identifiers:
        add(column_name)
    for column_name in display_columns:
        add(column_name)
    for column_name in searchable_columns:
        add(column_name)

    return ordered[:6]


def _infer_related_tables(
    table_name: str,
    relationships: list[TableRelationship],
) -> list[str]:
    related = sorted(
        {
            relationship.to_table
            for relationship in relationships
            if relationship.from_table == table_name
        }
        | {
            relationship.from_table
            for relationship in relationships
            if relationship.to_table == table_name
        }
    )
    return related


def _infer_recommended_followup_tables(
    entity_type: str,
    related_tables: list[str],
) -> list[str]:
    # Customize follow-up preferences here if your DB has preferred traversal paths.
    ranked: list[str] = []
    priorities = {
        "component": ("interfaces", "wire_list", "cable_assemblys"),
        "interface": ("components", "wire_list"),
        "wire": ("components", "cable_assemblys", "interfaces"),
        "cable": ("wire_list", "components"),
        "gpio": ("components", "interfaces"),
    }
    for candidate in priorities.get(entity_type, ()):
        if candidate in related_tables and candidate not in ranked:
            ranked.append(candidate)
    for table_name in related_tables:
        if table_name not in ranked:
            ranked.append(table_name)
    return ranked[:5]


def _build_search_variants(search_term: str) -> list[str]:
    raw = (search_term or "").strip()
    if not raw:
        return []

    variants: list[str] = []

    def add(value: str) -> None:
        normalized = value.strip()
        if normalized and normalized not in variants:
            variants.append(normalized)

    add(raw)
    add(raw.strip("\"'"))
    compact = re.sub(r"[^A-Za-z0-9]+", "", raw)
    add(compact)
    spaced_alnum = re.sub(r"([A-Za-z])(\d)", r"\1 \2", raw)
    spaced_alnum = re.sub(r"(\d)([A-Za-z])", r"\1 \2", spaced_alnum)
    add(spaced_alnum)
    collapsed_spaces = " ".join(TOKEN_RE.findall(raw))
    add(collapsed_spaces)
    return variants[:5]


def _field_requested(requested_fields: list[str], field_name: str) -> bool:
    if not requested_fields:
        return True
    requested = {item.lower() for item in requested_fields}
    return field_name.lower() in requested


def _filter_key_attributes(
    key_attributes: dict[str, object],
    requested_fields: list[str],
) -> dict[str, object]:
    if not requested_fields:
        return key_attributes
    requested = {item.lower() for item in requested_fields}
    return {
        key: value
        for key, value in key_attributes.items()
        if key.lower() in requested
    }


def _filter_connection_row(
    row: dict[str, object],
    requested_fields: list[str],
) -> dict[str, object]:
    if not requested_fields:
        return row
    requested = {item.lower() for item in requested_fields}
    return {
        key: value
        for key, value in row.items()
        if key.lower() in requested or key in {"wire_id", "cable_assy_id"}
    }


def _score_table_for_hint(table: TableSchema, entity_hint: str | None) -> int:
    if not entity_hint:
        return 0
    hint_tokens = _tokenize(entity_hint)
    purpose_tokens = _tokenize(table.table_purpose)
    table_tokens = _tokenize(table.table_name.replace("_", " "))
    return len(hint_tokens & purpose_tokens) + (2 * len(hint_tokens & table_tokens))


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
        common_identifiers = [
            column.name
            for column in columns
            if column.name.lower() in IDENTIFIER_COLUMN_CANDIDATES
        ]
        display_columns = [
            candidate
            for candidate in DISPLAY_COLUMN_CANDIDATES
            if any(column.name.lower() == candidate for column in columns)
        ]
        entity_type = _infer_entity_type(table_name, columns)
        related_tables = _infer_related_tables(table_name, relationships)
        best_lookup_columns = _infer_best_lookup_columns(
            columns=columns,
            searchable_columns=searchable_columns,
            display_columns=display_columns,
            common_identifiers=common_identifiers,
        )
        tables.append(
            TableSchema(
                table_name=table_name,
                columns=list(columns),
                primary_key_columns=primary_key_columns,
                searchable_columns=searchable_columns,
                best_lookup_columns=best_lookup_columns,
                notes_columns=notes_columns,
                display_columns=display_columns,
                foreign_keys=relationships_by_table.get(table_name, []),
                entity_type=entity_type,
                table_purpose=_describe_table_purpose(table_name, columns),
                common_question_types=_infer_common_question_types(table_name, entity_type),
                common_identifiers=common_identifiers,
                related_tables=related_tables,
                recommended_followup_tables=_infer_recommended_followup_tables(entity_type, related_tables),
                lookup_examples=_infer_lookup_examples(table_name, columns),
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
    entity_hint: str | None = None,
) -> list[TableSchema]:
    if candidate_tables:
        allowed = {table_name.strip() for table_name in candidate_tables if table_name.strip()}
        return [table for table in catalog.tables if table.table_name in allowed]
    if entity_hint:
        ranked = sorted(
            catalog.tables,
            key=lambda table: _score_table_for_hint(table, entity_hint),
            reverse=True,
        )
        if ranked and _score_table_for_hint(ranked[0], entity_hint) > 0:
            return [table for table in ranked if _score_table_for_hint(table, entity_hint) > 0]
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
    search_term: str,
    candidate_tables: list[str] | None = None,
    requested_fields: list[str] | None = None,
    entity_hint: str | None = None,
    follow_relationships: bool = False,
    max_tables: int = 5,
    max_rows_per_table: int = 5,
) -> EngineeringDbLookupResult:
    catalog = get_engineering_db_schema_catalog()
    requested_fields = requested_fields or []
    search_terms_tried = _build_search_variants(search_term)
    if not catalog.ok:
        return EngineeringDbLookupResult(
            ok=False,
            search_term=search_term,
            requested_fields=requested_fields,
            entity_hint=entity_hint,
            follow_relationships=follow_relationships,
            search_terms_tried=search_terms_tried,
            guidance="Unable to query the engineering DB.",
            error=catalog.error,
        )

    scoped_catalog_tables = _normalize_candidate_tables(candidate_tables, catalog, entity_hint=entity_hint)
    if not scoped_catalog_tables:
        schema_context = retrieve_engineering_db_schema_context(search_term, max_tables=max_tables)
        if not schema_context.ok:
            return EngineeringDbLookupResult(
                ok=False,
                search_term=search_term,
                requested_fields=requested_fields,
                entity_hint=entity_hint,
                follow_relationships=follow_relationships,
                search_terms_tried=search_terms_tried,
                guidance="Unable to determine relevant tables for the engineering DB lookup.",
                error=schema_context.error,
            )
        scoped_names = [item.table_name for item in schema_context.suggested_tables]
        scoped_catalog_tables = [table for table in catalog.tables if table.table_name in scoped_names]
    else:
        scoped_names = [table.table_name for table in scoped_catalog_tables]

    records: list[EngineeringDbRecord] = []

    try:
        conn = get_db_connection()
        for table in scoped_catalog_tables[:max_tables]:
            searchable_columns = table.searchable_columns or table.display_columns or table.primary_key_columns
            if not searchable_columns:
                continue

            where_parts = []
            score_parts = []
            where_params: list[object] = []
            score_params: list[object] = []
            for column_name in searchable_columns:
                variant_checks = []
                for variant in search_terms_tried:
                    wildcard = f"%{variant}%"
                    variant_checks.append(
                        sql.SQL("{}::text ILIKE %s").format(sql.Identifier(column_name))
                    )
                    where_params.append(wildcard)
                    score_parts.append(
                        sql.SQL("CASE WHEN {}::text ILIKE %s THEN 1 ELSE 0 END").format(sql.Identifier(column_name))
                    )
                    score_params.append(wildcard)
                if variant_checks:
                    where_parts.append(sql.SQL("(") + sql.SQL(" OR ").join(variant_checks) + sql.SQL(")"))

            if not where_parts:
                continue

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

            params = score_params + where_params + [max_rows_per_table]

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
                key_attributes = _filter_key_attributes(key_attributes, requested_fields)
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
                if follow_relationships and related_tables:
                    summary_parts.append(f"related_tables={', '.join(related_tables[:3])}")

                if _field_requested(requested_fields, "notes") or _field_requested(requested_fields, "notes_path"):
                    if notes_path is not None and "notes" not in key_attributes and "notes_path" not in key_attributes:
                        key_attributes["notes_path"] = str(notes_path)

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
            search_term=search_term,
            scoped_tables=scoped_names,
            records=[],
            requested_fields=requested_fields,
            entity_hint=entity_hint,
            follow_relationships=follow_relationships,
            search_terms_tried=search_terms_tried,
            guidance="The engineering DB lookup failed before records could be returned.",
            error=str(exc),
        )

    records.sort(key=lambda item: (item.confidence or 0), reverse=True)

    return EngineeringDbLookupResult(
        ok=True,
        search_term=search_term,
        scoped_tables=scoped_names,
        records=records,
        requested_fields=requested_fields,
        entity_hint=entity_hint,
        follow_relationships=follow_relationships,
        search_terms_tried=search_terms_tried,
        guidance=(
            "Use the returned DB facts first. Pass only a short search term into this tool. "
            "If a record includes notes_path and deeper context is needed, call read-note with that exact path."
        ),
    )


def engineering_db_connection_lookup(
    cable_assy_id: str,
    endpoint_component: str | None = None,
    endpoint_jack: str | None = None,
    requested_fields: list[str] | None = None,
    max_rows: int = 50,
) -> EngineeringDbConnectionLookupResult:
    requested_fields = requested_fields or []

    # Tune this query path if your real wire endpoint rules become more specific.
    # Right now this is intentionally deterministic and maps directly onto wire_list.
    lookup_sql = """
    SELECT
        wire_id,
        cable_assy_id,
        component_a,
        jack_a,
        component_b,
        jack_b,
        wire_purpose
    FROM wire_list
    WHERE cable_assy_id = %s
      AND (
        (%s IS NULL AND %s IS NULL)
        OR (%s IS NOT NULL AND %s IS NOT NULL AND component_a = %s AND jack_a = %s)
        OR (%s IS NOT NULL AND %s IS NOT NULL AND component_b = %s AND jack_b = %s)
      )
    ORDER BY wire_id
    LIMIT %s;
    """

    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            lookup_sql,
            (
                cable_assy_id,
                endpoint_component,
                endpoint_jack,
                endpoint_component,
                endpoint_jack,
                endpoint_component,
                endpoint_jack,
                endpoint_component,
                endpoint_jack,
                endpoint_component,
                endpoint_jack,
                max_rows,
            ),
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()
    except Exception as exc:
        return EngineeringDbConnectionLookupResult(
            ok=False,
            cable_assy_id=cable_assy_id,
            endpoint_component=endpoint_component,
            endpoint_jack=endpoint_jack,
            requested_fields=requested_fields,
            guidance="The engineering DB connection lookup failed before exact wire rows could be returned.",
            error=str(exc),
        )

    records: list[EngineeringDbConnectionRecord] = []
    for raw_row in rows:
        row = dict(raw_row)
        matched_side = None
        other_end_component = row.get("component_b")
        other_end_jack = row.get("jack_b")

        if endpoint_component and endpoint_jack:
            if row.get("component_a") == endpoint_component and row.get("jack_a") == endpoint_jack:
                matched_side = "a"
                other_end_component = row.get("component_b")
                other_end_jack = row.get("jack_b")
            elif row.get("component_b") == endpoint_component and row.get("jack_b") == endpoint_jack:
                matched_side = "b"
                other_end_component = row.get("component_a")
                other_end_jack = row.get("jack_a")

        filtered_row = _filter_connection_row(
            {
                "wire_id": row.get("wire_id"),
                "cable_assy_id": row.get("cable_assy_id"),
                "component_a": row.get("component_a"),
                "jack_a": row.get("jack_a"),
                "component_b": row.get("component_b"),
                "jack_b": row.get("jack_b"),
                "wire_purpose": row.get("wire_purpose"),
                "matched_side": matched_side,
                "other_end_component": other_end_component,
                "other_end_jack": other_end_jack,
            },
            requested_fields,
        )

        # Keep the strongly answer-bearing fields even when requested_fields is narrow.
        records.append(
            EngineeringDbConnectionRecord(
                wire_id=filtered_row.get("wire_id"),
                cable_assy_id=str(filtered_row.get("cable_assy_id") or cable_assy_id),
                component_a=filtered_row.get("component_a"),
                jack_a=filtered_row.get("jack_a"),
                component_b=filtered_row.get("component_b"),
                jack_b=filtered_row.get("jack_b"),
                wire_purpose=filtered_row.get("wire_purpose"),
                matched_side=filtered_row.get("matched_side"),
                other_end_component=filtered_row.get("other_end_component"),
                other_end_jack=filtered_row.get("other_end_jack"),
            )
        )

    return EngineeringDbConnectionLookupResult(
        ok=True,
        cable_assy_id=cable_assy_id,
        endpoint_component=endpoint_component,
        endpoint_jack=endpoint_jack,
        requested_fields=requested_fields,
        records=records,
        guidance=(
            "Use this tool for exact cable and endpoint traversal questions. "
            "It reads wire_list directly so fields like wire_purpose come from the matched wire row."
        ),
    )
