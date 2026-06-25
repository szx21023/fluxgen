# TODO — 待辦與已知問題

來源:初始 commit 的程式碼審查(整體 / 錯誤處理 / 安全性 三方向)。
✅ **已修**:CRITICAL — `/files` 靜態掛載原本會把 `backend/`(含 `.env` 的 `FAL_KEY`)整個對外公開,已改成只掛 `outputs/`。

以下為其餘待辦,依優先序排列。

## High

- [x] **上傳檔大小上限**:兩層防護。(1) middleware 在 multipart 解析前用 `Content-Length` 早期擋掉過大上傳(回 413),避免 Starlette 先把整包落地系統暫存檔塞爆硬碟 — 一般瀏覽器上傳皆帶 Content-Length。(2) handler 再串流分塊(1 MiB/塊)寫入並累計大小,超過 `MAX_UPLOAD_MB`(預設 10)即中止、刪半成品檔、回 413,讀回記憶體有界。殘留:不帶 `Content-Length` 的 chunked 上傳仍會先落到系統暫存檔才被第 (2) 層擋下;若要完全堵住需在 ASGI 串流層累計位元組。
- [ ] **驗證上傳內容**:目前只信任 client 的 `content-type` 與 `filename`,不驗實際位元組。改成嗅探 magic bytes,副檔名由偵測到的型別決定。
- [x] **mock 無 ffmpeg 時的假成功**:`mock.py` 原本在找不到 ffmpeg 時回一個 32 bytes 的壞 mp4(`_MINIMAL_MP4`),任務卻標 `done` → 使用者看到空白播放器、零錯誤。已改為直接 raise `RuntimeError`,任務正確標 `failed` 並回明確錯誤訊息,並刪除 `_MINIMAL_MP4` 後備常數。已驗證:透過真實 HTTP 端點,有 ffmpeg → `done` 產出合法 h264 影片;無 ffmpeg(實際移出 `PATH`)→ `failed` 帶明確錯誤。
- [ ] **fal 下載未驗內容**:`fal.py` 對下載回應只檢查 HTTP 狀態;200 的 HTML 錯誤頁 / 空 body 會被存成 `.mp4` 並標 done。加 content-type / magic-byte 檢查。
- [ ] **錯誤可觀測性**:`jobs.py` 的 `except Exception` 把 `str(exc)` 原樣回前端(可能洩漏伺服器檔案絕對路徑),且伺服器端無 log/traceback。改為 server 端 `logger.exception(...)` + 回前端一則 sanitized 訊息。
- [ ] **前端輪詢韌性**:`api.js` 一次網路抖動就把任務永久標「失敗」並停止輪詢;非 JSON 錯誤回應會讓 `res.json()` 丟錯蓋掉真因。加重試/退避,並 `res.json().catch(() => ({}))`。

## Medium

