import streamlit as st
import pandas as pd
import geopandas as gpd
import numpy as np
import plotly.graph_objects as go
from shapely.geometry import Point, Polygon, MultiPolygon
from shapely.ops import unary_union
import os
import shutil
import itertools

# --- PAGE CONFIG ---
st.set_page_config(
    page_title="BRINC Commander | Station Optimizer", 
    layout="wide", 
    page_icon="https://i.imgur.com/fdz302t.png" # Using a small cropped version of the logo for favicon
)

# --- BRINC COLOR PALETTE & ASSETS ---
BRINC_CYAN = "#00E5FF"
BRINC_DARK_BG = "#121212" # Main background
BRINC_CARD_BG = "#1E1E1E" # Card background
BRINC_TEXT_MAIN = "#FFFFFF"
BRINC_TEXT_SUB = "#B0BEC5"
BRINC_LOGO_URL = "https://i.imgur.com/fdz302t.png" # The BRINC Logo provided

# Station Ring Colors (BRINC themed cyans/grays)
STATION_COLORS = [
    "#00E5FF", "#FFFFFF", "#00B8D4", "#B0BEC5", 
    "#18FFFF", "#ECEFF1", "#00838F", "#90A4AE"
]

# --- CUSTOM CSS INJECTION FOR DARK THEME & CARDS ---
st.markdown(f"""
    <style>
        /* Main Background */
        .stApp {{
            background-color: {BRINC_DARK_BG};
            color: {BRINC_TEXT_MAIN};
        }}
        /* Hide default Streamlit header/footer */
        header {{visibility: hidden;}}
        footer {{visibility: hidden;}}
        
        /* Custom Metric Card Style */
        div.metric-container {{
            background-color: {BRINC_CARD_BG};
            border: 1px solid #333;
            padding: 20px;
            border-radius: 8px;
            text-align: center;
            box-shadow: 0 4px 6px rgba(0,0,0,0.3);
        }}
        div.metric-container h3 {{
            margin: 0;
            font-size: 1.1rem;
            color: {BRINC_TEXT_SUB};
            font-weight: 400;
        }}
        div.metric-container h2 {{
            margin: 10px 0 0 0;
            font-size: 2.5rem;
            color: {BRINC_CYAN};
            font-weight: 700;
        }}

        /* Custom Station List Card Style */
        div.station-card {{
            background-color: {BRINC_CARD_BG};
            border-left: 6px solid {BRINC_CYAN};
            padding: 15px;
            margin-bottom: 10px;
            border-radius: 4px;
            display: flex;
            align-items: center;
        }}
        div.station-num {{
            font-size: 1.5rem;
            font-weight: bold;
            color: {BRINC_TEXT_MAIN};
            margin-right: 15px;
            background: rgba(0, 229, 255, 0.2);
            width: 40px;
            height: 40px;
            display: flex;
            justify-content: center;
            align-items: center;
            border-radius: 50%;
        }}
        div.station-details h4 {{
             margin: 0; color: {BRINC_TEXT_MAIN}; font-size: 1.1rem;
        }}
        div.station-details p {{
             margin: 5px 0 0 0; color: {BRINC_TEXT_SUB}; font-size: 0.9rem;
        }}
        
        /* Adjust Streamlit widgets to dark mode */
        .stSelectbox label, .stSlider label, .stRadio label, .stMultiSelect label {{
            color: {BRINC_TEXT_MAIN} !important;
        }}
        div[data-baseweb="select"] > div {{
            background-color: {BRINC_CARD_BG} !important;
            color: {BRINC_TEXT_MAIN} !important;
            border-color: #333 !important;
        }}
        div[data-baseweb="popover"] {{ background-color: {BRINC_CARD_BG} !important; }}
        div[data-testid="stExpander"] {{
            background-color: {BRINC_CARD_BG};
            border: 1px solid #333;
            border-radius: 8px;
        }}
    </style>
""", unsafe_allow_html=True)

# --- SESSION STATE INITIALIZATION ---
if 'box_open' not in st.session_state: st.session_state.box_open = True

