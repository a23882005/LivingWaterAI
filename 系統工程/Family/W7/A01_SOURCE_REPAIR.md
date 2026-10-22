# W7-A01｜來源故障修復與接任核對

日期：2026-10-22，責任：Family中PM本人。契約v1.5.10；H2校驗62檔、3內ZIP、37施工列、83原WBS均PASS。

基準main：e90855a805459dca63210fecbfdf3334ccacc672。PR22、23、24已從GitHub核對merged。

## 原失敗與修補
09h run39706423028/job119587409400：BAMLH0A0HYM2、WALCL的FRED官方API回應JSONDecodeError，FRED CSV回應ParserError。m14於WALCL失敗後停止，原日誌不能推論另兩成分也失敗。11h run39716589459/job119620041321保留ready=false、20/22，含m06_rate日期問題。

HTTP成功回應被既有HTTP快取保存，即使後續內容解析失敗也沒有移除；FRED單一provider沒有內容異常重試。此次對HTTP200但解析或schema失敗的FRED來源清除該回應快取並最多重試一次，沿用節流、總期限與正常HTTP錯誤處理。正常來源不增加請求；429不因本修補增加解析重試。

Fetcher新增fredattempts，記每次成功/失敗、實際核實時間、HTTP狀態、content-type及body SHA256；不保存body或API key。原回應body未封存，無法從舊解析錯誤確定是HTML、截斷或其他供應商異常；不將猜測寫為根因。快取替代後的完整JSON/CSV診斷持久化依A06接續。

## 真實重跑及測試
修改前後各一次從正式FRED CSV取得：m02=3.33%，觀測2026-10-20；WALCL/WDTGAL最後共同週三2026-10-14、RRP最後2026-10-21。m14維持2026-07-15至2026-10-14的13週差，結果-77.286 USD bn。原公式及期限未改。這是本機來源重跑，非修補後Actions或線上發布證據。

5項新增測試PASS：異常200後成功、持續異常最多兩次、429不解析重試、API失敗轉CSV並保留診斷/遮蔽key、正常來源僅一次請求。既有D009狀態與告警9項PASS，爬蟲self-test PASS。證據見evidence/A01/。

## 隔離與接續
修補分支w7/macro-repair-20261022；main及正式資料保持既有版本。發現09h工作流push未限制分支，為落實A01～A12隔離要求，增加main條件，避免推送修補分支寫入共用automation-state；A08仍須完成後續正式接線，A13才整套切換。

A01來源重現/修補/本機驗證完成；雙端讀回依Checkpoint登記。正式W7工項仍0/29；下一項由本人做A02。Production HOLD、交易NONE、W4取消、RM17凍結；BR CLOSED沿用。
