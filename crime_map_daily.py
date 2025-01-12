import folium
import pandas as pd
import json
from folium.plugins import MarkerCluster, HeatMap
from datetime import datetime

def load_data():
    """
    Loads 'summary_report.zip' with at least 'Lat', 'Long', 'Date'.
    Converts 'Date' to 'YYYY-MM-DD' strings, drops missing lat/long/dates.
    """
    df = pd.read_csv("data/summary_report.zip", compression="zip", encoding="cp1252")
    df = df.dropna(subset=["Lat", "Long", "Date"])
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce").dt.strftime("%Y-%m-%d")
    df = df.dropna(subset=["Date"])
    return df

def create_map_load_all(df, output_html="map.html"):
    """
    Demonstrates loading ALL points (markers + heat) at once, then
    toggling them in memory for each new date range selection,
    thus avoiding re-constructing all markers from scratch each time.

    - Title block at the top
    - Disclaimer overlay (scrollable if too tall)
    - Loading overlay
    - Foldable date selector at the top center
    - MarkerCluster & HeatMap with all points cached
    - The map is centered on Oak Park (zoom=13, max_bounds=True).
    - Footer fixed at bottom
    - After clicking "Apply," the date selector folds back in.
    """

    # 1) Create a Folium map centered on Oak Park
    m = folium.Map(
        location=[41.885, -87.78],
        zoom_start=13,
        max_bounds=True
    )

    # 2) Create empty overlays => Folium includes plugin scripts + layer control
    cluster_layer = MarkerCluster(name="Cluster Markers").add_to(m)
    heat_layer = HeatMap([], name="Heatmap").add_to(m)

    # Add layer control
    folium.LayerControl(position="topright").add_to(m)

    # 3) Convert data -> JSON for passing to JS
    keep_cols = [
        "Lat", "Long", "Date", "Offense", "Complaint #",
        "Time", "Location", "Victim/Address", "Narrative", "File Name"
    ]
    keep_cols = [c for c in keep_cols if c in df.columns]
    df_use = df[keep_cols].copy()
    data_list = df_use.to_dict(orient="records")
    data_js = json.dumps(data_list)

    # 4) Get references to the Folium layers' JS variable names
    cluster_name = cluster_layer.get_name()
    heat_name = heat_layer.get_name()

    # 5) Title block HTML
    title_html = '''
    <h3 align="center" style="font-size:20px"><b>Oak Park Crime Map</b></h3>
    <br>
    <h3 align="center" style="font-size:10px">
    <a href="https://jesse-anderson.net/">My Portfolio</a> |
    <a href="https://blog.jesse-anderson.net/">My Blog</a> |
    <a href="https://blog.jesse-anderson.net/posts/OP-Crime-Documentation/">Documentation</a> |
    <a href="mailto:jesse@jesse-anderson.net">Contact</a> |
    <a href="https://forms.gle/GnyaVwo1Vzm8nBH6A">
        Add me to Weekly Updates
    </a> |
    <a href="https://jesse-anderson.net/OP-Crime-Maps/crime_map_cumulative.html">
    Comp. Map
    </a>
    </h3>
    '''
    m.get_root().html.add_child(folium.Element(title_html))

    # 6) Disclaimer + Loading Overlays
    disclaimers_html = """
    <style>
    /* Full-screen disclaimers */
    #disclaimerOverlay {
      position: fixed;
      z-index: 999999; /* On top */
      left: 0;
      top: 0;
      width: 100%;
      height: 100%;
      background-color: rgba(255, 255, 255, 0.95);
      color: #333;
      display: block; /* shown by default */
      overflow: auto; /* allow scrolling if it's very tall on mobile */
      text-align: center;
      padding-top: 100px;
      font-family: Arial, sans-serif;
    }
    #disclaimerContent {
      background: #f9f9f9;
      border: 1px solid #ccc;
      display: inline-block;
      padding: 20px;
      max-width: 80vh; /* 80% of viewport height */
      overflow-y: auto;
      margin-bottom: 40px;
      text-align: left;
    }
    #acceptButton {
      margin-top: 20px;
      padding: 10px 20px;
      font-size: 16px;
      cursor: pointer;
    }

    /* A "loading" overlay while we create markers in memory */
    #loadingOverlay {
      position: fixed;
      z-index: 99998;
      left: 0;
      top: 0;
      width: 100%;
      height: 100%;
      background-color: rgba(255, 255, 255, 0.8);
      color: #333;
      display: none; /* hidden initially, shown in initMap() */
      text-align: center;
      padding-top: 100px;
      font-family: Arial, sans-serif;
    }
    #loadingOverlayContent {
      background: #f1f1f1;
      border: 1px solid #ccc;
      display: inline-block;
      padding: 20px;
      max-width: 400px;
      text-align: left;
    }
    </style>

    <div id="disclaimerOverlay">
      <div id="disclaimerContent">
        <h2>Important Legal Disclaimer</h2>
        <p><strong>By using this demonstrative research tool, you acknowledge and agree:</strong></p>
        <ul>
            <li>This tool is for <strong>demonstration purposes only</strong>.</li>
            <li>The data originated from publicly available Oak Park Police Department PDF files.
                View the official site here:
                <a href="https://www.oak-park.us/village-services/police-department"
                   target="_blank">Oak Park Police Department</a>.</li>
            <li>During parsing, <strong>~10%</strong> of complaints were <strong>omitted</strong>
                due to parsing issues; thus the data is <strong>incomplete</strong>.</li>
            <li>The <strong>official</strong> and <strong>complete</strong> PDF files remain
                with the Oak Park Police Department.</li>
            <li>You <strong>will not hold</strong> the author <strong>liable</strong> for <strong>any</strong>
                decisions—formal or informal—based on this tool.</li>
            <li>This tool <strong>should not</strong> be used in <strong>any</strong> official or unofficial
                <strong>decision-making</strong>.</li>
        </ul>
        <p><strong>By continuing, you indicate your acceptance of these terms
           and disclaim all liability.</strong></p>
        <hr/>
        <button id="acceptButton" onclick="hideDisclaimer()">I Accept</button>
      </div>
    </div>

    <!-- A "loading" overlay -->
    <div id="loadingOverlay">
      <div id="loadingOverlayContent">
        <h2>Loading All Points...</h2>
        <p>Please wait while we build the map overlays in memory.</p>
      </div>
    </div>

    <script>
    function hideDisclaimer() {
      document.getElementById('disclaimerOverlay').style.display = 'none';
      initMap();
    }
    </script>
    """
    m.get_root().html.add_child(folium.Element(disclaimers_html))

    # 7) Minimal CSS for top-center toggle + date-control
    style_html = """
    <style>
      .top-center-toggle {
        position: absolute;
        top: 10px;
        left: 50%;
        transform: translateX(-50%);
        z-index: 9999;
        font-family: Arial, sans-serif;
      }
      .toggle-button {
        cursor: pointer;
        background: #007bff;
        color: #fff;
        border: none;
        padding: 6px 12px;
        border-radius: 4px;
        font-size: 14px;
      }

      .date-control {
        display: none; /* hidden initially; toggled by button */
        position: absolute;
        top: 50px; /* below the toggle button */
        left: 50%;
        transform: translateX(-50%);
        background: white;
        padding: 8px;
        border-radius: 6px;
        box-shadow: 0 0 15px rgba(0,0,0,0.2);
        font-family: Arial, sans-serif;
        z-index: 9998;
      }
      .date-control label {
        font-weight: bold;
      }
    </style>
    """
    m.get_root().header.add_child(folium.Element(style_html))

    # 8) custom JS (caching approach)
    #    After user clicks "Apply," we fold the date selector back in
    custom_js = f"""
    <script>
    var realData = {data_js};

    function initMap() {{
      document.getElementById('loadingOverlay').style.display = 'block';

      var mapObj = window['{m.get_name()}'];
      if (!mapObj) {{
        console.error("Map object not found!");
        return;
      }}

      var clusterObj = window["{cluster_name}"];
      var heatObj = window["{heat_name}"];

      var allMarkers = [];
      var allHeatPoints = [];

      console.log("Building all markers in memory...");
      for (var i = 0; i < realData.length; i++) {{
        var rec = realData[i];
        var lat = rec["Lat"];
        var lng = rec["Long"];
        var d = rec["Date"] || "Unknown";

        var offense = rec["Offense"] || "Unknown";
        var complaint = rec["Complaint #"] || "Not found";
        var timeVal = rec["Time"] || "Not found";
        var locVal = rec["Location"] || "Not found";
        var victim = rec["Victim/Address"] || "Not found";
        var narrative = rec["Narrative"] || "Not found";
        var fileName = rec["File Name"] || "";

        var popup_html = `
            <b>Complaint #:</b> ${{complaint}}<br/>
            <b>Offense:</b> ${{offense}}<br/>
            <b>Date:</b> ${{d}}<br/>
            <details>
              <summary><b>View Details</b></summary>
              <b>Time:</b> ${{timeVal}}<br/>
              <b>Location:</b> ${{locVal}}<br/>
              <b>Victim:</b> ${{victim}}<br/>
              <b>Narrative:</b> ${{narrative}}<br/>
              <b>URL:</b> <a href="${{fileName}}" target="_blank">PDF Link</a>
            </details>
        `;

        if (lat == null || lng == null) continue;

        var marker = L.marker([lat, lng]).bindPopup(popup_html);

        allMarkers.push({{
          marker: marker,
          date: d,
          lat: lat,
          lng: lng
        }});

        allHeatPoints.push({{ lat: lat, lng: lng, date: d }});
      }}
      console.log("Total markers in memory:", allMarkers.length);

      var toggleDiv = L.DomUtil.create('div', 'top-center-toggle');
      toggleDiv.innerHTML = `
        <button id="toggleDateBtn" class="toggle-button">Toggle Date Selector</button>
      `;
      mapObj.getContainer().appendChild(toggleDiv);

      var dateDiv = L.DomUtil.create('div', 'date-control');
      dateDiv.innerHTML = `
        <label>Start Date:</label><br/>
        <input type="date" id="startDate"/><br/>
        <label>End Date:</label><br/>
        <input type="date" id="endDate"/><br/>
        <button id="applyDates" style="margin-top:5px;">Apply</button>
      `;
      mapObj.getContainer().appendChild(dateDiv);

      var isShown = false;
      document.getElementById('toggleDateBtn').addEventListener('click', function() {{
        isShown = !isShown;
        dateDiv.style.display = isShown ? 'block' : 'none';
      }});

      var now = new Date();
      var yyyy = now.getFullYear();
      var mm = String(now.getMonth()+1).padStart(2, '0');
      var dd = String(now.getDate()).padStart(2, '0');
      var todayStr = yyyy + "-" + mm + "-" + dd;

      var ninetyThreeAgo = new Date(now.getTime() - 93*24*60*60*1000);
      var yyyy2 = ninetyThreeAgo.getFullYear();
      var mm2 = String(ninetyThreeAgo.getMonth()+1).padStart(2, '0');
      var dd2 = String(ninetyThreeAgo.getDate()).padStart(2, '0');
      var defaultStart = yyyy2 + "-" + mm2 + "-" + dd2;

      document.getElementById('startDate').value = defaultStart;
      document.getElementById('endDate').value = todayStr;

      function updateMapRange(startDate, endDate) {{
        clusterObj.clearLayers();
        heatObj.setLatLngs([]);

        let heatInRange = [];
        let count = 0;

        for (var i = 0; i < allMarkers.length; i++) {{
          var entry = allMarkers[i];
          var d = entry.date;
          if (d >= startDate && d <= endDate) {{
            clusterObj.addLayer(entry.marker);
            heatInRange.push([entry.lat, entry.lng]);
            count++;
          }}
        }}

        heatObj.setLatLngs(heatInRange);
        console.log("In-range markers:", count);
      }}

      document.getElementById('applyDates').addEventListener('click', function() {{
        var s = document.getElementById('startDate').value;
        var e = document.getElementById('endDate').value;
        if (s > e) {{
          alert("Start date cannot be after end date!");
          return;
        }}
        updateMapRange(s, e);

        // Fold the date selector back in
        isShown = false;
        dateDiv.style.display = 'none';
      }});

      document.getElementById('loadingOverlay').style.display = 'none';
      updateMapRange(defaultStart, todayStr);
    }}
    </script>
    """
    m.get_root().html.add_child(folium.Element(custom_js))

    # 9) Footer (fixed at bottom)
    footer_html = f"""
    <style>
    .footer {{
        position: fixed;
        left: 0;
        bottom: 0;
        width: 100%;
        background-color: #f1f1f1;
        color: #555;
        text-align: center;
        padding: 0px 0;
        font-size: 10px;
        box-shadow: 0 -2px 5px rgba(0,0,0,0.1);
        z-index: 10000; /* On top */
    }}
    .footer a {{
        color: #555;
        text-decoration: none;
        margin: 0 10px;
    }}
    .footer a:hover {{
        text-decoration: underline;
    }}
    </style>
    <div class="footer">
        Copyright &copy; {datetime.now().year} Jesse Anderson. All rights reserved.
    </div>
    """
    m.get_root().html.add_child(folium.Element(footer_html))

    # 10) Save final HTML
    m.save(output_html)
    print(f"Map saved to {output_html}")

def main():
    df = load_data()
    create_map_load_all(df)

if __name__ == "__main__":
    main()
