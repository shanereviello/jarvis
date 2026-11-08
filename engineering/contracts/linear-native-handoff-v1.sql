-- Additive, explicit two-agent handoff transport. Install after Codex transport.
-- No existing Jarvis row, workflow, credential or grant is changed here.
BEGIN;
CREATE TABLE linear_bridge.native_handoff_apps (
 organization_id uuid NOT NULL, role text NOT NULL CHECK(role IN ('jarvis','codex')),
 app_user_id uuid NOT NULL, PRIMARY KEY(organization_id,role), UNIQUE(organization_id,app_user_id)
);
CREATE TABLE linear_bridge.native_handoff_issues (
 organization_id uuid NOT NULL, issue_id uuid NOT NULL, binding jsonb NOT NULL,
 PRIMARY KEY(organization_id,issue_id)
);
CREATE TABLE linear_bridge.native_handoffs (
 id uuid PRIMARY KEY, organization_id uuid NOT NULL, sender text NOT NULL, recipient text NOT NULL,
 source_session_id uuid NOT NULL, issue_id uuid NOT NULL, body jsonb NOT NULL,
 comment_id uuid NOT NULL UNIQUE, comment_body text NOT NULL,
 parent_handoff_id uuid REFERENCES linear_bridge.native_handoffs(id), depth integer NOT NULL CHECK(depth BETWEEN 1 AND 4),
 source_quiescence jsonb, comment_state text NOT NULL DEFAULT 'pending' CHECK(comment_state IN ('pending','uncertain','confirmed')),
 session_state text NOT NULL DEFAULT 'blocked' CHECK(session_state IN ('blocked','pending','uncertain','bound')),
 target_session_id uuid UNIQUE,
 state text NOT NULL DEFAULT 'requested' CHECK(state IN ('requested','acknowledged','completed','declined')),
 result text, created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
 CHECK(sender<>recipient), FOREIGN KEY(organization_id,sender) REFERENCES linear_bridge.native_handoff_apps(organization_id,role),
 FOREIGN KEY(organization_id,recipient) REFERENCES linear_bridge.native_handoff_apps(organization_id,role),
 FOREIGN KEY(organization_id,issue_id) REFERENCES linear_bridge.native_handoff_issues(organization_id,issue_id)
);
CREATE UNIQUE INDEX native_handoff_one_active_source ON linear_bridge.native_handoffs(organization_id,sender,source_session_id)
 WHERE state IN ('requested','acknowledged');
CREATE FUNCTION linear_bridge.native_handoff_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'retained handoff intent is immutable'; END $$;
CREATE TRIGGER native_handoff_no_delete BEFORE DELETE ON linear_bridge.native_handoffs
 FOR EACH ROW EXECUTE FUNCTION linear_bridge.native_handoff_immutable();
CREATE TRIGGER native_handoff_fixed_context BEFORE UPDATE OF id,organization_id,sender,recipient,source_session_id,
 issue_id,body,comment_id,comment_body,parent_handoff_id,depth ON linear_bridge.native_handoffs
 FOR EACH ROW EXECUTE FUNCTION linear_bridge.native_handoff_immutable();
CREATE TABLE linear_bridge.native_handoff_events (
 sequence bigserial PRIMARY KEY, id uuid NOT NULL REFERENCES linear_bridge.native_handoffs(id),
 organization_id uuid NOT NULL, state text NOT NULL, snapshot jsonb NOT NULL,
 observed_at timestamptz NOT NULL DEFAULT now(), UNIQUE(id,state)
);
CREATE TRIGGER native_handoff_events_no_update BEFORE UPDATE OR DELETE ON linear_bridge.native_handoff_events
 FOR EACH ROW EXECUTE FUNCTION linear_bridge.native_handoff_immutable();
CREATE FUNCTION linear_bridge.native_handoff_event() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 INSERT INTO linear_bridge.native_handoff_events(id,organization_id,state,snapshot)
  VALUES(NEW.id,NEW.organization_id,NEW.state,to_jsonb(NEW)) ON CONFLICT(id,state) DO NOTHING;
 RETURN NEW;
END $$;
CREATE TRIGGER native_handoff_recorded_state AFTER INSERT OR UPDATE OF state ON linear_bridge.native_handoffs
 FOR EACH ROW EXECUTE FUNCTION linear_bridge.native_handoff_event();

CREATE FUNCTION linear_bridge.native_handoff_request(p_org uuid,p_sender text,p_body jsonb,p_comment text)
 RETURNS uuid LANGUAGE plpgsql AS $$
