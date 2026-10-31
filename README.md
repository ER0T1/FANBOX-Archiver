# FANBOX Archiver

**正式版本：v1.3.16（2026-10-31）**

FANBOX Archiver 是 Windows 11 優先、Python 3.12+ 的 pixivFANBOX 個人備份工具，提供 Windows 桌面程式、瀏覽器 GUI 與命令列介面。它只保存目前登入帳號有權瀏覽的投稿，不會繞過付費牆、CAPTCHA、反自動化機制或其他存取限制。

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
- 提供動態本機閱讀器與選用的完全離線靜態網站，可搜尋、篩選、排序並閱讀歷史版本、Creator Profile 與 Fan Card。
- 首頁、Post 與 Fan Card 共用「跟隨系統／深色／淺色」主題，支援跨頁與已開啟分頁同步。
- SHA-256、檔案大小及圖片格式／尺寸驗證。
- 嚴格 HTTPS 主機白名單、Windows 安全檔名及目錄穿越防護。
- 不將帳號密碼或 Cookie 寫入設定檔、資料庫或日誌。

## v1.3.16 更新重點

- 建立 Fan Card 權益正規化模型，明確區分目前可使用、無法使用、未提供、提供中但存取狀態未知及資料不足，不把缺欄位推測為可存取。
- 動態閱讀器、完全離線靜態頁與 `fancard.md` 統一使用結構化方案權益卡片；Discord 特典與未知權益都有安全的名稱、狀態與說明，不再顯示原始 JSON dump。
- 權益顯示只使用必要欄位，不回傳未知原始欄位、token 或 URL；FANBOX 回應沒有可驗證的安全重播連結時，不提供虛構的「開啟 Discord」操作。
- 新增 Discord 可用／不可用、缺欄位、未知權益、Reader/API、靜態輸出與 390px 窄螢幕回歸測試。

## v1.3.15 更新重點

- 設定頁把下載、同步與新工作預設整合為單一「備份」主卡，依工作數量、工作預設、內容保存、更新判定及網路失敗處理分區；Markdown 與日誌整理到獨立「輸出與紀錄」。
- 「單次最多下載投稿數」與「連續未變投稿停止掃描數」補上明確說明；前者只計 new／updated／retry，略過投稿不占下載配額。
- 歷史回補可依序掃描多個遠端頁面直到補滿下載上限或遇到可驗證停止條件；cursor 只會越過候選均已安全處理的頁面，取消、失敗與 dry-run 不會跳頁。
- 備份計畫新增要求上限、符合數、選取數、掃描頁數、回補前狀態與停止原因；工作摘要會說明少於上限是因遠端耗盡、回補完成、連續未變門檻或其餘投稿不需下載。
- 設定儲存失敗會保留使用者輸入並在操作區顯示 API 錯誤；fieldset 與子區塊恢復一致間距，390px 維持單欄且無水平溢位。

## v1.3.14 更新重點

- 新增完全合成、去識別化的大型封存效能基準，預設建立 20 位創作者與 1,000 篇投稿，不會連線 FANBOX 或使用真實帳號資料。
- 分段量測封存寫入、磁碟讀取、JSON 解析、純 SQLite、含 JSON 摘要補值的 Reader、動態 API、靜態索引首次／重用與瀏覽器首屏，並輸出機器可讀的 `benchmark.json`。
- 基準同步輸出文章列表、創作者篩選與搜尋的 SQLite `EXPLAIN QUERY PLAN`，讓索引或快取調整以實測結果為依據。
- 1,000 篇實測定位首頁列表排序為可改善路徑，因此加入發布時間索引並改用索引支援的版本統計子查詢；萬用字元搜尋維持原行為，不在缺乏大型資料證據時導入全文索引。

開發者可在專案根目錄執行：

```powershell
python scripts/benchmark_archive.py --root .tmp/benchmark-archive --reset --browser chrome
```

