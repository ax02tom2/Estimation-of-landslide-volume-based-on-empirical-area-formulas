import streamlit as st
import pandas as pd
import folium
from folium.plugins import Draw
from streamlit_folium import st_folium
from shapely.geometry import shape
from pyproj import Geod
import geopandas as gpd
import json
import zipfile
import os
import tempfile
from branca.element import Element
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut

# -----------------------------------------------------------------------------
# 系統設定
# -----------------------------------------------------------------------------
st.set_page_config(page_title="崩塌量體推估系統", layout="wide")

st.title("⛰️ 崩塌量體推估系統 (面積經驗公式對照)")
st.markdown("本系統整合多組實證經驗公式，支援**手動輸入**及**線上衛星底圖/空間檔案上傳**，快速推估崩塌量體 (V) 與平均滑動深度 (D)。")

# -----------------------------------------------------------------------------
# 經驗公式定義
# -----------------------------------------------------------------------------
FORMULAS = [
    {"name": "陳樹群等 (2010)", "formula": "V = 0.04 * A^1.38", "a": 0.04, "b": 1.38},
    {"name": "Cha et al. (2018)", "formula": "V = 0.596 * A^1.02", "a": 0.596, "b": 1.02},
    {"name": "Guzzetti et al. (2008)", "formula": "V = 0.084 * A^1.43", "a": 0.084, "b": 1.43},
    {"name": "Guzzetti et al. (2009)", "formula": "V = 0.074 * A^1.45", "a": 0.074, "b": 1.45},
    {"name": "Larsen & Torres Sanchez (1998)", "formula": "V = 1.826 * A^0.989", "a": 1.826, "b": 0.989},
    {"name": "Martin et al. (2002)", "formula": "V = 1.0359 * A^0.88", "a": 1.0359, "b": 0.88}
]

# 台灣縣市中心座標字典 (解決 Geocoding 搜尋不穩定的問題)
TAIWAN_CITIES = {
    "選擇縣市快速定位...": None,
    "台北市": [25.032969, 121.565418], "新北市": [25.011985, 121.464522],
    "基隆市": [25.132644, 121.739958], "桃園市": [24.993628, 121.300979],
    "新竹縣": [24.838323, 121.017725], "新竹市": [24.813828, 120.967479],
    "苗栗縣": [24.560158, 120.821427], "台中市": [24.147735, 120.673648],
    "彰化縣": [24.051796, 120.539458], "南投縣": [23.903673, 120.672539],
    "雲林縣": [23.709203, 120.431337], "嘉義縣": [23.451842, 120.255461],
    "嘉義市": [23.480075, 120.449111], "台南市": [22.999728, 120.227027],
    "高雄市": [22.627278, 120.301435], "屏東縣": [22.673895, 120.488050],
    "宜蘭縣": [24.702107, 121.737750], "花蓮縣": [23.987158, 121.601571],
    "台東縣": [22.758333, 121.144444], "澎湖縣": [23.571089, 119.580231],
    "金門縣": [24.432709, 118.322384], "連江縣": [26.150493, 119.936081]
}

def render_results(area_m2):
    if area_m2 <= 0: return
    area_ha = area_m2 / 10000
    area_km2 = area_m2 / 1000000
    
    st.markdown("---")
    st.markdown(f"### 🎯 基準面積計算結果")
    st.markdown(f"**{area_m2:,.2f} 平方公尺 ($m^2$)** ｜ **{area_ha:,.4f} 公頃 ($ha$)** ｜ **{area_km2:,.6f} 平方公里 ($km^2$)**")
    
    cols = st.columns(3)
    for idx, f in enumerate(FORMULAS):
        v = f["a"] * (area_m2 ** f["b"])
        d = v / area_m2 if area_m2 > 0 else 0
        with cols[idx % 3]:
            with st.expander(f"📌 {f['name']}", expanded=True):
                st.markdown(f"""
                <div style='text-align: center; padding: 5px;'>
                    <p style='color: #888; font-size: 0.85em; margin-bottom: 5px;'>公式: {f['formula']}</p>
                    <h3 style='color: #2e6c80; margin-top: 0px;'>V = {v:,.0f} <small>m³</small></h3>
                    <p style='color: #555; margin-bottom: 0px;'>平均滑動深度 (D): <b>{d:,.2f}</b> m</p>
                </div>
                """, unsafe_allow_html=True)

