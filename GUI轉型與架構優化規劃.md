# FANBOX Archiver GUI 轉型與架構優化規劃

> 盤點日期：2026-10-27  
> 現況版本：v1.1.2  
> 決策摘要：保留 Python 下載核心與 CLI，以 TypeScript 建立 GUI；本機網頁伺服器直接從 SQLite 與封存檔案動態組裝閱讀頁，不再要求每次下載後執行 `fanbox-archiver index`。現有靜態索引保留為可選的離線匯出功能。

## 1. 現況結論

目前專案不是需要推倒重寫的原型，而是一個已有良好安全邊界、資料模型、版本保存、續傳、離線閱讀器及測試基礎的可用工具。測試以專案內暫存目錄執行時為 **63 passed**。

最值得改善的不是下載語言本身，而是介面層與核心流程的分離程度：

- `cli.py` 約 729 行，除了參數與終端輸出，也負責登入材料選擇、備份 run lifecycle、Fan Card 流程、瀏覽器 session、進度回報與錯誤轉譯。
- `ArchiveService` 自行建立 storage、database、downloader，依賴注入不足，未來 GUI、API 與測試較難替換 adapter。
- 核心流程是同步阻塞式，適合 CLI，但 GUI 需要背景工作、取消、狀態查詢與可恢復的事件流。
- SQLite 目前每個方法各自開啟連線，適合單一 CLI 行程；GUI 同時讀取狀態與背景寫入前，需明確定義單一 writer、busy timeout 與 WAL 策略。
- 前端已有約 200 行的離線 JavaScript 閱讀介面，是導入 TypeScript 元件與 UI design system 的良好起點，不必從零驗證資訊架構。
- 現有日常流程把「下載」與「建立靜態閱讀網站」拆成兩次操作。資料其實已在 SQLite、`post.json` 與版本 manifest 中，伺服器可按請求組裝頁面；強制再跑一次完整 `index` 是不必要的操作負擔。
- `indexer.py`、`database.py`、`service.py`、`parser.py` 都超過 400 行，職責已開始集中，應在加 GUI 前拆小。
- 專案資料夾目前不是 Git repository；正式進入跨前後端與打包工作前，應先建立可回溯的版本控制與 CI。

## 2. 語言與架構決策

### 2.1 不建議現在把核心全面重寫成 TypeScript

原因：

1. 下載速度主要受刻意設定的 3 秒請求間隔、FANBOX 回應與磁碟 I/O 限制，不是 Python 計算效能。改寫 TypeScript 不會消除這些瓶頸。
2. 現有 Python 已涵蓋 Playwright、HTTP、解析、SQLite、Pydantic schema、原子檔案操作、安全路徑與 63 個測試。全面改寫會重新引入資料遺失、權限繞過、版本相容及續傳錯誤風險。
3. GUI 與網頁整合需要的是穩定的 API／工作事件邊界，不要求下載核心和前端使用同一語言。
4. TypeScript 很適合 UI 狀態、表單、元件、即時進度與型別化 API client；Python 則可繼續承擔已驗證的下載與封存核心。

### 2.2 建議目標架構

```text
CLI (Typer) ───────────────┐
                           ▼
TypeScript GUI ── HTTP ── Application Layer ── Domain / Use Cases
                  SSE/WS         │
                                 ├─ FANBOX / Playwright adapter
                                 ├─ Downloader adapter
                                 ├─ SQLite repository
                                 ├─ Filesystem archive
                                 ├─ Dynamic reader service
                                 └─ Optional static export builder
```

- CLI 只做參數解析、文字呈現與 exit code。
- GUI 只透過本機 API 操作，不直接碰資料庫或下載目錄。
- Application layer 提供 `plan_backup`、`run_backup`、`verify_archive`、`build_index`、`login` 等 use case。
- CLI 與 API 使用相同 use case，確保行為一致。
- 所有長工作以 job 執行，透過結構化事件回報狀態。
- 閱讀首頁、文章、版本與 Fan Card 由伺服器按請求查詢 SQLite，並只在需要時讀取對應 JSON；下載完成後不需重建頁面。
- `index` 改為選用的「匯出靜態網站」功能，供完全離線、搬移或備份時使用，不再是 GUI 的資料來源。
- 初期 GUI 在瀏覽器開啟；成熟後再用 Tauri 封裝，Python 後端作 sidecar。

