-- Additive evidence for the bounded existing-Jarvis admission patch.
-- No existing workflow, credential, session, run, role or grant is changed.
BEGIN;
CREATE TABLE linear_bridge.jarvis_engineering_admissions (
 sequence bigserial UNIQUE NOT NULL,delivery_id uuid PRIMARY KEY, organization_id uuid NOT NULL, session_id uuid NOT NULL,
 issue_id uuid NOT NULL, permitted boolean NOT NULL, observation jsonb NOT NULL,
 binding jsonb NOT NULL, handoff_id uuid REFERENCES linear_bridge.native_handoffs(id),
 observed_at timestamptz NOT NULL DEFAULT now()
);
CREATE TRIGGER jarvis_engineering_admissions_retained BEFORE UPDATE OR DELETE
 ON linear_bridge.jarvis_engineering_admissions FOR EACH ROW EXECUTE FUNCTION linear_bridge.native_handoff_immutable();
CREATE FUNCTION linear_bridge.jarvis_engineering_admit(p_delivery uuid,p_org uuid,p_session uuid,p_issue uuid,
 p_permitted boolean,p_observation jsonb,p_binding jsonb,p_handoff uuid)
 RETURNS boolean LANGUAGE plpgsql AS $$
DECLARE v_prior record; v_binding jsonb;
BEGIN
 SELECT binding INTO v_binding FROM linear_bridge.native_handoff_issues WHERE organization_id=p_org AND issue_id=p_issue;
 IF v_binding IS NULL OR v_binding<>p_binding OR octet_length(p_observation::text)>8192
 THEN RAISE EXCEPTION 'exact bounded installed engineering context required'; END IF;
 IF p_handoff IS NOT NULL AND NOT EXISTS (SELECT 1 FROM linear_bridge.native_handoffs h
  WHERE h.id=p_handoff AND h.organization_id=p_org AND h.recipient='jarvis' AND h.issue_id=p_issue
  AND h.body->'binding'=p_binding AND h.source_quiescence IS NOT NULL AND h.comment_state='confirmed'
  AND (h.target_session_id IS NULL OR h.target_session_id=p_session))
 THEN RAISE EXCEPTION 'exact verified Jarvis handoff required'; END IF;
 SELECT * INTO v_prior FROM linear_bridge.jarvis_engineering_admissions WHERE delivery_id=p_delivery;
 IF FOUND THEN
  IF v_prior.organization_id<>p_org OR v_prior.session_id<>p_session OR v_prior.issue_id<>p_issue
   OR v_prior.permitted<>p_permitted OR v_prior.observation<>p_observation OR v_prior.binding<>p_binding
   OR v_prior.handoff_id IS DISTINCT FROM p_handoff THEN RAISE EXCEPTION 'admission identity changed'; END IF;
  RETURN v_prior.permitted;
 END IF;
 IF p_permitted AND p_handoff IS NOT NULL THEN
  PERFORM linear_bridge.native_handoff_bind(p_org,'jarvis',p_handoff,p_session);
 END IF;
 INSERT INTO linear_bridge.jarvis_engineering_admissions(delivery_id,organization_id,session_id,issue_id,permitted,observation,binding,handoff_id)
  VALUES(p_delivery,p_org,p_session,p_issue,p_permitted,p_observation,p_binding,p_handoff);
 RETURN p_permitted;
END $$;
REVOKE ALL ON TABLE linear_bridge.jarvis_engineering_admissions FROM PUBLIC;
REVOKE ALL ON SEQUENCE linear_bridge.jarvis_engineering_admissions_sequence_seq FROM PUBLIC;
REVOKE ALL ON FUNCTION linear_bridge.jarvis_engineering_admit(uuid,uuid,uuid,uuid,boolean,jsonb,jsonb,uuid) FROM PUBLIC;
CREATE TABLE linear_bridge.jarvis_engineering_runs (
 sequence bigserial UNIQUE NOT NULL,run_id text PRIMARY KEY,delivery_id uuid UNIQUE NOT NULL REFERENCES linear_bridge.jarvis_engineering_admissions(delivery_id),
 organization_id uuid NOT NULL,session_id uuid NOT NULL,issue_id uuid NOT NULL,
 hermes_session_id text NOT NULL,binding jsonb NOT NULL,recorded_at timestamptz NOT NULL DEFAULT now()
);
CREATE TRIGGER jarvis_engineering_runs_retained BEFORE UPDATE OR DELETE ON linear_bridge.jarvis_engineering_runs
 FOR EACH ROW EXECUTE FUNCTION linear_bridge.native_handoff_immutable();
CREATE FUNCTION linear_bridge.jarvis_engineering_run_bind(p_run text,p_delivery uuid)
 RETURNS text LANGUAGE plpgsql AS $$
