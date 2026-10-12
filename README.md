# ⛰️ 崩塌量體推估系統 (Landslide Volume Estimation System)

## 📖 專案簡介 (Project Overview)
本專案為一個基於 Streamlit 開發的 Web 應用程式。主要功能為透過使用者輸入的「崩塌面積 (A)」，利用國內外多組實證經驗公式，快速推估「崩塌量體 (V)」與「平均滑動深度 (D)」。系統支援手動數值輸入、線上衛星圖網頁圈繪，以及多種 GIS 空間檔案上傳。

---

## 🛠️ 核心功能 (Core Features)

1. **多重經驗公式自動計算**：
   * 內建 6 組經驗公式 (如：陳樹群等 2010, Guzzetti 等 2008/2009 等)。
   * 支援單位自動換算 (m², ha, km²)。
2. **多源衛星底圖與時序比對**：
   * 內建 `Google Satellite` (近期預設)、`NLSC 國土測繪中心正射影像` (台灣官方)、`ESRI World Imagery`，透過右上角圖層控制器切換，解決單一底圖不知拍攝年份與雲遮問題。
3. **線上圈繪與面積計算 (Folium)**：
   * 使用 `folium.plugins.Draw` 提供多邊形圈繪功能，並透過 PyProj (WGS84) 計算真實地球曲面面積。
   * 支援 **Export** 功能，可將手動圈繪的範圍匯出為 GeoJSON 留底。
4. **GIS 空間檔案上傳解析**：
   * 支援格式：`ZIP (包含完整 Shapefile)`, `KML`, `KMZ`, `GeoJSON`。
   * 自動擷取檔案幾何形狀並套疊至地圖上，精準計算面積。
5. **雙層連動精準定位系統**：
   * 內建台灣 368 鄉鎮市區清單，雙層下拉選單 (縣市 -> 鄉鎮市區) 連動定位。
   * 保留 Geopy (Nominatim) 地址/地標搜尋作為輔助。

---

## ⚠️ 給其他 AI 與開發者的「最高除錯鐵律」(Crucial AI Guidelines)
**任何接手此專案的 AI 或開發者，在修改程式碼前請務必遵守以下鐵律，這些是經過無數次 Try & Error 確立的最佳實踐：**

### 1. UI 排版與數值格式 (UI & Formatting)
* **絕對禁用表格 (Data Grid)**：結果呈現必須使用卡片式 (`st.expander`) 展開，上下分層對齊。
* **千位逗號與小數點**：總量體 (V) 數值強制採用千位數逗號 (,) **且無小數點** (`{v:,.0f}`)；面積與深度可保留小數點。

### 2. 地圖圈繪節點防遮擋機制 (Folium Draw Nodes)
* **問題**：Leaflet.Draw 預設的編輯節點 (白色方塊) 過大，會嚴重遮擋衛星圖。單純使用 Streamlit 的 `st.markdown` CSS 無法穿透 iframe。
* **唯一解法**：必須使用 `branca.element.Element` 將客製化的 **JavaScript 與 CSS 強制注入地圖的核心 HTML (`m.get_root().html.add_child`)**。
* **規範**：節點尺寸必須維持在 `3px` 左右的無框紅點 (`#ff0000`)。請參考原始碼中的 `inject_folium_draw_fix(m)` 模組，**嚴禁修改或移除此函式**。

### 3. GIS 檔案上傳防呆機制 (Spatial File Handling)
* **上傳樣式限制**：上傳套疊在地圖上的多邊形，**必須設定為「無底色 (透明)、只留紅色外框」** (`fillColor: 'transparent', fillOpacity: 0, color: '#ff0000'`)，以免遮擋衛星底圖。
* **自動縮放**：解析上傳檔案後，必須取得 `total_bounds`，並使用 `m.fit_bounds()` 自動將地圖縮放至該圖層範圍。
* **無聲 TWD97 (EPSG:3826) 轉換**：台灣工程界常有上傳「無 .prj 檔的 Shapefile」導致 EPSG 遺失的問題。
  * **邏輯**：當 `gdf.crs is None` 時，檢查 `minx` (X座標)。若 `> 180`，代表絕對不是經緯度，系統需在後台**默默將其視為 TWD97 (EPSG:3826) 並轉換為 EPSG:4326**。
  * **禁止警告**：此轉換過程為「無聲防呆 (Silent Fallback)」，**絕對不要**在畫面上印出警告或提示標語干擾使用者。

### 4. API 呼叫的靜默處理 (Silent Fail-safes)
* 地理編碼 API (Nominatim) 非常不穩定且容易 Timeout。
* 所有牽涉到 `geolocator.geocode` 的呼叫必須包裝在 `try-except` 中。若發生 `GeocoderTimedOut` 或其他錯誤，直接 `pass` 或回傳 `None`，**嚴禁在畫面上噴出紅字錯誤 (st.error)**，以確保主功能 (圈繪、計算) 永不中斷。

### 5. 棄用 Canvas 影像上傳功能
* **歷史教訓**：過去曾嘗試使用 `streamlit-drawable-canvas` 讓使用者上傳本地相片畫圖，但因 Streamlit 的 WebSocket 傳輸限制，處理高解析度大圖時極易造成連線崩潰 (`ClientDisconnect`) 導致白畫面；且該套件強制要求滑鼠右鍵才能閉合多邊形，嚴重破壞使用者體驗。
* **決議**：該功能已被**永久捨棄**。請專注於優化 Tab 2 的 Folium 地圖與多時序衛星底圖切換。

---

## 📦 依賴套件 (Requirements)
參見 `requirements.txt`：
```text
streamlit
pandas
Pillow
folium
streamlit-folium
shapely
pyproj
geopandas
fastkml
lxml
geopy
```

## 🚀 執行方式 (How to Run)
1. 確保已安裝 Python 3.8+ 
2. 安裝套件：`pip install -r requirements.txt`
3. 啟動服務：`streamlit run app.py`