DECLARE v_id uuid; v_issue uuid; v_session uuid; v_recipient text; v_binding jsonb; v_old record; v_parent record;
BEGIN
 IF p_sender NOT IN ('jarvis','codex') OR p_body->>'contract' IS DISTINCT FROM 'native-agent-handoff.v1'
  OR p_body->>'organization_id' IS DISTINCT FROM p_org::text OR p_body->>'sender' IS DISTINCT FROM p_sender
  OR p_body->'execution_authority_granted' IS DISTINCT FROM 'false'::jsonb
  OR p_body->'human_approval_inferred' IS DISTINCT FROM 'false'::jsonb
  OR octet_length(p_body::text)>32768 OR octet_length(p_comment)>49152 THEN RAISE EXCEPTION 'invalid bounded handoff intent'; END IF;
 v_id:=(p_body->>'id')::uuid; v_issue:=(p_body->>'issue_id')::uuid; v_session:=(p_body->>'source_session_id')::uuid;
 v_recipient:=CASE WHEN p_sender='jarvis' THEN 'codex' ELSE 'jarvis' END;
 IF p_body->>'recipient' IS DISTINCT FROM v_recipient OR NOT EXISTS (
  SELECT 1 FROM linear_bridge.native_handoff_apps s JOIN linear_bridge.native_handoff_apps t ON s.organization_id=t.organization_id
  WHERE s.organization_id=p_org AND s.role=p_sender AND t.role=v_recipient
   AND s.app_user_id::text=p_body->>'sender_app_user_id' AND t.app_user_id::text=p_body->>'recipient_app_user_id')
 THEN RAISE EXCEPTION 'wrong native handoff identities'; END IF;
 SELECT binding INTO v_binding FROM linear_bridge.native_handoff_issues WHERE organization_id=p_org AND issue_id=v_issue;
 IF v_binding IS NULL OR v_binding<>p_body->'binding' THEN RAISE EXCEPTION 'unmapped or changed work/architecture'; END IF;
 IF p_sender='codex' THEN
  IF NOT EXISTS (SELECT 1 FROM linear_bridge.codex_sessions s WHERE s.organization_id=p_org
   AND s.app_user_id::text=p_body->>'sender_app_user_id' AND s.session_id=v_session AND s.issue_id=v_issue AND s.binding=v_binding)
  THEN RAISE EXCEPTION 'actual Codex source binding required'; END IF;
 ELSE
  IF NOT EXISTS (SELECT 1 FROM linear_bridge.agent_sessions s WHERE s.organization_id=p_org::text
   AND s.agent_session_id=v_session::text AND s.issue_id=v_issue::text AND s.hermes_session_id IS NOT NULL)
  THEN RAISE EXCEPTION 'actual Jarvis source binding required'; END IF;
 END IF;
 SELECT * INTO v_old FROM linear_bridge.native_handoffs WHERE id=v_id;
 IF FOUND THEN
  IF v_old.body<>p_body OR v_old.comment_body<>p_comment OR v_old.sender<>p_sender OR v_old.organization_id<>p_org
   THEN RAISE EXCEPTION 'handoff identity changed'; END IF;
  RETURN v_id;
 END IF;
 SELECT * INTO v_parent FROM linear_bridge.native_handoffs WHERE organization_id=p_org AND recipient=p_sender AND target_session_id=v_session;
 IF FOUND THEN
  IF (p_body->>'parent_handoff_id')::uuid IS DISTINCT FROM v_parent.id OR (p_body->>'depth')::integer<>v_parent.depth+1
   OR v_parent.depth>=4 OR v_parent.issue_id<>v_issue THEN RAISE EXCEPTION 'invalid or exhausted handoff chain'; END IF;
 ELSE
  IF p_body->'parent_handoff_id' IS DISTINCT FROM 'null'::jsonb OR (p_body->>'depth')::integer<>1 THEN RAISE EXCEPTION 'unknown handoff parent'; END IF;
 END IF;
 IF (SELECT count(*) FROM linear_bridge.native_handoffs WHERE organization_id=p_org)>=10000 THEN RAISE EXCEPTION 'handoff capacity reached; retain pending requests'; END IF;
 INSERT INTO linear_bridge.native_handoffs(id,organization_id,sender,recipient,source_session_id,issue_id,body,comment_id,comment_body,parent_handoff_id,depth)
  VALUES(v_id,p_org,p_sender,v_recipient,v_session,v_issue,p_body,(p_body->>'comment_id')::uuid,p_comment,
   (p_body->>'parent_handoff_id')::uuid,(p_body->>'depth')::integer);
 RETURN v_id;
END $$;

CREATE FUNCTION linear_bridge.native_handoff_quiescence(p_org uuid,p_role text,p_session uuid)
 RETURNS jsonb LANGUAGE plpgsql AS $$
