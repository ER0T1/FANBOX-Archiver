# FANBOX Archiver

**內部測試版本：v1.3.48-alpha（2026-11-04）**

FANBOX Archiver 是 Windows 11 優先、Python 3.12+ 的 pixivFANBOX 個人備份工具，提供 Windows 桌面程式、瀏覽器 GUI 與命令列介面。它只保存目前登入帳號有權瀏覽的投稿，不會繞過付費牆、CAPTCHA、反自動化機制或其他存取限制。

原始碼與問題回報：<https://github.com/ER0T1/FANBOX-Archiver>。動態閱讀器與桌面程式頂端的「GitHub」按鈕也連到這裡，只在點擊時開啟，頁面載入時不會連線。

> pixivFANBOX 的介面並非穩定的公開 API，平台規範也可能限制自動化蒐集。請只在你有權備份且符合現行服務條款的範圍使用。本工具預設單一下載佇列、每次請求至少間隔 3 秒，遇到 401、403 或 429 會停止或回報，而非規避限制。

## 功能

- 提供 Tauri 2 Windows 桌面程式，自動管理本機 Python sidecar，並可沿用既有 CLI 封存。
- 解析 `article`、`image`、`file`、`text` 等結構化投稿，另提供渲染後 HTML 備援解析。
- 保留文字、粗體、原圖、cover、附件、外部連結卡片與原始順序，輸出 UTF-8 `post.md` 與完整 `post.json`。
- 原始圖片及任意附件串流下載；使用 `.part` 暫存檔及 HTTP Range 續傳。
- 保存創作者頭像、文章贊助檔位與台灣時區發布／更新時間。
- 自動保存支援中創作者的每月 Fan Card、可用卡面與方案資訊；正確處理未提供卡面的月份。
- Fan Card 方案權益會以保守、可理解的狀態卡片呈現；已知 Discord 特典不再輸出原始 JSON，也不偽造外部加入連結。
- SQLite 記錄投稿、版本、資源及執行狀態，以內容指紋避免重複下載。
- 提供動態本機閱讀器（瀏覽器與 Windows 桌面版），可搜尋、篩選、排序並閱讀歷史版本、Creator Profile 與 Fan Card；不啟動程式時可直接閱讀各資料夾中的 Markdown。
- 投稿卡片顯示封存時保存的標籤；創作者投稿頁可依跨頁統計的標籤快速篩選。
- 動態閱讀器與桌面程式提供「跟隨系統／暗色／亮色」主題，在「設定」選擇後寫入 `config.yaml`；另可為亮色／暗色各自訂 13 個顏色（只接受允許清單與 `#RRGGBB`）。
- 介面文字由隨程式提供的翻譯目錄產生，繁體中文為基準與缺漏備援；可在「設定」選擇介面語言（目前提供繁體中文），封存內容不會被翻譯，也不依賴遠端翻譯資源。
- SHA-256、檔案大小及圖片格式／尺寸驗證。
- 嚴格 HTTPS 主機白名單、Windows 安全檔名及目錄穿越防護。
- 不將帳號密碼或 Cookie 寫入設定檔、資料庫或日誌。

目前所有 `v1.x.x-alpha` 均為內部測試版本；同一版本線完成正式發布驗收後，才會移除 `-alpha`（例如 `v1.5.0-alpha` → `v1.5.0`）。

> 💡 完整歷史版本更新重點請參閱 [CHANGELOG.md](CHANGELOG.md)。

## v1.3.52-alpha 更新重點

- 介面國際化第五批（伺服器文字，第二部分）：備份與驗證過程中產生的文字改由翻譯目錄提供，並依介面語言顯示（翻譯目錄由 730 條增為 842 條）。範圍包括連線與下載錯誤、登入工作階段錯誤、備份警告與失敗原因、Fan Card 保存提示、驗證進度與驗證問題說明、設定值錯誤，以及舊靜態網站清理提示。內容與文字不變，目前仍只提供繁體中文。
- 工作紀錄（備份事件、驗證結果與進度）保存時保留翻譯鍵，日後切換語言也能以新語言顯示；升級前的紀錄維持原文。
- 設定值錯誤（例如不支援的時區）改為只顯示原因本身，不再夾帶驗證程式庫的英文說明。
- Windows 工作排程器中的工作說明改依設定的介面語言建立；命令列的錯誤訊息與驗證問題也依介面語言顯示。
- 維持原文、不翻譯：寫入封存檔案的內容（Markdown 標籤、Fan Card Markdown、解析警告）、稽核報告與診斷資訊、資料庫中的錯誤欄位，以及只會在程式異常時出現的內部一致性錯誤。日期格式會在新增語系時一併處理。

