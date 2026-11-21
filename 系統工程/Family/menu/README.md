最後修改日期時間：2026/10/25 09:28（台灣時間）
# Joseph 十四項選單與程式路由

版本：v1.13｜2026-10-24（台灣）
依指揮官最新決定執行。舊檔名前綴是穩定識別，畫面編號與操作鍵以本表為準；相對連結固定同一Git commit。

|編號|功能|操作鍵|規則／入口|
|---|---|---|---|
|01|第一次建倉|`first_allocation`|[01_第一次建倉.md](01_第一次建倉.md)|
|02|查看我的資料與持倉|`read_portfolio`|依Sources同版路由與正式handler|
|03|檢視與調整目標配置|`adjust_target`|[03_目標配置調整.md](03_目標配置調整.md)|
|04|評估現在各標的物投入速度|`deployment_pace`|[04_買賣與持倉調整.md](04_買賣與持倉調整.md)|
|05|尋找新標的物|`research_candidates`|[04_尋找新標的物.md](04_尋找新標的物.md)|
|06|安排新增投資資金|`new_funding`|[05_新增資金安排.md](05_新增資金安排.md)|
|07|查看目前總體經濟情況|`macro_link`|[07_總經網站.md](07_總經網站.md)|
|08|查看今日重大財經新聞|`market_news`|依Sources同版路由與正式handler|
|09|查看我的投資標的相關新聞|`holding_news`|依Sources同版路由與正式handler|
|10|更新生活狀況與投資需求|`update_profile`|依Sources同版路由與正式handler|
|11|記錄交易與資金變動|`record_event`|依Sources同版路由與正式handler|
|12|查看上次我的配置報告|`previous_report`|[12_查看配置報告.md](12_查看配置報告.md)|
|13|產生我的最新配置報告|`generate_report`|[11_產生配置報告.md](11_產生配置報告.md)|
|14|帳號：登出／修改密碼|`account`|[14_帳號管理.md](14_帳號管理.md)|

程式：`../W7/family_menu.py`。入口提供`project_name`與`login_account`建立`FamilyMenu`；登入帳號由各專案Sources指定。`welcome()`先介紹並請輸入密碼；`login()`交由注入的auth驗證後接續待辦；`select()`依新編號分流；`complete_work()`供選單及直接需求交付結果後完整顯示選單。私人功能由呼叫端提供的auth驗證，公開07直接回網站。
12／13共用`report_handlers()`接W6 `report_archive.py`。以Asia/Taipei時間命名，逐次新檔保存、同秒加序號、同run同內容去重、不同內容拒絕；產物讀回通過後才完成manifest，成功報告可查上次或指定日期。報告引擎、私有folder與同一writer lock由正式設定注入，不提供示範正式路徑。
驗收範圍：本輪路由、登入接續、選單呈現、報告日期命名與Drive協定合成測試。正式renderer／私有報告folder設定與真人端到端併入B07/B16，W7仍6/23。


<!-- USER_PROGRAM_ATLAS_LOCATION_REGISTRATION_20261031 -->
## 2026/10/31｜使用者要求之文件位置登錄（非中PM驗收裁定）

依使用者要求新增[全系統程式盤點與 V82 流程對照索引](https://github.com/a23882005/LivingWaterAI/blob/family/w8-complete-04-joseph-mou/%E7%B3%BB%E7%B5%B1%E5%B7%A5%E7%A8%8B/%E5%85%A8%E7%B3%BB%E7%B5%B1%E7%A8%8B%E5%BC%8F%E7%9B%A4%E9%BB%9E%E8%88%87V82%E6%B5%81%E7%A8%8B%E5%B0%8D%E7%85%A7/README.md)，保存於 `系統工程/全系統程式盤點與V82流程對照/`；閱讀版、頁次導航及完整程式位置見該入口。

程式盤點固定於 PR59 `5163116bcdedaabbc3cf09ae091ca96968a26fdd`：531 個原始碼檔（Python 525、PHP 4、CJS 2；含測試、工具及5個備份），不是531個獨立功能。main `591cf6256dc8942d68cf4441529b4b08391624b5` 對照為363個，兩分支不相加。11個HTML另列、不混入531。

此登錄僅為文件位置／來源對照交接，不代表中PM獨立驗收、PR合併、正式部署或金融Gate通過；原Owner、權限、規則、Checkpoint與驗收裁定完整保留，Production HOLD／交易NONE不變。舊文件中的數量、版本及交接包校驗值仍是各自歷史截點，不以本次盤點覆蓋。
