# 本人最新標的決定與未定比例

中 PM 已獨立驗收 **PASS_LILIAN_SOURCE_DECISION_PRIVATE_DELIVERY**，接受業務版本 `61ce0851f9f47c7a856bdf7462abb9633110ea51`／tree `7d430d281f7317e50dd210feb2370ef2b4567e9d`，與施工封存 `782e8a19b3cc63a38c5077eb26514e9e36d37c09` 同 tree。正式裁定：Google Drive 根目錄／TEMP／`PM_PR60_782e8a1_Lilian修正版_獨立驗收裁定_20261103.md`，6524 bytes，SHA256 `1f1ee5e1041aeabc1dfa6c1f067f4c6a1bd728651336aa0a9db984a7dec1a27e`；[中 PM 發布完成與本線回寫交辦](https://github.com/a23882005/LivingWaterAI/pull/60#issuecomment-6595348307)。裁定封存時的公開待授權已由 Owner 核准及 `61ce0851` 發布完成更新。

工單 `FAMILY-REPORT-OWNER-DECISION-20261103-r1`，依 [中 PM 公開施工留言](https://github.com/a23882005/LivingWaterAI/pull/60#issuecomment-6592917746)，base `661c8ace`。本次只回寫 `Report_HTML_Checkpoint.json` 與本 README，並更新原私人入口／回寫收據；業務程式及原報告保持。Lilian 16 頁／22 張來源卡／5 件私人正式保存檔已通過，舊 26 頁分析、其他三戶、原 137 頁／20 件與 77 頁／20 件、第一與第二階段及歷史 PASS 保留。

W5 snapshot 未納入 profile 時，報表來源可用可信 operator 設定補充同一正式 DB 的原列。`formal_report_source.build_report_source` 新增 `owner_decision`、`expected_owner_decision_digest`、`profile_db_path`、`evaluation_at`，四項須完整具備。先驗已核實 PM 原件的完整 digest，再以 SQLite `mode=ro`／`query_only` 讀本人 `funding_goal` 的 KNOWN／OWNER_VERIFIED 原列，逐值相等並核前後 DB SHA、snapshot SHA 及可得時間。原文與 PM 結構投影各自保存，不把自由文字解析成比例核准。公開選單參數沒有增加。

原完整表保存於 `historical_confirmed_target_details`，當期完整表不再沿用；`owner_target_decision.selection_lines` 只移除已排除標的、加入已確認而權重待定的標的，原其他比例逐值保持。adapter 再驗每列是否等於該決定投影，拒絕填 0、代配比例、錯戶／DB／原列／digest、未來來源及新 DB 套舊 result。current 將已記錄股數與原日期交原表格，顯示帳戶名稱時另外保留原 account key。

renderer 僅在 `_build_blocks` 的目標摘要、第5章與相依漂移提示增加必要分支。最新完整比例未定時，使用標的／選擇狀態／已知比例表，不畫完整百分比圓餅、不正規化；無新決定時原 blocks 完全一致。其他 AST、母版資產、CSS／配色／字級、章序、來源換行及 reader 不改。W5、金融 producer、W6 receiver、正式 DB/ledger、共享 README/Checkpoint 不改。

來源新版本尚無合格金融結果時，可產 SOURCE_REVIEW 本人來源／決定修正版，歷史分析保留原件查閱；不改寫舊 run/hash。現金來源鍵保持獨立證據，不加成可部署餘額，NAV／買額／漂移／四雷達不補造。後續完整金融資料及介面由 PM 鎖定，既有 no-host producer 需要從其可信設定供應此 profile／投影補充；本輪不擴改登入、選單或金融線。

施工封存完整回歸 **291 主案例＋162 子案例、17 項實際 Chromium** 通過，0 failures/errors/skips。公開 JUnit 只對舊 registry 參數名稱中的 identity 去識別，原始 JUnit 在私人證據包。來源／DB只讀與前後不變、未核准權重、future／錯戶、現金／NAV資格、既有 canonical／Mentor／雷達及原版渲染路徑均包含。

中 PM 本輪獨立重跑新增 owner-decision **8 主案例＋13 子案例**，全部通過，與上述施工封存分列；PM 未重跑完整 291 主案例或 Chromium。PM 另核 source/current 重現、PDF 全 16 頁轉圖與 22 來源全文／字框、5 件新下載的 bytes／SHA／私人 parent、舊 Lilian 14 章 blocks 及其他三戶原件保存。已核准的固定 15 檔／286561 bytes 由原工具發布並逐檔遠端讀回一致；接受業務版本的 [CI 41577308922](https://github.com/a23882005/LivingWaterAI/actions/runs/41577308922) 為 completed/success，沿既有 workflow，與封存全回歸及 PM 獨立測試分列。本次文件回寫只核 JSON、狀態／歷史保留、兩檔 diff 與其他 tracked bytes 不變；新文件 commit 的 CI 實況另存私人回寫收據。

閱讀 `source_versions.json` → `validation.json` → `junit.xml` → `synthetic_artifacts.json`。真人值／DB hash／私人 ID／報告／前後畫面與五件保存／查閱收據只交 Owner／中 PM 私人入口；精確檔名與連結在私人完成回覆。完整金融 PASS0／真實 cycle0，Production HOLD／交易 NONE，PR60 Draft/unmerged。受管 file://、真人登入與實機 UAT 限制依既有裁定分列。
