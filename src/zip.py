from pathlib import Path

import folium
import geopandas as gpd

# Resolve paths against the project root (the parent of this src/ directory) so
# the script runs correctly from anywhere.
ROOT = Path(__file__).resolve().parent.parent

# https://gis-bexar.opendata.arcgis.com/datasets/Bexar::bexar-county-zip-code-areas/explore
zip_codes_geojson = ROOT / "Bexar_County_ZIP_Code_Areas.geojson"

# Read the GeoJSON file using geopandas
gdf = gpd.read_file(zip_codes_geojson)

# Ensure the field name for ZIP codes matches your dataset
zip_code_field = "ZIP"  # Update this if your dataset uses a different field name

# Define the zones with their corresponding ZIP codes and colors
zones2025 = {
    "ILSA": {
        "zip_codes": ["78202","78203","78204","78205","78206","78207","78208", "78210", "78211", "78214", "78215", "78226", "78235", "78236"],
        "color": "yellow"
    }
}

zones = {
    "ILSA": {
        "zip_codes": ["78202","78203","78204","78205","78206","78207","78208", "78210", "78211", "78214", "78215", "78219", "78220", "78225",  "78226", "78228", "78235", "78236", "78237" ],
        "color": "yellow"
    }
}

zones1 = {
    "Zone 1 - Northwest": {
        "zip_codes": ["78250", "78254", "78238", "78251"],
        "color": "DarkTurquoise"
    },
    "Zone 2 - Northside": {
        "zip_codes": ["78257", "78258", "78255", "78256", "78249", "78260", "78259", "78261", "78248", "78231", "78232", "78266"],
        "color": "red"
    },
    "Zone 3 - North Central": {
        "zip_codes": ["78229", "78240", "78230", "78216", "78213"],
        "color": "DarkSeaGreen"
    },
    "Zone 4 - Live Oak/Alamo Heights": {
        "zip_codes": ["78247", "78233", "78217", "78239", "78218", "78209"],
        "color": "purple"
    },
    "Zone 5 - Eastside": {
        "zip_codes": ["78244", "78219", "78220", "78203", "78215", "78205", "78204", "78234", "78212", "78201", "78210"],
        "color": "orange"
    },
    "Zone 6 - Central Downtown": {
        "zip_codes": ["78227", "78228", "78237", "78225"],
        "color": "FireBrick"
    },
    "Zone 7 - Westside": {
        "zip_codes": ["78253", "78245", "78252"],
        "color": "pink"
    },
    "Zone 8 - Southside": {
        "zip_codes": ["78236", "78226", "78242", "78235", "78224", "78264", "78263", "78214", "78223", "78222"],
        "color": "cyan"
    },
    "Zone X - ILSA": {
        "zip_codes": ["78202","78203","78204","78205","78206","78207","78208", "78210", "78211", "78214", "78215", "78226", "78235", "78236"],
        "color": "yellow"
    }
}

# Critical:         "zip_codes": ["78202","78207", "78208", "78211"],

# Create a map centered on San Antonio
san_antonio_center = [29.4241, -98.4936]
m = folium.Map(location=san_antonio_center, zoom_start=11)

# Function to add a zone to the map
def add_zone_to_map(gdf, zone, color):
    zone_gdf = gdf[gdf[zip_code_field].isin(zone["zip_codes"])]
    folium.GeoJson(
        zone_gdf,
        style_function=lambda feature: {
            'fillColor': color,
            'color': 'black',
            'weight': 1,
            'fillOpacity': 0.6,
        },
        tooltip=folium.GeoJsonTooltip(fields=[zip_code_field], aliases=['ZIP Code:'])
    ).add_to(m)

# Add each zone to the map
for zone_name, data in zones.items():
    add_zone_to_map(gdf, data, data["color"])

# Create a legend with a solid white background
legend_html = '''
<div style="position: fixed; 
     bottom: 50px; left: 50px; width: 260px; height: 80px; 
     background-color: white; border:2px solid grey; z-index:9999; font-size:14px;
     ">&nbsp; <b>Legend</b> <br>
     &nbsp;&nbsp;<i class="fa fa-map-marker fa-2x" style="color:yellow"></i>&nbsp; Zone ILSA &nbsp; 
</div>
'''
legend_html1 = '''
<div style="position: fixed; 
     bottom: 50px; left: 50px; width: 260px; height: 300px; 
     background-color: white; border:2px solid grey; z-index:9999; font-size:14px;
     ">&nbsp; <b>Legend</b> <br>
     &nbsp;&nbsp;<i class="fa fa-map-marker fa-2x" style="color:DarkTurquoise"></i>&nbsp; Zone 1 - Northwest &nbsp; <br>
     &nbsp;&nbsp;<i class="fa fa-map-marker fa-2x" style="color:red"></i>&nbsp; Zone 2 - Northside &nbsp; <br>
     &nbsp;&nbsp;<i class="fa fa-map-marker fa-2x" style="color:DarkSeaGreen"></i>&nbsp; Zone 3 - North Central &nbsp; <br>
     &nbsp;&nbsp;<i class="fa fa-map-marker fa-2x" style="color:purple"></i>&nbsp; Zone 4 - Live Oak/Alamo Heights &nbsp; <br>
     &nbsp;&nbsp;<i class="fa fa-map-marker fa-2x" style="color:orange"></i>&nbsp; Zone 5 - Eastside &nbsp; <br>
     &nbsp;&nbsp;<i class="fa fa-map-marker fa-2x" style="color:FireBrick"></i>&nbsp; Zone 6 - Central Downtown &nbsp; <br>
     &nbsp;&nbsp;<i class="fa fa-map-marker fa-2x" style="color:pink"></i>&nbsp; Zone 7 - Westside &nbsp; <br>
     &nbsp;&nbsp;<i class="fa fa-map-marker fa-2x" style="color:cyan"></i>&nbsp; Zone 8 - Southside &nbsp; <br>
     &nbsp;&nbsp;<i class="fa fa-map-marker fa-2x" style="color:yellow"></i>&nbsp; Zone ILSA &nbsp; 
</div>
'''
m.get_root().html.add_child(folium.Element(legend_html))

# Save the map to an HTML file
m.save(str(ROOT / "san_antonio_zones_map_with_boundaries.html"))
