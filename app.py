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
from geopy.exc import GeocoderTimedOut, GeocoderServiceError

# -----------------------------------------------------------------------------
# 系統設定
# -----------------------------------------------------------------------------
st.set_page_config(page_title="崩塌量體推估系統", page_icon="🗺️", layout="wide")

st.title("⛰️ 崩塌量體推估系統 (面積經驗公式對照)")
st.markdown("本系統整合多組實證經驗公式，支援**手動輸入**及**線上衛星底圖/空間檔案上傳**，快速推估崩塌量體 (V) 與平均滑動深度 (D)。")

# -----------------------------------------------------------------------------
# 經驗公式與全台鄉鎮市區資料
# -----------------------------------------------------------------------------
FORMULAS = [
    {"name": "陳樹群等 (2010)", "formula": "V = 0.04 * A^1.38", "a": 0.04, "b": 1.38},
    {"name": "Cha et al. (2018)", "formula": "V = 0.596 * A^1.02", "a": 0.596, "b": 1.02},
    {"name": "Guzzetti et al. (2008)", "formula": "V = 0.084 * A^1.43", "a": 0.084, "b": 1.43},
    {"name": "Guzzetti et al. (2009)", "formula": "V = 0.074 * A^1.45", "a": 0.074, "b": 1.45},
    {"name": "Larsen & Torres Sanchez (1998)", "formula": "V = 1.826 * A^0.989", "a": 1.826, "b": 0.989},
    {"name": "Martin et al. (2002)", "formula": "V = 1.0359 * A^0.88", "a": 1.0359, "b": 0.88}
]

# 全新顏色對應表 (故意避開預設藍色，從橘色、紫色、綠色開始)
DRAW_COLORS = ['#FF8C00', '#800080', '#008000', '#0000FF', '#8B4513', '#FF00FF', '#000000']
DRAW_EMOJIS = ['🟠', '🟣', '🟢', '🔵', '🟤', '🟪', '⚫']

