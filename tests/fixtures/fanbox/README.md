# FANBOX 合約 fixture

本目錄只保存人工合成、去識別化且可公開檢查的 FANBOX 回應片段，用來偵測解析介面變動；不得直接提交從瀏覽器、日誌或真實帳號匯出的內容。

更新流程：

1. 只擷取重現解析問題所需的最小欄位，不保存 HTTP headers、Cookie、token 或完整回應。
2. 將 Creator、Post、Plan、User、Transaction 等識別碼與名稱改成固定假值，移除私人文字、交易識別碼及不必要的時間資料。
3. 媒體網址只使用本目錄既有的保留測試網域；若只觀察到縮圖或預覽網址，fixture 應明確使用 `thumbnailUrl`／`previewUrl`，不得改寫成 `originalUrl`。
4. 先執行 `pytest tests/test_fanbox_contract.py`，再執行完整測試與 `npm run release:check`。
5. 未取得合法、去識別化的 video fixture 前，不新增猜測欄位或媒體網址。

`fancard.json` 的月份與金額為合成值，不包含付款工具、支持者資料或真實交易 ID。
