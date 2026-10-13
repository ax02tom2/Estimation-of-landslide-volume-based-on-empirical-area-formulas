# ⛰️ 崩塌量體推估系統 (Landslide Volume Estimation System)

> 本文件同時給「人」與「其他 AI（Gemini / ChatGPT / Claude 等）」閱讀。
> 接手前請先讀完 **「AI 接手守則」** 與 **「變更紀錄」**，再動程式碼。

---

## 📖 專案簡介 (Project Overview)

以 Streamlit 開發的 Web 應用程式。輸入「崩塌面積 (A)」後，用多組國內外實證經驗公式 `V = a × A^b`，快速推估「崩塌量體 (V)」與「平均滑動深度 (D = V / A)」。

支援三種取得面積的方式：
1. 手動輸入數值（m² / ha / km² 自動換算）
2. 衛星底圖上直接圈繪多邊形
3. 上傳 GIS 空間檔案（ZIP-Shapefile / KML / KMZ / GeoJSON）

- 主程式：單一檔案 `app.py`
- 部署方式：GitHub + Streamlit Cloud
- 語言 / 介面：繁體中文

## 📁 檔案結構

```text
.
├── app.py                  # 主程式（全部邏輯都在這一個檔案）
├── requirements.txt        # 依賴套件
├── README.md               # 本文件
└── .streamlit/config.toml  # maxUploadSize = 1000 (MB)
```

---

## 🛠️ 核心功能 (Core Features)

1. **多重經驗公式自動計算**：內建 6 組公式（陳樹群等 2010、Cha et al. 2018、Guzzetti et al. 2008 / 2009、Larsen & Torres Sanchez 1998、Martin et al. 2002），定義在 `app.py` 的 `FORMULAS`。面積單位一律以 **m²** 代入。
2. **多源衛星底圖**：Google 衛星（預設）、NLSC 國土測繪中心正射影像、ESRI World Imagery，由右上角圖層控制器切換，用來比對不同拍攝年份與雲遮。
3. **線上圈繪與面積計算**：`folium.plugins.Draw` 提供多邊形圈繪，用 `pyproj.Geod(ellps="WGS84")` 計算橢球面真實面積。支援 Export 匯出 GeoJSON。
4. **GIS 檔案上傳**：自動解析、套疊到地圖並縮放到範圍，面積同樣以 `Geod` 計算。
5. **鄉鎮市區定位**：縣市 → 鄉鎮市區雙層連動選單（資料在 `TW_DISTRICTS`），另有 Geopy (Nominatim) 地址 / 地標搜尋作為輔助。
6. **多多邊形顏色辨識**（2026-10-13 新增，見下節）：每個圈繪的多邊形依順序自動上不同顏色，且與下方「選擇計算目標」選單的顏色圓點一致。

---

## 🎨 多邊形依序變色機制 (Polygon Coloring) — 設計說明

### 需求
圈繪的多邊形面積相近、位置相鄰時，不容易分辨選單中的「多邊形 N」是地圖上的哪一個。要求：第 1 個多邊形一種顏色、第 2 個另一種顏色，依此類推，並與選單對應。

### 目前做法（請維持）
- 類別 `PolygonColorizer(MacroElement)`（`app.py`，在 `inject_folium_draw_fix` 之前）。
- 監聽 Leaflet.Draw 的 `draw:created` 事件。圖形**畫完當下**：
  1. 掃描地圖上所有已有 `feature.properties.color_idx` 的圖層，取最大值 + 1 當新編號。
  2. 把編號寫入 `layer.feature.properties.color_idx`。
  3. 用 `layer.setStyle(...)` 依編號從 `DRAW_COLORS` 取色。
- `streamlit-folium` 回傳的 `all_drawings` 來自 `window.drawnItems.toGeoJSON().features`，所以 `properties.color_idx` 會一起回到 Python。
- Python 端（選單建立處）讀取 `drawing["properties"]["color_idx"]`，用它從 `DRAW_EMOJIS` 取圓點、命名「多邊形 {color_idx+1}」。讀不到時才退回用清單順序 `i`。
- 因為顏色與編號是**建立時固定**的：刪除某個多邊形不會讓其他多邊形變色或跳號（例如刪掉第 2 個，第 3 個仍是綠色、仍叫「多邊形 3」）。

### 必須維持的約束
- `DRAW_COLORS` 與 `DRAW_EMOJIS` 的**項目順序與數量必須一一對應**（目前 7 組：🟠🟣🟢🔵🟤🟪⚫ ↔ `#FF8C00 #800080 #008000 #0000FF #8B4513 #FF00FF #000000`）。超過 7 個多邊形會循環。
- 上傳圖層的樣式是「透明底 + 紅色外框 `#ff0000`」，**不可使用紅色當圈繪顏色**，避免混淆。
- `PolygonColorizer` 必須在 `Draw` 外掛**之前**加入地圖（目前由 `inject_folium_draw_fix(m)` 在 `Draw(...)` 之前呼叫），這樣 handler 才會先於 Draw 外掛的 `drawnItems.addLayer(e.layer)` 執行，屬性才會在圖層被收進群組前寫好。

### 已棄用的舊做法（不要改回去）
舊版用 `setInterval` 每 200 ms 掃描整個 DOM 的 `<path>`，依 DOM 順序（`drawIndex`）硬改 stroke / fill。缺點：DOM 順序不保證等於 `all_drawings` 的順序（編輯、刪除、圖層重排都可能錯位），且持續輪詢浪費效能，也是「分不清哪個是哪個」的主因。

