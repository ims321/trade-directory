const SUPABASE_URL = "https://dokxnqhxhdgyonwpwzii.supabase.co";
const ANON_KEY     = "PASTE_YOUR_EYJ_KEY_HERE"; // <--- PUT YOUR eyJ... KEY HERE

const sb = supabase.createClient(SUPABASE_URL, ANON_KEY);
const $ = s => document.querySelector(s);
let page = 0;
const PAGE = 25;

document.addEventListener("DOMContentLoaded", async () => {
  $("#ask").addEventListener("click", ask);
  $("#go").addEventListener("click", () => { page = 0; load(0); });
  $("#q").addEventListener("keydown", e => { if (e.key === "Enter") ask(); });
  
  // Get total count for the badge
  const { count } = await sb.from("company_listing").select('*', { count: 'exact', head: true });
  $("#total-count").textContent = `${count || 0} Companies`;
  
  load(0);
});

function render(rows) {
  if (!rows || rows.length === 0) {
    $("#rows").innerHTML = '<tr><td colspan="6" style="text-align:center;color:#999;">No companies found matching those filters.</td></tr>';
    return;
  }
  $("#rows").innerHTML = rows.map(r => `
    <tr>
      <td><strong>${r.name ?? ""}</strong></td>
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
    .select("name,country_code,website,email,sector_label,trade_role,hs_codes")
    .order("name")
    .range(p * PAGE, (p + 1) * PAGE - 1);

  if (country) q = q.eq("country_code", country);
  if (sector)  q = q.ilike("sector_label", `%${sector}%`); // Changed to ilike for partial matches
  if (role)    q = q.ilike("trade_role", `%${role}%`);     // Changed to ilike for partial matches
  if (hs)      q = q.contains("hs_codes", [hs]);

  const { data, error } = await q;
  if (error) { 
    console.error(error); 
    $("#rows").innerHTML = `<tr><td colspan="6" style="color:red;">Error: ${error.message}</td></tr>`;
    return; 
  }
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
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message }),
    });
    const body = await res.json();
    answerDiv.textContent = body.answer ?? body.error ?? "No answer.";
    if (body.rows) render(body.rows);
  } catch (e) {
    answerDiv.textContent = "Error connecting to AI function.";
  }
}
