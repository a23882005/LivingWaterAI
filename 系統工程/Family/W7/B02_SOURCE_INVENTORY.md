# W7-B02 共用來源與計算器核實進度

2026-10-22；Family總PM本人，sequential。狀態 IN_PROGRESS，未簽PASS。

已從Drive實體資料夾定位共用SQLite，下載831488 bytes，schema user_version=1，quick_check=ok。既有遷移紀錄 F2-W1-WORK1-B-XLSX-TO-SHARED-DB-v1 為PASS，來源SHA與現行正式XLSX一致。四業務表列數11/57/137/201，欄數44/10/13/13；規則表57列中38個W2 canonical rules，與封案摘要38條不衝突。

XLSX下載58469 bytes，SHA256 f639f5b46b7ff0c7ab2884a0ce01739d852c94f8e383f1966463d48178a77b02；GitHub xlsx_minimal_reader 實際讀取四表成功、公式0。未重算WORK12或覆寫任何DB。

程式定位：C正式Runtime/work2/benchmark_reader.py 是讀取與品質閘門；work2/xlsx_minimal_reader.py 僅讀儲存值。work3/engine.py 的 evaluate_performance_risk 為績效風險投影入口，單一有效資產可傳遞合格基準，多資產不可用摘要加權冒充歷史CAGR/MDD；規劃投影須同幣別且有可追溯假設。Family/W6/runtime/performance_reference.py 的 weighted_reference 僅為歷史加權參考，並非投組CAGR或情境分數。

尚待核實：WORK12既有歷史含息/回撤計算成果的實體位置、現行共用DB與XLSX reader的正式切換接線。既有WORK12 40/40 PASS/CLOSED完整沿用；定位缺口不撤銷該結案，也不自行重建資料或填補UNKNOWN。

B01補正：名稱搜尋漏列系統工程/資料庫中的四個較早同名家人DB（各16384 bytes，僅metadata已讀）。先前『未找到既存獨立庫』只描述搜尋結果，不能推導不存在。現用映射仍指向B01從已驗收W5原bytes建立的四庫；舊庫未刪改，角色待補正，不以名稱自動選庫。B01原四庫校驗證據保持，不宣稱舊庫內容已核實。

DB/file ID/schema/來源指紋及舊庫映射的私有登錄僅Drive：Family_W7_B02_來源核實登錄.json，ID14oaZUx8eduNzeOcjzrAm8sNksjwleGb_。DB不進GitHub或工程ZIP。

Production HOLD、交易NONE、W4取消、RM17凍結。正式W7驗收0/29；下一步本人續B02後再B03。