# --- HEADER SECTION ---
col_header1, col_header2 = st.columns([1, 4])
with col_header1:
    st.image(BRINC_LOGO_URL, width=180)
with col_header2:
    st.title("DRONE STATION OPTIMIZATION")
    st.caption("Advanced Unmanned Systems // Tactical Command")

st.markdown("---")

# --- SPEED OPTIMIZATION: CACHING ---
@st.cache_data
def process_geo_data(shp_path, selection):
    gdf = gpd.read_file(shp_path)
    if gdf.crs is None: gdf.set_crs(epsg=4269, inplace=True)
    gdf['geometry'] = gdf['geometry'].simplify(0.0001, preserve_topology=True)
    name_col = 'DISTRICT' if 'DISTRICT' in gdf.columns else 'NAME'
    
    if selection == "SHOW ALL DISTRICTS":
        active_gdf = gdf.to_crs(epsg=4326)
        boundary = unary_union(active_gdf.geometry)
    else:
        active_gdf = gdf[gdf[name_col] == selection].to_crs(epsg=4326)
        boundary = active_gdf.iloc[0].geometry
    return gdf, active_gdf, boundary, name_col

# --- DATA IMPORT SECTION ---
call_data, station_data, shape_components = None, None, []
# Using an expander that matches the dark theme styling
with st.expander("📁 FILE UPLOAD & JURISDICTION SELECTION", expanded=st.session_state.box_open):
    col_up1, col_up2 = st.columns([3, 2])
    with col_up1:
        uploaded_files = st.file_uploader("Upload Incident CSV, Station CSV, and 4 Shapefiles", accept_multiple_files=True)
    
    # Process files
    if uploaded_files:
        for f in uploaded_files:
            fname = f.name.lower()
            if fname == "calls.csv": call_data = f
            elif fname == "stations.csv": station_data = f
            elif any(fname.endswith(ext) for ext in ['.shp', '.shx', '.dbf', '.prj']):
                shape_components.append(f)

        # Auto-close logic
        if call_data and station_data and len(shape_components) >= 4 and st.session_state.box_open:
            st.session_state.box_open = False
            st.rerun()

