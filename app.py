import os
import glob
import streamlit as st
import geopandas as gpd
import pandas as pd
import folium
from streamlit_folium import st_folium
import plotly.express as px
import requests

st.set_page_config(layout="wide", page_title="Castor Farm GIS & Weather Dashboard", page_icon="🌱")

# --- WMO WEATHER CODE MAPPING ---
WMO_WEATHER_MAP = {
    0: ("☀️ Clear sky", "☀️"),
    1: ("🌤️ Mainly clear", "🌤️"),
    2: ("⛅ Partly cloudy", "⛅"),
    3: ("☁️ Overcast", "☁️"),
    45: ("🌫️ Fog", "🌫️"),
    48: ("🌫️ Depositing rime fog", "🌫️"),
    51: ("🌦️ Light drizzle", "🌦️"),
    53: ("🌦️ Moderate drizzle", "🌦️"),
    55: ("🌧️ Dense drizzle", "🌧️"),
    61: ("🌦️ Slight rain", "🌦️"),
    63: ("🌧️ Moderate rain", "🌧️"),
    65: ("🌧️ Heavy rain", "🌧️"),
    80: ("🌦️ Slight rain showers", "🌦️"),
    81: ("🌧️ Moderate rain showers", "🌧️"),
    82: ("⛈️ Violent rain showers", "⛈️"),
    95: ("⛈️ Thunderstorm", "⛈️")
}

def decode_weather(code, rain_mm):
    if code in WMO_WEATHER_MAP:
        desc, icon = WMO_WEATHER_MAP[code]
        return f"{icon} {desc.split(' ', 1)[1]}"
    if rain_mm == 0:
        return "☀️ Sunny / Dry"
    elif rain_mm < 2.5:
        return "🌤️ Light Drizzle"
    elif rain_mm < 10.0:
        return "🌦️ Moderate Rain"
    else:
        return "🌧️ Heavy Rain"

def sanitize_gdf(df):
    clean_df = df.copy()
    for col in clean_df.columns:
        if pd.api.types.is_datetime64_any_dtype(clean_df[col]) or isinstance(clean_df[col].iloc[0] if len(clean_df) > 0 else None, pd.Timestamp):
            clean_df[col] = clean_df[col].astype(str)
    return clean_df

@st.cache_data
def load_data():
    # Direct search paths including exact repo file name
    possible_paths = [
        "farms_polygons_All.gpkg",
        "farm_boundaries.gpkg",
        "data/farms_polygons_All.gpkg",
        "data/farm_boundaries.gpkg",
    ]
    
    file_path = None
    for p in possible_paths:
        if os.path.exists(p):
            file_path = p
            break
            
    if file_path is None:
        gpkg_files = glob.glob("*.gpkg") + glob.glob("**/*.gpkg", recursive=True)
        if gpkg_files:
            file_path = gpkg_files[0]
            
    if file_path is None:
        return None

    try:
        gdf = gpd.read_file(file_path, layer="farm_boundaries")
    except Exception:
        gdf = gpd.read_file(file_path)

    if gdf.crs is None or gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs(epsg=4326)
    return sanitize_gdf(gdf)

@st.cache_data(ttl=3600)
def fetch_weather_forecast(lat, lon):
    url = (
        f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
        f"&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum,"
        f"precipitation_probability_max,wind_speed_10m_max,et0_fao_evapotranspiration&timezone=auto"
    )
    try:
        res = requests.get(url, timeout=10).json()
        if "daily" in res:
            return res["daily"]
    except Exception:
        pass
    return None

# --- LOAD DATA AUTOMATICALLY ---
gdf = load_data()

if gdf is None:
    st.error("Dataset not found in repository. Please ensure '.gpkg' file is committed to your GitHub repo.")
    st.stop()

# --- APP HEADER ---
st.title("🌱 Castor Project Location & Weather Prediction Dashboard")
st.caption("Interactive Spatial GIS Monitoring & Regional Agro-Weather Forecast System")

# --- SIDEBAR HIERARCHY FILTERS ---
st.sidebar.header("📍 Location Hierarchy Filter")
counties = ["All"] + sorted([str(x) for x in gdf['County'].dropna().unique() if str(x).strip() != ""])
selected_county = st.sidebar.selectbox("Select County", counties)

filtered_gdf = gdf.copy()
if selected_county != "All":
    filtered_gdf = filtered_gdf[filtered_gdf['County'] == selected_county]

subcounties = ["All"] + sorted([str(x) for x in filtered_gdf['Subcounty'].dropna().unique() if str(x).strip() != ""])
selected_subcounty = st.sidebar.selectbox("Select Subcounty", subcounties)