輸出目錄已由 Git 忽略；若不需瀏覽器首屏量測，可改用 `--browser none`。既有非空目錄預設不會覆寫，只有明確加入 `--reset` 才會重建指定的基準目錄。

## v1.3.13 更新重點

- 稽核完整 Python、Web 與桌面 E2E 測試層級；保留備份、SQLite、安全、CLI、版本與閱讀流程等關鍵防線，不因執行時間移除必要 E2E。
- 合併舊設定預設值與非強制改寫的重複案例，Python 測試由 116 項精簡為 115 項，覆蓋行為不變。
- 將 FANBOX 新舊支援方案回應改為具名參數化測試，並抽出 CLI 與 BackupUseCase 共用 fixture，減少重複設定與認證樣板。

## v1.3.12 更新重點

- 備份頁右上角「工作歷史」改為與歷史頁「建立新工作」完全相同的橘色實心主要按鈕樣式。

## v1.3.11 更新重點

- 重新設計備份頁右上角「工作歷史」為符合深色／淺色主題的膠囊式次要操作，補齊 hover 與鍵盤焦點狀態。
- Creator 搜尋下拉選單現在會在點擊元件外空白處時關閉，並同步更新 `aria-expanded`；再次點擊搜尋框仍可正常開啟。

## v1.3.10 更新重點

- 備份頁預設顯示新工作表單；執行中工作仍優先顯示進度，完成後保留結果。工作歷史改為頁首按鈕開啟的獨立列表，不再自動開啟上一筆工作或內嵌於表單。
- 創作者範圍改為可依名稱／Creator ID 搜尋的鍵盤可操作多選清單；空清單代表全部支援中的創作者，工作摘要與歷史可區分全部、單一與多位創作者。
- 完整備份表單新增 Profile／Fan Card 選項，並從新的 `backup_defaults` 設定載入預覽與拉取預設值；投稿上限改用 `sync.max_posts_per_run`，單次覆寫不會回寫全域設定。
- GUI 工作會保存多創作者、預覽、投稿上限與 Profile／Fan Card 選項，重試完整沿用原值；舊版單一 `creator` 工作仍可還原與重試。

## v1.3.9 更新重點

- 新增完全合成、去識別化的 FANBOX 合約 fixture，覆蓋 Creator Profile、`article`、`image`、`file`、`text`、內嵌投稿與 Fan Card，並文件化安全更新流程。
- 結構化解析器在媒體對應資料或原始下載 URL 缺漏時會保留可理解警告與原始區塊，不再讓單一非必要欄位中斷整篇投稿；只有縮圖／預覽 URL 時明確拒絕推測成原圖。
- 投稿與 Profile 解析警告會經 CLI／GUI 共用的備份事件呈現，並隨封存 JSON 保存，方便辨識 FANBOX 介面變動；影片格式仍等待合法、去識別化的真實 fixture，不預先猜測。

## v1.3.8 更新重點

- `backup` 成為 CLI 唯一下載入口，支援重複指定多個 `--creator` 或 `--post`，並接受 Creator／Post ID、標準 FANBOX 網址與 Creator 子網域網址。
- `--creator` 與 `--post` 明確互斥；`--profile`、`--fancard` 只可搭配 Creator 使用。指定 Post、Creator、GUI 與完整支援中備份都共用 `BackupUseCase`。
- 移除沒有獨立責任的 `download` 與 `sync` 指令；`--dry-run` 不再寫入備份執行紀錄、創作者同步狀態或封存內容。

## v1.3.7 更新重點

- 完全離線靜態網站新增 Creator Profile 歷史版本與最新版本閱讀頁，並從創作者列表直接進入；索引仍只公開閱讀所需中繼資料，不納入原始私密欄位。
- 靜態文章閱讀頁新增上一篇／下一篇與篇數位置導覽，創作者與 Fan Card 清單補齊搜尋及穩定排序，維持封存搬移後可直接閱讀。
- 動態閱讀器、桌面啟動頁與靜態網站改用共用設計 token，統一明暗色彩、狀態色、圓角與陰影；備份、維護與設定等需本機服務的操作仍只保留在動態介面。

