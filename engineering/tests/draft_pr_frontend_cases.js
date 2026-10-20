(async function draftPrFrontendCases(bridge) {
  const assert=(value,message)=>{if(!value)throw new Error(message);};
  const create={repository_full_name:'fixture/library',head:'codex/task-one',base:'main',draft:true};
  const sha='a'.repeat(40),url='https://github.com/fixture/library/pull/7';
  const cases=[];
  async function test(name,options={},expected={}) {
    let armed=false,outcome=false,creates=0,attachments=0,completes=0;
    let cliCompletePayload;
    const cli=async(action,data)=>{
      if(action==='prepare'){
        if(armed||outcome)throw new Error('existing fence');
        return {branch_read:{url:'branch'},prs_read:{url:'prs'},create};
      }
      if(action==='arm'){
        if(data.prs.length||data.branch.commit.sha!==sha)throw new Error('preflight');
        armed=true;return {create};
      }
      if(action==='unknown'){outcome=true;return {status:'unknown'};}
      if(action==='complete'){
        completes++;cliCompletePayload=data;
        if(options.hostLost)throw new Error('host response lost');
        outcome=true;return {status:data.head_sha===sha?'draft_created':'unknown'};
      }
      throw new Error('unexpected action');
    };
    const github=async(name,args)=>{
      if(name==='fetch'){
        if(options.badFetch)return {isError:true};
        const value=args.url==='branch'?{name:create.head,commit:{sha:options.headChanged?'b'.repeat(40):sha}}:(options.existing?[{number:3}]:[]);
        return {structuredContent:{content:JSON.stringify(value)}};
      }
      assert(JSON.stringify(args)===JSON.stringify(create),'request changed');creates++;
      if(options.replyLost)throw new Error('create response lost');
      if(options.createError)return {isError:true};
      return {structuredContent:{url,number:7,head:options.nullHead?null:create.head,head_sha:options.headRace?'b'.repeat(40):sha,head_repo_full_name:'fixture/library',base:'main',draft:true,merged:false,state:'open',body:'PRIVATE_NEVER_PERSIST'}};
    };
    const attach=async(candidate)=>{assert(candidate===url,'attachment URL');attachments++;if(options.attachLost)throw new Error('attach failed');};
    let result,failed=false;
    try {result=await bridge({cli,github,attach});}catch(_){failed=true;}
    assert(failed===!!expected.failed,name+': failure state');
    assert(creates===(expected.creates??1),name+': creation count');
    if(expected.status)assert(result.status===expected.status,name+': outcome');
    if(expected.attachments!==undefined)assert(attachments===expected.attachments,name+': attachment count');
    if(cliCompletePayload)assert(!JSON.stringify(cliCompletePayload).includes('PRIVATE_NEVER_PERSIST'),'private response body copied');
    if(options.attachLost)assert(result.attachment_pending===true&&completes===1,'attachment failure retried creation or lost completion');
    if(expected.fence)assert(armed,name+': fence lost');
    if(options.replay){
      try{await bridge({cli,github,attach});throw new Error('replay allowed');}catch(e){assert(e.message==='existing fence','wrong replay result');}
      assert(creates===1,'replayed creation');
    }
    cases.push(name);
  }
  await test('success_exact_request_and_receipt',{replay:true},{status:'draft_created',attachments:1});
  await test('lost_create_response',{replyLost:true},{status:'unknown',attachments:0,fence:true});
  await test('connector_error',{createError:true},{status:'unknown',attachments:0,fence:true});
  await test('existing_pr_refused',{existing:true},{failed:true,creates:0});
  await test('head_drift_before_create',{headChanged:true},{failed:true,creates:0});
  await test('fetch_error_before_fence',{badFetch:true},{failed:true,creates:0});
  await test('head_race_after_create_is_attached',{headRace:true},{status:'unknown',attachments:1,fence:true});
  await test('attachment_failure_no_creation_retry',{attachLost:true},{status:'draft_created',attachments:1});
  await test('host_response_loss_no_creation_retry',{hostLost:true},{failed:true,attachments:1,fence:true});
  await test('malformed_head_still_persists_unknown',{nullHead:true,headRace:true},{status:'unknown',attachments:1,fence:true});
  return {passed:cases.length,cases};
})