if selected_subcounty != "All":
    filtered_gdf = filtered_gdf[filtered_gdf['Subcounty'] == selected_subcounty]

wards = ["All"] + sorted([str(x) for x in filtered_gdf['Ward'].dropna().unique() if str(x).strip() != ""])
selected_ward = st.sidebar.selectbox("Select Ward", wards)

if selected_ward != "All":
    filtered_gdf = filtered_gdf[filtered_gdf['Ward'] == selected_ward]

# --- TOP METRICS ---
col1, col2 = st.columns(2)
col1.metric("Selected Farms", len(filtered_gdf))
col2.metric("Total Acres", f"{filtered_gdf['Acres'].sum():.2f}" if 'Acres' in filtered_gdf.columns else "N/A")

st.markdown("---")

# --- DASHBOARD TABS ---
tab1, tab2, tab3 = st.tabs(["🗺️ GIS Map & Status", "📊 Hierarchy Analytics & Subcounty Weather", "🌤️ Detailed Region Weather Forecast"])

with tab1:
    st.subheader("Interactive Farm Boundaries Map")
    if not filtered_gdf.empty:
        bounds = filtered_gdf.total_bounds
        centroid_lat = (bounds[1] + bounds[3]) / 2
        centroid_lon = (bounds[0] + bounds[2]) / 2

        m = folium.Map(
            location=[centroid_lat, centroid_lon],
            zoom_start=12,
            tiles="https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}",
            attr="Google Satellite Hybrid"
        )

        tooltip_cols = [c for c in ["Farmer Name", "Acres", "Contract No"] if c in filtered_gdf.columns]
        popup_cols = [c for c in ["Farmer Name", "County", "Subcounty", "Ward", "Seed Variety", "Field Officer"] if c in filtered_gdf.columns]

        folium.GeoJson(
            filtered_gdf,
            name="Farm Boundaries",
            style_function=lambda feature: {
                'fillColor': '#228B22', 'color': '#006400', 'weight': 2, 'fillOpacity': 0.4
            },
            highlight_function=lambda feature: {
                'fillColor': '#FFD700', 'color': '#FF8C00', 'weight': 3, 'fillOpacity': 0.7
            },
            tooltip=folium.GeoJsonTooltip(fields=tooltip_cols) if tooltip_cols else None,
            popup=folium.GeoJsonPopup(fields=popup_cols) if popup_cols else None
        ).add_to(m)

        st_folium(m, width=1200, height=500)
    else:
        st.warning("No farm polygons found for selected location hierarchy.")

