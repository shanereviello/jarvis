// Dedicated Codex route; do not replace or edit the existing Jarvis Worker.
// Bind CODEX_WEBHOOK_SECRET and CODEX_N8N_BRIDGE_SECRET as private Worker secrets.
// Bind a dedicated CF_ACCESS_CLIENT_ID / CF_ACCESS_CLIENT_SECRET service token
// admitted by the Access application protecting the Codex backend webhook path.
// CODEX_N8N_URL is the fixed authenticated n8n production webhook, not caller input.
export default {
  async fetch(request, env) {
    // Only fixed stage codes and HTTP status are logged: never payloads, headers or secrets.
    const log = (stage, status) => console.log(JSON.stringify({event:'codex_webhook',stage,status}));
    const deny = (status, stage) => { log(stage,status); return new Response('Codex webhook refused', {status}); };
    const url = new URL(request.url);
    if (request.method !== 'POST' || url.pathname !== '/webhooks/codex' || url.search) return deny(404,'route');
    const maximum = 131072;
    const declared = request.headers.get('content-length');
    if (declared && (!/^\d+$/.test(declared) || Number(declared) > maximum)) return deny(413,'size');
    if (!env.CODEX_WEBHOOK_SECRET || !env.CODEX_N8N_BRIDGE_SECRET ||
        !env.CF_ACCESS_CLIENT_ID || !env.CF_ACCESS_CLIENT_SECRET ||
        !env.CODEX_N8N_URL || env.CODEX_WEBHOOK_SECRET.length < 24 ||
        env.CODEX_N8N_BRIDGE_SECRET.length < 32) return deny(503,'configuration');
    let target;
    try { target = new URL(env.CODEX_N8N_URL); } catch { return deny(503,'target_configuration'); }
    if (target.protocol !== 'https:' || target.username || target.password || target.search || target.hash) return deny(503,'target_configuration');
    const reader = request.body?.getReader();
    if (!reader) return deny(400,'missing_body');
    const chunks = []; let size = 0;
    while (true) {
      const {done,value} = await reader.read(); if (done) break;
      size += value.byteLength;
      if (size > maximum) { await reader.cancel(); return deny(413,'size'); }
      chunks.push(value);
    }
    const raw = new Uint8Array(size); let cursor = 0;
    for (const chunk of chunks) { raw.set(chunk,cursor); cursor+=chunk.byteLength; }
    const signature = request.headers.get('linear-signature') || '';
    const delivery = request.headers.get('linear-delivery') || '';
    if (!/^[0-9a-f]{64}$/.test(signature) ||
        !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(delivery)) return deny(403,'signature_or_delivery_header');
    const key = await crypto.subtle.importKey('raw',new TextEncoder().encode(env.CODEX_WEBHOOK_SECRET),
      {name:'HMAC',hash:'SHA-256'},false,['verify']);
    const supplied = Uint8Array.from(signature.match(/../g),part=>parseInt(part,16));
    if (!await crypto.subtle.verify('HMAC',key,supplied,raw)) return deny(403,'signature_mismatch');
    let body;
    try { body = JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(raw)); } catch { return deny(400,'invalid_json'); }
    if (typeof body.webhookTimestamp !== 'number' || !Number.isFinite(body.webhookTimestamp) ||
        Math.abs(Date.now()-body.webhookTimestamp)>60000) return deny(403,'timestamp');
    if (body.organizationId !== env.CODEX_ORGANIZATION_ID) return deny(403,'organization');
    if (body.type !== 'AgentSessionEvent') return deny(403,'event_type');
    const digest = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',raw)))
      .map(b=>b.toString(16).padStart(2,'0')).join('');
    const headers = new Headers({
      'Content-Type':'application/json',
      'Linear-Delivery':delivery,
      'X-RRAS-Codex-Verified':'v1',
      'X-RRAS-Codex-Body-SHA256':digest,
      'X-RRAS-Codex-Bridge':env.CODEX_N8N_BRIDGE_SECRET,
      'CF-Access-Client-Id':env.CF_ACCESS_CLIENT_ID,
      'CF-Access-Client-Secret':env.CF_ACCESS_CLIENT_SECRET
    });
    try {
      const response = await fetch(target.toString(),{method:'POST',headers,body:raw,
        redirect:'manual',signal:AbortSignal.timeout(3500)});
      // Preserve non-2xx/uncertain intake for Linear's retry; never acknowledge a
      // merely forwarded request or leak an internal response body.
      log(response.ok ? 'accepted' : 'upstream_rejected',response.ok ? 200 : 503);
      if (!response.ok) log('upstream_status',response.status);
      return new Response(response.ok ? 'Accepted' : 'Codex intake unavailable',
        {status:response.ok ? 200 : 503});
    } catch { return deny(503,'upstream_unreachable'); }
  }
};
