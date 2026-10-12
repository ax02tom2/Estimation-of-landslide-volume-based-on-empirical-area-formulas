import streamlit as st
import pandas as pd
from PIL import Image
import folium
from folium.plugins import Draw
from streamlit_folium import st_folium
from shapely.geometry import shape, Polygon
from pyproj import Geod
from streamlit_drawable_canvas import st_canvas

# -----------------------------------------------------------------------------
# 系統設定與記憶偏好套用 (卡片式排版、防護機制)
# -----------------------------------------------------------------------------
st.set_page_config(page_title="崩塌量體推估系統", layout="wide")

st.title("⛰️ 崩塌量體推估系統 (面積經驗公式對照)")
st.markdown("本系統整合多組實證經驗公式，支援**手動輸入**、**線上衛星底圖圈繪**及**自訂空拍影像上傳**，快速推估崩塌量體 (V) 與平均滑動深度 (D)。")

# -----------------------------------------------------------------------------
# 經驗公式定義 (資料來源：崩塌量體推估(面積經驗公式)(1100913).xlsx)
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
    """結果渲染模組 - 遵守無 Data Grid 限制，使用卡片式對齊排版"""
    if area_m2 <= 0:
        return
        
    area_ha = area_m2 / 10000
    area_km2 = area_m2 / 1000000
    
    st.markdown("---")
    st.markdown(f"### 🎯 基準面積計算結果")
    st.markdown(f"**{area_m2:,.2f} 平方公尺 ($m^2$)** ｜ **{area_ha:,.4f} 公頃 ($ha$)** ｜ **{area_km2:,.6f} 平方公里 ($km^2$)**")
    
    # 應用記憶偏好：採用卡片式 (st.expander) 展開，上下分層對齊
    cols = st.columns(3)
    for idx, f in enumerate(FORMULAS):
        v = f["a"] * (area_m2 ** f["b"])
        d = v / area_m2 if area_m2 > 0 else 0
        
        with cols[idx % 3]:
            with st.expander(f"📌 {f['name']}", expanded=True):
                # 應用記憶偏好：總量體數值強制採用千位數逗號 (,) 且無小數點
                st.markdown(f"""
                <div style='text-align: center; padding: 5px;'>
                    <p style='color: #888; font-size: 0.85em; margin-bottom: 5px;'>公式: {f['formula']}</p>
                    <h3 style='color: #2e6c80; margin-top: 0px;'>V = {v:,.0f} <small>m³</small></h3>
                    <p style='color: #555; margin-bottom: 0px;'>平均滑動深度 (D): <b>{d:,.2f}</b> m</p>
                </div>
                """, unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 主功能切換 Tabs
# -----------------------------------------------------------------------------
tab1, tab2, tab3 = st.tabs(["🔢 1. 數值直接輸入", "🗺️ 2. 衛星底圖圈繪 (線上)", "🖼️ 3. 自訂影像上傳 (離線/最新)"])

# ====== Tab 1: 數值直接輸入 ======
with tab1:
    st.subheader("手動輸入面積 (自動換算單位)")
    # 確保輸入列中的欄位精準對齊同一高度
    col_input, col_unit = st.columns([2, 1])
    with col_input:
        input_area = st.number_input("輸入面積數值", min_value=0.0, value=0.0, step=0.1)
    with col_unit:
        unit_choice = st.selectbox("選擇輸入單位", ["平方公尺 (m²)", "公頃 (ha)", "平方公里 (km²)"])
    
    # 單位無縫換算為 m2
    if unit_choice == "公頃 (ha)":
        base_area_m2 = input_area * 10000
    elif unit_choice == "平方公里 (km²)":
        base_area_m2 = input_area * 1000000
    else:
        base_area_m2 = input_area
        
    if base_area_m2 > 0:
        render_results(base_area_m2)

# ====== Tab 2: 衛星底圖圈繪 ======
with tab2:
    st.subheader("在地圖上圈繪崩塌範圍")
    st.info("💡 說明：請使用地圖左側的「多邊形工具 (Draw a polygon)」圈出範圍，系統將自動計算地球曲面面積 (WGS84)。")
    
    # 預設中心點為台灣
    m = folium.Map(location=[23.6978, 120.9605], zoom_start=7) 
    
    # 加入免費的 Google 衛星影像作為底圖
    folium.TileLayer(
        tiles='https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}',
        attr='Google',
        name='Google Satellite',
        overlay=False,
        control=True
    ).add_to(m)
    
    # 限制只能畫多邊形
    Draw(export=True, position='topleft', draw_options={
        'polyline': False, 'rectangle': False, 'circle': False, 
        'circlemarker': False, 'marker': False, 
        'polygon': {'allowIntersection': False}
    }).add_to(m)
    
    map_data = st_folium(m, width="100%", height=500, key="folium_map")
    
    # 若有圈出幾何圖形，自動計算真實世界面積
    if map_data and map_data.get("all_drawings"):
        latest_drawing = map_data["all_drawings"][-1]
        if latest_drawing["geometry"]["type"] == "Polygon":
            geom = shape(latest_drawing["geometry"])
            geod = Geod(ellps="WGS84")
            area, _ = geod.geometry_area_perimeter(geom)
            render_results(abs(area))

# ====== Tab 3: 自訂影像上傳 ======
with tab3:
    st.subheader("上傳最新空拍或正射影像 (解決底圖過舊問題)")
    st.info("💡 說明：無空間座標的普通相片，請先在左下方設定「影像比例尺」，再使用多邊形工具圈繪範圍。")
    
    uploaded_file = st.file_uploader("選擇最新影像檔案 (JPG/PNG)", type=["jpg", "jpeg", "png"])
    
    if uploaded_file:
        # 應用記憶偏好：嚴格容量攔截鎖 (防止 Cloud 記憶體溢出)
        if uploaded_file.size > 20 * 1024 * 1024:
            st.error("❌ 檔案過大！為防止雲端主機 OOM 崩潰，請上傳小於 20MB 的圖片。")
            st.stop()
            
        try:
            img = Image.open(uploaded_file)
            
            # 應用記憶偏好：啟用輕量化縮圖機制
            img.thumbnail((1200, 1200))
            st.success(f"✅ 影像安全載入！為確保雲端伺服器穩定，已自動優化解析度適應螢幕 ({img.width} x {img.height} 像素)。")
            
            col_scale1, col_scale2 = st.columns(2)
            with col_scale1:
                # 比例尺校正
                px_per_unit = st.number_input("校正比例尺：影像中「100 像素」約等於多少公尺 (m)？", min_value=0.1, value=10.0, step=1.0)
                meters_per_pixel = px_per_unit / 100.0
            with col_scale2:
                st.write("") 
                st.write(f"👉 系統當前換算率: **1 像素 = {meters_per_pixel:.3f} 公尺**")
            
            st.markdown("請在下方影像上**點擊滑鼠左鍵**建立多邊形頂點以圈繪範圍：")
            
            # 使用 Drawable Canvas 進行影像上方畫圖
            canvas_result = st_canvas(
                fill_color="rgba(255, 165, 0, 0.4)", # 橘色半透明
                stroke_width=2,
                stroke_color="#ff0000",
                background_image=img,
                update_streamlit=True,
                height=img.height,
                width=img.width,
                drawing_mode="polygon",
                key="canvas_image",
            )
            
            # 計算在 Canvas 上畫出的 Polygon 面積
            if canvas_result.json_data is not None:
                objects = canvas_result.json_data["objects"]
                if objects:
                    for obj in objects:
                        if obj["type"] == "path":
                            points = []
                            for cmd in obj["path"]:
                                if cmd[0] in ['M', 'L'] and len(cmd) >= 3:
                                    points.append((cmd[1], cmd[2]))
                            
                            if len(points) >= 3:
                                poly = Polygon(points)
                                px_area = poly.area
                                # 像素面積轉換為實際面積
                                real_area = px_area * (meters_per_pixel ** 2)
                                render_results(real_area)
                                break # 單次計算第一個封閉區域
                                
        except Exception as e:
            # 應用記憶偏好：Gemini 除錯鐵律 - 印出詳細的系統報錯字串
            st.error(f"⚠️ 影像處理或計算時發生錯誤: {str(e)}")