### 2.3 何時才考慮替換 Python 核心

只有 profiling 顯示 CPU 熱點明確且影響實際使用時才考慮。優先順序是：

1. 減少不必要 API 呼叫、重複 SHA-256、重複 JSON／HTML 建置。
2. 改善 SQLite 查詢與批次 transaction。
3. 對純 CPU 熱點使用 Rust extension 或獨立工具。
4. 最後才評估整體語言移植。

TypeScript 應先用在前端，不應以「可能更快」作為重寫下載核心的理由。

## 3. 優化項目與優先級

### P0：建立可安全演進的基線

- 初始化 Git；確認 `FANBOX/`、`.fanbox-browser/`、`config.yaml`、log 與 cache 永不進版控。
- 將封存資料與 source checkout 的預設位置解耦，至少支援使用者資料目錄或明確自訂路徑。
- 加入 Ruff、Pyright 或 mypy、coverage 與 CI；保留 Windows Python 3.12 為主要矩陣。
- 將 pytest `--basetemp` 設定到可寫位置，避免受 Windows sandbox／權限影響。
- 建立資料庫 schema migration 測試、備份格式相容測試與 CLI smoke test。

完成標準：乾淨 checkout 可一鍵安裝、lint、type-check、執行 63+ 測試，且不需要真實 Cookie。

### P1：抽出共用 Application Layer

新增建議模組：

```text
src/fanbox_archiver/application/
├── backup.py
├── auth.py
├── catalog.py
├── maintenance.py
├── jobs.py
└── events.py
```

核心改動：

- 將 `cli._run_backup()` 搬成 `BackupUseCase`；終端 `Console`、`Progress` 不得出現在 application layer。
- 將 Fan Card 保存從 CLI 編排搬入 backup use case。
- 定義型別化事件：`JobStarted`、`PlanReady`、`ItemStarted`、`AssetProgress`、`ItemCompleted`、`Warning`、`JobFailed`、`JobFinished`。
- 將單一 `progress_callback` 改為 `EventSink` protocol；CLI、API、測試各自實作 sink。
- 加入 cooperative cancellation token；在文章與資源邊界安全停止，不在原子發布途中中斷。
- 使用依賴注入建立 `ArchiveService`，允許傳入 database、storage 與 downloader factory。
- 建立穩定 DTO，避免 API 直接序列化 `sqlite3.Row` 或內部 Pydantic model。
- CLI 新增 `--json` 或 `--output json`，便於自動化與回歸驗證。

完成標準：`backup`、`verify`、`index` 的 CLI 行為不變，且同一 use case 可由測試在沒有 Typer／Rich 的情況下呼叫。

### P1：資料庫與工作一致性

- GUI 初期只允許一個 mutation job，同時可有唯讀查詢；禁止兩個備份工作並行。
- 對 SQLite 設定合理 `busy_timeout`；評估啟用 WAL，使 GUI 查詢不阻塞背景寫入。
- 將一個 job 的 run 狀態、計數、錯誤與取消狀態完整落庫，程式重啟後仍可判斷上次是否中斷。
- 為常用查詢檢查 index：post status、creator/status、version post_id、run started_at。
- 將多次相鄰寫入合併成明確 transaction，但檔案 publish 與 DB commit 順序須維持可恢復性。
- 加入 schema version endpoint 與 migration 前備份狀態，GUI 可顯示升級結果。

完成標準：背景備份時可持續讀取統計；強制關閉程式後，下次啟動能回報 interrupted job 並安全 retry。

### P2：本機 Web API 與 Job Runner

建議使用 FastAPI，但 job runner 必須是專案自己的單工作者 queue，而不是直接把長時間下載塞進 request handler。

第一版 API：

```text
GET    /api/health
GET    /api/config
PATCH  /api/config
GET    /api/auth/status
POST   /api/auth/login
GET    /api/creators
GET    /api/posts
GET    /api/posts/{post_id}
GET    /api/posts/{post_id}/versions
GET    /api/posts/{post_id}/versions/{version}
GET    /api/fancards
GET    /api/fancards/{creator_id}/{month}
GET    /api/status
POST   /api/jobs/backup/plan
POST   /api/jobs/backup
POST   /api/jobs/verify
POST   /api/jobs/index
GET    /api/jobs/{job_id}
POST   /api/jobs/{job_id}/cancel
GET    /api/events
```

