# TODO — 待辦與已知問題

來源:初始 commit 的程式碼審查(整體 / 錯誤處理 / 安全性 三方向)。
✅ **已修**:CRITICAL — `/files` 靜態掛載原本會把 `backend/`(含 `.env` 的 `FAL_KEY`)整個對外公開,已改成只掛 `outputs/`。

以下為其餘待辦,依優先序排列。

## High

- [ ] **上傳檔大小上限**:`main.py` 的 `await image.read()` 把整包讀進記憶體,無上限 → 大檔可 OOM / 塞爆硬碟。加 max size 與 413。
- [ ] **驗證上傳內容**:目前只信任 client 的 `content-type` 與 `filename`,不驗實際位元組。改成嗅探 magic bytes,副檔名由偵測到的型別決定。
- [ ] **mock 無 ffmpeg 時的假成功**:`mock.py` 在找不到 ffmpeg 時回一個 26 bytes 的壞 mp4,任務卻標 `done` → 使用者看到空白播放器、零錯誤。應改為 raise 明確錯誤(預設 provider 正是 mock)。
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

- [ ] `tempfile.mktemp` 已棄用(TOCTOU)→ 改 `NamedTemporaryFile` / `mkstemp`,並在 `finally` 清理。
- [ ] `_MINIMAL_MP4` 宣告的 box 長度與實際內容不符,註解稱「結構合法」不精確。
- [ ] `get_provider()` 每次呼叫都重建 provider → 可用 `functools.lru_cache` memoize。
- [ ] 上傳檔從不清理 → 加任務完成後清除或定期清掃。
- [ ] 前端切換分頁時未清掉舊的 `file`/`prompt`;`submitImageJob` 應在 `file` 為空時擋下。
- [ ] `jobs.py` 的 `created_at` / `updated_at` 用兩次 `_now()` → 呼叫一次共用,建立時兩個時間戳才一致。
- [ ] 文件化:`CORS_ORIGINS=*` 絕不可與 credentials 並用。

## 審查中確認安全(無須處理)

`/api/jobs/{job_id}` 與輸出檔名皆用 server 端 uuid,無路徑遍歷;prompt 以 JSON 欄位傳遞、mock 用 argv 執行,無 shell injection;`.env` 已被 `.gitignore` 正確排除,未進版控。
