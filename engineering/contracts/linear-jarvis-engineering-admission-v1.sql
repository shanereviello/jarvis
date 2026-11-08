-- Additive evidence for the bounded existing-Jarvis admission patch.
-- No existing workflow, credential, session, run, role or grant is changed.
BEGIN;
CREATE TABLE linear_bridge.jarvis_engineering_admissions (
 delivery_id uuid PRIMARY KEY, organization_id uuid NOT NULL, session_id uuid NOT NULL,
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
REVOKE ALL ON FUNCTION linear_bridge.jarvis_engineering_admit(uuid,uuid,uuid,uuid,boolean,jsonb,jsonb,uuid) FROM PUBLIC;
COMMIT;
