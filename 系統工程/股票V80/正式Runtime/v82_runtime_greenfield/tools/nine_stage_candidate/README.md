# 九階隔離比較工具

本工具依 `FAMILY-V82-UNIFIED-20261103-r2` 施工，預設關閉。正式金融入口、核准 v1.0 profile、49+13 欄、日率、C7B、資金授權及原始守門均沿用原程式。工具不註冊正式 profile、不寫 DB／帳本、不建立券商意圖。

## 五個 profile

|ID|政策差異|
|---|---|
|BASELINE_V03|重用 PM v0.3 的 M、獨立 R、九階 eligibility 與事件；成功事件第 11 根仍到期|
|PARTIAL_VIEW_ONLY|與基線的 Stage／Mode／Target／Gap／金額一致，提供局部已知與依賴視圖|
|CONFIRMED_UNTIL_ORIGINAL_FAILURE|僅已確認事件免於時間到期；仍先檢原失敗線及缺 bar|
|LOW_PLATEAU_EXACT_EQUAL|strict low 加入因果且完全等 Low 平台，僅供 OffLow／R1；完整無形態與缺資料分開|
|COMBINED_CONFIRMED_AND_PLATEAU|組合上述兩項政策差異|

續存提案的代價：價格漲高後回落，只要沒有觸及原固定 P／A 失敗線，仍可保留技術確認；沒有另加移動停損或買進許可。

`pm_reference/` 保留 PM 原演算法，僅調整為相對 import。原件、套件檔 SHA 及工單 SHA 見 `PM_SOURCE_LOCK.json`；numeric 僅移除 PM 原件的一個尾端空白行，與現行核准 numeric 位元相同。原 PM 研究包 113 項 manifest 已核對；舊研究的歷史統計不代表完整策略績效。

## 使用

在上層 `tools/` 目錄執行：

```sh
python -m nine_stage_candidate.replay
python -m nine_stage_candidate.replay --enable-research --input /private/input.json --output /private/baseline.json --profile BASELINE_V03 --compact-daily
```

第一行只回 `DISABLED`。第二行需明示啟用，輸出檔必須不存在。輸入含 `rows`、同長度 `inputs`、`source`；數字使用 Decimal 字串，旗標僅 bool／None 或明示 TRUE／FALSE／UNKNOWN。

`source` 必須具 instrument、listing、currency、price_basis、calendar、vintage 與 data_provenance。真實來源另需 available_at、decision_cutoff，每根 session_close_at；未完成或尚未可得資料不能進入該次決策。幣別／上市地／basis／vintage 切換、明示分段或缺 bar 會重置數值窗口與事件。

`inputs` 的 qP、qV、depth、a_normal、valuation_legal、up、fundamental 應由既有正式 producer 提供。沒有合法 qV 就保留 UNKNOWN；合成測試中的價格衍生 qV 明示 SYNTHETIC，只用於邊界測試。當期發行人 P/E、P/B 可保留日期作參考，不能推定 Forward PE 或自身歷史 qV。`source_view.py` 沿輸入原契約有效期顯示參考資料，不創造共用 TTL。

## 輸出與承接

每根保留 OHLC 對應的 primitive、M8／R10 具名槽位、去重 ID、三值、事件 state、條件證明及最少缺項。`condition_results` 的底二 TRUE 不代表已選定底二；Up UNKNOWN 時 `final_mode/final_stage` 仍待判。FALSE AND UNKNOWN 的未知不列為該條件缺項。

`financial_result` 分列 Target／Projected／Gap／Permission／slice／final_amount 及依賴。候選目標只作隔離比較；未知 Stage 不會被底部局部條件替代，缺現金不會抹掉市場資訊。原 daily slice／共享 MIN／fees／lot／資金守恆與單一 writer 仍由正式金融鏈裁決，工具不初始化 cycle；退階與負 Gap 不產生賣單。

`--compact-daily` 保存每日數字、條件、具名 M/R、依賴、原因及事件，省去重複的巢狀證明樹；最後一根仍包含完整 lineage。完整明細可由同一輸入、profile ID／規則 digest 重播。五組日輸出的決策差異只按事件狀態及低點政策歸因，不把額外診斷欄位誤算為策略差異。

PR60 接收端保持由原報表施工線處理；本 sidecar 是候選研究資料，不能標作正式客戶金融結果。

## 驗證

```sh
python -m pytest tools/nine_stage_candidate/tests -q
```

同套合成案例亦由 Family W8 測試入口收集，沿既有 PR59 CI 執行。案例涵蓋 PM 逐欄差異、M／R 分工、精確邊界、第 10／11 根、失敗優先、三值短路、平底確認、不同未來前綴、分段、未知 Up、退階、現金獨立及預設關閉。