TW_DISTRICTS = {
    "請選擇縣市...": ["請先選擇縣市"],
    "台北市": ["中正區", "大同區", "中山區", "松山區", "大安區", "萬華區", "信義區", "士林區", "北投區", "內湖區", "南港區", "文山區"],
    "新北市": ["萬里區", "金山區", "板橋區", "汐止區", "深坑區", "石碇區", "瑞芳區", "平溪區", "雙溪區", "貢寮區", "新店區", "坪林區", "烏來區", "永和區", "中和區", "土城區", "三峽區", "樹林區", "鶯歌區", "三重區", "新莊區", "泰山區", "林口區", "蘆洲區", "五股區", "八里區", "淡水區", "三芝區", "石門區"],
    "桃園市": ["中壢區", "平鎮區", "龍潭區", "楊梅區", "新屋區", "觀音區", "桃園區", "龜山區", "八德區", "大溪區", "復興區", "大園區"],
    "台中市": ["中區", "東區", "南區", "西區", "北區", "北屯區", "西屯區", "南屯區", "太平區", "大里區", "霧峰區", "烏日區", "豐原區", "后里區", "石岡區", "東勢區", "和平區", "新社區", "潭子區", "大雅區", "神岡區", "大肚區", "沙鹿區", "龍井區", "梧棲區", "清水區", "大甲區", "外埔區", "大安區"],
    "台南市": ["中西區", "東區", "南區", "北區", "安平區", "安南區", "永康區", "歸仁區", "新化區", "左鎮區", "玉井區", "楠西區", "南化區", "仁德區", "關廟區", "龍崎區", "官田區", "麻豆區", "佳里區", "西港區", "七股區", "將軍區", "學甲區", "北門區", "新營區", "後壁區", "白河區", "東山區", "六甲區", "下營區", "柳營區", "鹽水區", "善化區", "大內區", "山上區", "新市區", "安定區"],
    "高雄市": ["新興區", "前金區", "苓雅區", "鹽埕區", "鼓山區", "旗津區", "前鎮區", "三民區", "楠梓區", "小港區", "左營區", "仁武區", "大社區", "岡山區", "路竹區", "阿蓮區", "田寮區", "燕巢區", "橋頭區", "梓官區", "彌陀區", "永安區", "湖內區", "鳳山區", "大寮區", "林園區", "鳥松區", "大樹區", "旗山區", "美濃區", "六龜區", "內門區", "杉林區", "甲仙區", "桃源區", "那瑪夏區", "茂林區"],
    "基隆市": ["仁愛區", "信義區", "中正區", "中山區", "安樂區", "暖暖區", "七堵區"],
    "新竹市": ["東區", "北區", "香山區"],
    "嘉義市": ["東區", "西區"],
    "新竹縣": ["竹北市", "湖口鄉", "新豐鄉", "新埔鎮", "關西鎮", "芎林鄉", "寶山鄉", "竹東鎮", "五峰鄉", "橫山鄉", "尖石鄉", "北埔鄉", "峨眉鄉"],
    "苗栗縣": ["竹南鎮", "頭份市", "三灣鄉", "南庄鄉", "獅潭鄉", "後龍鎮", "通霄鎮", "苑裡鎮", "苗栗市", "造橋鄉", "頭屋鄉", "公館鄉", "大湖鄉", "泰安鄉", "銅鑼鄉", "三義鄉", "西湖鄉", "卓蘭鎮"],
    "彰化縣": ["彰化市", "芬園鄉", "花壇鄉", "秀水鄉", "鹿港鎮", "福興鄉", "線西鄉", "和美鎮", "伸港鄉", "員林市", "社頭鄉", "永靖鄉", "埔心鄉", "溪湖鎮", "大村鄉", "埔鹽鄉", "田中鎮", "北斗鎮", "田尾鄉", "埤頭鄉", "溪州鄉", "竹塘鄉", "二林鎮", "大城鄉", "芳苑鄉", "二水鄉"],
    "南投縣": ["南投市", "中寮鄉", "草屯鎮", "國姓鄉", "埔里鎮", "仁愛鄉", "名間鄉", "集集鎮", "水里鄉", "魚池鄉", "信義鄉", "竹山鎮", "鹿谷鄉"],
    "雲林縣": ["斗南鎮", "大埤鄉", "虎尾鎮", "土庫鎮", "褒忠鄉", "東勢鄉", "台西鄉", "崙背鄉", "麥寮鄉", "斗六市", "林內鄉", "古坑鄉", "莿桐鄉", "西螺鎮", "二崙鄉", "北港鎮", "水林鄉", "口湖鄉", "四湖鄉", "元長鄉"],
    "嘉義縣": ["番路鄉", "梅山鄉", "竹崎鄉", "阿里山鄉", "中埔鄉", "大埔鄉", "水上鄉", "鹿草鄉", "太保市", "朴子市", "東石鄉", "六腳鄉", "新港鄉", "民雄鄉", "大林鎮", "溪口鄉", "義竹鄉", "布袋鎮"],
    "屏東縣": ["屏東市", "三地門鄉", "霧台鄉", "瑪家鄉", "九如鄉", "里港鄉", "高樹鄉", "鹽埔鄉", "長治鄉", "麟洛鄉", "竹田鄉", "內埔鄉", "萬丹鄉", "潮州鎮", "泰武鄉", "來義鄉", "萬巒鄉", "崁頂鄉", "新埤鄉", "南州鄉", "林邊鄉", "東港鎮", "琉球鄉", "佳冬鄉", "新園鄉", "枋寮鄉", "枋山鄉", "春日鄉", "獅子鄉", "車城鄉", "牡丹鄉", "恆春鎮", "滿州鄉"],
    "宜蘭縣": ["宜蘭市", "頭城鎮", "礁溪鄉", "壯圍鄉", "員山鄉", "羅東鎮", "三星鄉", "大同鄉", "五結鄉", "冬山鄉", "蘇澳鎮", "南澳鄉"],
    "花蓮縣": ["花蓮市", "新城鄉", "秀林鄉", "吉安鄉", "壽豐鄉", "鳳林鎮", "光復鄉", "豐濱鄉", "瑞穗鄉", "萬榮鄉", "玉里鎮", "卓溪鄉", "富里鄉"],
    "台東縣": ["台東市", "綠島鄉", "蘭嶼鄉", "延平鄉", "卑南鄉", "鹿野鄉", "關山鎮", "海端鄉", "池上鄉", "東河鄉", "成功鎮", "長濱鄉", "太麻里鄉", "金峰鄉", "大武鄉", "達仁鄉"],
    "澎湖縣": ["馬公市", "西嶼鄉", "望安鄉", "七美鄉", "白沙鄉", "湖西鄉"],
    "金門縣": ["金沙鎮", "金湖鎮", "金寧鄉", "金城鎮", "烈嶼鄉", "烏坵鄉"],
    "連江縣": ["南竿鄉", "北竿鄉", "莒光鄉", "東引鄉"]
}

