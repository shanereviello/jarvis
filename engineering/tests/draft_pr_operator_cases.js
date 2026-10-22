(async function operatorCases(operator, bridge) {
  const assert = (condition, name) => { if (!condition) throw new Error(name); };
  const release = '/opt/rras-engineering/releases/workflow-0123456789ab';
  const commands = [];
  const base = (changes = {}) => ({release, packagePath: '/tmp/review', workspace: '/tmp/operator', ...changes});
  const toolsFor = (execute, extra = {}) => ({exec_command: execute, write_stdin: async () => {throw new Error('unexpected_poll');},
    mcp__codex_apps__github_fetch: async args => ({structuredContent:{content:JSON.stringify(args.url.includes('/branches/') ? {name:'codex/fixture',commit:{sha:'a'.repeat(40)}} : [])}}),
    mcp__codex_apps__github_create_pull_request: async () => ({structuredContent:{url:'https://github.com/fixture/library/pull/1',head:'codex/fixture',head_sha:'a'.repeat(40),base:'main',head_repo_full_name:'fixture/library',number:1,draft:true,merged:false,state:'open'}}),
    codex_app__attach_artifact: async () => ({}), ...extra});
  const ok = value => ({output: JSON.stringify({...value,operator_binding_protocol:1}),exit_code:0});
  const cases=[];
  const rejects = async (fn, name) => { let failed=false;try {await fn();} catch (_) {failed=true;} assert(failed,name);cases.push(name); };
  let executions=0,polls=0;
  const fake=toolsFor(async request => {commands.push(request.cmd);executions++;return {output:'{"operator_binding_protocol":1,"suc',session_id:17};},
    {write_stdin:async args => {assert(args.session_id===17,'same_session');polls++;return {output:'cess":true}',exit_code:0};}});
  const result=await operator({...base({packagePath:"/tmp/review'$(touch /tmp/NEVER_EXECUTED)\nfixture",workspace:'/tmp/work `literal` $HOME'}),tools:fake,
    bridge:async ({cli,github,attach}) => {const value=await cli('arm',{text:"quotes'\"$()`;\n"});await github('fetch',{url:'fixture'});await attach('https://github.com/fixture/library/pull/1');return value;}});
  assert(result.success && executions===1 && polls===1,'same_process_resume');cases.push('same_process_resume_and_literal_arguments');
  await rejects(()=>operator({...base({release:'/tmp/worker-code'}),tools:fake,bridge}),'unprotected_release_refused');
  await rejects(()=>operator({...base({packagePath:'relative'}),tools:fake,bridge}),'relative_paths_refused');
  await rejects(()=>operator({...base(),tools:{},bridge}),'missing_tools_refused');
  await rejects(()=>operator({...base(),tools:toolsFor(async()=>({output:'private error',exit_code:1})),bridge:async({cli})=>cli('prepare')}),'host_nonzero_refused');
  await rejects(()=>operator({...base(),tools:toolsFor(async()=>({output:'not-json',exit_code:0})),bridge:async({cli})=>cli('prepare')}),'invalid_host_json_refused');
  await rejects(()=>operator({...base(),tools:toolsFor(async()=>({output:'[]',exit_code:0})),bridge:async({cli})=>cli('prepare')}),'host_array_refused');
  await rejects(()=>operator({...base(),tools:fake,bridge:async({cli})=>cli('merge')}),'unadmitted_cli_action_refused');
  await rejects(()=>operator({...base(),tools:fake,bridge:async({github})=>github('merge_pull_request',{})}),'unadmitted_github_operation_refused');
  await rejects(()=>operator({...base(),tools:fake,bridge:async({cli})=>cli('complete',{value:'x'.repeat(65537)})}),'oversized_cli_metadata_refused');
  await rejects(()=>operator({...base(),tools:toolsFor(async()=>({output:'{"status":"old_helper"}',exit_code:0})),bridge:async({cli})=>cli('prepare')}),'obsolete_helper_protocol_refused');
  let defaultCommand;
  await operator({...base({workspace:undefined}),tools:toolsFor(async request=>{defaultCommand=request.cmd;return ok({selected:true});}),bridge:async({cli})=>cli('prepare')});
  assert(!defaultCommand.includes('--workspace') && defaultCommand.includes('--package'),'host_selects_default_workspace');
  cases.push('host_selected_workspace_without_frontend_home');
  let created=0,attached=0;
  const actions=[];
  const execute=async request=>{
    commands.push(request.cmd);
    const action=['prepare','arm','complete','unknown'].find(x=>request.cmd.includes("'"+x+"'"));actions.push(action);
    if(action==='prepare') return ok({branch_read:{url:'/branches/codex/fixture'},prs_read:{url:'/pulls'}});
    if(action==='arm') return ok({create:{repository_full_name:'fixture/library',head:'codex/fixture',base:'main',draft:true}});
    if(action==='complete') return ok({status:'draft_created'});
    if(action==='unknown') return ok({status:'unknown'});
    throw new Error('unexpected_action');
  };
  const integration=toolsFor(execute,{
    mcp__codex_apps__github_create_pull_request:async()=>{created++;return {structuredContent:{url:'https://github.com/fixture/library/pull/1',head:'codex/fixture',head_sha:'a'.repeat(40),base:'main',head_repo_full_name:'fixture/library',number:1,draft:true,merged:false,state:'open'}};},
    codex_app__attach_artifact:async()=>{attached++;return {};}});
  assert((await operator({...base(),tools:integration,bridge})).status==='draft_created','integrated_success');
  assert(created===1 && attached===1 && actions.join(',')==='prepare,arm,complete','single_create_attach');cases.push('actual_bridge_single_create_and_attach');
  actions.length=0;
  const ambiguous=toolsFor(execute,{mcp__codex_apps__github_create_pull_request:async()=>{throw new Error('lost_response');}});
  assert((await operator({...base(),tools:ambiguous,bridge})).status==='unknown','lost_response_unknown');
  assert(actions.join(',')==='prepare,arm,unknown','no_creation_retry');cases.push('actual_bridge_lost_response_no_retry');
  const attachError=toolsFor(execute,{codex_app__attach_artifact:async()=>({isError:true})});
  assert((await operator({...base(),tools:attachError,bridge})).attachment_pending===true,'attachment_pending');cases.push('attachment_tool_error_reported');
  return {cases,commands};
})
