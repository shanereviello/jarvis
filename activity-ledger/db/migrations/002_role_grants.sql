BEGIN;

SET ROLE jarvis_activity_owner;

-- Bring the read/reporting and logical-backup roles up to date for tables
-- introduced before their role grants were applied, including administrative
-- ledger tables.
GRANT USAGE ON SCHEMA activity TO jarvis_activity_reader, jarvis_activity_backup;
GRANT SELECT ON ALL TABLES IN SCHEMA activity TO jarvis_activity_reader, jarvis_activity_backup;
GRANT SELECT ON ALL SEQUENCES IN SCHEMA activity TO jarvis_activity_backup;

-- Preserve least privilege for existing objects; neither role is a writer or
-- schema administrator.
REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
    ON ALL TABLES IN SCHEMA activity
    FROM jarvis_activity_reader, jarvis_activity_backup;
REVOKE CREATE ON SCHEMA activity FROM jarvis_activity_reader, jarvis_activity_backup;
REVOKE USAGE, UPDATE ON ALL SEQUENCES IN SCHEMA activity
    FROM jarvis_activity_reader, jarvis_activity_backup;
GRANT SELECT ON ALL SEQUENCES IN SCHEMA activity TO jarvis_activity_backup;

-- Pre-production correction: runtime evidence showed these grants had been
-- applied while version 2 was absent from the ledger. This candidate was not
-- accepted as a production migration, so the version record is repaired
-- atomically with the grants. Recorded production migrations are immutable.
INSERT INTO activity.schema_migrations(version) VALUES (2)
ON CONFLICT (version) DO NOTHING;

RESET ROLE;
COMMIT;
