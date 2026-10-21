# Family BR v0.3.6｜已結案

正式狀態CLOSED／PASS_WITH_DECLARED_LIMITS，9/9工程項接收。依2026-10-21指揮官最新收斂指示，完整契約、九項證據、用途限制及後續責任以CLOSEOUT_DECISION.md為準。BR施工待辦已清零；W7先討論再開工。

## 已驗證成果

83項測試PASS；115原W5依賴/184來源固定；32節點來源鏈；23份CSV與92時間/用途邊界；官方VOO身分、200交易日、3次股息與分割比例核驗；GitHub可信封存時點；200筆真實行情11欄獨立重算一致；原W5安全Golden雙跑一致及合成完整正向Golden。

## 執行與交付

使用Python 3.12及requirements.lock。取得同ID Drive完整BR包與既有W5交接包後執行：

```sh
python -m pip install -r requirements.lock
python run_all.py /path/to/w5_handoff /path/to/evidence_output
```

W5交接需含repo/系統工程/Family/W5、baseline/sources、synthetic_evidence及market_intake。完整BR證據/fixture在Drive，GitHub為程式與治理版本；完整包不重複攜帶全部W5引擎。source_lock先校驗來源再匯入；可信呼叫端固定版本pin。run_all的historical_ready/br_major_gate為當時技術能力測試結果，行政結案狀態以CHECKPOINT及CLOSEOUT_DECISION為準；歷史log不改寫。

## 使用邊界

支援固定封存後唯讀重播，早於封存的逐bar首發時間及全真實完整策略用途仍受限制。SourceRegistry、UNKNOWN及拒絕保護保持；Adj Close使用既有稅前近似績效口徑，避免重複還原與重複加息。純計算callback應隔離執行，Python函式本身不提供OS沙箱。正式持久化、身分/Project隔離與runtime屬W7討論範圍。

Production HOLD、交易NONE、W4取消、RM17凍結。BR執行程式沿v0.3.5，本版為結案治理更新。

正式BR包：https://drive.google.com/file/d/1e6Pyuw9yy6RDNyLHTs812Vmaki4LVDnz/view
W5交接：https://drive.google.com/file/d/1lm3ss_YSN7VVaQDSRqDrJ_Zk40XhsCX0/view
Master：https://docs.google.com/document/d/1coxJ34aDseT09Oxo6OdiMlR6GmYm8RQckvnpr9KlRdo/edit
