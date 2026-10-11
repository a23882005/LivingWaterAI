# C Error／Warning／Blocking Reason Contract｜v1.0.1（RECHECK修正版）

## Issue共同欄位
`code / severity / field_path / message / owner / blocking / source_reference_ids[]`

結構不變量：`severity=BLOCKING`時`blocking`必須為true；反向不強制，因某些INFO/WARNING狀態（例如NOT_RUN fixture）可以阻擋正式輸出但不代表系統故障。

## 保留／新增 Code
| Code | Default Severity | 用途 |
|---|---|---|
| C_SCHEMA_REQUIRED_MISSING | ERROR | Required欄位缺失 |
| C_SCHEMA_TYPE_INVALID | ERROR | 型別不符 |
| C_SCHEMA_ENUM_INVALID | ERROR | Enum不合法 |
| C_STATE_VALUE_INCONSISTENT | ERROR | value_state與value／snapshot互相矛盾 |
| C_ALLOCATION_STAGE_MISMATCH | ERROR | Current／Proposed／Final Target Slot與stage錯接 |
| C_CONFIRMATION_STATE_INCONSISTENT | ERROR | confirmation_status與confirmed_at/by或Final Target身分矛盾 |
| C_FORMAL_OUTPUT_STATE_INCONSISTENT | ERROR | eligible／scope／blocking reason互相矛盾 |
| C_TRACE_SOURCE_REFERENCE_MISSING | ERROR | trace／issue引用不存在的source_id |
| C_IDENTITY_RUN_ID_MISMATCH | BLOCKING | 同輪run_id不一致 |
| C_SOURCE_SOT_MISMATCH | BLOCKING | Formal SOT身分不符 |
| C_SOURCE_FINGERPRINT_MISMATCH | BLOCKING | 檔案／來源指紋不符 |
| C_DATA_STALE | WARNING/ERROR | 資料過期；是否Blocking由Requiredness決定 |
| C_SOURCE_NATIVE_STATUS_UNMAPPED | ERROR | 上游native sentinel尚未合法映射 |
| C_DATA_INSUFFICIENT | ERROR | Required資料不足 |
| C_DATA_UNKNOWN_REQUIRED | BLOCKING | Required欄位UNKNOWN且足以改變正式結果 |
| C_OPTIONAL_DATA_UNKNOWN | WARNING | Optional欄位UNKNOWN |
| C_FALLBACK_USED | WARNING | 合法Fallback已使用 |
| C_PROXY_USED | WARNING | 合法Proxy已使用，必須揭露 |
| C_PROXY_UNAUTHORIZED | BLOCKING | 未授權Proxy |
| C_FX_REQUIRED_NOT_AVAILABLE | BLOCKING | 跨幣別正式金額需要FX但不可用 |
| C_UNSUPPORTED_BY_BASELINE | BLOCKING | B基準不足以支持所要求Portfolio級正式指標 |
| C_FORMAL_OUTPUT_BLOCKED | BLOCKING | Formal Output Gate未通過 |
| C_PARTIAL_OUTPUT | WARNING | 僅部分欄位可正式輸出 |
| C_MODULE_NOT_RUN | INFO | 模組尚未執行；可阻擋正式輸出，但不代表runtime錯誤 |
| C_CROSS_MODULE_CONFLICT | BLOCKING | 模組輸入／輸出互相矛盾 |
| C_RUNTIME_NOT_READY | BLOCKING | 後續Runtime尚未可正式整合 |
| C_INTERNAL_ERROR | ERROR | 非Business Rule的內部錯誤 |

## 邊界
這些Code是C整合層資料／流程狀態，不得拿來新增V70/V82/V75 Business Rule，也不得把B資料品質問題改寫成市場Hard Gate。