## v1.3.6 更新重點

- 代理開發規則明定專案測試與正式驗證預設在非沙箱環境執行，避免把程序、瀏覽器或 Windows 暫存目錄限制誤判為產品失敗。
- pytest 驗證需使用儲存庫內、已忽略追蹤且工作專用的 `--basetemp` 目錄；無法取得非沙箱權限時必須標示為未執行。

## v1.3.5 更新重點

- 修正動態網頁備份執行期間每次輪詢都先清空頁面，造成畫面閃爍與視窗捲動位置跳回頂端的回歸問題。
- 背景工作輪詢改為保留既有畫面，再以原地更新方式刷新備份進度；維護與設定頁的輪詢也不再插入載入佔位畫面。
- GUI E2E 新增備份輪詢期間維持視窗捲動位置、且不顯示載入佔位內容的回歸驗證。

## v1.3.4 更新重點

- 備份、封存驗證與設定頁改為共用全域工作狀態；任一工作執行時，其他互斥操作會停用並顯示目前工作。
- 工作完成、失敗或取消後，相關控制項會透過頁面輪詢自動解鎖；後端既有單工作鎖與 `409` 防線維持不變。
- GUI E2E 新增跨頁互斥與自動恢復驗證，避免維護或設定頁在備份期間誤導使用者可執行衝突操作。

## v1.3.3 更新重點

- 開發目標、規劃、任務狀態、決策與開發紀錄改以 Anytype 的 FANBOX Archiver 專案空間為主，儲存庫則繼續作為程式、測試、版本與使用說明的事實來源。
- 代理開發流程新增開工前讀取 Anytype、完工後回寫版本／commit／驗證證據／風險／後續工作，以及讀回確認與避免重複物件的要求。
- 補充 Anytype 與儲存庫衝突、連線或權限失敗、純檢查工作、敏感資訊及內部規劃不得重複維護等處理規則。

## v1.3.2 更新重點

- 將已完成、重疊或狀態過時的五份開發規劃整合為唯一的 [後續開發規劃](規劃與想法/開發規劃.md)。
- 新規劃以 v1.3.1 完成狀態為基線，重新排列正式簽章、GUI 工作一致性、影片投稿、FANBOX 回歸防護、效能量測及桌面操作的優先順序與驗收標準。
- 保留獨立的 Anytype 知識管理參考文件；版本歷史繼續由 README 保存，避免多份規劃互相矛盾。

## v1.3.1 更新重點

- 安裝生命週期測試新增主程式 `ProductVersion` 斷言，確保覆蓋升級不只是檔案存在，而是真的換成目標版本。
- 使用保存的舊版 NSIS 安裝器實測 `1.2.0 → 1.3.0` 及 `1.3.0 → 1.3.1`，確認版本更新、解除安裝、登錄清理及外部封存資料保留。
- 新增儲存庫層級 `AGENTS.md`，要求所有後續程式更新同步 README、增加 PATCH 版本、執行驗證並建立本機 Git commit；未經明確要求不得推送。

## v1.3.0 更新重點

