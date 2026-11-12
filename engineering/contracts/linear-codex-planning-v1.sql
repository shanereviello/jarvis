-- Additive planning-only transport. Install only after isolated acceptance and
-- a separately reviewed production migration. Never writes execution events.
BEGIN;
CREATE TABLE linear_bridge.codex_planning_sessions (
  organization_id uuid NOT NULL, app_user_id uuid NOT NULL, session_id uuid NOT NULL, issue_id uuid NOT NULL,
  PRIMARY KEY (organization_id,app_user_id,session_id),
  FOREIGN KEY (organization_id,app_user_id) REFERENCES linear_bridge.codex_apps(organization_id,app_user_id)
);
CREATE TABLE linear_bridge.codex_planning_events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), organization_id uuid NOT NULL, app_user_id uuid NOT NULL,
  session_id uuid NOT NULL, source_key text NOT NULL, envelope jsonb NOT NULL,
  state text NOT NULL DEFAULT 'pending' CHECK (state IN ('pending','dispatching','running','completed','interrupted','failed','uncertain')),
  runtime_result jsonb,
  received_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (organization_id,app_user_id,source_key),
  FOREIGN KEY (organization_id,app_user_id,session_id) REFERENCES linear_bridge.codex_planning_sessions(organization_id,app_user_id,session_id)
);
CREATE TABLE linear_bridge.codex_planning_deliveries (
  organization_id uuid NOT NULL, app_user_id uuid NOT NULL, delivery_id uuid NOT NULL,
  body_sha256 text NOT NULL CHECK(body_sha256 ~ '^[0-9a-f]{64}$'),
  event_id uuid NOT NULL REFERENCES linear_bridge.codex_planning_events(id),
  PRIMARY KEY(organization_id,app_user_id,delivery_id)
);
CREATE TABLE linear_bridge.codex_planning_outbox (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),organization_id uuid NOT NULL,app_user_id uuid NOT NULL,
  session_id uuid NOT NULL,source_key text NOT NULL,content jsonb NOT NULL,
  state text NOT NULL DEFAULT 'pending' CHECK(state IN ('pending','uncertain','sent','dead_letter')),
  reason text,
  created_at timestamptz NOT NULL DEFAULT now(),updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(organization_id,app_user_id,source_key),
  FOREIGN KEY(organization_id,app_user_id,session_id) REFERENCES linear_bridge.codex_planning_sessions(organization_id,app_user_id,session_id)
);
CREATE UNIQUE INDEX codex_one_planning_executor ON linear_bridge.codex_planning_events (organization_id,app_user_id)
  WHERE state IN ('dispatching','running','uncertain') AND coalesce(envelope->>'signal','')<>'stop';
-- Existing execution intake locks codex_apps before its inserts. These guards
-- make the partition symmetric even if an issue is admitted for execution
-- while an older planning session or delivery is still retained.
CREATE FUNCTION linear_bridge.codex_execution_reject_planning_identity() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_TABLE_NAME='codex_sessions' THEN
    IF EXISTS(SELECT 1 FROM linear_bridge.codex_planning_sessions s WHERE s.organization_id=NEW.organization_id
        AND s.app_user_id=NEW.app_user_id AND s.session_id=NEW.session_id)
      THEN RAISE EXCEPTION 'session already belongs to planning'; END IF;
  ELSIF TG_TABLE_NAME='codex_events' THEN
    IF EXISTS(SELECT 1 FROM linear_bridge.codex_planning_events e WHERE e.organization_id=NEW.organization_id
        AND e.app_user_id=NEW.app_user_id AND e.source_key=NEW.source_key)
      THEN RAISE EXCEPTION 'source already belongs to planning'; END IF;
  ELSIF TG_TABLE_NAME='codex_deliveries' THEN
    IF EXISTS(SELECT 1 FROM linear_bridge.codex_planning_deliveries d WHERE d.organization_id=NEW.organization_id
        AND d.app_user_id=NEW.app_user_id AND d.delivery_id=NEW.delivery_id)
      THEN RAISE EXCEPTION 'delivery already belongs to planning'; END IF;
  END IF;
  RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION linear_bridge.codex_execution_reject_planning_identity() FROM PUBLIC;
CREATE TRIGGER codex_sessions_no_planning BEFORE INSERT ON linear_bridge.codex_sessions
  FOR EACH ROW EXECUTE FUNCTION linear_bridge.codex_execution_reject_planning_identity();
CREATE TRIGGER codex_events_no_planning BEFORE INSERT ON linear_bridge.codex_events
  FOR EACH ROW EXECUTE FUNCTION linear_bridge.codex_execution_reject_planning_identity();
CREATE TRIGGER codex_deliveries_no_planning BEFORE INSERT ON linear_bridge.codex_deliveries
  FOR EACH ROW EXECUTE FUNCTION linear_bridge.codex_execution_reject_planning_identity();