DECLARE v_context record;v_prior record;
BEGIN
 SELECT a.*,s.hermes_session_id INTO v_context FROM linear_bridge.jarvis_engineering_admissions a
 JOIN linear_bridge.hermes_runs r ON r.hermes_run_id=p_run AND r.agent_session_id=a.session_id::text AND r.delivery_id=a.delivery_id
 JOIN linear_bridge.agent_sessions s ON s.agent_session_id=a.session_id::text AND s.organization_id=a.organization_id::text
 WHERE a.delivery_id=p_delivery AND a.permitted;
 IF NOT FOUND THEN RAISE EXCEPTION 'actual admitted Hermes runtime binding required'; END IF;
 SELECT * INTO v_prior FROM linear_bridge.jarvis_engineering_runs WHERE run_id=p_run;
 IF FOUND THEN
  IF v_prior.delivery_id<>p_delivery THEN RAISE EXCEPTION 'native run identity changed'; END IF;
  RETURN p_run;
 END IF;
 INSERT INTO linear_bridge.jarvis_engineering_runs(run_id,delivery_id,organization_id,session_id,issue_id,hermes_session_id,binding)
  VALUES(p_run,p_delivery,v_context.organization_id,v_context.session_id,v_context.issue_id,v_context.hermes_session_id,v_context.binding);
 RETURN p_run;
END $$;
REVOKE ALL ON TABLE linear_bridge.jarvis_engineering_runs FROM PUBLIC;
REVOKE ALL ON SEQUENCE linear_bridge.jarvis_engineering_runs_sequence_seq FROM PUBLIC;
REVOKE ALL ON FUNCTION linear_bridge.jarvis_engineering_run_bind(text,uuid) FROM PUBLIC;
CREATE TABLE linear_bridge.jarvis_engineering_checkpoints (
 sequence bigserial PRIMARY KEY,id uuid UNIQUE NOT NULL,run_id text NOT NULL REFERENCES linear_bridge.jarvis_engineering_runs(run_id),
 organization_id uuid NOT NULL,issue_id uuid NOT NULL,report_json text NOT NULL,report_sha256 text NOT NULL,
 observed_at timestamptz NOT NULL DEFAULT now()
);
CREATE TRIGGER jarvis_engineering_checkpoints_retained BEFORE UPDATE OR DELETE ON linear_bridge.jarvis_engineering_checkpoints
 FOR EACH ROW EXECUTE FUNCTION linear_bridge.native_handoff_immutable();
CREATE FUNCTION linear_bridge.jarvis_engineering_checkpoint(p_id uuid,p_org uuid,p_session uuid,p_alias text,p_run text,p_report text)
 RETURNS uuid LANGUAGE plpgsql AS $$
DECLARE v_run record;v_prior record;v_report jsonb;
BEGIN
 IF octet_length(p_report)>32768 THEN RAISE EXCEPTION 'bounded native checkpoint required'; END IF;
 v_report:=p_report::jsonb;
 SELECT * INTO v_run FROM linear_bridge.jarvis_engineering_runs WHERE run_id=p_run AND organization_id=p_org
  AND session_id=p_session AND hermes_session_id=p_alias;
 IF NOT FOUND OR v_report->>'contract' IS DISTINCT FROM 'engineering-reporting.v1'
  OR v_report->>'operation' IS DISTINCT FROM 'checkpoint.report'
  OR v_report#>>'{source,kind}' IS DISTINCT FROM 'agent_reported'
  OR v_report#>>'{source,namespace}' IS DISTINCT FROM 'hermes_runtime_adapter'
  OR v_report#>>'{source,id}' IS DISTINCT FROM p_run
  OR v_report#>>'{context,project_id}' IS DISTINCT FROM v_run.binding->>'project_id'
  OR v_report#>>'{context,work,work_item_id}' IS DISTINCT FROM v_run.binding->>'work_id'
  OR v_report#>>'{context,work,work_revision_sha256}' IS DISTINCT FROM v_run.binding->>'work_revision_sha256'
  OR v_report#>>'{context,architecture,markdown_sha256}' IS DISTINCT FROM v_run.binding->>'architecture_sha256'
  OR (v_report#>'{context,architecture,version}') IS DISTINCT FROM v_run.binding->'architecture_version'
 THEN RAISE EXCEPTION 'exact retained native checkpoint source and context required'; END IF;
 SELECT * INTO v_prior FROM linear_bridge.jarvis_engineering_checkpoints WHERE id=p_id;
 IF FOUND THEN
  IF v_prior.report_json<>p_report OR v_prior.run_id<>p_run OR v_prior.organization_id<>p_org
   THEN RAISE EXCEPTION 'native checkpoint identity changed'; END IF;
  RETURN p_id;
 END IF;
 IF (SELECT count(*) FROM linear_bridge.jarvis_engineering_checkpoints WHERE organization_id=p_org)>=10000
 THEN RAISE EXCEPTION 'checkpoint transport capacity reached; retain pending source'; END IF;
 INSERT INTO linear_bridge.jarvis_engineering_checkpoints(id,run_id,organization_id,issue_id,report_json,report_sha256)
 VALUES(p_id,p_run,p_org,v_run.issue_id,p_report,encode(sha256(convert_to(p_report,'UTF8')),'hex'));
 RETURN p_id;
END $$;
REVOKE ALL ON TABLE linear_bridge.jarvis_engineering_checkpoints FROM PUBLIC;
REVOKE ALL ON SEQUENCE linear_bridge.jarvis_engineering_checkpoints_sequence_seq FROM PUBLIC;
REVOKE ALL ON FUNCTION linear_bridge.jarvis_engineering_checkpoint(uuid,uuid,uuid,text,text,text) FROM PUBLIC;
COMMIT;
