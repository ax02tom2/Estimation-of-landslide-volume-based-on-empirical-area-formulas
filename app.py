import streamlit as st
import pandas as pd
from PIL import Image
import folium
from folium.plugins import Draw
from streamlit_folium import st_folium
from shapely.geometry import shape, Polygon, MultiPolygon
from pyproj import Geod
import geopandas as gpd
import json
import zipfile
import io
import os
import tempfile
from branca.element import Element

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

def render_results(area_m2):
    """結果渲染模組 (卡片式對齊)"""
    if area_m2 <= 0:
        return
        
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
    """處理上傳的空間檔案，支援 ZIP(Shapefile), KML, KMZ, GeoJSON"""
    try:
        gpd.io.file.fiona.drvsupport.supported_drivers['KML'] = 'rw'
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
                    return None, 0
                shp_path = os.path.join(tmpdir, shp_files[0])
                gdf = gpd.read_file(shp_path)
        else:
            return None, 0

        # 強制轉換為 WGS84
        if gdf.crs and gdf.crs.to_epsg() != 4326:
            gdf = gdf.to_crs(epsg=4326)
        elif gdf.crs is None:
             gdf.set_crs(epsg=4326, inplace=True)

        # 計算 WGS84 面積
        geod = Geod(ellps="WGS84")
        total_area = 0
        for geom in gdf.geometry:
            if geom.type == 'Polygon' or geom.type == 'MultiPolygon':
                area, _ = geod.geometry_area_perimeter(geom)
                total_area += abs(area)
                
        return json.loads(gdf.to_json()), total_area
        
    except Exception as e:
        st.error(f"檔案解析失敗: {str(e)}")
        return None, 0

# -----------------------------------------------------------------------------
# 注入 Folium 畫圖節點縮小修正 (極小紅點)
# -----------------------------------------------------------------------------
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
        width: 3px !important;
        height: 3px !important;
        margin-left: -1px !important;
        margin-top: -1px !important;
        border-radius: 50% !important;
        background-color: #ff0000 !important;
        border: none !important;
    }
    .leaflet-draw-tooltip { display: none !important; }
    </style>
    """
    m.get_root().header.add_child(Element(css_injection))

# -----------------------------------------------------------------------------
# 主功能切換 Tabs (已精簡，徹底刪除自訂影像上傳)
# -----------------------------------------------------------------------------
tab1, tab2 = st.tabs(["🔢 1. 數值直接輸入", "🗺️ 2. 衛星底圖圈繪 (含 GIS 檔案)"])

# ====== Tab 1: 數值直接輸入 ======
with tab1:
    st.subheader("手動輸入面積 (自動換算單位)")
    col_input, col_unit = st.columns([2, 1])
    with col_input:
        input_area = st.number_input("輸入面積數值", min_value=0.0, value=0.0, step=0.1)
    with col_unit:
        unit_choice = st.selectbox("選擇輸入單位", ["平方公尺 (m²)", "公頃 (ha)", "平方公里 (km²)"])
    
    if unit_choice == "公頃 (ha)":
        base_area_m2 = input_area * 10000
    elif unit_choice == "平方公里 (km²)":
        base_area_m2 = input_area * 1000000
    else:
        base_area_m2 = input_area
        
    if base_area_m2 > 0:
        render_results(base_area_m2)

# ====== Tab 2: 衛星底圖圈繪 (含檔案上傳) ======
with tab2:
    st.subheader("在地圖上圈繪或上傳崩塌範圍")
    st.info("💡 說明：左側工具列可直接圈繪。若要上傳既有範圍，Shapefile 格式請將相關檔案打包成 ZIP 壓縮檔上傳。")
    
    col_map, col_upload = st.columns([3, 1])
    with col_upload:
        st.write("📂 **上傳空間範圍檔 (ZIP/KML/GeoJSON)**")
        spatial_file = st.file_uploader("支援 ZIP(Shapefile), KML, KMZ, GeoJSON", type=['zip', 'kml', 'kmz', 'geojson'])
    
    map_center = [23.6978, 120.9605] # 預設台灣中心
    map_zoom = 7
    uploaded_geojson = None
    uploaded_area = 0

    if spatial_file:
        uploaded_geojson, uploaded_area = process_spatial_file(spatial_file)
        # 自動定位到上傳圖層的中心
        if uploaded_geojson and len(uploaded_geojson.get('features', [])) > 0:
            try:
                first_geom = uploaded_geojson['features'][0]['geometry']
                if first_geom['type'] == 'Polygon':
                    coords = first_geom['coordinates'][0][0]
                elif first_geom['type'] == 'MultiPolygon':
                    coords = first_geom['coordinates'][0][0][0]
                else:
                    coords = None
                
                if coords:
                    map_center = [coords[1], coords[0]]
                    map_zoom = 15
            except:
                pass 

    with col_map:
        m = folium.Map(location=map_center, zoom_start=map_zoom) 
        
        # 呼叫縮小節點的函式
        inject_folium_draw_fix(m) 
        
        # 預設 Google 衛星圖
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
        
        map_data = st_folium(m, width="100%", height=500, key="folium_map_satellite")
    
    final_area = 0
    # 以最後手動繪製的幾何為主
    if map_data and map_data.get("all_drawings") and len(map_data["all_drawings"]) > 0:
        latest_drawing = map_data["all_drawings"][-1]
        if latest_drawing["geometry"]["type"] == "Polygon":
            geom = shape(latest_drawing["geometry"])
            geod = Geod(ellps="WGS84")
            area, _ = geod.geometry_area_perimeter(geom)
            final_area = abs(area)
            st.success("✅ 已套用手動圈繪範圍面積。")
            
    # 若無手動繪製，則採用上傳檔案的總面積
    elif spatial_file and uploaded_area > 0:
        final_area = uploaded_area
        st.success("✅ 已套用上傳圖層面積。")
        
    if final_area > 0:
         render_results(final_area)
