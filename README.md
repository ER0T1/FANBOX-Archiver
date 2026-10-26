# FANBOX Archiver

**正式版本：v1.1.2（2026-10-27）**

FANBOX Archiver 是 Windows 11 優先、Python 3.12+ 的命令列個人備份工具。它只保存目前登入帳號有權瀏覽的 pixivFANBOX 投稿，不會繞過付費牆、CAPTCHA、反自動化機制或其他存取限制。

> pixivFANBOX 的介面並非穩定的公開 API，平台規範也可能限制自動化蒐集。請只在你有權備份且符合現行服務條款的範圍使用。本工具預設單一下載佇列、每次請求至少間隔 3 秒，遇到 401、403 或 429 會停止或回報，而非規避限制。

## 功能

- 解析 `article`、`image`、`file`、`text` 等結構化投稿，另提供渲染後 HTML 備援解析。
- 保留文字、粗體、原圖、cover、附件、外部連結卡片與原始順序，輸出 UTF-8 `post.md` 與完整 `post.json`。
- 原始圖片及任意附件串流下載；使用 `.part` 暫存檔及 HTTP Range 續傳。
- 保存創作者頭像、文章贊助檔位與台灣時區發布／更新時間。
- 自動保存支援中創作者的每月 Fan Card、可用卡面與方案資訊；正確處理未提供卡面的月份。
- SQLite 記錄投稿、版本、資源及執行狀態，以內容指紋避免重複下載。
- 產生完全離線的本機閱讀網站，可搜尋、篩選、排序並閱讀歷史版本與 Fan Card。
- 首頁、Post 與 Fan Card 共用「跟隨系統／深色／淺色」主題，支援跨頁與已開啟分頁同步。
- SHA-256、檔案大小及圖片格式／尺寸驗證。
- 嚴格 HTTPS 主機白名單、Windows 安全檔名及目錄穿越防護。
- 不將帳號密碼或 Cookie 寫入設定檔、資料庫或日誌。

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

登入成功後，`auth`、`download`、`sync` 和 `retry` 會自動沿用 `.fanbox-browser/` 中的工作階段：

```powershell
fanbox-archiver auth check
fanbox-archiver download "https://www.fanbox.cc/@creator/posts/123456"
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

# 5. 建立並開啟離線閱讀索引
fanbox-archiver index
fanbox-archiver open
```

日後只需重複執行 `backup` 與 `index`；已完成且內容未變的 Post 不會重複下載。

### 常用指令

先以離線 HTML 驗證解析結果（預設不下載遠端資源）：

```powershell
fanbox-archiver import-html ".\範例1.html" --metadata-only
```

下載單篇目前有權存取的投稿：

```powershell
fanbox-archiver download "https://www.fanbox.cc/@creator/posts/123456"
```

有限範圍同步、預覽及本機驗證：

```powershell
fanbox-archiver backup --dry-run
fanbox-archiver backup
fanbox-archiver backup --creator "https://www.fanbox.cc/@creator-id"
fanbox-archiver creators --refresh
fanbox-archiver creators --json
fanbox-archiver sync --creator creator-id --dry-run
fanbox-archiver sync --creator creator-id
fanbox-archiver creators
fanbox-archiver verify
fanbox-archiver retry
fanbox-archiver status
fanbox-archiver versions 123456
```

`backup` 是日常使用入口；它會輪替處理支援中創作者、持續保存歷史回補游標，且已完成未更新的投稿不占 `sync.max_posts_per_run` 額度。`sync --creator` 與 `sync --supporting` 保留為相容指令。先執行 `--dry-run` 並確認使用範圍符合平台規範。

互動終端會顯示目前投稿、資源名稱與下載大小；非互動環境不輸出動畫。執行日誌位於 `FANBOX/logs/` 並按日輪替，Cookie、Authorization 與常見查詢憑證會先遮蔽。`status` 會另外顯示最近一次執行、失敗投稿及尚未完成歷史回補的創作者。

目前下載仍刻意維持單一佇列，`download.max_concurrent` 只接受 `1`，避免意外提高 FANBOX 請求頻率。

### 本機閱讀索引

備份完成後建立索引，便可在不啟動伺服器、也不連線至外站的情況下閱讀：

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
fanbox-archiver download --help
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
```

測試包含規劃書提供的 HTML：應辨識 `範例1.html` 的 9 張正文原圖，且不把 `/w/1200/` 預覽圖當作原圖。

## 已知限制

- API 與渲染後 DOM 可能隨 FANBOX 更新而變動；解析失敗時會回報，不會猜測縮圖為原圖。
- 外部嵌入內容會保存 FANBOX 提供的連結卡片資料；第三方 iframe 不會直接寫入離線頁，以避免執行不受信任的遠端內容。
- 登入、2FA 與 CAPTCHA 必須由使用者在專用瀏覽器視窗中親自完成；程式不會代填或規避。
- 同步採保守的循序模式，不保證能在內容下架前完成備份。
- FANBOX 未提供穩定公開 API，平台介面變更時可能需要更新 parser。

