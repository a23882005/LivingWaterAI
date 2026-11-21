# Joseph／MOU 第04項施工接手紀錄

## 任務與責任

接任者承接 Family 中PM／總PM的工程責任，當前施工只集中 Joseph、MOU 第04項：正式資料 → 原生輸入產製 → FamilyRunner → 完整分析與原生 Mentor。既有 W6 成果保留、W7 Owner PASS／CLOSED沿用；W8仍IN_PROGRESS，Gate D／E待驗。此次沒有完成第04項。

Owner已明確裁定現有持倉就是正式持倉、已核准目標直接沿用；不再要求同一份持倉完整性確認、不另建暫時持倉。保留來源的原始日期、精度與未知值。只沿用既有引擎；不做報告、其他家人、Hostinger／Render、常駐服務或新投資算法。架構為 GitHub程式＋Drive獨立DB，ChatGPT按需執行。

## 唯一施工位置

- Repository：a23882005/LivingWaterAI。
- Draft PR：https://github.com/a23882005/LivingWaterAI/pull/59
- Branch：family/w8-complete-04-joseph-mou。
- 本交接前施工head：4446f1de5f4b67c1771836845c305834fb7393b2，尚未合併。
- 2026/10/27核對main已前進到3a22fd2；包含停止未授權Hostinger部署的修正。先fresh-fetch並保留main的新修正，勿用舊分支覆寫main。

## 目前確切失敗

Joseph、MOU最近的原FamilyRunner實跑均為：

```json
{"status":"DATA_UNAVAILABLE","issue_codes":[{"code":"NATIVE_INPUT_MAPPING_REQUIRED","field_path":"native_bundle","producer":"W5"}],"mentor":null}
```

目標文件、本人帳戶類別與正式持倉邊界已通過；尚未到達完整原生計算與Mentor。原因是實際request仍沒有完整native_bundle，實際context也缺原生上下文。不要把尚未到達的技術／資金檢查，誤報成當前唯一實跑錯誤。

`assemble_native_input()`只是組合上游已產製的原生契約、建立digests與binding；它沒有從原始持倉／行情產生完整原生契約。真正尚未完成的是來源產製端。不要再包一層要求別人提供完整包的adapter，當作完成這個缺口。

## 已保存的修改

| Commit | 實際內容 |
| --- | --- |
| cc337515 | 核准目標文件唯讀輸入、本人帳戶類別來源綁定、外部目標來源入口 |
| 72193437 | Owner正式持倉裁定經project/menu/provider送到FamilyRunner |
| 14038d08 | CurrentNativeSources保留official_asset_facts |
| bf5bd016 | 讀出sealed source持倉與Owner更正，保留各來源層 |
| aa4aca38 | assemble_native_input及provider入口接線；仍依賴上游完整來源 |
| 4446f1de | technical_source_bridge使用各檔自己的artifact_written_at，取代固定10/19、10/20時間；原價格／訊號規則未改 |

4446f1de的三條既有CI SUCCESS：40465740661、40465740654、40465740655。技術橋接相關本機32測試PASS。這些只驗證修改，未驗收兩戶第04項PASS。

## 直接閱讀的程式

- W8/on_demand_project.py：build_project_menu，按需執行入口。
- W8/official_family_entry.py：analyze_positions與build_official_family_menu。
- W8/on_demand_analysis.py：OnDemandAnalysisProvider、assemble_native_input。
- W8/approved_target_input.py：build_approved_target_view、bind_document_account_scope、bind_official_holdings。
- W8/on_demand_current_sources.py：build_current_sources、read_official_holdings、run_original_v70。
- W8/on_demand_market_observations.py：現有cache數值及部分原V82/V75運算，不是完整canonical決策來源。
- W5/family_runner.py：_validate、_compute、analyze，原生正式dispatch。
- W5/native_pipeline.py：run_native_pipeline，C7／股票／債券／資金／SGOV／Work8／Work9。
- W5/stock_engine.py、bond_engine.py、c7_engine.py、mentor_bridge.py：原引擎呼叫及原生Mentor。
- W5/family_boundary.py及各*_source_bridge.py：既有來源與身分／金額／時間綁定。

