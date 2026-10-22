# W7-A07／A08 隔離施工紀錄（2026-10-22）
責任：Family總PM本人，sequential。正式W7驗收仍0/29。

A07：每次合法報告先原子保存macro18_latest_diagnostics.json（完整報告、canonical SHA256、記錄時間），再以觀測值／日期及LEI觀測指紋決定歷史三份輪替。同值的新核實時間與失敗診斷因此可追溯。記錄時間不代表成功核實。讀取驗證schema、報告及digest，告警另核對同一批報告。復原保留原日期及last_verified_at，標STALE／HISTORICAL_BACKUP，不刷新核實。USABLE快取的FAILED取得亦計入告警，原status及首／三／持續／核心規則保留。

期限逐項盤點（不放寬既有門檻）：
- crawler：m04/m15/m18/m19/m20 65日；m16 90日，2026-08-01觀測於2026-10-22之後逾既有發布截止；m05成功即時來源不以月首年齡拒絕，但未來日期拒絕、取得失敗仍STALE；其他12日。config原max_age_days：月項65、m16 90、其餘12，未改值。
- builder：m04/m05/m15/m18/m19/m20/m06_inf 46日；超過須有已核實且尚未到期之同觀測月官方下次發布日，發布日例外僅既定核心月項，不能替m06_inf增添例外。m16 90日；m14 14日；季度m06/rstar/outputgap 150日且季末；估值參考90日；其他市場資料4工作日。
- 政策m06_rate：來源取得及成功核實各小於26小時（等於26即拒絕），不以政策生效日硬裁26小時；前端正式操作另驗快照26小時、輸入未變及現行各項資格。
- 快取USABLE既有例外僅m04/m15/m18，仍受下游日期／來源／正式資格檢查；其他快取STALE，m02/m14失敗不因此放行。各層門檻共同生效，不擇寬採用。

A08：09h工作流接入JSON/CSV/報告一致檢查、最新診斷snapshot、同批告警讀取、artifact及automation-state git add；保留歷史復原、三份輪替與告警流程。修復分支只執行唯讀repair-qa，main guard維持。concurrency依ref分隔。
本機state/alert 12項、source/output 7項通過；YAML解析通過。各案例日誌見evidence/A07。
A08工程接線完成，實際main診斷保存、產物與狀態分支讀回一致之完整完成條件仍待A13協調切換；不得將隔離QA視為正式整鏈驗收。A04實際Task啟用同待A13。
下一步本人A09補齊後端與歸檔測試並接入Action，再A10瀏覽器測試。
Production HOLD／交易NONE／W4取消／RM17凍結；正式DB僅Drive。
