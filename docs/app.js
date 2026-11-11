const SUPABASE_URL = "https://dokxnqhxhdgyonwpwzii.supabase.co";
const ANON_KEY     = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImRva3hucWh4aGRneW9ud3B3emlpIiwicm9sZSI6ImFub24iLCJpYXQiOjE3OTQyMjU0MTgsImV4cCI6MjEwOTgwMTQxOH0.C8IXHVzlS4aXuoZxAtoIDz4wxGxo76IHctfY1BuEye4"; // <--- PUT YOUR eyJ... KEY HERE

const sb = supabase.createClient(SUPABASE_URL, ANON_KEY);
const $ = s => document.querySelector(s);

let currentCountryCode = null;
let currentCountryName = null;

// 1. Initialize Map
const southWest = L.latLng(-85, -180);
const northEast = L.latLng(85, 180);
const worldBounds = L.latLngBounds(southWest, northEast);

const map = L.map('map', { 
    maxBounds: worldBounds,
    maxBoundsViscosity: 1.0,
    minZoom: 1,
    zoomAnimation: false, 
    fadeAnimation: false
}).fitBounds(worldBounds);

L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { 
    attribution: '&copy; OpenStreetMap',
    noWrap: true 
}).addTo(map);

setTimeout(() => { map.invalidateSize({ pan: false }); map.fitBounds(worldBounds); }, 100);
setTimeout(() => { map.invalidateSize({ pan: false }); map.fitBounds(worldBounds); }, 500);

let geoLayer;

// 2. Load Map Data & Populate Dropdown
fetch('https://raw.githubusercontent.com/datasets/geo-countries/master/data/countries.geojson')
  .then(res => res.json())
  .then(data => {
    // Populate the Country Dropdown
    const countrySelect = $("#f-country");
    const countryList = [];
    
    data.features.forEach(f => {
        const props = f.properties;
        const countryName = props.ADMIN || props.name || "Unknown";
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
        
        if (countryCode && countryCode !== "-99") {
            countryList.push({ code: countryCode, name: countryName });
        }
    });

    // Sort alphabetically and add to dropdown
    countryList.sort((a, b) => a.name.localeCompare(b.name));
    countryList.forEach(c => {
        const opt = document.createElement('option');
        opt.value = c.code;
        opt.textContent = c.name;
        countrySelect.appendChild(opt);
    });

    // Load the Map Layer
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
          
          if (countryCode && countryCode !== "-99") {
            selectCountry(countryCode, countryName, layer);
          }
        });
        
        layer.on('mouseover', function() { if(!currentCountryCode) layer.setStyle({ fillOpacity: 0.3 }); });
        layer.on('mouseout', function() { if(!currentCountryCode) layer.setStyle({ fillOpacity: 0.1 }); });
      }
    }).addTo(map);
  });

// 3. Selection Logic (Called by Map Click OR Dropdown)
function selectCountry(code, name, layer = null) {
    currentCountryCode = code;
    currentCountryName = name;
    
    // Update Dropdown
    $("#f-country").value = code;
    
    // Update Title
    $("#country-title").textContent = `Companies in ${name}`;
    
    // Update Map Highlight
    if (geoLayer) {
        geoLayer.eachLayer(l => {
            const lProps = l.feature.properties;
            let lCode = lProps.ISO_A2 || lProps.ISO_A2_EH || lProps.WB_A2;
            
            // FIX missing ISO codes in the map
            if (lCode === "-99" || !lCode) {
                const lName = lProps.ADMIN || lProps.name || "";
                if (lName.includes("India")) lCode = "IN";
                else if (lName.includes("South Africa")) lCode = "ZA";
                else if (lName.includes("United Kingdom")) lCode = "GB";
                else if (lName.includes("United States")) lCode = "US";
                else if (lName.includes("France")) lCode = "FR";
                else if (lName.includes("Brazil")) lCode = "BR";
                else if (lName.includes("Australia")) lCode = "AU";
            }

            if (lCode === code) {
                l.setStyle({ color: "#ff0000", fillOpacity: 0.5 });
                if (!layer) map.fitBounds(l.getBounds()); // Zoom to country if selected via dropdown
            } else {
                l.setStyle({ color: "#3388ff", fillOpacity: 0.1 });
            }
        });
    }
    
    // Load Data
    loadCompanies(code, $("#f-role").value, $("#f-source").value);
}

function resetWorldwide() {
    currentCountryCode = null;
    currentCountryName = null;
    $("#f-country").value = "";
    $("#country-title").textContent = "Global View";
    
    if (geoLayer) {
        geoLayer.eachLayer(l => l.setStyle({ color: "#3388ff", fillOpacity: 0.1 }));
    }
    
    map.fitBounds(worldBounds);
    loadCompanies(null, $("#f-role").value, $("#f-source").value);
}

// 4. Load initial count
sb.from("company_listing").select('*', { count: 'exact', head: true }).then(({ count }) => {
  $("#total-count").textContent = `${count || 0} Companies`;
});
loadCompanies(null, null, null);

// 5. Fetch Companies
async function loadCompanies(countryCode, role, source) {
  if (!countryCode) $("#country-title").textContent = "Global View";
  
  $("#rows").innerHTML = '<tr><td colspan="5" style="text-align:center;color:#999;">Loading...</td></tr>';
  
  let q = sb.from("company_listing")
    .select("name,country_code,website,email,sector_label,trade_role,source")
    .order("name")
    .limit(100);

  if (countryCode) q = q.ilike("country_code", countryCode);
  if (role) q = q.ilike("trade_role", `%${role}%`);
  if (source) q = q.ilike("source", `%${source}%`);

  const { data, error } = await q;
  
  if (error) { 
    $("#rows").innerHTML = `<tr><td colspan="5" style="color:red;">Error: ${error.message}</td></tr>`;
  } else if (!data || data.length === 0) {
    $("#rows").innerHTML = '<tr><td colspan="5" style="text-align:center;color:#999;">No companies found for this filter.</td></tr>';
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

// 6. Event Listeners
document.addEventListener("DOMContentLoaded", () => {
    // Country Dropdown Change
    $("#f-country").addEventListener("change", (e) => {
        const code = e.target.value;
        if (!code) {
            resetWorldwide();
        } else {
            const name = e.target.options[e.target.selectedIndex].text;
            selectCountry(code, name);
        }
    });

    // Apply Filter Button (Role & Source only)
    $("#apply-filter").addEventListener("click", () => {
        loadCompanies(currentCountryCode, $("#f-role").value, $("#f-source").value);
    });
});

// 7. AI Search
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
