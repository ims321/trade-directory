const SUPABASE_URL = "https://dokxnqhxhdgyonwpwzii.supabase.co";
const ANON_KEY     = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImRva3hucWh4aGRneW9ud3B3emlpIiwicm9sZSI6ImFub24iLCJpYXQiOjE3OTQyMjU0MTgsImV4cCI6MjEwOTgwMTQxOH0.C8IXHVzlS4aXuoZxAtoIDz4wxGxo76IHctfY1BuEye4"; // <--- PUT YOUR eyJ... KEY HERE

const sb = supabase.createClient(SUPABASE_URL, ANON_KEY);
const $ = s => document.querySelector(s);

// 1. Initialize Map with FREE OpenStreetMap Tiles (No API Key Required)
const map = L.map('map').setView([20, 0], 2);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
  attribution: '&copy; OpenStreetMap contributors'
}).addTo(map);

let geoLayer;

// 2. Load GeoJSON for Country Borders
fetch('https://raw.githubusercontent.com/datasets/geo-countries/master/data/countries.geojson')
  .then(res => res.json())
  .then(data => {
    geoLayer = L.geoJSON(data, {
      style: { color: "#3388ff", weight: 1, fillOpacity: 0.1 },
      onEachFeature: function(feature, layer) {
        
        layer.on('click', function(e) {
          // Try multiple standard GeoJSON properties to find the 2-letter country code
          const props = feature.properties;
          const countryCode = props.ISO_A2 || props.iso_a2 || props.ID || props.id;
          const countryName = props.ADMIN || props.name || "Selected Country";
          
          // Highlight clicked country
          geoLayer.eachLayer(function(l) { l.setStyle({ color: "#3388ff", fillOpacity: 0.1 }); });
          layer.setStyle({ color: "#ff0000", fillOpacity: 0.5 });
          
          $("#country-title").textContent = `Companies in ${countryName} (${countryCode})`;
          
          if (countryCode && countryCode !== "-99") {
            loadCompanies(countryCode);
          } else {
            $("#rows").innerHTML = '<tr><td colspan="5" style="text-align:center;color:#999;">Could not determine country code for this region.</td></tr>';
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
loadCompanies(null); // Load all initially

// 4. Fetch Companies from Supabase
async function loadCompanies(countryCode) {
  $("#rows").innerHTML = '<tr><td colspan="5" style="text-align:center;color:#999;">Loading...</td></tr>';
  
  let q = sb.from("company_listing")
    .select("name,country_code,website,email,sector_label,trade_role,source")
    .order("name")
    .limit(100);

  if (countryCode) {
    // Use ilike for safer matching in case the DB has full names instead of ISO codes
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