以上路徑均相對`系統工程/Family/`。

## 必須實作的來源產製

`native_bundle`需要stock_request、bond_request、stock_evidence、producer_contract、stock_source_fields、bond_evidence、asset_framework、physical_sgov。

trusted_context需要funding_source、valuation_source、v70_source、c7_source、technical_source，並有native_owner、stock_instrument、bond_instruments來源映射。以原schema／builder產製並綁定同client/run/owner/snapshot；投資金額、現金、價格、訊號不得從fixture或任意0補入。

現有正式DB內不只有portfolio_position：Joseph sealed W6已保存明細18列（含現金列），另有Owner更正；MOU sealed截圖來源16檔。舊ledger僅Joseph7列、MOU12列。read_official_holdings已讀出兩層；後續需依原來源與最新裁定做實際輸入映射。MOU舊registry缺ADBE、AVGO、CPAI、DYNF、MDT；Joseph來源含VALU及USD_CASH，現金列不得當成股票。不要只讀舊ledger而漏掉已正式保存來源。

## UNKNOWN追查結論與界線

W5/technical_source_bridge.py的build_partial_technical會先建立32個UNKNOWN，再按既定映射計算部分訊號。W8/on_demand_market_observations.py的evaluate_observed_history目前將canonical向量初始化UNKNOWN；算出數值不代表canonical訊號已接好。請分清來源缺欄、程式尚未映射與規則真正待裁定。

正式V82母文件已於本對話fresh-read，並非只搜尋檔名：Drive根目錄《V82.md》（v1.21.0）及《V82股票操作白皮書.md》。V82 Work7-A明文保留非Executable Candidate，包括MACD連續2完成Bar、0.25×ATR Noise Band。這些Candidate不是可自行升格的正式參數；也不能據此推論所有正常部署訊號均無規則。核對正式全文與既有producer後再接線，不以UNKNOWN硬改FALSE取得通過。

## 私人資料與證據

私人DB、目標原文與金融值只從有權限的Drive取用，勿加入公開repo／Actions artifact或日誌。正式DB與各治理文件的位置由main的W8/Checkpoint.json、Family正式索引及Drive三份管理文件取得，勿按同名檔猜庫。

Drive TEMP既有`Family_04_Joseph_MOU_input_binding.json`沿原ID更新，保存兩戶實際request/context/result、目標來源及Owner正式持倉裁定；main Checkpoint.active_04_focus.evidence列有正式ID及已核對SHA。這份遠端檔停在正式持倉裁定後的實跑版本，未含本對話所有後續scratch診斷。

本對話scratch診斷位於`/workspace/scratch/ced277ccb412/private_work/focus04/`：Family_04_latest_repair_run.json、Family_04_after_receipt_fix.json、official_holdings_source_inventory.json。新環境未必保留scratch，應以Drive正式原件重新產生；不可把scratch存在當成已同步Drive。後續提交尚未全部回寫三份Drive治理及main Checkpoint的work_head，交付時須補同步。

## 工作方法與完成條件

同一輪持續實作／實跑／修錯，沿PR59；局部測試與文件更新不算第04項完成。完成需兩戶本人正式來源進入原FamilyRunner，取得完整原生分析及原生Mentor，保存可追溯輸入／輸出／call_trace／版本與必要驗證，再同步Checkpoint、Drive工程管理／檔案管理／Master WBS。重要Drive修改前先讀根《檔案管理.md》、核對最新原件、備份、原ID更新與讀回。

遇到無法取得的必要來源或必須Owner決定的正式規則時，一次列出確切欄位、查過的位置與影響。既有正式持倉裁定沿用。完整結果產出前保留IN_PROGRESS。