動態閱讀設計：

- 首頁、篩選與分頁直接查 SQLite，只回傳摘要 DTO，不把所有正文一次載入瀏覽器。
- 開啟文章時才讀取指定版本的 `post.json`，由後端轉成穩定 Reader DTO；前端負責畫面組裝。
- 圖片、封面與附件以 post／version／asset ID 取得，後端根據 DB 或 manifest 解析實際檔案；不得接受任意本機路徑。
- 最新版本由資料庫的 `latest_version_id` 決定，因此備份 transaction 完成後立即出現在 GUI。
- 備份完成事件使前端重新整理相關 query；不需要呼叫 index builder。
- Markdown／HTML 顯示轉換可做記憶體或磁碟 cache，cache key 使用內容 fingerprint；內容更新時自然失效。
- `IndexBuilder` 留作 export adapter。為了 CLI 相容仍保留 `fanbox-archiver index`，之後可新增較清楚的 `fanbox-archiver export-site` 別名。

安全要求：

- 僅監聽 `127.0.0.1`，預設使用隨機可用 port。
- 啟動時產生 session token；所有 mutation endpoint 驗證 token 與 Origin。
- 不提供任意 URL、任意檔案路徑或 shell command endpoint。
- Cookie 不回傳前端、不進 API log、不寫 localStorage。
- API error 使用穩定 error code，詳細敏感資訊只寫已遮蔽的本機 log。
- 保留目前 HTTPS allowlist、429 停止、單佇列及 3 秒間隔規則。

完成標準：CLI 與 API 對相同 fixture 產生相同 plan、狀態、檔案與 DB 結果。

### P2：TypeScript GUI MVP

建議技術：Vite + TypeScript + React（或偏好更輕量時使用 Preact）。不要先導入大型全端框架，因為後端是本機 Python API，也不需要 SSR。

MVP 畫面：

1. 儀表板：登入狀態、最後備份、文章／版本／異常數量、歷史回補進度。
2. 備份：全部或單一 Creator、dry-run、max posts、計畫預覽、開始／取消。
3. 工作中心：目前文章、資源進度、成功／略過／失敗、結構化錯誤。
4. 創作者與文章：沿用現有閱讀器的搜尋、篩選、排序與本機頁連結。
5. 維護：verify、retry、index rebuild、開啟封存資料夾。
6. 設定：只暴露安全且可理解的選項；危險清除操作使用二次確認。

前端規則：

- 由 OpenAPI 產生 TypeScript client／types，避免手寫兩套資料契約。
- 進度事件採 SSE 即可；只有需要雙向即時控制時才用 WebSocket。
- UI 重新整理後從 job endpoint 恢復狀態，不依賴單頁記憶體。
- 重用現有色彩、主題、文章卡片與響應式設計語言。
- GUI 不取代離線網站；離線閱讀器仍是可攜、無伺服器的輸出。
- 日常閱讀使用動態 server；「匯出離線網站」放在進階／維護功能，不在備份成功後自動執行。

完成標準：不開終端即可登入、預覽、備份、查看進度、驗證、重試與開啟內容；新下載文章在工作完成後立即可讀，不需建索引。使用者仍可按需要匯出靜態網站。

### P3：桌面封裝

- 先以 `fanbox-archiver serve` 驗證數週，再導入 Tauri。
- 將 Python API 打包成 Windows sidecar；Tauri 負責視窗、啟停、單一實例與開啟資料夾。
- sidecar 啟動後透過隨機 port + one-time token 回報 readiness。
- 關閉視窗時若 job 執行中，提供「留在背景／安全停止／取消關閉」。
- 第一個正式封裝只支援 Windows 11 x64；確認升級、資料目錄與瀏覽器 profile 不被覆蓋後，再考慮其他平台。
- CLI 仍作為同一安裝包中的進階入口，並保證設定與 DB 格式相同。

完成標準：安裝程式不要求使用者另裝 Python／Node；GUI 與 CLI 可讀寫同一 archive，但 mutation job 有跨行程鎖避免同時執行。

## 4. 效能改善計畫

先量測再改寫。新增下列 telemetry，但只保存本機且不含敏感資料：