with tab2:
    st.subheader("Breakdown by Location Hierarchy & Subcounty Weather Drill-Down")
    
    col_a, col_b = st.columns(2)
    
    subcounty_counts = filtered_gdf['Subcounty'].value_counts().reset_index()
    subcounty_counts.columns = ['Subcounty', 'Farm Count']
    fig_sub = px.bar(subcounty_counts, x='Subcounty', y='Farm Count', title="Farms per Subcounty", color='Farm Count', color_continuous_scale='Greens')
    col_a.plotly_chart(fig_sub, use_container_width=True)

    ward_counts = filtered_gdf['Ward'].value_counts().reset_index()
    ward_counts.columns = ['Ward', 'Farm Count']
    fig_ward = px.bar(ward_counts, x='Ward', y='Farm Count', title="Farms per Ward", color='Farm Count', color_continuous_scale='Greens')
    col_b.plotly_chart(fig_ward, use_container_width=True)

    st.markdown("---")
    
    st.subheader("🌤️ Subcounty Weather Prediction Drill-Down")
    available_subcounties = sorted([str(s) for s in filtered_gdf['Subcounty'].dropna().unique() if str(s).strip() != ""])
    
    if available_subcounties:
        target_subcounty = st.selectbox("Select Subcounty to view 7-Day Weather Forecast:", available_subcounties)
        sub_gdf = filtered_gdf[filtered_gdf['Subcounty'] == target_subcounty]
        
        if not sub_gdf.empty:
            s_bounds = sub_gdf.total_bounds
            s_lat = (s_bounds[1] + s_bounds[3]) / 2
            s_lon = (s_bounds[0] + s_bounds[2]) / 2

            daily_res = fetch_weather_forecast(s_lat, s_lon)
            if daily_res:
                codes = daily_res.get("weather_code", [0]*7)
                rains = daily_res.get("precipitation_sum", [0.0]*7)
                probs = daily_res.get("precipitation_probability_max", [0]*7)
                max_t = daily_res.get("temperature_2m_max", [0.0]*7)
                min_t = daily_res.get("temperature_2m_min", [0.0]*7)
                winds = daily_res.get("wind_speed_10m_max", [0.0]*7)
                et0 = daily_res.get("et0_fao_evapotranspiration", [0.0]*7)
                dates = daily_res.get("time", [])

                cond_list = [decode_weather(c, r) for c, r in zip(codes, rains)]

                sub_weather_df = pd.DataFrame({
                    "Date": dates,
                    "Weather Condition": cond_list,
                    "Max Temp (°C)": max_t,
                    "Min Temp (°C)": min_t,
                    "Rainfall (mm)": rains,
                    "Rain Chance (%)": probs,
                    "Max Wind (km/h)": winds,
                    "ET0 Evapotranspiration (mm)": et0
                })

                st.write(f"### 📍 7-Day Weather Forecast for **{target_subcounty} Subcounty** (Lat: `{s_lat:.4f}`, Lon: `{s_lon:.4f}`)")
                
                card_cols = st.columns(len(dates))
                for idx, col in enumerate(card_cols):
                    if idx < len(dates):
                        day_name = pd.to_datetime(dates[idx]).strftime("%a %d")
                        cond_str = cond_list[idx]
                        col.metric(
                            label=f"{day_name}",
                            value=f"{max_t[idx]}°C",
                            delta=f"{rains[idx]} mm rain"
                        )
                        col.caption(f"{cond_str}")

                st.markdown("<br>", unsafe_allow_html=True)
                st.dataframe(sub_weather_df, use_container_width=True)
            else:
                st.error("Unable to fetch weather forecast for this subcounty.")
    else:
        st.info("No subcounties available for current filter.")

    st.subheader("Tabular Data Preview")
    display_cols = ["Farmer Name", "County", "Subcounty", "Ward", "Acres", "Seed Variety", "Field Officer"]
    st.dataframe(filtered_gdf[[col for col in display_cols if col in filtered_gdf.columns]], use_container_width=True)

with tab3:
    st.subheader("Overall Region Weather Forecast & Summary")
    if not filtered_gdf.empty:
        bounds = filtered_gdf.total_bounds
        lat = (bounds[1] + bounds[3]) / 2
        lon = (bounds[0] + bounds[2]) / 2

        daily_res = fetch_weather_forecast(lat, lon)
        if daily_res:
            codes = daily_res.get("weather_code", [0]*7)
            rains = daily_res.get("precipitation_sum", [0.0]*7)
            probs = daily_res.get("precipitation_probability_max", [0]*7)
            max_t = daily_res.get("temperature_2m_max", [0.0]*7)
            min_t = daily_res.get("temperature_2m_min", [0.0]*7)
            et0 = daily_res.get("et0_fao_evapotranspiration", [0.0]*7)
            dates = daily_res.get("time", [])

            cond_list = [decode_weather(c, r) for c, r in zip(codes, rains)]

            daily_data = pd.DataFrame({
                "Date": dates,
                "Daily Weather Condition": cond_list,
                "Max Temp (°C)": max_t,
                "Min Temp (°C)": min_t,
                "Rainfall (mm)": rains,
                "Precipitation Prob (%)": probs,
                "Evapotranspiration ET0 (mm)": et0
            })

            st.write(f"**7-Day Regional Weather Forecast** (Lat: `{lat:.4f}`, Lon: `{lon:.4f}`):")
            st.dataframe(daily_data, use_container_width=True)

            total_rain_7d = sum(rains)
            max_daily_rain = max(rains)

            st.markdown("### 🌾 Weekly Weather Prediction Summary")
            
            if total_rain_7d >= 50 or max_daily_rain >= 20:
                st.info(
                    f"🌧️ **Active Rain Cycle ({total_rain_7d:.1f} mm expected over 7 days):** "
                    f"Significant precipitation predicted across the selected region with a maximum daily rainfall of {max_daily_rain:.1f} mm."
                )
            elif 15 <= total_rain_7d < 50:
                st.success(
                    f"🌱 **Moderate Rainfall Pattern ({total_rain_7d:.1f} mm expected over 7 days):** "
                    f"Steady precipitation expected with well-distributed showers across subcounties."
                )
            else:
                st.warning(
                    f"☀️ **Predominantly Dry Weather ({total_rain_7d:.1f} mm expected over 7 days):** "
                    f"Low rainfall forecast across the region alongside high evapotranspiration levels."
                )
        else:
            st.error("Failed to fetch weather forecast data.")
