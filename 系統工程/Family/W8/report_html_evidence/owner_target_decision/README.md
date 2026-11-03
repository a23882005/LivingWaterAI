# 本人最新標的決定與未定比例

工單 `FAMILY-REPORT-OWNER-DECISION-20261103-r1`，依 [中 PM 公開施工留言](https://github.com/a23882005/LivingWaterAI/pull/60#issuecomment-6592917746)，base `661c8ace`。原第二階段與歷史 PASS 保留；本次修正待中 PM 獨立驗收。

W5 snapshot 未納入 profile 時，報表來源可用可信 operator 設定補充同一正式 DB 的原列。`formal_report_source.build_report_source` 新增 `owner_decision`、`expected_owner_decision_digest`、`profile_db_path`、`evaluation_at`，四項須完整具備。先驗已核實 PM 原件的完整 digest，再以 SQLite `mode=ro`／`query_only` 讀本人 `funding_goal` 的 KNOWN／OWNER_VERIFIED 原列，逐值相等並核前後 DB SHA、snapshot SHA 及可得時間。原文與 PM 結構投影各自保存，不把自由文字解析成比例核准。公開選單參數沒有增加。

原完整表保存於 `historical_confirmed_target_details`，當期完整表不再沿用；`owner_target_decision.selection_lines` 只移除已排除標的、加入已確認而權重待定的標的，原其他比例逐值保持。adapter 再驗每列是否等於該決定投影，拒絕填 0、代配比例、錯戶／DB／原列／digest、未來來源及新 DB 套舊 result。current 將已記錄股數與原日期交原表格，顯示帳戶名稱時另外保留原 account key。

renderer 僅在 `_build_blocks` 的目標摘要、第5章與相依漂移提示增加必要分支。最新完整比例未定時，使用標的／選擇狀態／已知比例表，不畫完整百分比圓餅、不正規化；無新決定時原 blocks 完全一致。其他 AST、母版資產、CSS／配色／字級、章序、來源換行及 reader 不改。W5、金融 producer、W6 receiver、正式 DB/ledger、共享 README/Checkpoint 不改。

來源新版本尚無合格金融結果時，可產 SOURCE_REVIEW 本人來源／決定修正版，歷史分析保留原件查閱；不改寫舊 run/hash。現金來源鍵保持獨立證據，不加成可部署餘額，NAV／買額／漂移／四雷達不補造。後續完整金融資料及介面由 PM 鎖定，既有 no-host producer 需要從其可信設定供應此 profile／投影補充；本輪不擴改登入、選單或金融線。

完整回歸 **291 主案例＋162 子案例、17 項實際 Chromium** 通過，0 failures/errors/skips。公開 JUnit 只對舊 registry 參數名稱中的 identity 去識別，原始 JUnit 在私人證據包。來源／DB只讀與前後不變、未核准權重、future／錯戶、現金／NAV資格、既有 canonical／Mentor／雷達及原版渲染路徑均包含。

閱讀 `source_versions.json` → `validation.json` → `junit.xml` → `synthetic_artifacts.json`。真人值／DB hash／私人 ID／報告／前後畫面與五件保存／查閱收據只交 Owner／中 PM 私人入口；精確檔名與連結在私人完成回覆。完整金融 PASS0／真實 cycle0，Production HOLD／交易 NONE，PR60 Draft/unmerged。受管 file://、真人登入與實機 UAT 限制依既有裁定分列。
