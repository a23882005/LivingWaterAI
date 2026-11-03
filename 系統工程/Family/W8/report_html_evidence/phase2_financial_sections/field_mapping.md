# 來源欄位與章節對照

`/result`、`/request` 指已驗過身份、DB、snapshot、run、digest、owner、cutoff 的原物件。顯示器不新增市場來源或金融結果。

| 章節 | 原欄位／顯示用途 | 資料缺項邊界 |
| --- | --- | --- |
| bond/7 | all_asset_coverage.bonds[*]：market、original_pred009、holdings、sgov_roles、missing_inputs | 原 V75 條件與完整買額資格分列；不套股票九階 |
| market/8 | positions[0].macro_observations：HY OAS/VIX/MOVE 原值、單位、觀察日、方向、速度、新鮮度、信用 C1/C2/C3 | 缺正式半年／三年情境明示待補，不發明機率 |
| radar/9 | all_asset_coverage：expected/observed/missing/excluded、denominators、coverage_complete、financial_completeness_asserted | 來源覆蓋不是金融完整；C 缺失時四雷達六軸維持 UNKNOWN |
| valuation/10 | positions[*]：coverage_basis、market/numeric、holding/source_facts、formal_conclusion/approved_v10_analysis、valuation_observations | 原 Right/Up/Left/底二條件與正式模式／階段分列；價格、當期 PE、qP/qV 日期與資格各自保留 |
| actions/11 | positions[*].proposed_amount、formal_conclusion/canonical_target_rate、daily_slice/cap、buy_permission、deployment_gap；coverage.cash_accounts 及 cash_observations | cap 標明非金額，未知不填 0；逐帳戶分幣別，buying power 不轉現金；原 Work9/Mentor 來源缺失明示 |
| risks/12 | core_observation/result：permission/hard_gate、technical/runaway_down、structural_risk/risk_grade；event_coverage、order_source、data_complete | 缺委託／資金不抹去技術觀察，未提供正式檢視頻率不代擬 |
| education/13 | 對當次原欄位及缺項邊界的閱讀說明 | 正式教材來源待補；不創買進門檻或金融指標 |
| institutions/14 | request.macro_snapshot.payload.indicators：value、unit、dataDate、status、detail、完整 source URL | 原件觀察與正式機構預測分列，沒有新增機構結論 |

每個顯示列的 `quoted_fields` 保存 `{label,pointer,present,value}`；缺鍵與原 null 分別由 present 辨識。`source_result_sha256` 綁定原 result。`report_source_lineage.member_analysis` 與 `input_sections` 保存原物件，`section_projection.quoted_fields` 只列實際採用 fallback 的章節；顯式上游 envelope 原值優先，不在映射內冒認已顯示 fallback。`sections` 是本次接收的實際章節 envelope。

envelope 保留 client/run/section/value_state/source_id/rules_sha/as_of/payload_sha256/payload；純顯示 rules_sha 與 upstream_rules_sha 分開。as_of 是原分析時點，內文各欄保留原觀察日期；availability 不晚於 cutoff，出表與保存時間另列。長欄位分卡，同行標的仍逐一標名；相同原 URL 的總經項可共卡，沒有截斷來源、加總金額或重排金融建議。

新增 coverage 驗證核對根 digest、本人/DB/cutoff、巢狀本人、expected/observed/missing、股票/V75 路由、各分母、債券 result digest、已知現金 account_key、SOURCE_REVIEW/NO_TRADE/不寫 DB 等旗標。已有舊 member receipt 無 coverage sidecar 仍沿舊入口，其原值與守門保留。原正式 canonical C／Work9／Mentor 已知路徑沿第一階段回歸，不由部分結果冒充。