- 新增 Tauri 2 Windows 桌面程式，啟動時自動選擇空閒的 loopback 連接埠、啟動 PyInstaller Python sidecar，並在視窗關閉時停止完整程序樹。
- 新增首次啟動封存設定，可選擇既有 `config.yaml`、匯入包含 `backup.db` 的 FANBOX 封存資料夾，或建立新的預設封存；選擇結果會保存在本機並於後續啟動沿用。
- 新增「封存 → 變更封存位置」與啟動失敗復原流程；切換資料來源只清除桌面選擇狀態，不會刪除設定檔、資料庫或投稿。
- 瀏覽器 GUI 完整拆分為型別化 TypeScript 模組，涵蓋 API client、投稿、創作者、設定、工作佇列、導覽與桌面啟動頁，正式頁面只載入單一編譯後的 `core.js`。
- 新增隔離的 localhost GUI E2E 測試，涵蓋投稿導覽、搜尋、分頁、置頂排序、Creator Profile、Fan Card、設定保存、封存驗證與工作輪詢。
- 新增 sidecar 健康檢查、Rust 測試、NSIS 安裝／覆蓋升級／解除安裝生命週期測試，以及外部封存資料保留驗證。
- 新增 Windows CI 與正式發布工作流程；一般 push 產生未簽章測試 artifact，`vMAJOR.MINOR.PATCH` tag 則驗證版本、簽章安裝器並建立附有 SHA-256 校驗檔的 GitHub Release。
- 新增跨 Python、Rust 與 Tauri 設定的版本一致性檢查，並禁止安裝器靜默降級。
- 保留原有 `fanbox-archiver` CLI、`serve` 指令與靜態網站匯出流程，既有使用方式不受影響。

## v1.2.0 更新重點

- 新增只監聽 `127.0.0.1` 的動態本機閱讀器；直接讀取 SQLite 與封存 JSON，備份後重新整理即可看到新內容，不必重建索引。
- 新增投稿、Creator Profile 與 Fan Card 的動態閱讀頁，支援歷史版本切換、搜尋、篩選、排序與臺北時區顯示。
- 新增網頁備份控制台、持久化工作佇列與結構化事件紀錄；可執行 dry-run、正式備份、完整性驗證、安全停止及明確重試。
- CLI 與網頁介面共用備份應用層，並以單一工作佇列避免同時修改封存；中斷中的工作會在重新啟動後標記為 `interrupted`，不會擅自續傳。
- 新增 Creator Profile 封存、版本紀錄與空資料提示；沒有文字或圖片時會顯示明確空狀態。
- 投稿閱讀頁新增頂部與底部的上一篇／下一篇導覽，並支援鍵盤左右方向鍵。
- 支援辨識、回填、排序及標示 Creator 置頂投稿；Creator 投稿列表改為每 50 篇分頁。
- 修正 Profile 版本選單排列方向、備份歷史篩選重設、詳細紀錄捲動位置跳動等操作問題。
- 投稿 Cover 與內嵌預覽圖改為完整顯示，避免裁切文字或內容；內嵌投稿贊助檔位統一為膠囊樣式。
- 備份控制板取消固定最大寬度，會依頁面容器自適應延展。
- 瀏覽器 GUI（包含啟動、導覽、搜尋、鍵盤操作與工作輪詢）已完整搬至 TypeScript，頁面只載入單一 `core.js`；編譯產物會隨 Python wheel 發布，一般使用者不需安裝 Node.js。
- 保留 `index`／`open` 靜態匯出流程，供搬移封存或不啟動伺服器的環境使用。

## v1.1.2 更新重點

- 支援 `https://<creator-id>.fanbox.cc/posts/<post-id>` 形式的 FANBOX 官方創作者子網域投稿網址。
- 修正投稿頁重新導向創作者子網域後，背景 API 請求可能因 CORS 發生 `Failed to fetch` 的問題。
- 背景 API 請求固定從 `www.fanbox.cc` 的標準來源發出，同時保留登入工作階段。
- 為背景瀏覽器 API 請求加入 60 秒逾時，避免網路異常時無限等待。
- 維持嚴格的資源下載白名單；允許投稿頁子網域不會擴大可下載檔案的來源範圍。

## v1.1.1 更新重點

- 統一首頁、文章與 Fan Card 頁面的日期時間格式為 `yyyy年MM月dd日 HH:mm`。
- 所有日期時間固定換算為 UTC+8 臺北時間，畫面不顯示 `UTC+8`、`+08:00` 或其他時區尾碼。
- 修正 Fan Card「支援開始」直接顯示 FANBOX 原始 ISO 時間的問題。
- 首頁建置時間、文章列表時間及年份篩選改用相同的臺北時區規則。

## v1.1.0 更新重點

