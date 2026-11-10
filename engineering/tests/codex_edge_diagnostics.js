const {webcrypto}=require('node:crypto');global.crypto=webcrypto;
const fs=require('node:fs'),assert=require('node:assert/strict');
(async()=>{
 const source=fs.readFileSync(process.argv[2],'utf8');
 const worker=(await import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'))).default;
 const logs=[];console.log=(line)=>logs.push(JSON.parse(line));
 const env={CODEX_WEBHOOK_SECRET:'synthetic-signing-secret-32-bytes',CODEX_N8N_BRIDGE_SECRET:'synthetic-bridge-secret-32-bytes',CF_ACCESS_CLIENT_ID:'synthetic-access-id',CF_ACCESS_CLIENT_SECRET:'synthetic-access-secret',CODEX_N8N_URL:'https://example.invalid/webhook',CODEX_ORGANIZATION_ID:'fixture-organization'};
 async function req(body,signing=env.CODEX_WEBHOOK_SECRET){
  const bytes=JSON.stringify(body),key=await crypto.subtle.importKey('raw',new TextEncoder().encode(signing),{name:'HMAC',hash:'SHA-256'},false,['sign']);
  const sig=Buffer.from(await crypto.subtle.sign('HMAC',key,new TextEncoder().encode(bytes))).toString('hex');
  return new Request('https://fixture.invalid/webhooks/codex',{method:'POST',headers:{'linear-signature':sig,'linear-delivery':'00000000-0000-4000-8000-000000000001'},body:bytes});
 }
 const body={webhookTimestamp:Date.now(),organizationId:env.CODEX_ORGANIZATION_ID,type:'AgentSessionEvent',message:'PRIVATE-CONTENT-DO-NOT-LOG'};
 assert.equal((await worker.fetch(await req(body,'wrong-secret'),env)).status,403);assert.equal(logs.at(-1).stage,'signature_mismatch');
 assert.equal((await worker.fetch(await req({...body,organizationId:'wrong'}),env)).status,403);assert.equal(logs.at(-1).stage,'organization');
 assert.equal((await worker.fetch(await req({...body,webhookTimestamp:0}),env)).status,403);assert.equal(logs.at(-1).stage,'timestamp');
 assert.equal((await worker.fetch(await req({...body,type:'wrong'}),env)).status,403);assert.equal(logs.at(-1).stage,'event_type');
 global.fetch=async()=>new Response('internal payload should not be logged',{status:403});
 assert.equal((await worker.fetch(await req(body),env)).status,503);assert.equal(logs.at(-2).stage,'upstream_rejected');assert.deepEqual(logs.at(-1),{event:'codex_webhook',stage:'upstream_status',status:403});
 global.fetch=async(_url,options)=>{assert.equal(options.redirect,'manual');return new Response(null,{status:302,headers:{location:'https://other.invalid/private'}})};
 assert.equal((await worker.fetch(await req(body),env)).status,503);assert.deepEqual(logs.at(-1),{event:'codex_webhook',stage:'upstream_status',status:302});
 global.fetch=async()=>new Response('ok',{status:200});assert.equal((await worker.fetch(await req(body),env)).status,200);assert.equal(logs.at(-1).stage,'accepted');
 const result=JSON.stringify(logs);for(const secret of [env.CODEX_WEBHOOK_SECRET,env.CODEX_N8N_BRIDGE_SECRET,env.CF_ACCESS_CLIENT_SECRET,'PRIVATE-CONTENT-DO-NOT-LOG','internal payload'])assert(!result.includes(secret));
 process.stdout.write(JSON.stringify({signature_mismatch:true,scope_rejections:true,upstream_status:true,no_sensitive_logs:true,security_checks_preserved:true}));
})().catch(e=>{process.stderr.write(e.stack);process.exitCode=1});