- 每次 run 的 API request 數、429／retry 數、等待節流時間。
- 每篇解析、hash、資源下載、manifest、publish、index build 耗時。
- 動態首頁 query、文章 JSON 載入、Reader DTO 轉換與首屏 render 耗時。
- 實際下載 bytes、續傳 bytes、重用資源數、重複 hash 數。
- SQLite query／transaction 時間與 lock wait。

可優先實作的低風險改善：

- 以遠端 `updated_at`、ETag、size 與已存 fingerprint 避免不必要內容抓取或 SHA-256。
- 同一 run 共用 HTTP／browser session，維持既有節流器。
- 對 DB 寫入做小批次 transaction；不要對每個 UI progress tick 寫 SQLite。
- 日常 listing 由 SQLite 分頁查詢，不再產生靜態頁；文章正文採 lazy load。
- 靜態 indexer 降級為按需匯出工具並保持增量輸出，不得拖慢或阻塞一般備份完成流程。
- hash 與影像驗證若成為 CPU 熱點，可送入有限 thread pool；遠端下載仍保持單佇列。
- 增加 1,000、10,000 篇 synthetic fixture benchmark，追蹤 plan、status、index 與首次 UI render。

不建議的「優化」：提高 FANBOX 並行下載數、縮短保守間隔、以多行程規避 429，或為了吞吐繞過權限／反自動化限制。

## 5. 建議開發時程

### 里程碑 0：工程基線（1～2 天）

- Git、lint、type-check、coverage、CI。
- 測試暫存路徑與 fixture 整理。
- 建立效能 baseline 報告。

### 里程碑 1：共用應用層（3～5 天）

- 抽出 BackupUseCase、EventSink、CancellationToken。
- CLI 改接 use case，維持相容。
- Fan Card 與 run lifecycle 移出 CLI。
- 增加 application integration tests。

### 里程碑 2：Job／DB 強化（2～4 天）

- 單工作者 queue、持久 job state、取消與中斷恢復。
- SQLite busy timeout／WAL／跨行程 mutation lock。
- 狀態與歷史 API 所需 DTO。

### 里程碑 3：Local API（2～4 天）

- FastAPI、OpenAPI、SSE、localhost token security。
- 動態文章／版本／Fan Card Reader API、安全媒體檔案路由、分頁查詢。
- 下載完成後透過事件與 query invalidation 立即更新畫面，不執行 `index`。
- CLI 加 `serve`，建立 API parity tests。

### 里程碑 4：GUI MVP（5～8 天）

- TypeScript dashboard、備份預覽、進度、錯誤、維護、設定。
- 沿用既有閱讀 UI 視覺與無障礙規則。
- E2E 測試完整 dry-run 與 fixture backup。

### 里程碑 5：Tauri 封裝（3～6 天）

- Windows sidecar、安裝／升級、單一實例、關閉行為。
- 封裝 smoke test 與資料相容驗證。

總估計約 3～5 週的個人開發量；每一里程碑都可獨立發布，不必等全面完成。

## 6. 下一個立即實作批次

下一個 PR／版本只做架構抽離，不先做 GUI：

1. 建立 `application/events.py` 與事件 dataclass／protocol。
2. 建立 `application/backup.py`，將 `cli._run_backup()` 與 Fan Card 編排搬入。
3. 新增 cancellation token，但 CLI 第一版只需支援 Ctrl+C 安全停止。
4. CLI 使用 `RichEventSink` 呈現原本進度與訊息。
5. 測試 `NullEventSink`／`CollectingEventSink`，確認事件順序與失敗狀態。
6. 保持所有現有 CLI command、設定檔、資料庫與輸出格式相容。
7. 接著先做一個最小 `serve` proof-of-concept：動態列出文章並讀取單篇最新版本，驗證不依賴 `_site/` 也可完整閱讀。

此批次完成後，API 與 GUI 才有穩固接點，也能最早發現抽象是否合理。

## 7. 暫不納入

- 不把 FANBOX Cookie 傳至遠端 server。
- 不建立多使用者 SaaS 或公開網路服務。
- 不解壓附件、不執行第三方內容。
- 不提高 FANBOX 下載並行度。
- 不移除 CLI、不變更現有 archive 格式。
- 不移除 `index`；它改為選用的靜態匯出／攜帶功能。
- 不在缺乏 profiling 證據前重寫 Python 核心。

