# W5 → W7 恢復接口

驗證範圍：STAGING_VERIFIED，單一程序同一 StagingAnalysisStore；不是正式跨程序復原或持久化 PASS。

請求鍵為 (client_id, request_id)，input_digest 為 Family.W5.digest.v1 型別保真編碼，包含 run、snapshot、版本及完整輸入。同鍵不同 digest 拒絕；不同資料必須重新建立請求，不得接續舊結果。首次計算與一次純計算重試的總預算隨 entry 保存，重送不得重置。引擎錯誤不自動重試；呼叫端可在同一輸入及有效權限下恢復一次。成功後可重送快取，但每次仍重驗當前權限、版本及來源。

FamilyRunner 使用獨立 context_provider，發布前及讀取快取時重新驗證。任何計算都沒有交易副作用；只有主調度者能發布。逾時工作沒有發布回呼，晚到結果不可覆蓋已完成結果。完成 Mentor 後中斷不保存部分結果，恢復時整體重算並只發布一次。

snapshot() 回傳可 JSON 序列化的型別標記上下文，保存 journal、input_digest、status、attempts、timeouts、result、publication_count。此 snapshot 是交接證據，不提供正式重新載入保證。

W7 接收條件：沿用上述同鍵和 digest 語意，提供可信身分/分析許可及目前來源版本 provider；以正式儲存交易/CAS 實作跨程序的請求鎖、版本重驗與唯一發布；持久保存重試預算。W7 自行驗證程序崩潰、雙程序競爭與恢復，未驗證前不得將本線 staging 證據宣稱為正式恢復。Production HOLD、交易 NONE。

可執行證據：tests/test_family_end_to_end.py、tests/test_recovery_bridge.py；前者實際呼叫原 C7、V82、V75、C8C9 與 Mentor，不替換計算回傳。
