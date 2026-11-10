const SUPABASE_URL = "https://dokxnqhxhdgyonwpwzii.supabase.co";
const ANON_KEY     = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImRva3hucWh4aGRneW9ud3B3emlpIiwicm9sZSI6ImFub24iLCJpYXQiOjE3OTQyMjU0MTgsImV4cCI6MjEwOTgwMTQxOH0.C8IXHVzlS4aXuoZxAtoIDz4wxGxo76IHctfY1BuEye4"; // <--- PUT YOUR eyJ... KEY HERE

const sb = supabase.createClient(SUPABASE_URL, ANON_KEY);
const $ = s => document.querySelector(s);

document.addEventListener("DOMContentLoaded", async () => {
  $("#ask").addEventListener("click", ask);
  $("#q").addEventListener("keydown", e => { if (e.key === "Enter") ask(); });
  
  $("#f-country").addEventListener("change", () => load(0));
  $("#f-sector").addEventListener("change", () => load(0));
  $("#f-role").addEventListener("change", () => load(0));
  $("#f-hs").addEventListener("input", () => load(0));
  
  try {
    const { count } = await sb.from("company_listing").select('*', { count: 'exact', head: true });
    $("#total-count").textContent = `${count || 0} Companies`;
  } catch (err) { $("#total-count").textContent = "Directory"; }
  
  load(0);
});

function render(rows) {
  if (!rows || rows.length === 0) {
    $("#rows").innerHTML = '<tr><td colspan="7" style="text-align:center;color:#999;">No companies found matching those filters.</td></tr>';
    return;
  }
  $("#rows").innerHTML = rows.map(r => `
    <tr>
      <td><strong>${r.name ?? ""}</strong></td>
      <td><span class="source-badge">${r.source ?? "Unknown"}</span></td>
      <td>${r.trade_role ?? ""}</td>
      <td>${r.sector_label ?? ""}</td>
      <td>${r.country_code ?? ""}</td>
      <td>${r.website ? `<a href="${r.website}" target="_blank" rel="noopener">${r.website.replace('https://', '')}</a>` : ""}</td>
      <td>${r.email ?? ""}</td>
    </tr>`).join("");
}

async function load(p = 0) {
  const country = $("#f-country").value || null;
  const sector  = $("#f-sector").value || null;
  const role    = $("#f-role").value || null;
  const hs      = $("#f-hs").value.trim() || null;

  let q = sb.from("company_listing")
    .select("name,country_code,website,email,sector_label,trade_role,source,hs_codes")
    .order("name")
    .limit(100);

  if (country) q = q.eq("country_code", country);
  if (sector)  q = q.ilike("sector_label", `%${sector}%`);
  if (role)    q = q.ilike("trade_role", `%${role}%`);
  if (hs)      q = q.contains("hs_codes", [hs]);

  const { data, error } = await q;
  if (error) { $("#rows").innerHTML = `<tr><td colspan="7" style="color:red;">Error: ${error.message}</td></tr>`; return; }
  render(data);
}

async function ask() {
  const message = $("#q").value.trim();
  if (!message) return;
  const answerDiv = $("#answer");
  answerDiv.style.display = "block";
  answerDiv.textContent = "Thinking...";

  try {
    const res = await fetch(`${SUPABASE_URL}/functions/v1/ask-directory`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ message }),
    });
    const body = await res.json();
    answerDiv.textContent = body.answer ?? body.error ?? "No answer.";
    if (body.rows) render(body.rows);
  } catch (e) { answerDiv.textContent = "Error connecting to AI function."; }
}
