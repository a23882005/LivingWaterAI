# 給 Family 中PM：W5 剩餘來源協調

目前16/18，既有核心未修改，Production HOLD、交易NONE。請沿現有資料定位，不要求家人重新填寫。收到下列資料/裁決後，W5只補受影響接線與驗證，再完成18整線交付。

1. **W5-09 技術與實際來源**：需要既有producer的檔案/輸出路徑、版本及schema，明列asset_id、exchange、currency、timeframe、adjustment、parameters、price_field、sample_state、as_of、available_at、swings.confirmed_at及V82所需core facts。現有完整功能輸入是W5_SYNTHETIC_TEST，不冒充正式producer。責任：中PM指定原技術資料責任線；W5負責接線，不能自行造完整指標算法。週/月K未完成與分割調整須依該原producer規則驗收。

另請一併定位四位家人既有confirmed Target記錄（fileId/path、client_id、allocation_id、版本、confirmation evidence、target_lines）及相符C Work6原輸入；目前四個W1 DB的final_target_version均0筆。具名報價/FX/NAV與V70 tactical來源應提供原件，W3 feed ready不等於tactical budget。缺資料目前安全回不可用，並非要求新增問卷。

2. **W5-16 已核准並完成**：原Work9 None/null＋來源分欄，34項受影響案例PASS。正式語意與限制見PM16_APPROVAL_AND_ACCEPTANCE.md；本項已解除待裁定。

原目標金額/權重問題已由W5等值投影解決，不再列待裁決；原Frozen九schema已找回且使用，不須重寫。

完整成果：Google Drive Family/W5，同一累計ZIP。GitHub草稿PR：https://github.com/a23882005/LivingWaterAI/pull/22。此文件為待處理工作交回，16已接收中PM正式裁定，09來源由中PM續辦。
