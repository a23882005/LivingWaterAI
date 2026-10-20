# 給 Family 中PM：W5 剩餘兩項具名協調

目前15/18，既有核心未修改，Production HOLD、交易NONE。請沿現有資料定位，不要求家人重新填寫。收到下列資料/裁決後，W5只補受影響接線與驗證，再完成18整線交付。

1. **W5-09 技術與實際來源**：需要既有producer的檔案/輸出路徑、版本及schema，明列asset_id、exchange、currency、timeframe、adjustment、parameters、price_field、sample_state、as_of、available_at、swings.confirmed_at及V82所需core facts。現有完整功能輸入是W5_SYNTHETIC_TEST，不冒充正式producer。責任：中PM指定原技術資料責任線；W5負責接線，不能自行造完整指標算法。週/月K未完成與分割調整須依該原producer規則驗收。

另請一併定位四位家人既有confirmed Target記錄（fileId/path、client_id、allocation_id、版本、confirmation evidence、target_lines）及相符C Work6原輸入；目前四個W1 DB的final_target_version均0筆。具名報價/FX/NAV與V70 tactical來源應提供原件，W3 feed ready不等於tactical budget。缺資料目前安全回不可用，並非要求新增問卷。

2. **W5-16 債券客戶動作接口**：原C8C9_RUNTIME/C8C9_Work9_Unified_Deployment_Mentor_Return.py將V75 client_preference_action設為None；Work8僅收V82，原C7保護契約只涵蓋既有個股。W5已保留W1 holding_policy、C7 drift.client_facing_action、V75 raw action與金額，各有來源；未自創債券保護優先序。請中PM與C線具名決定：保留原None與來源分欄是否為本版核定交付，或核定最小接口修改的原檔/欄位/規則。未裁決前此棒不列完成。

原目標金額/權重問題已由W5等值投影解決，不再列待裁決；原Frozen九schema已找回且使用，不須重寫。

完整成果：Google Drive Family/W5，同一累計ZIP。GitHub草稿PR：https://github.com/a23882005/LivingWaterAI/pull/22。此文件為待處理工作交回，未宣稱中PM已接收或已裁決。
