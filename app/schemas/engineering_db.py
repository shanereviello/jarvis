from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass(slots=True)
class ColumnSchema:
    name: str
    data_type: str
    is_nullable: bool
    is_primary_key: bool = False
    is_foreign_key: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(slots=True)
class TableRelationship:
    from_table: str
    from_column: str
    to_table: str
    to_column: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(slots=True)
class TableSchema:
    table_name: str
    columns: list[ColumnSchema] = field(default_factory=list)
    primary_key_columns: list[str] = field(default_factory=list)
    searchable_columns: list[str] = field(default_factory=list)
    notes_columns: list[str] = field(default_factory=list)
    display_columns: list[str] = field(default_factory=list)
    foreign_keys: list[TableRelationship] = field(default_factory=list)
    table_purpose: str = ""
    common_identifiers: list[str] = field(default_factory=list)
    lookup_examples: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "table_name": self.table_name,
            "columns": [column.to_dict() for column in self.columns],
            "primary_key_columns": self.primary_key_columns,
            "searchable_columns": self.searchable_columns,
            "notes_columns": self.notes_columns,
            "display_columns": self.display_columns,
            "foreign_keys": [relationship.to_dict() for relationship in self.foreign_keys],
            "table_purpose": self.table_purpose,
            "common_identifiers": self.common_identifiers,
            "lookup_examples": self.lookup_examples,
        }


@dataclass(slots=True)
class EngineeringDbSchemaCatalog:
    ok: bool
    schema_name: str
    tables: list[TableSchema] = field(default_factory=list)
    relationships: list[TableRelationship] = field(default_factory=list)
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "schema_name": self.schema_name,
            "tables": [table.to_dict() for table in self.tables],
            "relationships": [relationship.to_dict() for relationship in self.relationships],
            "error": self.error,
        }


@dataclass(slots=True)
class EngineeringDbSchemaContextMatch:
    table_name: str
    score: int
    reason: str
    searchable_columns: list[str] = field(default_factory=list)
    notes_columns: list[str] = field(default_factory=list)
    related_tables: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(slots=True)
class EngineeringDbSchemaContextResult:
    ok: bool
    query: str
    suggested_tables: list[EngineeringDbSchemaContextMatch] = field(default_factory=list)
    relationships: list[TableRelationship] = field(default_factory=list)
    guidance: str = ""
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "query": self.query,
            "suggested_tables": [item.to_dict() for item in self.suggested_tables],
            "relationships": [relationship.to_dict() for relationship in self.relationships],
            "guidance": self.guidance,
            "error": self.error,
        }


@dataclass(slots=True)
class EngineeringDbRecord:
    table_name: str
    entity_type: str
    display_name: str
    summary: str
    key_attributes: dict[str, object] = field(default_factory=dict)
    relationships: list[dict[str, str]] = field(default_factory=list)
    notes_path: str | None = None
    confidence: float | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(slots=True)
class EngineeringDbLookupResult:
    ok: bool
    search_term: str
    scoped_tables: list[str] = field(default_factory=list)
    records: list[EngineeringDbRecord] = field(default_factory=list)
    requested_fields: list[str] = field(default_factory=list)
    entity_hint: str | None = None
    follow_relationships: bool = False
    search_terms_tried: list[str] = field(default_factory=list)
    guidance: str = ""
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "search_term": self.search_term,
            "scoped_tables": self.scoped_tables,
            "records": [record.to_dict() for record in self.records],
            "requested_fields": self.requested_fields,
            "entity_hint": self.entity_hint,
            "follow_relationships": self.follow_relationships,
            "search_terms_tried": self.search_terms_tried,
            "guidance": self.guidance,
            "error": self.error,
        }