- [ ] **BackgroundTasks 阻塞 event loop**:`write_bytes` / `read_bytes` / `base64` 為阻塞呼叫,跑在請求的 event loop 上,高負載會卡住其他請求。用 `asyncio.to_thread(...)` 分流。
- [ ] **fal 輪詢無 transient 容忍**:數分鐘的任務中一次 5xx 就整個作廢。對單次 status fetch 容忍有限次連續失敗。
- [ ] **記憶體 job store 重啟即失**:`_jobs` 重啟清空 → poller 拿到 404 被當失敗。換 Redis/DB,或前端把 404 當「狀態遺失」而非失敗。
- [ ] **fal 下載 URL allowlist**:`video_url` 來自 fal 回應,下載前未限制 https / 網域(輕度 SSRF)。
- [ ] **drawtext metacharacters**:`mock.py` 的跳脫只處理 `:'\`,未處理 `% , [ ] ; =`,且先跳脫後截斷可能切斷跳脫序列導致 ffmpeg 失敗。改為先截斷再跳脫,或用 `textfile=`。
- [ ] **`image_to_video` 讀檔無防呆**:`fal.py` 直接 `path.read_bytes()`,檔案若已被刪會丟 `FileNotFoundError` 並把路徑洩漏給前端。
- [ ] **`_fal_detail` 的 `except Exception` 過廣**:縮成 `except (ValueError, json.JSONDecodeError)`;截斷 300 字時標註 `(truncated)`。

## Low / nice-to-have

- [x] `tempfile.mktemp` 已棄用(TOCTOU)→ 已改 `mkstemp` + `finally` 清理(順帶修掉 ffmpeg 失敗時 temp 檔殘留)。導入 pre-commit 時由 bandit B306 抓出。
- [ ] `_MINIMAL_MP4` 宣告的 box 長度與實際內容不符,註解稱「結構合法」不精確。
- [ ] `get_provider()` 每次呼叫都重建 provider → 可用 `functools.lru_cache` memoize。
- [ ] 上傳檔從不清理 → 加任務完成後清除或定期清掃。
- [ ] 前端切換分頁時未清掉舊的 `file`/`prompt`;`submitImageJob` 應在 `file` 為空時擋下。
- [ ] `jobs.py` 的 `created_at` / `updated_at` 用兩次 `_now()` → 呼叫一次共用,建立時兩個時間戳才一致。
- [ ] 文件化:`CORS_ORIGINS=*` 絕不可與 credentials 並用。

## 功能想法(新功能)

- [x] **可選影片時長**:前端加 5s/10s 選擇器,duration 從請求一路帶到 provider(text 走 JSON、image 走 form),fal payload 帶 `str(duration)`,mock ffmpeg 反映時長。
  - 模型端:Kling v1.6 / v2.5-turbo 皆只收 `"5"` / `"10"`(已查證),預設 `"5"`。`ALLOWED_DURATIONS = (5, 10)` 為單一來源,換模型只改這裡。
  - 驗證:後端 mock e2e(5s→5.0s、10s→10.0s)、HTTP 驗證(合法 200 / 非法 422)、前端 Playwright(選擇器 + 10s 費用提示)。
  - 注意:image 端點 form 欄位用 `int = Form` + 手動檢查(不能用 `Literal[int]`,multipart 字串 `"5"` 對不上 int 的 Literal,會誤回 422)。
  - 殘留:`ALLOWED_DURATIONS` 仍寫死於 `schemas.py`;若預期常換模型,可改成從 `config.py` / `.env` 讀。

- [ ] **影片生影片(video-to-video / restyle)**:輸入一段影片 + prompt,重繪風格、保留原片動作。架構已支援(pluggable provider),只需比照 image-to-video 加一條路徑。
  - 候選模型(皆在 fal.ai,同一把 `FAL_KEY`):`decart/lucy-restyle`(專為 restyle,單一影片輸入)、`fal-ai/wan-vace-apps/video-edit`(可控、約 $0.20/支)。
  - 關鍵新邏輯:影片太大不能走現有 base64 data URI,要**先上傳到 fal storage 拿 URL**(`fal_client.upload_file_async()` 或手刻 storage REST),再把 URL 餵模型。
  - 改動:`config.py` 加 `fal_video_model` / `max_video_upload_mb`;`base.py`/`fal.py`/`mock.py` 加 `video_to_video()`;`schemas.py` 加 `JobKind.video_to_video` 與 `video_path`;`jobs.py`、`main.py`(新端點 `POST /api/jobs/video` + 中介層大小攔截涵蓋它);前端 `api.js`/`App.jsx` 加第三個 tab。
  - 注意:restyle 較慢較貴,`_MAX_WAIT`(600s) 可能要拉長;換模型後實測 `video.url` 回傳格式。

- [ ] **多檔上傳**:兩種意思,實作差很多。
  - **A. 批次**:一次丟 N 個檔,各自生成各自的影片。不限模型,前端 `<input multiple>` + 後端 `list[UploadFile]`,每檔開一個 job;前端要能同時輪詢/顯示多個 job。
  - **B. 多參考輸入合成同一支**(使用者關注的方向):多張參考圖/首尾幀/素材合成一支影片。**受模型限制** — 現用 Kling v2 只吃單張 `image_url`;需換成支援多輸入的模型 **Wan VACE**(`fal-ai/wan-vace-apps/video-edit`,fal.ai 上,有 `image_urls` 複數欄位)。payload 多帶 `image_urls` 陣列;多圖一樣走 fal storage 上傳拿 URL(與影片上傳同機制)。
  - A 與 B 可共用同一套 fal storage 上傳邏輯,差別只在「開幾個 job」與「payload 單張 vs 多張」。

- [ ] **動作模仿 / 多素材合成(含前端 UI/UX 設計)**:讓「A 角色做 B 的動作/行為」。
  - 核心觀念:**靜態圖沒有「動作」可抽取**,動作來源只有三種 —— (1) 參考影片(motion/performance transfer,最精準)、(2) 文字描述、(3) 單張姿勢圖/OpenPose(只能定一個姿勢,非連續動作)。「B 的人跟 A 做一樣行為」只有當 A 是**影片**時才成立。
  - 候選模型(皆 fal.ai,同一把 `FAL_KEY`):
    - 動作模仿(角色圖 + 驅動影片)→ `fal-ai/wan-motion`(含 pose retargeting 適配體型)、`fal-ai/kling-video/v2.6/standard/motion-control`(便宜,適合人像)。
    - 多角色/多素材合成(文字定動作)→ `fal-ai/kling-video/o1/reference-to-video`(**最多 7 個 reference**,多角色不糊臉)、`fal-ai/kling-video/v1.6/standard/elements`(最多 4 張)。
  - 共用基礎設施:同樣需先做 **fal storage 上傳拿 URL**(影片/多圖太大,base64 data URI 不可行)——與上面 video-to-video / 多檔上傳同一塊,先做這個。
  - **前端 UI/UX 設計**(尚未拍板,之後再做):
    - 第一原則:介面照**使用者意圖**組織,不照模型組織;模型名藏在後端,依輸入自動挑。
    - 多輸入用**有標籤的拖放槽**(角色槽/動作槽/場景槽),每槽只收對應型別、型別不符當場擋(順帶對齊「驗證上傳內容」那條)。
    - 動作槽放微文案引導:「想模仿動作請放**影片**;只有圖請用文字描述」——把「靜態圖沒動作」的概念內建進 UI。
    - 慢+貴(2–4 分鐘、$0.2 起):送出前顯示**預估時間/費用**,送出後給**分階段進度**(排隊→生成→後製);結果頁支援「沿用輸入只改 prompt 再生一次」。
    - **未決:整體導覽結構**——三選一:(A) 意圖卡片首頁「你想做什麼?」點卡進專屬表單(推薦,心智模型最清楚、加任務只加一張卡);(B) 沿用 tab 再加幾個(改動小,但 5+ tab 會擠且無法自我解釋);(C) 單一智慧畫布,丟素材自動推斷任務(最炫但不可預測、難引導)。決定前可先刻可點雛形(mock 資料、不接真 API)再選。
    - 待釐清:使用對象(自用/大眾/特定創作者)會影響上面選哪個——大眾要強引導(A),熟手嫌多一層。

## 審查中確認安全(無須處理)

`/api/jobs/{job_id}` 與輸出檔名皆用 server 端 uuid,無路徑遍歷;prompt 以 JSON 欄位傳遞、mock 用 argv 執行,無 shell injection;`.env` 已被 `.gitignore` 正確排除,未進版控。