### 驗證狀況（誠實紀錄）
- 已驗證：`py_compile` 通過；用 folium 實際產生 HTML，確認 `PolygonColorizer` 腳本在地圖變數宣告之後、且早於 Draw 外掛的 `addLayer` handler；確認 `streamlit-folium` 前端的 `all_drawings` 來源為 `drawnItems.toGeoJSON().features`。
- **尚未在真實瀏覽器中實測**。接手者請務必在實際網頁上：連畫 3 個以上多邊形 → 檢查地圖顏色與選單圓點是否一致 → 刪除中間一個 → 確認其餘顏色與編號不變。

---

## ⚠️ AI 接手守則 (Crucial AI Guidelines)

以下鐵律來自反覆除錯，修改前請務必遵守。

### 1. UI 排版與數值格式
- **禁用表格 (Data Grid)**：結果用卡片式 `st.expander`，上下分層對齊。
- **數字格式**：總量體 V 一律千位逗號且**無小數點**（`{v:,.0f}`）；面積與深度可保留小數。

### 2. 圈繪節點防遮擋
- **問題**：Leaflet.Draw 預設編輯節點（白方塊）過大，會遮擋衛星圖；Streamlit 的 `st.markdown` CSS 無法穿透 iframe。
- **做法**：用 `branca.element.Element` 把 CSS 與 JS 注入地圖本身（CSS 進 `m.get_root().header`，JS 進 `m.get_root().script`）。
- **規範**：節點維持約 `3px` 的無框紅點（`#ff0000`）。相關邏輯在 `inject_folium_draw_fix(m)`：**縮小節點的 CSS 與 `L.Edit.PolyVerticesEdit` 圖示設定必須保留**。
- 注意：因為 `root.script` 的內容會在地圖變數宣告**之前**執行，這類注入若需要用到地圖物件，請改用 `MacroElement`（如 `PolygonColorizer`）或延遲執行，不要直接引用 `map_xxxx` 變數。

### 3. GIS 檔案上傳防呆
- **樣式**：上傳圖層必須「透明底、紅色外框」（`fillColor: 'transparent', fillOpacity: 0, color: '#ff0000'`）。
- **自動縮放**：取 `total_bounds` 後 `m.fit_bounds()`。
- **靜默 TWD97 轉換**：`gdf.crs is None` 時，若 `minx > 180` 視為 EPSG:3826 並轉成 EPSG:4326；否則視為 EPSG:4326。此為「無聲防呆」，**不可在畫面顯示任何警告**。

### 4. API 靜默處理
- Nominatim 地理編碼常 timeout。所有 `geocode` 呼叫必須在 `try-except` 內，失敗就回傳 `None`，**不得 `st.error`**，確保圈繪與計算主功能不中斷。

### 5. 已永久捨棄的功能
- `streamlit-drawable-canvas` 本地相片畫圖：高解析大圖會因 WebSocket 限制造成 `ClientDisconnect` 白畫面，且需右鍵才能閉合多邊形。**不要再嘗試**。請專注在 Tab 2 的 Folium 地圖與多底圖切換。

### 6. 給 AI 的協作建議
- 修改前先讀整份 `app.py`，只改需要的段落，保留既有函式與命名。
- 回覆使用者一律用繁體中文。
- 若無法在真實瀏覽器驗證，請明講「未實測」，不要宣稱已驗證。
- 交付修改後的檔案時，確認檔案真的存在於可下載位置，而不是只貼說明。

---

## 🧱 程式結構速覽 (`app.py`)

| 區塊 | 說明 |
|---|---|
| `FORMULAS` | 6 組 `V = a·A^b` 經驗公式參數 |
| `DRAW_COLORS` / `DRAW_EMOJIS` | 圈繪顏色與選單圓點（需一一對應） |
| `TW_DISTRICTS` | 縣市 → 鄉鎮市區清單 |
| `render_results(area_m2)` | 依面積算出各公式的 V 與 D，以卡片顯示 |
| `process_spatial_file(file)` | 解析 geojson / kml / kmz / zip(shp)，回傳 (GeoJSON, 總面積 m², bounds) |
| `PolygonColorizer` | 圈繪完成時依序指定顏色並寫入 `color_idx` |
| `inject_folium_draw_fix(m)` | 注入縮小節點的 CSS / JS，並掛上 `PolygonColorizer` |
| `safe_geocode(query)` | 包了 try-except 的地理編碼 |
| Tab 1 | 手動輸入面積 |
| Tab 2 | 衛星底圖圈繪 / 檔案上傳 / 定位 / 選擇計算目標 |

## 📦 依賴套件 (Requirements)

見 `requirements.txt`：

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

另外 `app.py` 使用 `jinja2.Template` 與 `branca`，兩者會隨 `folium` 一併安裝，不需另外列出。

## 🚀 執行方式 (How to Run)

1. Python 3.8+
2. `pip install -r requirements.txt`
3. `streamlit run app.py`

---

## 📝 變更紀錄 (Changelog)

- **2026-10-13**：圈繪多邊形改為「畫完即依序上色」，顏色編號寫入圖形 `properties.color_idx`，與選單圓點、名稱同步；移除舊的 `setInterval` DOM 掃描變色迴圈；新增 `PolygonColorizer`。縮小節點的 CSS / JS 保留不變。（尚待真實瀏覽器實測。）