def render_results(area_m2):
    if area_m2 <= 0: return
    area_ha = area_m2 / 10000
    area_km2 = area_m2 / 1000000
    
    st.markdown("---")
    st.markdown(f"### 🎯 基準面積推估結果")
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

        if gdf.crs is None:
            minx, miny, maxx, maxy = gdf.total_bounds
            if minx > 180:
                gdf.set_crs(epsg=3826, inplace=True)
            else:
                gdf.set_crs(epsg=4326, inplace=True)
        
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

# -----------------------------------------------------------------------------
# 🚀 終極霸道變色腳本：強制介入 SVG 圖層修改顏色，無懼任何防護
# -----------------------------------------------------------------------------
def inject_folium_draw_fix(m):
    # 使用純字串與 REPLACE，避開任何 Python 與 JS 大括號語法衝突的風險
    js_template = """
    <script>
        // 縮小白點
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

        // 每 100 毫秒極速掃描所有路徑，強制上色
        setInterval(function() {
            var colors = COLOR_ARRAY_PLACEHOLDER;
            
            // 鎖定地圖圖層，避免改到外面的工具按鈕
            var panes = document.querySelectorAll('.leaflet-overlay-pane');
            if (panes.length === 0) return;
            
            panes.forEach(function(pane) {
                var paths = pane.querySelectorAll('path');
                var drawIndex = 0;
                
                for (var i = 0; i < paths.length; i++) {
                    var path = paths[i];
                    var strokeColor = path.getAttribute('stroke');
                    var fillOpacity = path.getAttribute('fill-opacity');
                    
                    // 排除防線：如果是紅色 (#ff0000) 且透明度為 0 的「上傳底框」，絕對不要動它！
                    if (strokeColor && strokeColor.toLowerCase() === '#ff0000') {
                        if (fillOpacity === '0' || fillOpacity === '0.0' || fillOpacity === 0) {
                            continue; 
                        }
                    }
                    
                    // 只要不是上傳的底框，全部視為手動圈繪的多邊形，依序強制換色
                    var targetColor = colors[drawIndex % colors.length];
                    
                    path.setAttribute('stroke', targetColor);
                    path.setAttribute('fill', targetColor);
                    path.style.stroke = targetColor;
                    path.style.fill = targetColor;
                    
                    drawIndex++;
                }
            });
        }, 100); 
    </script>
    """
    
    js_injection = js_template.replace("COLOR_ARRAY_PLACEHOLDER", str(DRAW_COLORS))
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