## v1.3.51-alpha 更新重點

- 介面國際化第五批（伺服器文字，第一部分）：動態閱讀器顯示的伺服器文字改由翻譯目錄提供，並依每次請求的介面語言顯示。範圍包括 API 錯誤訊息、閱讀頁的找不到／無法讀取提示、登入狀態訊息、自動備份的排程摘要與提示、程式關閉時的背景排程狀態、創作者的備份狀態、粉絲卡權益說明，以及時區提示（翻譯目錄由 633 條增為 730 條）。內容與文字不變，目前仍只提供繁體中文。
- 會保存下來的提示（排程延後／補跑提示、伺服器重新啟動導致的工作中斷說明）改為連同翻譯鍵一起保存，日後切換語言時也能以新語言顯示；升級前已保存的提示維持原文。
- 命令列 `creators` 的狀態欄與登入檢查訊息也依介面語言顯示。
- 測試語系 `qps-ploc` 的自動檢查不再豁免上述伺服器文字；閱讀、備份、維護與設定頁在手機寬度下都沒有遺漏。
- 尚未轉換：備份與驗證過程中產生的文字（備份事件、下載與連線錯誤、驗證問題說明）、設定值驗證錯誤，以及寫入封存檔案的內容（Markdown 標籤、解析警告、稽核報告；這些屬於封存內容，維持建立時的語言）。

## v1.3.50-alpha 更新重點

- 介面國際化第四批：命令列全部指令的訊息、表格欄位、錯誤提示，以及 `--help` 的指令與選項說明，改由翻譯目錄提供（翻譯目錄由 524 條增為 633 條）。輸出內容與文字不變，目前仍只提供繁體中文。
- 命令列的 `--help` 說明現在也依 `--lang` 或設定檔的 `display.language` 顯示；日誌內容維持不翻譯。
- 測試語系 `qps-ploc` 新增命令列檢查：所有指令與選項說明都已轉換，訊息語言依每次執行重新判斷、不受前一次執行影響。
- 尚未轉換：由伺服器與程式核心產生的文字（例如登入狀態訊息、備份事件與錯誤訊息、排程摘要、粉絲卡權益說明、創作者的備份狀態與驗證問題說明）。

## 安裝

