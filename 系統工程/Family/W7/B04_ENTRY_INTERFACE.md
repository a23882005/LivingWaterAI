# B04 家人共同入口實作與接線

2026-10-23｜總PM本人｜契約v1.6.0｜B04進行中

## 本輪交付

`probes/family_entry_probe.py`為能啟動的HTTP合成入口，使用Python標準函式庫。
`tests/test_family_entry_probe.py`以真實HTTP請求、不同連線、獨立服務程序重啟、並行Chat/Action請求驗證介面。
GitHub workflow `family-w7-capability-probe.yml`已接入同一組測試。

入口仍屬B04能力探測；正式DB存取管理依B06實作。這份程式只接受synthetic-開頭的測試身分及自有合成狀態庫；非探測DB拒絕開工且保留原bytes。

## 簡化身分與登入

- 每條已認證連線的Bearer key由服務端映射為家人帳號與chat/action用途，服務設定只存key的SHA256；不依請求中自填的帳號/Project決定權限。
- 測試key在執行時隨機產生；環境變數`FAMILY_PROBE_PRINCIPALS_JSON`提供digest→account/kind映射。正式認證的token取得、撤銷與保管尚待接服務，這裡沒有真人帳密。
- `/login`建立固定14400秒登入；有效期內重複登入、讀取、`/resume`都保留原到期時間。
- 同帳號的新HTTP連線與服務程序重開均能接續原session；同帳號跨裝置共用此業務session。Project作對話整理；API不接受Project欄位提升存取權。
- `/logout`撤銷同帳號業務登入；到期重新登入或登出，舊佇列工作取消，避免舊工作在新登入下執行。
- Action憑證映射指定帳號，使用同一業務session，不能代家人啟動或延長登入。正式批次策略於B18依核定契約接線。

## 單一入口

全部為POST JSON、Authorization: Bearer；成功回傳scope=SYNTHETIC_ONLY。

|路徑|輸入|回覆用途|
|---|---|---|
|/login|空物件|固定四小時session；chat用途|
|/resume|空物件|同帳號原session、到期時間|
|/logout|空物件|登出並取消未執行工作|
|/read|空物件|本戶合成計數與待辦筆數|
|/submit|request_id、整數delta|排隊回執；同ID同內容去重，異內容409|
|/status|request_id|本戶工作QUEUED/DONE/CANCELLED與結果|
|/drain|空物件|按提交順序完成本戶合成工作|

未知欄位/路徑、無效JSON、超大內容、錯誤憑證都有固定錯誤碼。狀態及回覆不含憑證。單一SQLite交易涵蓋合成資料變更與回執，避免提交前後中斷造成重複套用；讀者只看到完整提交。這項原子性範圍是合成SQLite，不延伸宣稱Drive檔案上傳已具備同樣原子性。

## 啟動與測試

從repo根目錄執行：

```sh
python -m pytest 系統工程/Family/W7/tests/test_family_entry_probe.py 系統工程/Family/W7/tests/test_session_queue_probe.py 系統工程/Family/W7/tests/test_work12_source_contract.py -q
```

單獨啟動時，先於執行環境設定隨機測試key的digest映射，再執行：

```sh
python 系統工程/Family/W7/probes/family_entry_probe.py --state /tmp/family-synthetic-probe.db --port 0
```

只綁定127.0.0.1；stdout輸出實際port，未部署公網服務。合成庫與key不納入GitHub或工作包。

## 接續施工所需的外部連線

本回合工具清單沒有Hostinger管理工具；本執行環境的Codex設定亦沒有Hostinger MCP註冊，無Codex CLI。未取得可驗證的既有Family服務端點或服務端Drive授權。Hostinger技能的註冊/OAuth需要應用程式宿主配合，遠端暫存執行環境的設定不等於指揮官Android應用程式已連線。

下一步由總PM本人接上既有託管環境的可用管理連線，核對服務能力及既有授權後，於TEMP合成資源實測Chat與Action共用入口、Drive下載/備份/同ID回存/讀回。正式家人/共用/帳號DB仍只存Drive。實際ChatGPT跨對話登入與Action到Drive端到端驗證保留為B04未結事項。

B04完成上述實證才簽收並接B05～B23。W7仍3/23；Production HOLD、交易NONE、W4取消、RM17凍結。
