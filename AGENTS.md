# FANBOX Archiver 代理開發規則

本檔案適用於整個儲存庫。每次代理開始修改前，都必須先閱讀並遵守以下規則。

## 版本、文件與 Git

- 只要本次工作實際修改任何需要納入 Git 的內容，就必須在同一次工作中：
  1. 將更新內容寫入 `README.md`，包含對應版本的更新重點或相關使用說明。
  2. 將語意化版本的修訂號（PATCH／Z）增加 1；不得自行增加 MAJOR 或 MINOR。
  3. 同步更新 `pyproject.toml`、`src/fanbox_archiver/__init__.py`、`src-tauri/Cargo.toml`、`src-tauri/Cargo.lock` 與 `src-tauri/tauri.conf.json` 的專案版本。
  4. 執行與變更範圍相稱的測試及 `npm run release:check`。
  5. 檢查 diff 後建立本機 Git commit，避免留下未提交的重要變更。
- 若本次只有檢查、說明或沒有檔案變更，不建立空版本，也不建立空 commit。
- commit 訊息優先使用 `Release vX.Y.Z`；若同一版本有特殊維護需求，訊息仍須清楚描述內容。
- 除非使用者當次明確要求，禁止推送 GitHub、建立 tag 或發布 Release。
- 提交前必須保留使用者既有變更，不得以 reset、checkout 或其他方式覆蓋不屬於本次工作的內容。
- 建置產物、測試暫存目錄、憑證與秘密不得提交。

## 驗證

- Windows 桌面版本需保持 Python、Rust 與 Tauri 版本一致。
- 安裝器相關變更需盡可能驗證安裝、升級、解除安裝及外部封存資料保留。
- 正式發布不得接受未簽章安裝器；一般本機與 CI 開發 artifact 可維持未簽章，但必須明確標示。
