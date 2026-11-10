import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const SUPABASE_URL = Deno.env.get("SUPABASE_URL")!;
const SERVICE_KEY  = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
const LLM_KEY      = Deno.env.get("LLM_API_KEY")?.trim()!;
const LLM_URL      = Deno.env.get("LLM_API_URL")?.trim()!;   
const LLM_MODEL    = Deno.env.get("LLM_MODEL")?.trim()!;

const COUNTRIES = ["ZA", "US", "IN"];
const TIERS     = ["verified", "probable", "shell_risk"];
const ROLES     = ["Importer", "Exporter", "Importer/Exporter", "Distributor", "Manufacturer", "Logistics/Forwarder"];
const SECTORS   = ["Fresh Produce", "Agriculture & Commodities", "Machinery & Equipment", "Metals & Steel", "Chemicals", "Pharmaceuticals", "Automotive", "Logistics & Transport"];

const EXTRACT_PROMPT = `Extract search filters from the user's request about import/export companies.
Return STRICT JSON only, no prose:
{"country":"ZA|US|IN|null","hs_prefix":"2-digit string or null","tier":"verified|probable|shell_risk|null","trade_role":"${ROLES.join('|')}|null","sector":"${SECTORS.join('|')}|null","keyword":"string or null"}`;

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status, 
    headers: { 
      "Content-Type": "application/json", 
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
      "Access-Control-Allow-Methods": "POST, OPTIONS"
    },
  });
}

async function sha256(s: string) {
  const b = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(s));
  return [...new Uint8Array(b)].map(x => x.toString(16).padStart(2, "0")).join("");
}

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return json({}, 200);
  if (req.method !== "POST") return json({ error: "method" }, 405);

  const admin = createClient(SUPABASE_URL, SERVICE_KEY);
  const DUMMY_USER_ID = "00000000-0000-0000-0000-000000000000";
  const { data: ok } = await admin.rpc("check_ai_quota", { p_user: DUMMY_USER_ID });
  if (!ok) return json({ error: "rate_limited", retry_after: "1h" }, 429);

  let msg = "";
  try { msg = String((await req.json()).message ?? "").slice(0, 2000); }
  catch { return json({ error: "bad_json" }, 400); }
  if (!msg.trim()) return json({ error: "empty" }, 400);

  const ex = await fetch(LLM_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${LLM_KEY}` },
    body: JSON.stringify({
      model: LLM_MODEL, response_format: { type: "json_object" }, temperature: 0, max_tokens: 500,
      messages: [{ role: "system", content: EXTRACT_PROMPT }, { role: "user", content: msg }],
    }),
  });

  if (!ex.ok) {
    const errText = await ex.text();
    return json({ error: "extractor_failed", details: errText }, 502);
  }

  let f: any = {};
  try { f = JSON.parse((await ex.json()).choices[0].message.content); }
  catch { return json({ error: "bad_extraction" }, 502); }

  const country = COUNTRIES.includes(f.country) ? f.country : null;
  const tier    = TIERS.includes(f.tier) ? f.tier : null;
  const role    = ROLES.includes(f.trade_role) ? f.trade_role : null;
  const sector  = SECTORS.includes(f.sector) ? f.sector : null;
  const hs      = /^\d{2}$/.test(f.hs_prefix ?? "") ? f.hs_prefix : null;
  const keyword = typeof f.keyword === "string" ? f.keyword.slice(0, 80) : null;

  const key = await sha256(JSON.stringify({ country, tier, role, sector, hs, keyword }));
  const { data: hit } = await admin.from("ai_cache").select("answer").eq("query_hash", key).maybeSingle();
  if (hit) return json({ answer: hit.answer, cached: true });

  let q = admin.from("company_listing")
    .select("name,country_code,website,email,sector_label,trade_role,verification_tier,hs_codes")
    .limit(25);
    
  if (country) q = q.eq("country_code", country);
  if (tier)    q = q.eq("verification_tier", tier);
  if (role)    q = q.eq("trade_role", role);
  if (sector)  q = q.eq("sector_label", sector);
  if (hs)      q = q.contains("hs_codes", [hs]);
  if (keyword) q = q.textSearch("search_vector", keyword, { type: "websearch" });

  const { data: rows, error: qErr } = await q;
  if (qErr) return json({ error: "query_failed", details: qErr.message }, 500);

  if (!rows?.length) {
    const answer = "No companies matched those filters.";
    await admin.from("ai_cache").insert({ query_hash: key, answer });
    return json({ answer, count: 0 });
  }

  const summary = await fetch(LLM_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${LLM_KEY}` },
    body: JSON.stringify({
      model: LLM_MODEL, temperature: 0, max_tokens: 800,
      messages: [
        { role: "system", content: "Summarise the result set in 2 sentences. Do not invent companies." },
        { role: "user", content: JSON.stringify(rows.slice(0, 15)) },
      ],
    }),
  }).then(r => r.ok ? r.json() : null)
    .then(j => j?.choices?.[0]?.message?.content ?? `Found ${rows.length} companies.`)
    .catch(() => `Found ${rows.length} companies.`);

  await admin.from("ai_cache").insert({ query_hash: key, answer: summary });
  return json({ answer: summary, count: rows.length, rows });
});