先安裝 [Python 3.12 或更新版本](https://www.python.org/downloads/)，然後在 PowerShell 執行：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[test]"
Copy-Item config.example.yaml config.yaml
```

如 PowerShell 禁止執行啟用腳本，也可直接使用 `.\.venv\Scripts\fanbox-archiver.exe`。

`config.yaml` 不存在或只包含 `{}` 時，程式會使用安全預設值啟動；複製
[`config.example.yaml`](config.example.yaml) 則可查看所有公開設定欄位與預設語意。範例檔不含 Cookie、token 或本機憑證，舊版缺少新欄位的設定仍會沿用模型預設值，不會被強制改寫。

開發者修改設定模型或新增範例格式後，請執行 `npm run release:check`。檢查會以設定模型或已登錄欄位為來源，列出範例檔缺少、多餘、放錯層級或偏離預設值的欄位名稱，不輸出秘密值。

## 登入狀態

本工具不接收或保存 FANBOX 密碼。若要使用線上指令，請從你自己的已登入瀏覽器工作階段取得完整 Cookie header，僅放入目前 PowerShell 行程的環境變數：

```powershell
$env:FANBOX_COOKIE = '完整 Cookie header'
fanbox-archiver auth
```

關閉該 PowerShell 視窗後，行程環境變數即消失。不要把 Cookie 貼進 `config.yaml`、命令列歷史、問題回報或 Git。

推薦使用專用瀏覽器設定檔。第一次執行時，程式會開啟 Chrome，由你親自登入：

```powershell
fanbox-archiver auth login
```

登入成功後，`auth`、`backup` 和 `retry` 會自動沿用 `.fanbox-browser/` 中的工作階段：

```powershell
fanbox-archiver auth check
fanbox-archiver backup --post "https://www.fanbox.cc/@creator/posts/123456"
```

程式不讀取帳號、密碼、2FA 或 CAPTCHA；這些資訊只會由你直接輸入 FANBOX／pixiv 頁面。專用設定檔含有敏感的登入 Cookie，已加入 `.gitignore`，不可分享或上傳。

只有 `auth login` 會顯示瀏覽器視窗；登入檢查、備份與單篇下載平常使用背景工作階段。背景工作階段失效時，程式會停止並提示重新執行 `auth login`。

`--browser chrome` 是舊有瀏覽器 Cookie 讀取備援。新版 Chrome 可能因 App-Bound Encryption 而拒絕外部解密，此時請使用上述 `auth login`。

## 使用方式

### 建議的第一次使用流程

```powershell
# 1. 建立專用登入工作階段
fanbox-archiver auth login

# 2. 確認登入有效
fanbox-archiver auth check

# 3. 預覽本次備份計畫
fanbox-archiver backup --dry-run

# 4. 執行備份；可依需要調整單次上限
fanbox-archiver backup --max-posts 100

# 5. 啟動動態本機閱讀器（不需建立索引）
fanbox-archiver serve
```

日後執行 `backup` 後，動態閱讀器會直接讀取 SQLite 與 `post.json`；重新整理頁面即可看到新內容，不需再次建立索引。已完成且內容未變的 Post 不會重複下載。

CLI 與動態閱讀器共用相同的備份應用層。備份計畫、Fan Card、文章進度、資源進度、完成、失敗與取消會產生結構化事件，供目前的終端介面及後續 GUI 工作佇列使用；取消只在文章邊界生效，不會中斷正在進行的版本原子發布。

### 常用指令

先以離線 HTML 驗證解析結果（預設不下載遠端資源）：

```powershell
fanbox-archiver import-html ".\範例1.html" --metadata-only
```

備份一篇或多篇目前有權存取的投稿（重複使用 `--post`）：

```powershell
fanbox-archiver backup --post "https://www.fanbox.cc/@creator/posts/123456"
fanbox-archiver backup --post 123456 --post "https://creator.fanbox.cc/posts/789012"
```

有限範圍同步、預覽及本機驗證：

```powershell
fanbox-archiver backup --dry-run
fanbox-archiver backup
fanbox-archiver backup --creator "https://www.fanbox.cc/@creator-id"
fanbox-archiver backup --creator creator-a --creator "https://creator-b.fanbox.cc"
fanbox-archiver backup --creator creator-id --profile --fancard
fanbox-archiver creators --refresh
fanbox-archiver creators --json
fanbox-archiver creators
fanbox-archiver audit
fanbox-archiver audit --json
fanbox-archiver repair-copy --output FANBOX-repaired
fanbox-archiver verify
fanbox-archiver retry
fanbox-archiver status
fanbox-archiver versions 123456
```

`backup` 是唯一下載入口；不帶 selector 時會輪替處理支援中創作者、保存 Profile 與 Fan Card，並持續保存歷史回補游標。指定 `--creator` 時預設備份投稿，可用 `--profile`、`--fancard` 加入對應資料；指定 `--post` 時只處理明列投稿。`--creator` 與 `--post` 互斥。已完成且未更新的投稿不占 `sync.max_posts_per_run` 額度。`--dry-run` 只查詢並顯示計畫，不寫入封存內容、同步狀態或執行紀錄。

`audit` 是版本與時間契約的唯讀稽核，不會像修復工具一樣修改資料；發現問題時以結束碼 `1` 回報。`--json` 適合保存或比較結構化報告，其中的 `repair_plan` 仍是 dry-run 預覽，不會自動套用。現有 `verify` 則保留資源完整性驗證與重試狀態整合語意，兩者用途不同。

`repair-copy` 不會修改原始封存，只接受尚不存在且位於原始封存外的 `--output` 目錄。它建立完整副本與修復前資料庫備份，並只套用 `audit` 已標示為 automatic 的動作（latest pointer／alias、依 manifest 重建版本列、把誤歸上個月的 Fan Card 版本移回擷取月份）；沒有 automatic 動作時不建立副本，其餘問題仍需人工判讀。確認副本內容前，不要用它取代原始封存。

舊指令遷移：`download <post>` 改用 `backup --post <post>`；`sync --creator <creator>` 改用 `backup --creator <creator>`；`sync --supporting` 改用不帶 selector 的 `backup`。

互動終端會顯示目前投稿、資源名稱與下載大小；非互動環境不輸出動畫。執行日誌位於 `FANBOX/logs/` 並按日輪替，Cookie、Authorization 與常見查詢憑證會先遮蔽。`status` 會另外顯示最近一次執行、失敗投稿及尚未完成歷史回補的創作者。

目前下載仍刻意維持單一佇列，`download.max_concurrent` 只接受 `1`，避免意外提高 FANBOX 請求頻率。

### 動態本機閱讀器

直接啟動本機閱讀伺服器：

```powershell
fanbox-archiver serve
```

伺服器只監聽 `127.0.0.1`，預設開啟 `http://127.0.0.1:8765/`。投稿、歷史版本、創作者與粉絲卡會在瀏覽時直接查詢 SQLite 並讀取對應 JSON，下載完成後重新整理即可看到新內容。投稿首頁會顯示封面與贊助檔位；每位創作者有獨立的個人資料、投稿與粉絲卡分頁。文章頂端與底部提供上一篇／下一篇，也可使用鍵盤左右方向鍵；創作者投稿每 50 篇分頁，並優先顯示 FANBOX 置頂投稿。網頁中的「備份」頁可先執行 dry-run、開始正式備份、查看固定計畫摘要、目前資源進度與可摺疊的詳細紀錄，或要求安全停止；「維護」頁可執行持久化封存完整性驗證；「設定」頁分成「帳號與登入」「一般」「備份」「主題」「關於與診斷」五個子頁面，各自儲存，未儲存就離開會先確認；「關於與診斷」會顯示版本、schema 與資料位置，並可開啟封存／日誌資料夾或複製診斷資訊（不含 Cookie 與登入資料）。備份與驗證共用單一工作佇列，避免同時修改封存。按 `Ctrl+C` 可停止伺服器；若不想自動開啟瀏覽器，可加上 `--no-open`。

每次啟動伺服器都會產生新的本機工作階段權杖，所有啟動／取消／重試工作請求都必須帶有該權杖；首頁與 API 禁止快取，並維持 Trusted Host、CSP 與僅監聽 loopback 的限制。工作請求、摘要及結構化事件會保存到 SQLite；伺服器重新啟動後仍可篩選與查看最近工作。若上次程序在 queued、running 或 cancelling 狀態中結束，重新啟動時會標記為 `interrupted`，但不會未經確認自動重新下載；使用者可在 GUI 明確選擇以相同設定建立一個新的重試工作。高頻資源進度採合併與節流寫入，工作列表 API 只傳摘要，選取工作後才載入完整事件，避免輪詢歷史工作時反覆傳輸大量紀錄。

### 開啟備份資料夾

```powershell
fanbox-archiver open
fanbox-archiver open --post 12810903
fanbox-archiver open --post 12810903 --version 1
fanbox-archiver open --creator comodox
fanbox-archiver open --fancard comodox --month 2026-10
```

`open` 以檔案總管開啟封存目錄，或指定投稿版本、創作者、Fan Card 月份的資料夾；資料夾中有 Markdown 與原始檔，不啟動程式也能閱讀或搬移。離線靜態網站與 `index` 指令已於 v1.3.46-alpha 移除，升級後程式會自動刪除舊版產生的 `FANBOX/_site/` 與 `FANBOX/index.html`（詳見 CHANGELOG）。

需要捨棄舊格式 Post 並重新完整備份時，可明確執行：

```powershell
fanbox-archiver clear-posts
```

此指令會永久刪除 Post、歷史版本與 Post 資源，並重設歷史回補游標；Creator、Fan Card、登入設定檔與程式日誌會保留。執行前會要求確認，非互動環境必須加上 `--yes`。

閱讀器的網頁資源全部隨程式提供，不使用 CDN、分析服務或遠端字型。

介面語言由 `config.yaml` 的 `display.language` 決定（`auto` 跟隨系統，找不到支援語言時使用繁體中文）。動態閱讀器重新整理頁面後套用；命令列的訊息與 `--help` 說明也依同一設定顯示（會讀取 `--config` 指定的設定檔），並可用全域選項 `--lang` 暫時覆寫，例如 `fanbox-archiver --lang zh-Hant status`；日誌內容不翻譯。開發與版面測試可使用 `qps-ploc` 測試語系，它會把已轉換的文字加上「［…］」並拉長。

所有指令皆可用 `--help` 查看參數：

```powershell
fanbox-archiver --help
fanbox-archiver backup --help
```

## 輸出格式

```text
FANBOX/
├── creator-id/
│   ├── creator-avatar.jpeg
│   ├── fancards/
│   │   └── 2026-10/
│   │       ├── card.jpeg          # FANBOX 有提供卡面時才存在
│   │       ├── fancard.md
│   │       ├── fancard.json
│   │       └── versions/v0001/
│   └── 2026-10-24_12805939/
│       ├── post.md
│       ├── post.json
│       ├── images/
│       ├── files/
│       ├── cover/
│       └── versions/
│           ├── v0001/
│           └── v0002/
└── backup.db
```

每次投稿語意內容變更都會建立新的 `versions/vNNNN/` 完整快照；根目錄維持最新版別名。每個版本包含 `manifest.json` 與檔案 SHA-256，未變更資源會優先使用硬連結以節省空間。

正式執行 `backup` 時也會保存每位支援中創作者當月的 Fan Card：

```text
FANBOX/<creator-id>/fancards/<YYYY-MM>/
├── card.jpeg                       # FANBOX 有提供卡面時才存在
├── fancard.md
├── fancard.json
└── versions/v0001/...
```

卡面原圖（若有）、方案資訊、金額、支援月份與完整 API 資料都保存在本機。若創作者把密碼或提示寫在卡面或方案資訊中，備份仍會保留；同月資料變更時會建立下一版本。

`<YYYY-MM>` 是擷取當下的日本時間月份（FANBOX 的月份邊界），不受顯示時區影響。月初創作者已換上新卡面、但本月付款紀錄尚未出現時，卡片仍歸到本月，manifest 會記錄 `target_month_payment_seen: false`；舊版曾把這類卡面存成上個月的新版本，可用 `audit` 找出（`fancard_month`）並以 `repair-copy` 在副本中修正。

原圖依正文出現順序命名為 `001.png`、`002.jpg`；附件盡量保留原名，撞名時加入資源 ID。工具不會自動解壓縮附件，也不會因遠端投稿失效而刪除本機備份。

## 測試

```powershell
python -m pytest
npm install
npm run check:web
npm run test:web
npm run test:e2e
npm run desktop:test-sidecar
npm run desktop:test-installer
npm run release:check
```

測試包含規劃書提供的 HTML：應辨識 `範例1.html` 的 9 張正文原圖，且不把 `/w/1200/` 預覽圖當作原圖。`test:e2e` 會以系統現有的 Chrome 啟動隔離的 localhost GUI，使用暫存封存驗證投稿導覽、搜尋、分頁、置頂排序、Creator Profile、Fan Card、設定保存、封存驗證與工作輪詢，不會讀寫正式資料。`desktop:test-sidecar` 會啟動已封裝的 sidecar、檢查健康端點，再終止完整程序樹。

`.github/workflows/windows.yml` 會在 Windows runner 執行 Python、TypeScript、Node、Chromium GUI E2E、Rust 與 sidecar 測試，接著產生 NSIS 安裝程式並上傳為 workflow artifact。CI 使用 Playwright Chromium；若瀏覽器無法啟動會直接失敗，不會將測試標記為略過。

瀏覽器 GUI 的 TypeScript 原始碼位於 `src/fanbox_archiver/web_src/`，已涵蓋型別化 API client、投稿與創作者閱讀元件、共用控制項、設定、備份工作、封存驗證，以及頁面啟動、導覽、搜尋、鍵盤事件與工作輪詢。修改後執行 `npm run build:web`，將編譯結果更新至會隨 Python wheel 發布的單一 `web_assets/core.js`；一般使用者執行 GUI 時不需要安裝 Node.js。

### Windows 桌面版開發

Tauri 2 骨架位於 `src-tauri/`。桌面程式會選擇空閒的 loopback 連接埠、啟動以 PyInstaller 封裝的 Python sidecar，等待健康檢查通過後才顯示既有 GUI；關閉桌面視窗時也會停止 sidecar。原本的 `fanbox-archiver` CLI 與 `serve` 指令保持不變。

首次啟動會顯示桌面設定頁，可選擇既有 `config.yaml`、直接匯入包含 `backup.db` 的 FANBOX 封存資料夾，或在應用程式資料目錄建立全新封存。選擇結果會保存在本機 `desktop-state.json`，後續啟動會直接沿用；匯入資料夾只會建立相容的設定檔，不會搬移或改寫原有投稿。需要切換資料來源時，可使用桌面程式的「封存 → 變更封存位置」回到選擇頁；這只會清除目前選擇，不會刪除設定檔、資料庫或投稿。若 sidecar 因設定檔已移動、內容無效或磁碟無法存取而啟動失敗，錯誤頁也會提供「重新選擇封存」按鈕。若先設定 `FANBOX_ARCHIVER_CONFIG`，桌面程式仍會優先使用該路徑，方便開發與自動化測試。桌面程式本身的日誌位於 `%LOCALAPPDATA%\local.fanbox-archiver.desktop\logs`（單檔約 1 MB、保留最新 5 個），可從「設定 → 關於與診斷」直接開啟。

首次建置需安裝 Rust stable（MSVC）、Visual Studio C++ Build Tools、Node.js，以及 Python 桌面建置依賴：

```powershell
.venv\Scripts\python.exe -m pip install -e ".[test,desktop]"
npm install
npm run desktop:sidecar
npm run desktop:check
npm run desktop:dev
```

`desktop:sidecar` 會產生 Tauri 規定的 `fanbox-archiver-sidecar-x86_64-pc-windows-msvc.exe`；該建置產物不納入 Git。`desktop:build` 會重新產生 sidecar 並建立 NSIS 安裝程式，輸出位於 `src-tauri/target/release/bundle/nsis/`。`desktop:test-installer` 只會在 `build/installer-smoke/` 安裝測試副本，先拒絕覆蓋環境中既有的 FANBOX Archiver，再驗證靜默安裝、覆蓋升級、主程式版本、解除安裝與外部封存資料保留。`1.2.0 → 1.3.0` 與 `1.3.0 → 1.3.1` 已用保存的舊版安裝器實測通過；後續版本可執行 `scripts/test-installer.ps1 -PreviousInstallerPath <舊版安裝程式>` 延續驗證。目前本機安裝器是未簽章的開發建置；正式公開散發需由 release workflow 使用 Windows PFX 憑證完成簽章。

### Windows 正式發布

推送 `vMAJOR.MINOR.PATCH` tag 會觸發 `.github/workflows/release.yml`。發布工作會先確認 `pyproject.toml`、Python 套件、`Cargo.toml` 與 `tauri.conf.json` 的版本完全相同，再執行測試、建立 sidecar、匯入暫時的 Windows PFX 憑證、產生並驗證 Authenticode 簽章、跑安裝生命週期測試，最後建立附有安裝程式及 `SHA256SUMS.txt` 的 GitHub Release。正式發布不接受未簽章安裝器。

需在 GitHub repository 設定：

- Secret `WINDOWS_CERTIFICATE`：PFX 檔案的 Base64 內容。
- Secret `WINDOWS_CERTIFICATE_PASSWORD`：PFX 匯出密碼。
- Variable `WINDOWS_TIMESTAMP_URL`：憑證提供者的 RFC 3161 時間戳服務；未設定時使用 `http://timestamp.digicert.com`。

一般 push／pull request 仍只產生未簽章的 CI artifact，不會接觸正式憑證。Tauri 設定已禁止靜默降級；每次正式升版都應把上一版安裝器傳給 `scripts/test-installer.ps1 -PreviousInstallerPath` 驗證。

## 已知限制

- API 與渲染後 DOM 可能隨 FANBOX 更新而變動；解析失敗時會回報，不會猜測縮圖為原圖。
- 外部嵌入內容會保存 FANBOX 提供的連結卡片資料；第三方 iframe 不會直接嵌入閱讀頁，以避免執行不受信任的遠端內容。
- 登入、2FA 與 CAPTCHA 必須由使用者在專用瀏覽器視窗中親自完成；程式不會代填或規避。
- 同步採保守的循序模式，不保證能在內容下架前完成備份。
- FANBOX 未提供穩定公開 API，平台介面變更時可能需要更新 parser。