def process_spatial_file(uploaded_file):
    try:
        try:
            import fiona
            fiona.drvsupport.supported_drivers['KML'] = 'rw'
        except Exception:
            pass 

        file_ext = uploaded_file.name.split('.')[-1].lower()
        gdf = None
        
        if file_ext == 'geojson':
            gdf = gpd.read_file(uploaded_file)
        elif file_ext == 'kml':
            gdf = gpd.read_file(uploaded_file, driver='KML')
        elif file_ext == 'kmz':
            with zipfile.ZipFile(uploaded_file, 'r') as kmz:
                kml_filename = [f for f in kmz.namelist() if f.endswith('.kml')][0]
                with kmz.open(kml_filename, 'r') as kml_file:
                    gdf = gpd.read_file(kml_file, driver='KML')
        elif file_ext == 'zip':
            with tempfile.TemporaryDirectory() as tmpdir:
                with zipfile.ZipFile(uploaded_file, 'r') as zip_ref:
                    zip_ref.extractall(tmpdir)
                shp_files = [f for f in os.listdir(tmpdir) if f.endswith('.shp')]
                if not shp_files:
                    st.error("ZIP 壓縮檔內找不到 .shp 檔案！")
                    return None, 0, None
                shp_path = os.path.join(tmpdir, shp_files[0])
                gdf = gpd.read_file(shp_path)
        else:
            return None, 0, None

        # 🚀 終極修正：處理台灣最常見的「TWD97 忘記附 .prj」災難
        if gdf.crs is None:
            minx, miny, maxx, maxy = gdf.total_bounds
            # 如果 X 座標大於 180 (經度極限)，絕對不可能是經緯度，大膽假設是 TWD97 (EPSG:3826)
            if minx > 180:
                gdf.set_crs(epsg=3826, inplace=True)
                st.warning("⚠️ 偵測到無座標系統但數值極大，已自動視為 TWD97 (EPSG:3826) 並進行轉換。")
            else:
                gdf.set_crs(epsg=4326, inplace=True)
        
        # 強制全部轉成 WGS84 經緯度，Folium 才畫得出來
        if gdf.crs.to_epsg() != 4326:
            gdf = gdf.to_crs(epsg=4326)

        geod = Geod(ellps="WGS84")
        total_area = 0
        for geom in gdf.geometry:
            if geom.type == 'Polygon' or geom.type == 'MultiPolygon':
                area, _ = geod.geometry_area_perimeter(geom)
                total_area += abs(area)
        
        bounds = gdf.total_bounds 
        return json.loads(gdf.to_json()), total_area, bounds
        
    except Exception as e:
        st.error(f"檔案解析失敗: {str(e)}")
        return None, 0, None

def inject_folium_draw_fix(m):
    js_injection = """
    <script>
        document.addEventListener("DOMContentLoaded", function() {
            setTimeout(function() {
                if (typeof L !== 'undefined' && L.Edit && L.Edit.PolyVerticesEdit) {
                    L.Edit.PolyVerticesEdit.prototype.options.icon = new L.DivIcon({
                        iconSize: new L.Point(2, 2),
                        className: 'leaflet-div-icon leaflet-editing-icon'
                    });
                    L.Edit.PolyVerticesEdit.prototype.options.touchIcon = new L.DivIcon({
                        iconSize: new L.Point(2, 2),
                        className: 'leaflet-div-icon leaflet-editing-icon leaflet-touch-icon'
                    });
                }
            }, 1000);
        });
    </script>
    """
    m.get_root().html.add_child(Element(js_injection))
    css_injection = """
    <style>
    .leaflet-div-icon.leaflet-editing-icon {
        width: 3px !important; height: 3px !important;
        margin-left: -1px !important; margin-top: -1px !important;
        border-radius: 50% !important; background-color: #ff0000 !important;
        border: none !important;
    }
    .leaflet-draw-tooltip { display: none !important; }
    </style>
    """
    m.get_root().header.add_child(Element(css_injection))


# -----------------------------------------------------------------------------
# 主功能切換 Tabs
# -----------------------------------------------------------------------------
tab1, tab2 = st.tabs(["🔢 1. 數值直接輸入", "🗺️ 2. 衛星底圖圈繪 (含 GIS 檔案)"])

with tab1:
    st.subheader("手動輸入面積 (自動換算單位)")
    col_input, col_unit = st.columns([2, 1])
    with col_input:
        input_area = st.number_input("輸入面積數值", min_value=0.0, value=0.0, step=0.1)
    with col_unit:
        unit_choice = st.selectbox("選擇輸入單位", ["平方公尺 (m²)", "公頃 (ha)", "平方公里 (km²)"])
    
    if unit_choice == "公頃 (ha)": base_area_m2 = input_area * 10000
    elif unit_choice == "平方公里 (km²)": base_area_m2 = input_area * 1000000
    else: base_area_m2 = input_area
        
    if base_area_m2 > 0: render_results(base_area_m2)