# --- MAIN APP LOGIC ---
if call_data and station_data and len(shape_components) >= 3:
    # Temp file handling
    if not os.path.exists("temp"): os.mkdir("temp")
    for f in shape_components:
        with open(os.path.join("temp", f.name), "wb") as buffer: buffer.write(f.getbuffer())
    
    try:
        # Load & Process Geo
        shp_path = [os.path.join("temp", f.name) for f in shape_components if f.name.endswith('.shp')][0]
        temp_gdf = gpd.read_file(shp_path)
        name_col_init = 'DISTRICT' if 'DISTRICT' in temp_gdf.columns else 'NAME'
        options = ["SHOW ALL DISTRICTS"] + sorted(temp_gdf[name_col_init].unique().tolist())
        
        # Jurisdiction Select (inside expander for clean look)
        with col_up2:
             selection = st.selectbox("📍 Select Active Jurisdiction", options)

        gdf_all, active_gdf, city_boundary, name_col = process_geo_data(shp_path, selection)
        utm_zone = int((city_boundary.centroid.x + 180) / 6) + 1
        epsg_code = f"326{utm_zone}" if city_boundary.centroid.y > 0 else f"327{utm_zone}"
        city_m = active_gdf.to_crs(epsg=epsg_code).unary_union
        
        # Load DataFrames
        df_calls = pd.read_csv(call_data).dropna(subset=['lat', 'lon'])
        df_stations_all = pd.read_csv(station_data).dropna(subset=['lat', 'lon'])
        
        # Spatial Join Calls
        gdf_calls = gpd.GeoDataFrame(df_calls, geometry=gpd.points_from_xy(df_calls.lon, df_calls.lat), crs="EPSG:4326")
        calls_in_city = gdf_calls[gdf_calls.within(city_boundary)].to_crs(epsg=epsg_code)
        calls_in_city['point_idx'] = range(len(calls_in_city))
        
        # Pre-calculate Station Coverage
        radius_m = 3218.69 
        station_metadata = []
        for i, row in df_stations_all.iterrows():
            s_pt_m = gpd.GeoSeries([Point(row['lon'], row['lat'])], crs="EPSG:4326").to_crs(epsg=epsg_code).iloc[0]
            mask = calls_in_city.geometry.distance(s_pt_m) <= radius_m
            station_metadata.append({
                'name': row['name'], 'lat': row['lat'], 'lon': row['lon'],
                'clipped_m': s_pt_m.buffer(radius_m).intersection(city_m),
                'indices': set(calls_in_city[mask]['point_idx'])
            })

        # --- CONTROLS SECTION (Top horizontal bar) ---
        st.markdown("##### **OPTIMIZER CONTROLS**")
        c1, c2, c3 = st.columns([2, 2, 3])
        with c1:
            k = st.slider("Drones to Deploy", 1, len(station_metadata), min(3, len(station_metadata)))
        with c2:
            # Using horizontal radio btns to look like tabs in the image
            strategy = st.radio("Strategy Mode", ("Max Response Volume", "Max Geographic Equity"), horizontal=True)
        with c3:
             if st.button("🔄 Reset Data Upload"):
                st.session_state.box_open = True
                st.rerun()


        # --- RUN OPTIMIZER ---
        combos = list(itertools.combinations(range(len(station_metadata)), k))
        if len(combos) > 500: combos = combos[:500] 
        
        best_combo = None
        if strategy == "Max Response Volume":
            max_val = -1
            for combo in combos:
                val = len(set().union(*(station_metadata[i]['indices'] for i in combo)))
                if val > max_val: max_val = val; best_combo = combo
        else:
            max_val = -1
            for combo in combos:
                val = unary_union([station_metadata[i]['clipped_m'] for i in combo]).area
                if val > max_val: max_val = val; best_combo = combo
            
        default_sel = [station_metadata[i]['name'] for i in best_combo] if best_combo else []
        # Hidden multiselect to maintain state logic, but controlled by optimizer
        active_names = default_sel

        # --- METRICS CALCULATION ---
        active_data = [s for s in station_metadata if s['name'] in active_names]
        all_ids = set().union(*[s['indices'] for s in active_data]) if active_data else set()
        total_calls = len(calls_in_city)
        cap_perc = (len(all_ids) / total_calls * 100) if total_calls > 0 else 0
        total_geo = unary_union([s['clipped_m'] for s in active_data]) if active_data else None
        land_perc = (total_geo.area / city_m.area * 100) if total_geo else 0
        uncovered = total_calls - len(all_ids)

        # --- METRICS ROW (Top Cards) ---
        st.markdown("---")
        m1, m2, m3, m4 = st.columns(4)
        
        # Using custom HTML strings to create the card look
        m1.markdown(f"""<div class="metric-container"><h3>Total Incidents</h3><h2>{total_calls:,}</h2></div>""", unsafe_allow_html=True)
        m2.markdown(f"""<div class="metric-container"><h3>Capacity %</h3><h2>{cap_perc:.1f}%</h2></div>""", unsafe_allow_html=True)
        m3.markdown(f"""<div class="metric-container"><h3>Land Covered %</h3><h2>{land_perc:.1f}%</h2></div>""", unsafe_allow_html=True)
        m4.markdown(f"""<div class="metric-container"><h3>Uncovered</h3><h2 style="color:#FF5252">{uncovered:,}</h2></div>""", unsafe_allow_html=True)
        st.markdown("---")

        # --- MAIN CONTENT SPLIT (Map Left, List Right) ---
        map_col, list_col = st.columns([2, 1])

        # --- RIGHT COLUMN: STATION LIST ---
        with list_col:
            st.markdown("##### **DEPLOYED STATIONS**")
            all_st_names = df_stations_all['name'].tolist()
            for i, s in enumerate(active_data):
                # Match color to map ring
                color = STATION_COLORS[all_st_names.index(s['name']) % len(STATION_COLORS)]
                # Custom HTML Card for station list
                st.markdown(f"""
                    <div class="station-card" style="border-left-color: {color};">
                        <div class="station-num" style="color: {color}; background: {color}33;">{i+1}</div>
                        <div class="station-details">
                            <h4>{s['name']}</h4>
                            <p>Lat: {s['lat']:.4f}, Lon: {s['lon']:.4f}</p>
                        </div>
                    </div>
                """, unsafe_allow_html=True)

        # --- LEFT COLUMN: THE MAP ---
        with map_col:
            fig = go.Figure()
            
            # 1. District Boundary Lines (Dark Gray)
            for _, row in gdf_all.to_crs(epsg=4326).iterrows():
                geom = row.geometry
                p_list = [geom] if isinstance(geom, Polygon) else list(geom.geoms)
                for p in p_list:
                    bx, by = p.exterior.coords.xy
                    fig.add_trace(go.Scattermapbox(mode="lines", lon=list(bx), lat=list(by), line=dict(color="#444", width=1), showlegend=False, hoverinfo='skip'))
            
            # 2. Incidents (Small faint blue dots, no hover)
            sample = calls_in_city.to_crs(epsg=4326).sample(min(3000, total_calls))
            fig.add_trace(go.Scattermapbox(
                lat=sample.geometry.y, lon=sample.geometry.x, mode='markers', 
                marker=dict(size=3, color='#00E5FF', opacity=0.2), # Using Brinc cyan for dots too
                hoverinfo='skip'
            ))
            
            # 3. Active Stations (Rings and Big Dots)
            for s in active_data:
                color = STATION_COLORS[all_st_names.index(s['name']) % len(STATION_COLORS)]
                angles = np.linspace(0, 2*np.pi, 60)
                clats = s['lat'] + (2/69.172) * np.sin(angles)
                clons = s['lon'] + (2/(69.172 * np.cos(np.radians(s['lat'])))) * np.cos(angles)
                
                # Ring
                fig.add_trace(go.Scattermapbox(
                    lat=list(clats)+[clats[0]], lon=list(clons)+[clons[0]], 
                    mode='lines', line=dict(color=color, width=3), 
                    hoverinfo='skip', showlegend=False
                ))
                # Center Dot
                fig.add_trace(go.Scattermapbox(
                    lat=[s['lat']], lon=[s['lon']], mode='markers', 
                    marker=dict(size=18, color=color), name=s['name'], hoverinfo='name'
                ))

            # Update layout for Dark Mode Map
            fig.update_layout(
                mapbox_style="carto-darkmatter", # Crucial for the dark theme look
                mapbox_zoom=11, mapbox_center={"lat": city_boundary.centroid.y, "lon": city_boundary.centroid.x},
                margin={"r":0,"t":0,"l":0,"b":0}, height=650,
                paper_bgcolor=BRINC_CARD_BG, plot_bgcolor=BRINC_CARD_BG, # Match plot background to card color
                font=dict(color=BRINC_TEXT_MAIN) # Legend text color
            )
            st.plotly_chart(fig, use_container_width=True)

    except Exception as e:
        st.error(f"System Error: {e}")
else:
    # Placeholder if no data loaded yet
    st.info("Awaiting Data Payload. Please upload files in the expander above.")
    # Generate empty cards for visual consistency before load
    m1, m2, m3, m4 = st.columns(4)
    m1.markdown(f"""<div class="metric-container"><h3>Total Incidents</h3><h2>--</h2></div>""", unsafe_allow_html=True)
    m2.markdown(f"""<div class="metric-container"><h3>Capacity %</h3><h2>--%</h2></div>""", unsafe_allow_html=True)
    m3.markdown(f"""<div class="metric-container"><h3>Land Covered %</h3><h2>--%</h2></div>""", unsafe_allow_html=True)
    m4.markdown(f"""<div class="metric-container"><h3>Uncovered</h3><h2>--</h2></div>""", unsafe_allow_html=True)