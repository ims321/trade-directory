const SUPABASE_URL = "https://dokxnqhxhdgyonwpwzii.supabase.co";
const ANON_KEY     = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImRva3hucWh4aGRneW9ud3B3emlpIiwicm9sZSI6ImFub24iLCJpYXQiOjE3OTQyMjU0MTgsImV4cCI6MjEwOTgwMTQxOH0.C8IXHVzlS4aXuoZxAtoIDz4wxGxo76IHctfY1BuEye4"; // <--- PUT YOUR eyJ... KEY HERE

const sb = supabase.createClient(SUPABASE_URL, ANON_KEY);
const $ = s => document.querySelector(s);

// 1. Initialize Map
// 🚨 THE FIX: Hardcoded global view, no wrap (prevents repeating worlds), strict bounds.
const southWest = L.latLng(-85, -180);
const northEast = L.latLng(85, 180);
const bounds = L.latLngBounds(southWest, northEast);

const map = L.map('map', { 
    maxBounds: bounds,
    maxBoundsViscosity: 1.0,
    minZoom: 2,
    zoomAnimation: false, 
    fadeAnimation: false
}).setView([20, 0], 2); // Center at lat 20, lon 0, zoom level 2

L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { 
    attribution: '&copy; OpenStreetMap',
    noWrap: true // Prevents the map from repeating horizontally
}).addTo(map);

// Force redraw once the page settles
setTimeout(() => { map.invalidateSize({ pan: false }); }, 100);
setTimeout(() => { map.invalidateSize({ pan: false }); }, 500);
setTimeout(() => { map.invalidateSize({ pan: false }); }, 1000);

window.addEventListener('resize', () => { map.invalidateSize({ pan: false }); });

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
          const countryName = props.ADMIN || props.name || "Selected Country";
          
          let countryCode = props.ISO_A2;
          if (countryCode === "-99" || !countryCode) countryCode = props.ISO_A2_EH;
          if (countryCode === "-99" || !countryCode) countryCode = props.WB_A2;
          if (countryCode === "-99" || !countryCode) countryCode = props.ID;
          
          if (countryCode === "-99" || !countryCode) {
              if (countryName.includes("India")) countryCode = "IN";
              else if (countryName.includes("South Africa")) countryCode = "ZA";
              else if (countryName.includes("United Kingdom")) countryCode = "GB";
              else if (countryName.includes("United States")) countryCode = "US";
              else if (countryName.includes("France")) countryCode = "FR";
              else if (countryName.includes("Brazil")) countryCode = "BR";
              else if (countryName.includes("Australia")) countryCode = "AU";
          }
          
          geoLayer.eachLayer(function(l) { l.setStyle({ color: "#3388ff", fillOpacity: 0.1 }); });
          layer.setStyle({ color: "#ff0000", fillOpacity: 0.5 });
          
          if (countryCode && countryCode !== "-99") {
            $("#country-title").textContent = `Companies in ${countryName} (${countryCode})`;
            loadCompanies(countryCode);
          } else {
            $("#country-title").textContent = `Companies in ${countryName}`;
            $("#rows").innerHTML = '<tr><td colspan="5" style="text-align:center;color:#999;">No companies found for this country.</td></tr>';
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
  if (!countryCode) $("#country-title").textContent = "Global View";
  
  $("#rows").innerHTML = '<tr><td colspan="5" style="text-align:center;color:#999;">Loading...</td></tr>';
  
  let q = sb.from("company_listing")
    .select("name,country_code,website,email,sector_label,trade_role,source")
    .order("name")
    .limit(100);

  if (countryCode) q = q.ilike("country_code", countryCode);

  const { data, error } = await q;
  
  if (error) { 
    $("#rows").innerHTML = `<tr><td colspan="5" style="color:red;">Error: ${error.message}</td></tr>`;
  } else if (!data || data.length === 0) {
    $("#rows").innerHTML = '<tr><td colspan="5" style="text-align:center;color:#999;">No companies found for this country.</td></tr>';
  } else {
    $("#rows").innerHTML = data.map(r => `
      <tr>
        <td><strong>${r.name ?? ""}</strong></td>
        <td><span class="source-badge">${r.source ?? "Unknown"}</span></td>
        <td>${r.trade_role ?? ""}</td>
        <td>${r.country_code ?? ""}</td>
        <td>${r.website ? `<a href="${r.website}" target="_blank" rel="noopener">${r.website.replace('https://', '')}</a>` : ""}</td>
      </tr>`).join("");
  }
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
