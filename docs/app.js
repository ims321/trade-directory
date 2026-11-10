const SUPABASE_URL = "https://dokxnqhxhdgyonwpwzii.supabase.co";
const ANON_KEY     = "PASTE_YOUR_EYJ_KEY_HERE"; // <--- PUT YOUR eyJ... KEY HERE

const sb = supabase.createClient(SUPABASE_URL, ANON_KEY);
const $ = s => document.querySelector(s);

// 1. Use standard OpenStreetMap tiles (No watermark)
const map = L.map('map').setView([20, 0], 2);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
  attribution: '&copy; OpenStreetMap contributors'
}).addTo(map);

let geoLayer;

// 2. Load Map Data
fetch('https://raw.githubusercontent.com/datasets/geo-countries/master/data/countries.geojson')
  .then(res => res.json())
  .then(data => {
    geoLayer = L.geoJSON(data, {
      style: { color: "#3388ff", weight: 1, fillOpacity: 0.1 },
      onEachFeature: function(feature, layer) {
        
        layer.on('click', function(e) {
          const props = feature.properties;
          let countryCode = props.ISO_A2;
          const countryName = props.ADMIN || props.name || "Selected Country";
          
          // FIX: Handle -99 country codes that break the map
          if (countryCode === "-99" || !countryCode) {
              if (countryName.includes("India")) countryCode = "IN";
              else if (countryName.includes("South Africa")) countryCode = "ZA";
              else if (countryName.includes("United Kingdom")) countryCode = "GB";
              else if (countryName.includes("United States")) countryCode = "US";
          }
          
          geoLayer.eachLayer(function(l) { l.setStyle({ color: "#3388ff", fillOpacity: 0.1 }); });
          layer.setStyle({ color: "#ff0000", fillOpacity: 0.5 });
          
          $("#country-title").textContent = `Companies in ${countryName} (${countryCode})`;
          
          if (countryCode && countryCode !== "-99") {
            loadCompanies(countryCode);
          } else {
            $("#rows").innerHTML = '<tr><td colspan="5" style="text-align:center;color:#999;">Country code not recognized on this map.</td></tr>';
          }
        });
        
        layer.on('mouseover', function() { layer.setStyle({ fillOpacity: 0.3 }); });
        layer.on('mouseout', function() { 
            if(layer.options.color !== "#ff0000") layer.setStyle({ fillOpacity: 0.1 }); 
        });
      }
    }).addTo(map);
  });

// 3. Load initial count
sb.from("company_listing").select('*', { count: 'exact', head: true }).then(({ count }) => {
  $("#total-count").textContent = `${count || 0} Companies`;
});
loadCompanies(null);

// 4. Fetch Companies
async function loadCompanies(countryCode) {
  $("#rows").innerHTML = '<tr><td colspan="5" style="text-align:center;color:#999;">Loading...</td></tr>';
  
  let q = sb.from("company_listing")
    .select("name,country_code,website,email,sector_label,trade_role,source")
    .order("name")
    .limit(100);

  if (countryCode) {
    q = q.ilike("country_code", countryCode);
  }

  const { data, error } = await q;
  
  if (error) { 
    $("#rows").innerHTML = `<tr><td colspan="5" style="color:red;">Error: ${error.message}</td></tr>`;
    return; 
  }
  
  if (!data || data.length === 0) {
    $("#rows").innerHTML = '<tr><td colspan="5" style="text-align:center;color:#999;">No companies found for this country.</td></tr>';
    return;
  }

  $("#rows").innerHTML = data.map(r => `
    <tr>
      <td><strong>${r.name ?? ""}</strong></td>
      <td><span class="source-badge">${r.source ?? "Unknown"}</span></td>
      <td>${r.trade_role ?? ""}</td>
      <td>${r.country_code ?? ""}</td>
      <td>${r.website ? `<a href="${r.website}" target="_blank" rel="noopener">${r.website.replace('https://', '')}</a>` : ""}</td>
    </tr>`).join("");
}

// 5. AI Search
$("#ask").addEventListener("click", async () => {
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
    if (body.rows) {
      $("#rows").innerHTML = body.rows.map(r => `
        <tr>
          <td><strong>${r.name ?? ""}</strong></td>
          <td><span class="source-badge">${r.source ?? "Unknown"}</span></td>
          <td>${r.trade_role ?? ""}</td>
          <td>${r.country_code ?? ""}</td>
          <td>${r.website ? `<a href="${r.website}" target="_blank" rel="noopener">${r.website.replace('https://', '')}</a>` : ""}</td>
        </tr>`).join("");
    }
  } catch (e) { answerDiv.textContent = "Error connecting to AI function."; }
});
