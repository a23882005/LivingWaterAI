# Family W5 接線施工中

契約：v2.2.1；基線：32c9322c8bb3150480f6c86becf28e04592f5e8e。
Production HOLD；交易授權 NONE。

本次已實作唯讀四庫讀取、原 W3 feed 封裝、精確資金合計守恆、C8C9 同名 schema 載入路徑解析。
既有 V82/V75 原生回歸已實跑；完整 Family 調度及 Mentor 回傳仍待接通。

安裝：Python 3.11 以上，`python -m pip install -r 系統工程/Family/W5/requirements.lock`。
本線測試：`python -m pytest 系統工程/Family/W5/tests`。
已交付 `run_analysis.py` 及受控 staging dispatcher；完整來源映射及Work9正向依Checkpoint續驗。

`family_input.read_snapshot` 只讀指定四庫隔離副本，保留歷史資料與未知值，不推導 AVAILABLE。
`market_bridge.read_macro_snapshot` 直接呼叫已接收 P70-5，原 payload 不變。
`funding_guard.check_aggregate` 是合計額度檢查，不產生新的配置或分配優先序。
`runtime_loader` 不修改核心檔，也不替換 Frozen schema；缺件維持 DEPENDENCY_MISSING。

詳見 Checkpoint.json 與 evidence/；私人四庫與讀取結果僅放私有 Drive。

## Work21依賴接收
九份Frozen原件保存在schemas/，雜湊與來源見frozen_schema_lock.json。runtime_loader驗證SHA-256後沿用原schema驗證。測試預設從repo根讀取原生程式；分離checkout時設定W5_SOURCE_ROOT為核定來源checkout根目錄。新增原Work21合成adapter案例，不改核心策略。

## Family 06～08呼叫邊界
`family_boundary.prepare_input(request, trusted_context=...)`先驗身份/版本與原W2 confirmed record，產PreparedInput；trusted_context由受控測試呼叫方提供，W7日後接認證，不能從未信任request複製。完整性證據須帶account_key、as_of、snapshot_digest及source_reference；缺證據時回DATA_UNAVAILABLE。
`permission_bridge.project_permissions`投影W1已確認用途與行動許可；`protect_existing`呼叫原C8C9 Work8保留風險與客戶行動。
`funding_bridge.reconcile_funding`呼叫原C8C9 Work6，再用同一funding_guard核對各筆股債占用。owner_binding須由可信來源核定family_owner/native_owner/currency/version/source_reference並給expected_binding_digest；W1資金用途key與C7券商domain保持分離。
`valuation.value_position`僅計算明確來源quantity × price × FX；不同幣別缺FX回UNKNOWN，暫估股數維持ESTIMATED。
後續15棒runner尚待實作；以上模組已逐一實測。


本輪新增股債原生計算與SGOV元件：stock_engine、bond_engine、tactical_budget、output_bridge、sgov_bridge。元件呼叫仍須由後續Family runner驗證身份、trusted producer contract、權限及來源binding；使用者入口尚未交付。工作項狀態及待補邊界以Checkpoint為準。

## Mentor與施工回歸
`mentor_bridge.explain_native`接原Work9 request/result與可信dispatcher context；重用Work9來源驗證及W2原理由表。trusted_context必須由受控呼叫方提供，含client、run、owner、幣別、分析許可、資料來源類型及完整result digest。原W2 mock說明器保持原版。

`vendor/w2/`只含原W2 Work21直接依賴；來源hash見w2_dependency_lock.json。執行測試前設 `W5_W2_ROOT` 為本W5目錄下vendor/w2的絕對路徑。執行 `python 系統工程/Family/W5/verify_dependencies.py` 核對90項hash，再用原pytest入口。

GitHub Actions使用同一pytest入口與核定基線checkout。現有strict XFAIL對應目標單位問題；施工回歸與W5整線驗收分別記錄。CLI已補交；15棒的完整來源映射與正向整線續作。

## Family 調度入口與 CLI

```sh
W5_TRUSTED_CONTEXT=/operator/context.json python 系統工程/Family/W5/run_analysis.py --request request.json --output result.json
```

獨立的 `--trusted-context` 亦可指定 operator 檔；每次驗證重新讀取。請求本身不能設定可信context provider。API以 `FamilyRunner(repo_root, context_provider=...)` 重用同一測試store，單次CLI使用新的隔離store；跨程序持久化由W7接手。成功exit 0，其餘狀態exit 2，結果保留issue code及NO_TRADE。

request沿用Family.W5.request.v1並加入native_bundle。受控provider的native_binding含schema_version=Family.W5.NativeBinding.v1、request_digest、bundle_digest、target_binding_digest、family_owner、native_owner、data_provenance及source_reference；對應的是已審核輸入。逐欄正式來源映射仍依Checkpoint續作，此digest驗證本身不替代語意核對。CLI不從request自動建立這份binding。

確認紀錄ID與配置ID分別保留為target_record_id及allocation_id，後者取原W2 draft.allocation_id。歷史確認payload/hash不改動。新入口已實際呼叫股債pipeline到既有Work8目標單位問題；完整Work9正向仍列待修。四庫歷史CLI讀取結果於私有ZIP的private_runner/，去識別摘要於evidence/runner_private_checks.json。