def safe_geocode(query):
    try:
        geolocator = Nominatim(user_agent="landslide_geo_app_tw")
        location = geolocator.geocode(query, timeout=3)
        return location
    except (GeocoderTimedOut, GeocoderServiceError):
        return None
    except Exception:
        return None

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
    st.info("💡 說明：您可以手動繪製多個圖形，系統會**自動依序變色**，並在下方選單顯示對應顏色以便選擇。")
    
    col_map, col_controls = st.columns([3, 1])
    
    map_center = [23.9782, 121.1332]
    map_zoom = 8
    fit_bounds_coords = None
    uploaded_geojson = None
    uploaded_area = 0

    with col_controls:
        st.write("### ⚙️ 操作面板")
        st.markdown("---")
        
        st.write("📍 **1. 快速定位鄉鎮市區**")
        city_options = list(TW_DISTRICTS.keys())
        selected_city = st.selectbox("選擇縣市：", city_options, key="city_selector")
        
        district_options = TW_DISTRICTS[selected_city]
        selected_district = st.selectbox("選擇鄉鎮市區：", district_options, key="district_selector")
        
        if selected_city != "請選擇縣市..." and selected_district != "請先選擇縣市":
            search_target = f"台灣 {selected_city} {selected_district}"
            location = safe_geocode(search_target)
            if location:
                map_center = [location.latitude, location.longitude]
                map_zoom = 13
                st.success(f"已精確定位：{selected_city}{selected_district}")

        st.write("🔍 **2. 進階地名/地址搜尋**")
        search_query = st.text_input("輸入詳細地址或地標", placeholder="例如：阿里山鄉...")
        if search_query:
            location = safe_geocode(search_query)
            if location:
                map_center = [location.latitude, location.longitude]
                map_zoom = 15
        
        st.markdown("---")
        
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
            name='Google 衛星影像 (預設/近期)',
            overlay=False,
            control=True
        ).add_to(m)

        folium.TileLayer(
            tiles='https://wmts.nlsc.gov.tw/wmts/PHOTO2/default/GoogleMapsCompatible/{z}/{y}/{x}',
            attr='NLSC',
            name='NLSC 國土測繪中心-正射影像',
            overlay=False,
            control=True
        ).add_to(m)

        folium.TileLayer(
            tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
            attr='Esri',
            name='ESRI World Imagery',
            overlay=False,
            control=True
        ).add_to(m)
        
        if uploaded_geojson:
            folium.GeoJson(
                uploaded_geojson,
                name="上傳的範圍",
                style_function=lambda x: {'fillColor': 'transparent', 'color': '#ff0000', 'weight': 2, 'fillOpacity': 0}
            ).add_to(m)
            
        Draw(export=True, position='topleft', draw_options={
            'polyline': False, 'rectangle': False, 'circle': False, 
            'circlemarker': False, 'marker': False, 
            'polygon': {'allowIntersection': False}
        }).add_to(m)
        
        folium.LayerControl(position='topright').add_to(m)
        
        map_data = st_folium(m, width="100%", height=650, key="folium_map_satellite")
    
    # -------------------------------------------------------------------------
    # 🚀 顏色聯動：將畫布上的顏色同步顯示在選項名稱上
    # -------------------------------------------------------------------------
    available_areas = {}
    
    if spatial_file and uploaded_area > 0:
        option_name = f"📂 上傳的空間圖層 (面積：約 {uploaded_area:,.0f} m²)"
        available_areas[option_name] = uploaded_area
        
    if map_data and map_data.get("all_drawings"):
        for i, drawing in enumerate(map_data["all_drawings"]):
            if drawing["geometry"]["type"] == "Polygon":
                geom = shape(drawing["geometry"])
                geod = Geod(ellps="WGS84")
                area, _ = geod.geometry_area_perimeter(geom)
                abs_area = abs(area)
                
                # 自動賦予對應的顏色球 (順序與 JS 變色腳本完全一致)
                emoji = DRAW_EMOJIS[i % len(DRAW_EMOJIS)]
                poly_name = f"多邊形 {i+1}"
                option_name = f"{emoji} 手動圈繪 - {poly_name} (面積：約 {abs_area:,.0f} m²)"
                
                available_areas[option_name] = abs_area
    
    if available_areas:
        st.markdown("---")
        st.markdown("### 🧮 選擇計算目標")
        st.write("系統偵測到畫面中包含多個範圍，請透過**顏色符號**與**面積大小**，選擇您要計算的目標：")
        
        options = list(available_areas.keys())
        default_index = len(options) - 1 
        
        selected_source = st.radio("選擇目標", options, index=default_index, label_visibility="collapsed")
        
        final_area = available_areas[selected_source]
        render_results(final_area)
