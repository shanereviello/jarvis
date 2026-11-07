-- Additive transport tables only. Run on an isolated fixture before reviewed install.
-- Does not alter legacy Jarvis tables, history SQLite, credentials, or grants.
BEGIN;
CREATE TABLE linear_bridge.codex_apps (
    organization_id uuid NOT NULL,
    app_user_id uuid NOT NULL,
    PRIMARY KEY (organization_id, app_user_id)
);
CREATE TABLE linear_bridge.codex_sessions (
    organization_id uuid NOT NULL,
    app_user_id uuid NOT NULL,
    session_id uuid NOT NULL,
    issue_id uuid NOT NULL,
    binding jsonb NOT NULL,
    PRIMARY KEY (organization_id, app_user_id, session_id),
    FOREIGN KEY (organization_id, app_user_id)
        REFERENCES linear_bridge.codex_apps(organization_id, app_user_id)
);
CREATE TABLE linear_bridge.codex_events (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL,
    app_user_id uuid NOT NULL,
    session_id uuid NOT NULL,
    source_key text NOT NULL,
    envelope jsonb NOT NULL,
    state text NOT NULL DEFAULT 'pending'
        CHECK (state IN ('pending','dispatching','running','completed','interrupted','failed','uncertain')),
    runtime_result jsonb,
    received_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id,app_user_id,source_key),
    FOREIGN KEY (organization_id,app_user_id,session_id)
        REFERENCES linear_bridge.codex_sessions(organization_id,app_user_id,session_id)
);
CREATE TABLE linear_bridge.codex_deliveries (
    organization_id uuid NOT NULL,
    app_user_id uuid NOT NULL,
    delivery_id uuid NOT NULL,
    body_sha256 text NOT NULL CHECK (body_sha256 ~ '^[0-9a-f]{64}$'),
    event_id uuid NOT NULL REFERENCES linear_bridge.codex_events(id),
    PRIMARY KEY (organization_id,app_user_id,delivery_id)
);
CREATE TABLE linear_bridge.codex_outbox (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL,
    app_user_id uuid NOT NULL,
    session_id uuid NOT NULL,
    source_key text NOT NULL,
    content jsonb NOT NULL,
    state text NOT NULL DEFAULT 'pending' CHECK (state IN ('pending','uncertain','sent','dead_letter')),
    reason text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id,app_user_id,source_key),
    FOREIGN KEY (organization_id,app_user_id,session_id)
        REFERENCES linear_bridge.codex_sessions(organization_id,app_user_id,session_id)
);
CREATE INDEX codex_events_ready ON linear_bridge.codex_events(organization_id,app_user_id,state,received_at);
-- One configured runtime/worktree per app in this slice. Serialize even distinct
-- issues to avoid overlapping edits; stops may coexist with the interrupted turn.
CREATE UNIQUE INDEX codex_one_runtime_executor ON linear_bridge.codex_events
    (organization_id,app_user_id)
    WHERE state IN ('dispatching','running','uncertain')
      AND coalesce(envelope->>'signal','')<>'stop';
CREATE INDEX codex_outbox_ready ON linear_bridge.codex_outbox(organization_id,app_user_id,state,created_at);