with tab2:
    st.subheader("在地圖上圈繪或上傳崩塌範圍")
    st.info("💡 說明：左側地圖可直接點擊圈繪。右側選單可快速定位縣市，或上傳 Shapefile(需打包為ZIP)/KML 檔案。")
    
    # 修正排版：左地圖 (3)，右選單 (1)
    col_map, col_controls = st.columns([3, 1])
    
    # 預設變數
    map_center = [23.6978, 120.9605]
    map_zoom = 7
    fit_bounds_coords = None
    uploaded_geojson = None
    uploaded_area = 0

    with col_controls:
        st.write("### ⚙️ 操作面板")
        st.markdown("---")
        
        # 功能 1：下拉選單快速定位
        st.write("📍 **1. 快速定位縣市**")
        selected_city = st.selectbox("選擇縣市：", list(TAIWAN_CITIES.keys()), label_visibility="collapsed")
        if TAIWAN_CITIES[selected_city]:
            map_center = TAIWAN_CITIES[selected_city]
            map_zoom = 11 # 縣市層級的適當縮放
        
        # 功能 2：精確文字搜尋 (選用)
        st.write("🔍 **2. 進階地名搜尋**")
        search_query = st.text_input("輸入鄉鎮市區、村里或地址", placeholder="例如：南投縣仁愛鄉...")
        if search_query:
            try:
                geolocator = Nominatim(user_agent="landslide_app")
                location = geolocator.geocode(search_query, timeout=5)
                if location:
                    map_center = [location.latitude, location.longitude]
                    map_zoom = 14
                    st.success(f"已定位：{location.name}")
                else:
                    st.warning("找不到該地區")
            except GeocoderTimedOut:
                st.error("搜尋服務超時")
            except Exception as e:
                pass
        
        st.markdown("---")
        
        # 功能 3：上傳空間檔案
        st.write("📂 **3. 上傳空間範圍檔**")
        st.caption("支援 ZIP(Shapefile), KML, KMZ, GeoJSON")
        spatial_file = st.file_uploader("上傳檔案", type=['zip', 'kml', 'kmz', 'geojson'], label_visibility="collapsed")
        
        if spatial_file:
            uploaded_geojson, uploaded_area, uploaded_bounds = process_spatial_file(spatial_file)
            if uploaded_bounds is not None:
                minx, miny, maxx, maxy = uploaded_bounds
                fit_bounds_coords = [[miny, minx], [maxy, maxx]]

    with col_map:
        m = folium.Map(location=map_center, zoom_start=map_zoom) 
        
        if fit_bounds_coords:
            m.fit_bounds(fit_bounds_coords)
            
        inject_folium_draw_fix(m) 
        
        folium.TileLayer(
            tiles='https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}',
            attr='Google',
            name='Google Satellite',
            overlay=False,
            control=True
        ).add_to(m)
        
        if uploaded_geojson:
            folium.GeoJson(
                uploaded_geojson,
                style_function=lambda x: {'fillColor': '#ff0000', 'color': '#ff0000', 'weight': 2, 'fillOpacity': 0.4}
            ).add_to(m)
            
        Draw(export=True, position='topleft', draw_options={
            'polyline': False, 'rectangle': False, 'circle': False, 
            'circlemarker': False, 'marker': False, 
            'polygon': {'allowIntersection': False}
        }).add_to(m)
        
        # 地圖高度配合視窗加高
        map_data = st_folium(m, width="100%", height=650, key="folium_map_satellite")
    
    final_area = 0
    if map_data and map_data.get("all_drawings") and len(map_data["all_drawings"]) > 0:
        latest_drawing = map_data["all_drawings"][-1]
        if latest_drawing["geometry"]["type"] == "Polygon":
            geom = shape(latest_drawing["geometry"])
            geod = Geod(ellps="WGS84")
            area, _ = geod.geometry_area_perimeter(geom)
            final_area = abs(area)
            st.success("✅ 已套用手動圈繪範圍面積。")
            
    elif spatial_file and uploaded_area > 0:
        final_area = uploaded_area
        st.success("✅ 已套用上傳圖層面積。")
        
    if final_area > 0:
         render_results(final_area)
