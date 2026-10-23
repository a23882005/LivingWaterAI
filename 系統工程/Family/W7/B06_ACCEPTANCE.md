# B06 驗收對照

| 原契約完成條件 | 直接證據 |
| --- | --- |
| 核驗、過期工作拒絕 | test_identity_before_io、test_expiry_after_backup_prevents_upload、test_logout_during_backup_stops_commit；session_guard每個提交邊界重查 |
| 競爭更新與排隊互斥 | test_competing_processes_merge_latest：8個獨立程序更新8筆；真實Drive兩worker合併後value=4、3筆唯一receipt |
| 最後完整讀者快照 | test_readers_get_complete_images：讀寫並行，每個讀者取得通過SQLite驗證的完整影像 |
| 備份、同ID回存、讀回 | test_backup_same_id_and_duplicate、test_adapter_same_id_backup_and_header_readback；真實Drive備份/提交/讀回，目標ID固定 |
| 實際還原 | test_restore_exact_bytes_rejects_old_work、test_restore_interrupted_retry；真實Drive原8192bytes完整還原，SHA256比對 |
| 交易及故障恢復 | test_real_process_exit_and_recovery、test_fresh_worker_resolves_uncertain_commit；真實worker exit73→新worker查已提交receipt，重試僅執行一次 |
| 外部改動與錯誤目標保護 | test_external_change_not_overwritten、test_moved_resource_rejected_before_write、test_bad_binding_and_alias_rejected |
| 表頭與維護權 | test_restore_backup_failure_releases_display_state、test_no_maintenance_role_cannot_restore；Drive MD同ID回Close，更新前備份及讀回 |

最終執行版本、Actions編號與逐位元還原結果以evidence/B06/closeout.json為準；前兩輪已成功結果保留於prior_runs.json。

B06驗收為共同I/O元件與Drive adapter；部署與帳號/登入由B07接入同一常駐服務，正式Actions由B18/B21接入已存在的共同佇列，四戶業務/完整系統由B23/W8驗證。全部由Family總PM本人循序完成。
