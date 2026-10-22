# B04正式驗收｜最小能力實測PASS

2026-10-23｜Family總PM本人｜依原契約v1.6.0裁定，未修改完成條件。

## 契約與裁定依據

本輪重新讀取main 109e99eaa2a760fc7ddc1fbf13c18e25f7540d35的《Family_W7_施工規劃與契約.md》。B04原文限定「合成資料與最小原型能力探測」，並明定正式共同寫入管理於B06、正式Action於B18/B21分別驗收。完成條件是合成實證入口、授權、回存及可行接線依據；補正條款採已驗證家人帳號識別，不以原生Project/device ID為前置。

前回Checkpoint將正式MCP服務、真實ChatGPT跨對話與長期OAuth列為B04整項阻擋，超出此項能力探測範圍。本輪撤回這個由PM自行增加的結案條件，保留實測成果與未完成工作，按原契約裁定B04 PASS。這是工序與驗收歸屬修正，不是新增功能PASS。

|B04完成條件|實證|
|---|---|
|最小可執行入口、受信任帳號映射、錯誤回覆|既有20項HTTP測試及18項HTTPS驗收；伺服器key digest映射合成帳號，外部account欄位拒絕|
|Actions執行及Drive服務授權|readiness真實OAuth刷新/讀取；run39866437563的10項故障邊界及TEMP同ID回存/復原|
|共同寫入、競爭與去重|run39869009274：14項程式測試、27項HTTPS/Drive整合檢查，兩種連線共用queue、單主機flock、獨立Drive讀回|
|中斷恢復與session交界|上傳後exit73、重新處理不重複；登出再登入補齊DONE；錯戶拒絕；過期寫入檢查|
|資料還原與可追溯證據|同ID恢復原8192 bytes，私密設定/臨時入口清理PASS；evidence/B04/shared_writer_action_run.json|

## 正式接線設計與後續責任

採既有HTTPS主機、單一共同queue/writer與Drive同ID存檔；ChatGPT透過MCP工具介面及OAuth識別家人帳號。Drive後端OAuth與家人服務登入分開。官方文件已核對：ChatGPT支援OAuth授權碼及S256 PKCE、預設OAuth client或動態註冊、Streamable HTTP。正式認證優先沿成熟identity provider/標準實作，不以目前合成key冒充ChatGPT已完成連線。

- B06：將已驗證的queue、journal、backup/restore、權限核驗接至正式資源管理；維持唯一writer。
- B07：家人帳號與登入服務、MCP/OAuth身分接線、固定四小時與跨對話接續；Google長期授權服務設定由本人在這一接線階段完成。
- B18/B21：正式Action資料流程接同一writer。
- B23：四戶、跨對話/裝置切換、真實保存讀回及完整接口驗收；補上實際四小時到期與服務暫時離線情境。
- W8/Gate D後部署：全系統端到端驗收、四戶正式安裝/部署與試用。仍由本人循序負責。

本輪結案只覆蓋B04合成實測範圍。實際ChatGPT連線、常駐服務、Google長期授權及正式四戶上線尚待上述工序完成；這些工作均列入Checkpoint後續責任，不刪除或宣稱通過。Production HOLD、交易NONE、W4取消、RM17凍結。

正式進度：B01～B04完成，4/23；下一項B05。

官方接線參考（2026-10-23讀取）：
- https://developers.openai.com/plugins/build/auth
- https://developers.openai.com/api/docs/guides/custom-mcp-server
- https://modelcontextprotocol.io/specification/2025-06-18/basic/transports