- 還原 FANBOX Post 的外部連結卡片，保留標題、摘要、創作者、贊助檔位及可用的預覽圖。
- 內嵌 FANBOX Post 若已有完整本機備份，會自動連到本機 `latest.html`；否則連至 FANBOX 原文。
- Fan Card 支援沒有卡面的正常狀態，並將閱讀頁區塊名稱統一為「方案資訊」。
- 首頁、文章與 Fan Card 閱讀頁加入共用三態主題；預設跟隨 Windows，並支援 `file://` 換頁保持與跨分頁同步。
- 強化靜態閱讀頁的安全輸出、相對連結與索引完整性檢查。

## v1.0.0 重點

- 一鍵增量備份全部支援中創作者，或只處理指定 Creator。
- 專用 Chrome 設定檔登入，不需把 Cookie 寫入設定檔。
- Post 完整版本保存、失敗接續下載、歷史回補與安全重試。
- Creator 頭像、Post cover、粗體文字、贊助檔位與 Fan Card 完整封存。
- 本機靜態閱讀索引，支援深色模式、Creator／狀態／年份篩選及全文中繼資料搜尋。
- 全程保守單佇列與請求間隔；不繞過權限、付費牆或反自動化限制。

## 安裝

先安裝 [Python 3.12 或更新版本](https://www.python.org/downloads/)，然後在 PowerShell 執行：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[test]"
Copy-Item config.example.yaml config.yaml
```

如 PowerShell 禁止執行啟用腳本，也可直接使用 `.\.venv\Scripts\fanbox-archiver.exe`。

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
fanbox-archiver verify
fanbox-archiver retry
fanbox-archiver status
fanbox-archiver versions 123456
```

`backup` 是唯一下載入口；不帶 selector 時會輪替處理支援中創作者、保存 Profile 與 Fan Card，並持續保存歷史回補游標。指定 `--creator` 時預設備份投稿，可用 `--profile`、`--fancard` 加入對應資料；指定 `--post` 時只處理明列投稿。`--creator` 與 `--post` 互斥。已完成且未更新的投稿不占 `sync.max_posts_per_run` 額度。`--dry-run` 只查詢並顯示計畫，不寫入封存內容、同步狀態或執行紀錄。

舊指令遷移：`download <post>` 改用 `backup --post <post>`；`sync --creator <creator>` 改用 `backup --creator <creator>`；`sync --supporting` 改用不帶 selector 的 `backup`。

互動終端會顯示目前投稿、資源名稱與下載大小；非互動環境不輸出動畫。執行日誌位於 `FANBOX/logs/` 並按日輪替，Cookie、Authorization 與常見查詢憑證會先遮蔽。`status` 會另外顯示最近一次執行、失敗投稿及尚未完成歷史回補的創作者。

目前下載仍刻意維持單一佇列，`download.max_concurrent` 只接受 `1`，避免意外提高 FANBOX 請求頻率。

### 動態本機閱讀器

直接啟動本機閱讀伺服器：

```powershell
fanbox-archiver serve
```

伺服器只監聽 `127.0.0.1`，預設開啟 `http://127.0.0.1:8765/`。投稿、歷史版本、創作者與粉絲卡會在瀏覽時直接查詢 SQLite 並讀取對應 JSON，因此下載完成後不必執行 `index`。投稿首頁會顯示封面與贊助檔位；每位創作者有獨立的個人資料、投稿與粉絲卡分頁。文章頂端與底部提供上一篇／下一篇，也可使用鍵盤左右方向鍵；創作者投稿每 50 篇分頁，並優先顯示 FANBOX 置頂投稿。網頁中的「備份」頁可先執行 dry-run、開始正式備份、查看固定計畫摘要、目前資源進度與可摺疊的詳細紀錄，或要求安全停止；「維護」頁可執行持久化封存完整性驗證；「設定」頁可安全修改一般下載、同步、Markdown 與日誌選項。備份與驗證共用單一工作佇列，避免同時修改封存。按 `Ctrl+C` 可停止伺服器；若不想自動開啟瀏覽器，可加上 `--no-open`。

每次啟動伺服器都會產生新的本機工作階段權杖，所有啟動／取消／重試工作請求都必須帶有該權杖；首頁與 API 禁止快取，並維持 Trusted Host、CSP 與僅監聽 loopback 的限制。工作請求、摘要及結構化事件會保存到 SQLite；伺服器重新啟動後仍可篩選與查看最近工作。若上次程序在 queued、running 或 cancelling 狀態中結束，重新啟動時會標記為 `interrupted`，但不會未經確認自動重新下載；使用者可在 GUI 明確選擇以相同設定建立一個新的重試工作。高頻資源進度採合併與節流寫入，工作列表 API 只傳摘要，選取工作後才載入完整事件，避免輪詢歷史工作時反覆傳輸大量紀錄。

### 選用的靜態網站匯出

需要搬移封存、在不啟動伺服器的環境閱讀，或產生完全靜態快照時，仍可手動建立索引：

```powershell
fanbox-archiver index
fanbox-archiver index --check
fanbox-archiver open
```

`index` 會在 `FANBOX/_site/` 增量產生唯讀閱讀頁，並建立穩定入口 `FANBOX/index.html`。`--force` 可完整重建衍生網站；原始 Post、Fan Card、資料庫與日誌不會被索引指令改寫。

也可直接定位特定內容：

```powershell
fanbox-archiver open --post 12810903
fanbox-archiver open --post 12810903 --version 1
fanbox-archiver open --creator comodox
fanbox-archiver open --fancard comodox --month 2026-10
fanbox-archiver open --folder --post 12810903
```

需要捨棄舊格式 Post 並重新完整備份時，可明確執行：

```powershell
fanbox-archiver clear-posts
```

此指令會永久刪除 Post、歷史版本與 Post 資源，並重設歷史回補游標；Creator、Fan Card、登入設定檔與程式日誌會保留。執行前會要求確認，非互動環境必須加上 `--yes`。

首頁索引只包含標題、日期、標籤與狀態等必要中繼資料。正文及 Fan Card 方案資訊只寫入各自的閱讀頁；Cookie、交易 ID、supporter ID 與付款方式不會進入索引。網站資源全部隨程式提供，不使用 CDN、分析服務或遠端字型。

所有指令皆可用 `--help` 查看參數：

```powershell
fanbox-archiver --help
fanbox-archiver backup --help
```

## 輸出格式

```text
FANBOX/
├── index.html
├── _site/
│   ├── assets/
│   ├── posts/
│   └── fancards/
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

首次啟動會顯示桌面設定頁，可選擇既有 `config.yaml`、直接匯入包含 `backup.db` 的 FANBOX 封存資料夾，或在應用程式資料目錄建立全新封存。選擇結果會保存在本機 `desktop-state.json`，後續啟動會直接沿用；匯入資料夾只會建立相容的設定檔，不會搬移或改寫原有投稿。需要切換資料來源時，可使用桌面程式的「封存 → 變更封存位置」回到選擇頁；這只會清除目前選擇，不會刪除設定檔、資料庫或投稿。若 sidecar 因設定檔已移動、內容無效或磁碟無法存取而啟動失敗，錯誤頁也會提供「重新選擇封存」按鈕。若先設定 `FANBOX_ARCHIVER_CONFIG`，桌面程式仍會優先使用該路徑，方便開發與自動化測試。

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
- 外部嵌入內容會保存 FANBOX 提供的連結卡片資料；第三方 iframe 不會直接寫入離線頁，以避免執行不受信任的遠端內容。
- 登入、2FA 與 CAPTCHA 必須由使用者在專用瀏覽器視窗中親自完成；程式不會代填或規避。
- 同步採保守的循序模式，不保證能在內容下架前完成備份。
- FANBOX 未提供穩定公開 API，平台介面變更時可能需要更新 parser。

