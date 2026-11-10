const SUPABASE_URL = "https://dokxnqhxhdgyonwpwzii.supabase.co";
// ENSURE THIS IS YOUR eyJ... KEY!
const ANON_KEY     = 
"eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImRva3hucWh4aGRneW9ud3B3emlpIiwicm9sZSI6ImFub24iLCJpYXQiOjE3OTQyMjU0MTgsImV4cCI6MjEwOTgwMTQxOH0.C8IXHVzlS4aXuoZxAtoIDz4wxGxo76IHctfY1BuEye4"; 

const sb = supabase.createClient(SUPABASE_URL, ANON_KEY);
const $ = s => document.querySelector(s);
let page = 0;
const PAGE = 25;

// Attach event listeners
document.addEventListener("DOMContentLoaded", () => {
  $("#auth-btn").addEventListener("click", login);
  $("#ask").addEventListener("click", ask);
  $("#go").addEventListener("click", () => { page = 0; load(0); });
  $("#q").addEventListener("keydown", e => { if (e.key === "Enter") ask(); });
  
  // Check login state
  sb.auth.getSession().then(({ data: { session } }) => {
    if (session) {
      $("#auth-box").style.display = "none";
    }
  });
  
  load(0);
});

async function login() {
  const email = $("#auth-email").value;
  const password = $("#auth-password").value;
  
  const btn = $("#auth-btn");
  btn.textContent = "Logging in...";

  console.log("Attempting login for:", email);

  try {
    const { data, error } = await sb.auth.signInWithPassword({ email, password });
    if (error) {
      console.error("Login error:", error);
      alert("Login failed: " + error.message);
      btn.textContent = "Log In";
    } else {
      console.log("Login successful:", data);
      $("#auth-box").style.display = "none";
    }
  } catch (err) {
    console.error("Unexpected error:", err);
    alert("Unexpected error: " + err.message);
    btn.textContent = "Log In";
  }
}

function render(rows) {
  if (!rows || rows.length === 0) {
    $("#rows").innerHTML = '<tr><td colspan="5" style="text-align:center;color:#999;">No companies found.</td></tr>';
    return;
  }
  $("#rows").innerHTML = rows.map(r => `
    <tr>
      <td>${r.name ?? ""}</td>
      <td>${r.country_code ?? ""}</td>
      <td>${r.website ? `<a href="${r.website}" target="_blank" rel="noopener">${r.website}</a>` : ""}</td>
      <td>${r.email ?? ""}</td>
      <td class="${r.verification_tier}">${r.verification_tier ?? ""}</td>
    </tr>`).join("");
}

async function load(p = 0) {
  const country = $("#f-country").value || null;
  const tier    = $("#f-tier").value || null;
  const hs      = $("#f-hs").value.trim() || null;

  let q = sb.from("company_listing")
    .select("name,country_code,website,email,verification_tier,hs_codes")
    .order("name")
    .range(p * PAGE, (p + 1) * PAGE - 1);

  if (country) q = q.eq("country_code", country);
  if (tier)    q = q.eq("verification_tier", tier);
  if (hs)      q = q.contains("hs_codes", [hs]);

  const { data, error } = await q;
  if (error) { 
    console.error(error); 
    $("#rows").innerHTML = `<tr><td colspan="5" style="color:red;">Error: ${error.message}</td></tr>`;
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
  
  const { data: { session } } = await sb.auth.getSession();
  if (!session) { 
    answerDiv.textContent = "Please log in using the box above to use the AI."; 
    return; 
  }

  try {
    const res = await fetch(`${SUPABASE_URL}/functions/v1/ask-directory`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${session.access_token}` },
      body: JSON.stringify({ message }),
    });
    const body = await res.json();
    answerDiv.textContent = body.answer ?? body.error ?? "No answer.";
    if (body.rows) render(body.rows);
  } catch (e) {
    answerDiv.textContent = "Error connecting to AI function.";
  }
}
