# Family 報告來源承接與完整 HTML｜獨立施工契約及回交

正式施工位置為 [Draft PR60](https://github.com/a23882005/LivingWaterAI/pull/60)，分支 `family/report-canonical-html-20261030`。中 PM 已在 Owner 明確核准後發布原 16 檔，遠端起點為 `b6a146b33fa7aae8c725ebbe28cdd375a449aaf9`；原 `95f2461`／`e3bfae8` 本機成果保持。先前自動核准拒絕是歷史診斷，不能再當作遠端現況。

依 [PR60 續工裁定](https://github.com/a23882005/LivingWaterAI/pull/60#issuecomment-6514477704)，本線負責瀏覽器重跑、四戶來源接線與本人報告的 Drive 保存／全新讀回。必要增量使用 `on_demand_w6.py` 的可信 producer 注入及 `on_demand_report_delivery.py` 的交付／查閱驗證；公開十四選單 API 與核准母版保持。原 V82／每日切片／cycle／共同資金仍屬 PR59；未合入 PR59，未修改私人 DB、金融規則、共享 Checkpoint。中 PM 負責來源與版本協調、獨立驗收及 Gate。

開工 main `2eaa56eceb0b5b6f7f1a338ea7f677f3a2d89136`；施工期間同步 docs-only main，交付 base `036f8415cda9f24e8f51c8b73630effbf90f59e6`。介面對照 PR59 `5a54ce25c1dedc39c781aa2e6acd9f867b581d56`，准改檔案無交疊。分支 `family/report-canonical-html-20261030`。恢復入口為本目錄 `Report_HTML_Checkpoint.json`。

治理依據：施工包 00～04／version_snapshot、main 的 `REPORT_HTML_CODEX_HANDOFF_20261030.md`、根 Drive `檔案管理.md`（ID `1OSLqc4U5bFCAKe94V_UlAWTM8WH1t2O9`）最新報告交辦、W6 `ENGINEERING_ACCEPTANCE.md`、Mentor 最新 C／Report handoff。保留 `W6_ENGINEERING_GATE=PASS_WITH_DECLARED_SOURCE_GAPS`、v16／v16.4 工程裁定及 Production HOLD／交易 NONE。

## 行為

1. `report.html` 在 Chromium 完成分頁及原 QA 後，以 `page.content()` 保存同一 DOM；PDF、PNG、reader 全部源自該 DOM。保存的 main 已有 14 章正文、目錄連結及頁碼，不需要再執行分頁程式。ZIP 增加同位元組的完整 `report.html`。
2. 有可驗證 C 來源時，使用 Work6 Final Target、Current、drift snapshot、protected 與 client-facing action。Current∪Target 逐檔保存；不以 DB 權重×本輪 NAV 取代 C 結果。原漂移槽完整保留；顯示反號及 FX 轉換有名稱、原值、分母與倍率。
3. 外部既有 W2 核准目標經原 W5 `validate_target`／W6 `receive_target` 驗證。DB 空表可承接；DB 與外部版本或內容衝突明確拒絕，包含最新 DB 確認版不完整的情況。確認時間、reference 與歷史 confirmation run 不重造。
4. 四雷達直接接 Work6 snapshot，重用 C 的軸標籤／順序驗證器；視圖順序與六軸、六級原值完整保留。長標籤只換行。UNKNOWN 不補零、不畫完整分數多邊形。
5. 八組章節透過既有 W6 `canonical_section` 驗證 client／run／section／來源／規則摘要／payload digest，再無損轉接；原始 envelope 留在 sidecar。章節可以有不同的既有 as-of，未提供、PARTIAL、STALE、UNKNOWN 保留其狀態。

## 公開 API 與可信注入

`OnDemandW6Renderer` 的輸入仍是可信 producer 回傳的 **`{market, engine}`**；選單 options 仍只有 date／language，不增加對家人必填欄位。可信 producer 可在 `engine.report_sources` 附上本線 sidecar。

`formal_report_source.build_report_source(snapshot, account=..., expected_client_id=...)` 原呼叫不變；增量可選 `approved_target`、`target_context`。Menu13／official entry 無需改參數：producer 也可把原 W2 物件放在 sidecar 的原始 request，並給 target_context，由 `w6_current_data` 承接。外部目標不會改寫原 formal_source digest，renderer／交付仍綁定原 authenticated source。

可信 producer 範例（原引擎結果已產出後；此處不執行／修正引擎）：

```python
bindings = adapter.make_report_sources(
    formal_source, original_w5_request, original_family_result,
    sections=vetted_section_envelopes,
    target_context=trusted_latest_target_context,
    scope="CANONICAL_CALCULATION",
)
engine = {**original_family_result,
          "source_db_sha256": formal_source["source_db_sha256"],
          "trade_authorization": "NONE", "report_sources": bindings}
return {"market": verified_same_run_market, "engine": engine}
```

部分分析可用 `scope="SOURCE_REVIEW"`、`result=None`，並在 `c7=` 注入原 `W5/c7_engine.run_c7_engine` receipt（`original_source/source_digest/result`）。來源回顧不要求 Work9、完整八章來源或正新增現金。原 W6 歷史／失敗接收器保持原件，完整既有缺資料回歸另外執行。

## 精確 producer → consumer 映射

路徑由 repo 根起算；C 指 `系統工程/C-配置決策引擎＋Mentor整合/正式Runtime`，Family 指 `系統工程/Family`。

| Producer／實際 path | Consumer／用途 | 單位、來源與資格 |
|---|---|---|
| `Family/W5/family_input.read_snapshot` → `snapshot.source_sha256/payload_digest/identity/tables` | `formal_report_source` → `source_db_sha256/snapshot_payload_sha256/source_account_keys/source_instruments` | 原本人 DB bytes SHA、tables digest、client／alias；快照本身不是即時估值 |
| 原 W2 物件 `request.confirmed_target.payload.draft.target_lines`、`confirmation_evidence`、`target_hash/target_version/confirmation_run_id` | `resolve_targets` → `current_confirmed_target_details`、`external_target_receipt` | 原 W5 validator；weight fraction → integer million-units 只接受可精確還原的值；不四捨五入核准比例 |
| 可信目標上下文 `target_context` | 固定 latest version/hash、target_key、來源 DB／snapshot、report run／evaluation | 必須含 `client_id/source_db_sha256/snapshot_payload_sha256/run_id/evaluation_at/source_id/target_key/expected_target_version/expected_target_hash`。版本採原 W5 latest context，不新簽署 |
| DB `portfolio_instrument` 或可信 `target_context.instrument_map[instrument_id]` | 外部目標 instrument_id → instrument_key／ticker／label | 同已存在 DB key 的 ticker 必須一致；拒絕重複、跨標的映射與不完整配置 |
| `Family/W5/family_runner._compute` → `result.native_result.family_sources.c7` | `prepare_report_sources` 的 C7 receipt | 原 `c7_engine` 形狀；`source_digest` 必須等於 `digest(original_source)` 及 `request.c7_source_digest` |
| `c7.original_source.canonical_input.allocations.current_allocation.snapshot` | `canonical_display` → actual；與市場逐檔估值核對 | C 已知完整 Current；fraction；保留原 denominator；不以歷史或假設值填 actual |
| `C/work6/adjustment_loop` → `c7.original_source.work6_result.final_target.snapshot` | `canonical_display` → target | 原確認資格、allocation_id、confirmed_at/by、source references；綁原 W2 allocation_id／version |
| 同上 `.drift_snapshot.items[]` | `CurrentData.drift[].canonical_item` 及雙條圖顯示欄位 | `current_weight/final_target_weight/drift` 原槽無損；`protected/client_facing_action` 原樣承接；Universe = Current∪Target |
| 同上 `.radar_snapshot` | `approved_radar.canonical_snapshot/views/axes/view_order` | 重用 `validate_radar_display_contract`；原 `CURRENT_ATTACK,TARGET_ATTACK,CURRENT_DEFENSE,TARGET_DEFENSE`；六軸原 label/order；1～6 整級或 UNKNOWN+null |
| `C/work7/asset_framework` → `c7.result` 的 `report_contract/drift_snapshot/radar_snapshot/parent_work6_snapshot_id` | 轉接資格與無損核對 | 必須同 client/run、同 Work6 snapshot、drift/radar 不得被改寫。完整計算要求 `READY_FOR_PM_GATE`，這不是 Production release |
| `Family/W5/family_runner` 的原 `request/result`；`W6/runtime/report_receiver.receive_action` | `report_source_lineage.action` | 重用 typed request digest、run/request ID、canonical digest、owner、trade scope；失敗原狀態保留 |
| `result.native_result.unified_result`（原 C8C9 Work9）與 `result.mentor`（原 `mentor_bridge`） | Work9 canonical／Mentor summary／source bindings 相等驗證 | canonical digest、source_result_digest、item_ids、run、native broker/account/domain、currency、Final Target ID；不重跑部署、不生成新經濟身分 |
| 可信 `sections.{bond,market,radar,valuation,actions,risks,education,institutions}` | `verified_sections` → 第 7～14 章 | 每一組使用原 W6 envelope：`client_id/run_id/section/value_state/source_id/rules_sha/as_of/payload/payload_sha256`；payload 為具 `heading/body/source_reference` 的原文陣列 |
| 經核實 `market.position_values_twd/included_cash_accounts/fx_to_twd` | actual 與 canonical 共分母核對 | 本人 DB／run、逐 account/instrument coverage；TWD；歷史／假設來源不進 actual。現金估值不表示可部署現金 |

雷達原六軸為：牛市初期、牛市中期、牛市末期、非衰退熊市／估值壓縮、景氣衰退熊市、金融／流動性危機。原軸 id／標籤與六級值都由 C 擁有。

八組正文在 **main／PR59 尚無單一具名 producer 固定產出全部八組 envelope**。本線已完成實際 receiver 驗證、來源保留、scope／缺值呈現與合成注入；不宣稱真人八組研究內容已產出。中 PM 需指定各組正式 producer 與 source_id／rules_sha；原 producer 缺少的部分維持 UNKNOWN，不能由報表補研究或偷帶舊客戶數字。

## 顯示轉換、分母與缺值

- C `drift = Target − Current` 保存在 `canonical_item.drift`。`display_transform=C_TARGET_MINUS_CURRENT_TO_W6_CURRENT_MINUS_TARGET_V1`：`差異百分點=-raw_drift*100`、`差異TWD=-raw_drift*denominator_twd`。圖例仍為「差額＝目前－目標」。不把反號寫回原槽。
- `actual/target.權重`、`drift.實際權重/目標權重` 是 fraction；`市值TWD/實際金額TWD/目標金額TWD/差異TWD` 是 TWD 元；百分點乘 100。純金額顯示用 C 已有權重×C 同一原分母；不重新決定目標或計算金融漂移。
- 非 TWD 分母只在同輪市場提供可追溯、已驗證 FX 時顯示轉換，`canonical_lineage` 保留原分母與 FX 倍率。市場與 C 分母核對到 0.01 TWD；權重核對沿原 C `5e-7` 容差；不修正上游值。
- `protected=true` 必須原值 Current=Target、drift=0、`HOLD_PROTECTED`。報告保留保護動作；風險說明與賣出指示分開。
- 未帶新 sidecar 的舊 API 仍可作 `DB_TARGET_SOURCE_REVIEW`，原 DB 目標顯示投影相容；不再把單純 `engine.status=OK` 宣稱為已驗證 C 正式計算。新 scope 的完整計算必須具備其宣稱的 C／Work9 來源；來源回顧不加此門檻。
- SOURCE_REVIEW 可保留失敗／部分結果；缺 target/drift/radar/章節明示 UNKNOWN，缺值不是零。資產類別原 N/A／其他資訊不被轉成數值；來源 envelope 與 C 原始物件完整留 sidecar。報告 renderer QA 通過不代表實盤資料或上游金融整線已通過。

## 母版與測試

核准母包 Drive ID `1oHZvKsKYa6VKFeV1C7D2KIUvGXzZxvyk`，SHA256 `b9b8d6eb1718b510f82e41e925f7a9145880caa8d3fe0a2dec4320ada515796e`。只讀原 report.mjs 的 CSS、mother.html、cover/header reference；不讀歷史 report_data／持倉數字，不將母包提交 Git。配色、封面、頁框、餅圖／雙條圖／四雷達／翻頁母版沿用原件。

合成輸入：`tests/fixtures/report_html/synthetic.py`；只有合成 ID、400/300/300 元的測試持倉、合成 C／W2／Work9 輸出形狀與正文。這是報告契約整線，**沒有執行或宣稱原投資引擎金融整線、真人四戶 E2E 或真實 Drive 發布**。

最短資料回歸：

```bash
python -m unittest discover -s 系統工程/Family/W8/tests -p test_report_canonical_adapter.py -v
```

完整重現依賴：既有 Python runtime（pytest、jsonschema、Playwright、PyMuPDF、Pillow）、Chromium、原 CI 的 jsdom `26.1.0`，及上述同 SHA 母包。取得母包後：

```bash
W6_APPROVED_ARCHIVE=/path/to/approved.zip \
REPORT_HTML_EVIDENCE_DIR=/tmp/family-report-evidence \
python -m unittest discover -s 系統工程/Family/W8/tests -p test_report_rendered_html.py -v
```

完整 W8＋W6 回歸需 `PYTHONPATH` 包含 `Family/W8`、`Family/W5`、`Family/W6/runtime`，`NODE_PATH` 指向 jsdom 的 node_modules：

```bash
python -m pytest 系統工程/Family/W8/tests 系統工程/Family/W6/runtime -q
```

未提供母包時，瀏覽器組明確 skip，不能據此宣稱視覺驗收通過。本次實際執行的命令、數量、JUnit 與逐頁 QA 文字見 `report_html_evidence/`。完整 HTML／PDF／index／ZIP、聯絡表與手機圖在工作區 `/workspace/report-evidence/` 回交，各產物 SHA 列入 artifact manifest。自動核准審查以可能敏感、目的地未獲確認為由拒絕 GitHub 報告衍生圖片上傳；因此 PR 只提交程式、合成測試及文字 QA，不以其他格式繞過該拒絕。

受管 Chromium 的 `file://` 導航回 `ERR_BLOCKED_BY_ADMINISTRATOR`。本輪以**已保存檔案的原始位元組**載入離線頁面、停用 JavaScript，驗證正文／目錄／頁碼；沒有注入 PAGINATION_SCRIPT。reader 分別驗證獨立 data URI fallback、離線 local-asset route 的同目錄 PNG；16 頁保存 DOM 與原 PNG 逐頁像素完全一致。中 PM 環境仍需雙擊 HTML／ZIP 開檔核對；不繞過受管瀏覽器政策。

## 剩餘依賴與唯一下一責任

施工責任：**原報告 Codex**；獨立驗收與來源協調責任：**Family 中 PM**。真人來源與完整證據留私人 Drive，本 PR 只保存程式、合成測試與去私人化文字 QA。完整金融整線未就緒時，已知來源仍可交付 SOURCE_REVIEW，缺值具名保留 UNKNOWN；檔案完成保存不表示金融或中 PM 整體 PASS。

恢復：checkout 本線 Draft PR head → 讀 Checkpoint／本契約 → 重跑上列 fixture → 對照最新 main／PR59 的准改檔交疊 → 只將中 PM 指定正式來源注入。遇到同檔並行變更時保留雙方差異，交中 PM 協調；其他無衝突工作可繼續。共享治理與本人 DB 寫入由中 PM 依既有 writer 程序協調；本線只保存新的正式報告與證據。

## PR60 續工：原生逐檔部分分析與正式保存

續工參考 PR59 `d8dea452ec47e3fb27fbd31e8db15a89b4a36122` 的原輸出 `Family.W8.MemberV82Request.v1`／`Family.W8.MemberV82Analysis.v1`。這不是 W5／Work9 完整部署結果。`MemberAnalysisReportProducer` 將原 request／result、可信來源 ID 與原 producer 規則 SHA 注入既有 `{market, engine}` API；不修改共用分析 producer 或複製金融實作。

`report_canonical_adapter._member_analysis` 核對本人／DB SHA／snapshot tables digest／run／時點／ALL_MEMBER_ACCOUNTS owner、原 request／report／逐檔 digest、universe 覆蓋及原正式判斷 binding。只有 SOURCE_REVIEW 可接這種部分分析；canonical_result、完整 Mentor 及執行金額不得由此補造。八組章節繼續使用原 receiver；估值章直接引用原逐檔分析，保留來源、時點及原值，其餘未提供的章節維持 UNKNOWN。

未提供已核實的投資池市值／現金範圍／FX 時，`w6_current_data` 保留 `current_total_twd=null`、`actual=[]`、`drift=[]`；本人 DB 已記錄的數量與各自日期另列。已核准目標比例可展示，目標金額仍為 null；四雷達不補零。來源分析時點在報告明示「市值尚未核實」，不冒充即時估值。資料回顧仍保存完整 14 章、目錄與分頁正文。

現金目標沿原 `instrument_type=CASH`／`quote_currency` 產生顯示身分，不創造股票 ticker。外部核准物件可以由 producer 呼叫原上游驗證器，再以 canonical target receipt 轉交；`MemberAnalysisReportProducer` 的 `approved_target/target_context/target_validator` 為可信設定，選單使用者仍只輸入 date／language。既有 Menu13 的 FormalReportSource digest 保持原來源綁定，目標增量位於 `engine.report_sources.approved_target_transfer`。新版原驗證器可從獨立的已鎖定上游程式載入，必須記錄其規則 SHA；本線不改 W5 驗證規則。READ_EXISTING_APPROVAL 保留原 action、原核准時間缺值及來源可取得時間，沒有新簽署事件。

同一已登錄投資工具若分成多個內部角色，僅在 operator 明列 `same_instrument_display_groups`、映射到同一 DB instrument 且 ticker 一致時，才合計其顯示比例。原目標物件與角色 ID 完整保留；未明列的重複 ticker 仍拒絕，不合併不同投資工具。

保存沿 `prepare_report_delivery → bind_connector_uploads → 實際 Drive upload → 各原件全新下載 → prepare_verified_manifest → manifest upload／全新下載 → verify_published_manifest`。沿用本人 Sources 的正式父資料夾與台灣時間檔名。manifest 同時記錄 `report_scope/content_state`，因此 COMPLETE 只代表檔案保存完成。

Menu12 沿既有認證後的固定本人資料夾查詢，再由 executor 呼叫 `verify_report_lookup`，核對實際下載的 manifest／PDF／HTML／ZIP、私人父目錄、本人／run／DB SHA／日期與逐檔 bytes／SHA。這不提供登入或宣稱真人 Project 登入 UAT；Android／iOS 實機 UAT 依 Owner 暫緩，受管 `file://` 限制仍照實記錄。四戶私人位置與讀回收據僅列在私人回交入口。

續工回歸為 255 項＋65 子案例、8 項 Chromium 測試，0 failures／errors／skips。四戶 SOURCE_REVIEW 的正式報告與 manifest 已逐戶保存並從原 ID 全新下載核對，69 頁保存 HTML 與 ZIP PNG 像素一致；四戶離線窄畫面 reader 及工程執行環境的 Menu12 查閱驗證通過。最後再下載四份本人 DB，與開工位元組完全一致。完整證據入口為私人 Google Drive 根目錄／TEMP／`Family_Report_HTML_PR60_續工驗收入口_20261030.txt`。這些是報告及保存工程結果；完整金融整線、真人 Project 登入 UAT 與中 PM 獨立驗收仍未宣稱 PASS。


## 2026-10-31 中 PM 排版補修：來源長字串完整換行

補修契約位於 PR60 的 issuecomment-6527625954，鎖定基準 81e741da51d79307210dbe061c0f65178ed733aa。中 PM 已獨立完成 43 項＋46 子案例，資料來源承接、靜態同源產物與正式保存／工程查閱分段 PASS；排版問題為 32 列估值來源字串超出卡片，不能由原高度 overflow=0 代表水平通過。

`w6_member_render._section_items` 與 `_radar_panels` 為來源 small 指定同一 source-reference 樣式；`_source_html` 僅增加 display:block、overflow-wrap:anywhere 與 word-break:normal。保留原 v16 CSS、字級、配色、圖表、來源全文／SHA／日期／scope 及 lineage；沒有截斷或隱藏來源。`render_current_w6` 在原高度 QA 之外，驗來源文字 Range 與來源容器位於卡片內緣、來源及頁面的 scrollWidth 不超 clientWidth，失敗仍拒絕產出。

新增合成長 URL、不可斷路徑、64 位 SHA 與中文標點案例。實際 Chromium 驗八組章節及四個雷達來源共 12 卡的文字範圍、容器及頁面寬度，並以 PDF 實際文字框核對卡片／頁面及全文，保留全部頁面 PNG 像素、ZIP 同源正文／PDF／reader、14 章／13 目錄目標／頁碼與窄畫面操作。核准四雷達 grid 仍使用原分頁與高度限制，過高的單一區塊仍會被原 QA 拒絕。

本輪回歸 257 項＋65 子案例、10 項 Chromium，0 failures/errors/skips。四戶按原凍結輸入重出 17／19／15／15 共 66 頁；60 張來源卡含全部 32 張估值來源逐字相同，text Range、scrollWidth 及 PDF 字框檢查通過。全部 saved HTML 與 ZIP PNG 逐頁像素相等；current digest、來源 DB SHA、核准目標、run、資料日期不變。正式 DB 已有後續版本，私人回交另列最新原件 SHA 與凍結值；本次純排版重出不混入新版 DB 或新版 PR59 分析。

四戶新 PDF／完整 report.html／index.html／ZIP／manifest 共 20 份原件已保存至本人 Sources 的原正式資料夾，使用新台灣時間檔名、保留舊歷史。全新下載 bytes／SHA／私人父目錄／run／DB 綁定及工程 Menu12 查閱通過。完整證據位於 Google Drive 根目錄／TEMP／`Family_Report_HTML_PR60_排版補修複驗入口_20261031.txt`，包名 `Family_Report_HTML_PR60_排版補修完整成果_待中PM複驗_20261031.zip`。依入口先讀 00，再讀 01 清單及 reports/各戶。公開僅為原 19 檔准改範圍內的程式／合成測試／去私人化文字 QA；本輪實際改 12 檔。

本輪沒有改正式 DB、金融 producer、核准權重、共用 README 或共用 Checkpoint。四戶保持 SOURCE_REVIEW，完整同輪 C／Work9／Mentor 與其餘七組正式 envelope 由中 PM 鎖定上游後另整合。file:// 政策、真人登入及實機 UAT 的分列狀態沿用原規則；排版與全案 Gate 交中 PM 複驗，沒有自行宣告整體 PASS。


## 2026-10-31 四戶最新正式 DB 報告

排版與保存的 1fe71862 已由中 PM 於 PR60 issuecomment-6531741680 正式 PASS、缺陷 CLOSED。本輪依 issuecomment-6531912321 與私人施工單，新下載每戶正式 DB／Sources，以本次 bytes／SHA 為基準，由原 W5 read_snapshot → formal_report_source → OnDemandW6Renderer 產生各自新 run／current；沒有把舊凍結報告改名，也沒有沿用舊原生金融 result。

`w6_current_data.build_w6_current_data` 只在準備完成且已驗本人、DB SHA、snapshot tables digest、run、時點與 owner 的 SOURCE_REVIEW、沒有 canonical C、market 明示 verified=false／valuation_state=UNKNOWN／SOURCE_REVIEW_TIME_NOT_MARKET_VALUATION 時，容許缺 NAV。原有 unknown 分支保留已記錄數量與各自日期、已核准目標比例；current_total、目前權重／金額、目標金額、漂移及雷達仍 UNKNOWN。已知 C／完整計算及未附可信 sidecar 的舊入口不藉此放寬。公開 options/API 不增加欄位。

原 DB 的具日期申報／歷史參考可以由可信 operator producer 以原 source_views envelope 的 PARTIAL 引用；source_id、rules_sha、原件 as-of、scope、逐欄原值及來源保留。這些是 DB 原件，不代表正式金融研究完成，不把舊價或預計／已撤回本金變為本輪現值或可用額度。未供完整同輪 C／Work9／Mentor、FX、現金範圍及研究內容具名 UNKNOWN。核准目標與確認版本保持，既有外部核准文件沿原只讀驗證器，沒有新簽署或 DB 回寫。

唯一產生程式變更 w6_current_data.py；w6_member_render.py 與 1fe71862 byte-for-byte 相同。新增三項 adapter 與一項 browser 回歸；完整261項＋68子案例、11項Chromium，0 failures/errors/skips。四戶23／23／15／16共77頁，76張來源卡與全部逐頁PNG／PDF／HTML／ZIP／reader QA通過。

新20件原件依本人Sources原folder、新台灣時間檔名保存，舊報告歷史保留；全部全新下載核對bytes／SHA／private parent／run／DB／current及工程Menu12查閱。四份正式DB再新下載與本輪起始完全相同。Owner回交四份直接PDF、各戶HTML／ZIP，私人完成入口與完整回交ZIP使用實際台灣時間命名並存Drive根目錄／TEMP，含新20檔索引、來源版本／日期／缺項、測試、逐頁視覺及保存收據。中PM獨立驗收本輪報告，金融源組裝PR59沿原線待其另鎖版本；共用README／Checkpoint由中PM維護。