CREATE FUNCTION linear_bridge.codex_planning_accept(p_org uuid,p_app uuid,p_delivery uuid,p_sha text,p_envelope jsonb)
RETURNS TABLE(event_id uuid,inserted boolean) LANGUAGE plpgsql AS $$
DECLARE v_session uuid; v_issue uuid; v_event uuid; v_prior record; v_context record;
BEGIN
  IF p_org IS NULL OR p_app IS NULL OR p_delivery IS NULL OR
     NOT EXISTS(SELECT 1 FROM linear_bridge.codex_apps a WHERE a.organization_id=p_org AND a.app_user_id=p_app)
     THEN RAISE EXCEPTION 'unregistered planning app'; END IF;
  IF p_envelope->>'contract' IS DISTINCT FROM 'codex-planning-event.v1' OR p_envelope->>'mode' IS DISTINCT FROM 'planning'
     OR p_envelope ? 'binding' OR p_envelope->>'organization_id' IS DISTINCT FROM p_org::text
     OR p_envelope->>'app_user_id' IS DISTINCT FROM p_app::text OR coalesce(p_envelope->>'action','') NOT IN ('created','prompted')
     OR coalesce(p_envelope->>'source_key','')='' OR coalesce(p_sha,'') !~ '^[0-9a-f]{64}$'
     THEN RAISE EXCEPTION 'invalid planning event'; END IF;
  v_session:=(p_envelope->>'session_id')::uuid;v_issue:=(p_envelope->>'issue_id')::uuid;
  IF v_session IS NULL OR v_issue IS NULL THEN RAISE EXCEPTION 'planning context required'; END IF;
  PERFORM 1 FROM linear_bridge.codex_apps a WHERE a.organization_id=p_org AND a.app_user_id=p_app FOR UPDATE;
  IF EXISTS(SELECT 1 FROM linear_bridge.codex_deliveries d WHERE d.organization_id=p_org AND d.app_user_id=p_app AND d.delivery_id=p_delivery)
     THEN RAISE EXCEPTION 'delivery already belongs to execution'; END IF;
  IF EXISTS(SELECT 1 FROM linear_bridge.codex_sessions s WHERE s.organization_id=p_org AND s.app_user_id=p_app AND s.session_id=v_session)
     OR EXISTS(SELECT 1 FROM linear_bridge.codex_events e WHERE e.organization_id=p_org AND e.app_user_id=p_app AND e.source_key=p_envelope->>'source_key')
     THEN RAISE EXCEPTION 'planning context already belongs to execution'; END IF;
  SELECT d.*,e.envelope INTO v_prior FROM linear_bridge.codex_planning_deliveries d
    JOIN linear_bridge.codex_planning_events e ON e.id=d.event_id
    WHERE d.organization_id=p_org AND d.app_user_id=p_app AND d.delivery_id=p_delivery;
  IF FOUND THEN
    IF v_prior.body_sha256<>p_sha OR v_prior.envelope<>p_envelope THEN RAISE EXCEPTION 'delivery identity changed'; END IF;
    RETURN QUERY SELECT v_prior.event_id,false; RETURN;
  END IF;
  SELECT s.* INTO v_context FROM linear_bridge.codex_planning_sessions s
    WHERE s.organization_id=p_org AND s.app_user_id=p_app AND s.session_id=v_session;
  IF FOUND AND v_context.issue_id<>v_issue THEN RAISE EXCEPTION 'planning session context changed'; END IF;
  IF NOT FOUND THEN
    IF p_envelope->>'action'<>'created' THEN RAISE EXCEPTION 'created event must be reconciled first'; END IF;
    INSERT INTO linear_bridge.codex_planning_sessions VALUES(p_org,p_app,v_session,v_issue);
  END IF;
  SELECT e.* INTO v_prior FROM linear_bridge.codex_planning_events e
    WHERE e.organization_id=p_org AND e.app_user_id=p_app AND e.source_key=p_envelope->>'source_key';
  IF FOUND THEN
    IF v_prior.envelope<>p_envelope THEN RAISE EXCEPTION 'source identity changed'; END IF;
    v_event:=v_prior.id;
    INSERT INTO linear_bridge.codex_planning_deliveries VALUES(p_org,p_app,p_delivery,p_sha,v_event);
    RETURN QUERY SELECT v_event,false; RETURN;
  END IF;
  INSERT INTO linear_bridge.codex_planning_events(organization_id,app_user_id,session_id,source_key,envelope)
    VALUES(p_org,p_app,v_session,p_envelope->>'source_key',p_envelope) RETURNING id INTO v_event;
  INSERT INTO linear_bridge.codex_planning_deliveries VALUES(p_org,p_app,p_delivery,p_sha,v_event);
  IF p_envelope->>'action'='created' THEN
    INSERT INTO linear_bridge.codex_planning_outbox(organization_id,app_user_id,session_id,source_key,content)
      VALUES(p_org,p_app,v_session,'initial:'||v_event::text,
        '{"type":"thought","body":"Codex received this planning request. The architecture will remain a draft until you approve it."}'::jsonb);
  END IF;
  RETURN QUERY SELECT v_event,true;
END $$;
REVOKE ALL ON FUNCTION linear_bridge.codex_planning_accept(uuid,uuid,uuid,text,jsonb) FROM PUBLIC;
COMMIT;