CREATE FUNCTION linear_bridge.codex_accept(
    p_org uuid,p_app uuid,p_delivery uuid,p_sha text,p_envelope jsonb
) RETURNS TABLE(event_id uuid,inserted boolean) LANGUAGE plpgsql AS $$
DECLARE v_session uuid; v_issue uuid; v_event uuid; v_prior record; v_context record;
BEGIN
    IF NOT EXISTS (SELECT 1 FROM linear_bridge.codex_apps a
                   WHERE a.organization_id=p_org AND a.app_user_id=p_app) THEN
        RAISE EXCEPTION 'unregistered Codex app';
    END IF;
    IF p_envelope->>'contract' IS DISTINCT FROM 'codex-admitted-event.v1'
       OR p_envelope->>'organization_id' IS DISTINCT FROM p_org::text
       OR p_envelope->>'app_user_id' IS DISTINCT FROM p_app::text
       OR coalesce(p_envelope->>'action','') NOT IN ('created','prompted')
       OR p_envelope->>'source_key' IS NULL OR p_envelope->'binding' IS NULL
       OR coalesce(p_sha,'') !~ '^[0-9a-f]{64}$' THEN RAISE EXCEPTION 'invalid scoped event'; END IF;
    v_session:=(p_envelope->>'session_id')::uuid; v_issue:=(p_envelope->>'issue_id')::uuid;
    -- Serializes same-app intake, including simultaneous duplicate deliveries.
    PERFORM 1 FROM linear_bridge.codex_apps a
      WHERE a.organization_id=p_org AND a.app_user_id=p_app FOR UPDATE;
    SELECT d.*,e.envelope INTO v_prior FROM linear_bridge.codex_deliveries d
      JOIN linear_bridge.codex_events e ON e.id=d.event_id
      WHERE d.organization_id=p_org AND d.app_user_id=p_app AND d.delivery_id=p_delivery;
    IF FOUND THEN
      IF v_prior.body_sha256<>p_sha OR v_prior.envelope<>p_envelope THEN
        RAISE EXCEPTION 'delivery identity changed';
      END IF;
      RETURN QUERY SELECT v_prior.event_id,false; RETURN;
    END IF;
    SELECT s.* INTO v_context FROM linear_bridge.codex_sessions s
      WHERE s.organization_id=p_org AND s.app_user_id=p_app AND s.session_id=v_session;
    IF FOUND AND (v_context.issue_id<>v_issue OR v_context.binding<>p_envelope->'binding') THEN
      RAISE EXCEPTION 'session context changed; use explicit continuation';
    END IF;
    IF NOT FOUND THEN
      IF p_envelope->>'action'<>'created' THEN RAISE EXCEPTION 'created event must be reconciled first'; END IF;
      INSERT INTO linear_bridge.codex_sessions VALUES(p_org,p_app,v_session,v_issue,p_envelope->'binding');
    END IF;
    SELECT e.* INTO v_prior FROM linear_bridge.codex_events e
      WHERE e.organization_id=p_org AND e.app_user_id=p_app
        AND e.source_key=p_envelope->>'source_key';
    IF FOUND THEN
      IF v_prior.envelope<>p_envelope THEN RAISE EXCEPTION 'source identity changed'; END IF;
      v_event:=v_prior.id;
      INSERT INTO linear_bridge.codex_deliveries VALUES(p_org,p_app,p_delivery,p_sha,v_event);
      RETURN QUERY SELECT v_event,false; RETURN;
    END IF;
    INSERT INTO linear_bridge.codex_events(organization_id,app_user_id,session_id,source_key,envelope)
      VALUES(p_org,p_app,v_session,p_envelope->>'source_key',p_envelope) RETURNING id INTO v_event;
    INSERT INTO linear_bridge.codex_deliveries VALUES(p_org,p_app,p_delivery,p_sha,v_event);
    IF p_envelope->>'action'='created' THEN
      INSERT INTO linear_bridge.codex_outbox(organization_id,app_user_id,session_id,source_key,content)
        VALUES(p_org,p_app,v_session,'initial:'||v_event::text,
          '{"type":"thought","body":"Codex received this request. Runtime execution follows the installed permissions and agreed architecture."}'::jsonb);
    END IF;
    RETURN QUERY SELECT v_event,true;
END $$;
-- SECURITY INVOKER is deliberate. Installation grants only the transport role's
-- reviewed privileges. PUBLIC must not receive implicit function execution.
REVOKE ALL ON FUNCTION linear_bridge.codex_accept(uuid,uuid,uuid,text,jsonb) FROM PUBLIC;
COMMIT;
