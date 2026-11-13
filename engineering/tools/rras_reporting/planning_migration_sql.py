"""Build one guarded PostgreSQL planning migration; never connect or execute it."""
import hashlib

SCHEMA_SHA256 = 'a36b974ced5b5c84ca96fee1486b8ed46227c749a493b1efe3c319718ba6ea2e'
GRANTS_SHA256 = '23ec64063687e8382f8b7c65e02831898c8f18b56d7ef1a4a3ed1d1b7ce365ef'


def inner(data, expected):
    if type(data) is not bytes or hashlib.sha256(data).hexdigest() != expected:
        raise ValueError('exact reviewed migration input required')
    text = data.decode('utf-8').strip()
    if not text.endswith('COMMIT;'):
        raise ValueError('transactional migration required')
    begin = text.find('BEGIN;')
    if begin < 0 or any(not line.lstrip().startswith('--') and line.strip() for line in text[:begin].splitlines()):
        raise ValueError('one outer migration transaction required')
    return text[begin + len('BEGIN;'):-len('COMMIT;')]


def build(schema, grants):
    schema_sql = inner(schema, SCHEMA_SHA256)
    grants_sql = inner(grants, GRANTS_SHA256)
    return '''BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '30s';
LOCK TABLE linear_bridge.codex_apps, linear_bridge.codex_sessions, linear_bridge.codex_events,
  linear_bridge.codex_deliveries, linear_bridge.codex_outbox IN ACCESS EXCLUSIVE MODE;
DO $guard$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='n8n_user') THEN RAISE EXCEPTION 'n8n role absent'; END IF;
  IF NOT EXISTS (SELECT 1 FROM linear_bridge.codex_apps WHERE
    organization_id='49caeb3f-bbf7-429d-83f6-7ab4de8c8bba'::uuid AND
    app_user_id='b5285a48-728b-4d3b-a962-77ac3ed61a5c'::uuid)
    THEN RAISE EXCEPTION 'selected app absent'; END IF;
  IF EXISTS (SELECT 1 FROM linear_bridge.codex_events WHERE state IN ('pending','dispatching','running','uncertain'))
    THEN RAISE EXCEPTION 'execution queue is not idle'; END IF;
END $guard$;
''' + schema_sql + '\n' + grants_sql + '''
DO $verify$
BEGIN
  IF EXISTS (SELECT 1 FROM (VALUES
       ('codex_planning_events','SELECT'), ('codex_planning_events','INSERT'), ('codex_planning_events','UPDATE'),
       ('codex_planning_outbox','SELECT'), ('codex_planning_outbox','INSERT'), ('codex_planning_outbox','UPDATE'),
       ('codex_planning_sessions','SELECT'), ('codex_planning_sessions','INSERT'),
       ('codex_planning_deliveries','SELECT'), ('codex_planning_deliveries','INSERT')
     ) required(name,privilege) WHERE NOT has_table_privilege('n8n_user','linear_bridge.' || name,privilege)) OR
     NOT has_function_privilege('n8n_user','linear_bridge.codex_planning_accept(uuid,uuid,uuid,text,jsonb)','EXECUTE') OR
     has_table_privilege('n8n_user','linear_bridge.codex_planning_events','DELETE') OR
     has_table_privilege('n8n_user','linear_bridge.codex_planning_outbox','DELETE')
     THEN RAISE EXCEPTION 'planning permissions differ'; END IF;
END $verify$;
COMMIT;
'''