DECLARE v_row record;
BEGIN
 IF p_role='codex' THEN
  IF EXISTS(SELECT 1 FROM linear_bridge.codex_events e JOIN linear_bridge.native_handoff_apps a
    ON a.organization_id=e.organization_id AND a.app_user_id=e.app_user_id
    WHERE e.organization_id=p_org AND a.role='codex' AND e.state IN ('dispatching','running','uncertain')
    AND e.session_id=p_session AND coalesce(e.envelope->>'signal','')<>'stop') THEN RETURN NULL; END IF;
  SELECT e.id,e.state,e.runtime_result INTO v_row FROM linear_bridge.codex_events e JOIN linear_bridge.native_handoff_apps a
   ON a.organization_id=e.organization_id AND a.app_user_id=e.app_user_id
   WHERE e.organization_id=p_org AND a.role='codex' AND e.session_id=p_session
   AND e.state IN ('completed','failed','interrupted') AND e.runtime_result->>'dispatch'=e.id::text
   AND e.runtime_result->>'state'=e.state AND coalesce(e.envelope->>'signal','')<>'stop'
   ORDER BY e.received_at DESC,e.id DESC LIMIT 1;
  IF FOUND THEN RETURN jsonb_build_object('source','codex_runtime','dispatch_id',v_row.id,'state',v_row.state); END IF;
 ELSIF p_role='jarvis' THEN
  SELECT r.hermes_run_id,r.status INTO v_row FROM linear_bridge.agent_sessions s JOIN linear_bridge.hermes_runs r
   ON r.hermes_run_id=s.latest_hermes_run_id AND r.agent_session_id=s.agent_session_id
   WHERE s.organization_id=p_org::text AND s.agent_session_id=p_session::text
    AND r.status IN ('completed','failed','interrupted','cancelled') AND r.completed_at IS NOT NULL;
  IF FOUND THEN RETURN jsonb_build_object('source','hermes_runtime','run_id',v_row.hermes_run_id,'state',v_row.status); END IF;
 END IF;
 RETURN NULL;
END $$;

CREATE FUNCTION linear_bridge.native_handoff_bind(p_org uuid,p_recipient text,p_id uuid,p_session uuid)
 RETURNS uuid LANGUAGE plpgsql AS $$
DECLARE v_row record;
BEGIN
 SELECT * INTO v_row FROM linear_bridge.native_handoffs WHERE id=p_id AND organization_id=p_org AND recipient=p_recipient FOR UPDATE;
 IF NOT FOUND OR v_row.source_quiescence IS NULL OR v_row.comment_state<>'confirmed'
  OR v_row.session_state NOT IN ('uncertain','bound') OR v_row.state='declined' THEN RAISE EXCEPTION 'native handoff not ready'; END IF;
 IF v_row.target_session_id IS NOT NULL AND v_row.target_session_id<>p_session THEN RAISE EXCEPTION 'recipient session changed'; END IF;
 UPDATE linear_bridge.native_handoffs SET target_session_id=p_session,session_state='bound',updated_at=now() WHERE id=p_id;
 RETURN p_session;
END $$;

CREATE FUNCTION linear_bridge.native_handoff_refresh(p_org uuid,p_id uuid) RETURNS text LANGUAGE plpgsql AS $$
DECLARE v_row record; v_done jsonb; v_active boolean;
BEGIN
 SELECT * INTO v_row FROM linear_bridge.native_handoffs WHERE id=p_id AND organization_id=p_org FOR UPDATE;
 IF NOT FOUND OR v_row.session_state<>'bound' OR v_row.state IN ('completed','declined') THEN RETURN NULL; END IF;
 v_done:=linear_bridge.native_handoff_quiescence(p_org,v_row.recipient,v_row.target_session_id);
 IF v_row.recipient='codex' THEN
  SELECT EXISTS(SELECT 1 FROM linear_bridge.codex_events e WHERE e.organization_id=p_org AND e.session_id=v_row.target_session_id
   AND e.runtime_result->>'thread' IS NOT NULL AND e.runtime_result->>'turn' IS NOT NULL) INTO v_active;
 ELSE
  SELECT EXISTS(SELECT 1 FROM linear_bridge.agent_sessions s JOIN linear_bridge.hermes_runs r
   ON r.agent_session_id=s.agent_session_id AND r.hermes_run_id=s.latest_hermes_run_id
   WHERE s.organization_id=p_org::text AND s.agent_session_id=v_row.target_session_id::text) INTO v_active;
 END IF;
 IF v_done IS NOT NULL THEN
  IF v_row.state='requested' THEN
   UPDATE linear_bridge.native_handoffs SET state='acknowledged',result='Actual recipient runtime is bound; no work outcome is inferred.',updated_at=now() WHERE id=p_id;
  END IF;
  UPDATE linear_bridge.native_handoffs SET state='completed',result='Recipient runtime reached terminal state; work acceptance remains separate.',updated_at=now() WHERE id=p_id;
  RETURN 'completed';
 ELSIF v_active THEN
  UPDATE linear_bridge.native_handoffs SET state='acknowledged',result='Actual recipient runtime is bound; no work outcome is inferred.',updated_at=now() WHERE id=p_id;
  RETURN 'acknowledged';
 END IF;
 RETURN 'requested';
END $$;
REVOKE ALL ON FUNCTION linear_bridge.native_handoff_request(uuid,text,jsonb,text) FROM PUBLIC;
REVOKE ALL ON FUNCTION linear_bridge.native_handoff_quiescence(uuid,text,uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION linear_bridge.native_handoff_bind(uuid,text,uuid,uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION linear_bridge.native_handoff_refresh(uuid,uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION linear_bridge.native_handoff_immutable() FROM PUBLIC;
REVOKE ALL ON FUNCTION linear_bridge.native_handoff_event() FROM PUBLIC;
COMMIT;
