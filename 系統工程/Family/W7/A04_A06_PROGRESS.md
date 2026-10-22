# W7-A04～A06施工進度

A04：真實Task提示詞／排程快照已保存，新提示詞完整保留原段並補共同契約、提交前驗證與讀回。新增validate_macro_supplement.py；3項測試含完整八項fixture、缺鍵／多鍵／缺政策證據／超時、原提示詞完整保留通過。狀態PREPARED_PENDING_A13_ACTIVATION；真實Task更新、真實產出與讀回依A13協調切換，尚待該段完成。

A05：每日程序GitHub來源統一8補充／4子項／v3／25獨立28傳輸26必要22計分，保留07:00與14:30既有市場工作，新增政策證據與A13切換方式；Drive獨立文件同ID更新及工作包鏡像。正式發布包重建在A13。

A06：每個工項保存attempted_at/result、FRED逐來源attempts、cache_used/cache_source及原核實證據；cache fallback保留原error與觀測日及原last_verified_at，不將本次嘗試時間作成功核實。manual覆寫保留抓取診斷，s03複用m07診斷。CSV欄位採全列聯集且複合欄位JSON序列化，報告呈現失敗與快取／核實資訊。

測試：取得失敗→cache fallback→JSON/CSV/報告三檔完整讀回、原錯誤與核實不刷新PASS；m14共同週三／精確13週／缺期拒絕PASS。來源重試5項與self-test回歸PASS。失敗案例使用明示合成fixture，未修改今日正式資料；真實Actions整鏈於A08/A13。

下一項A07狀態／告警／同值新證據持久化。正式W7驗收0/29及既有HOLD/NONE/W4/RM17維持。
