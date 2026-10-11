# Canonical Schema 說明｜Work1 RECHECK v1.0.1

## FieldValueState
固定四態：`KNOWN / NONE / UNKNOWN / NOT_APPLICABLE`。
本版新增state/value結構一致性：KNOWN必須真的帶值；NONE/UNKNOWN/N/A不得殘留一個看似可用的value／amount／snapshot。

## DataQualityState
沿用：`OK / FALLBACK_USED / INSUFFICIENT / UNKNOWN`。UNKNOWN value不得同時宣稱DQ=OK。

## FreshnessState
`FRESH / STALE / UNKNOWN / NOT_APPLICABLE`只描述時效，不是投資判斷。

## B Native Status Preservation
B native sentinel／quality flag原樣保留於`source_native_status`／SourceReference；Work2才依B Sheet2正式正規化。

## Proxy
Proxy只服務獲授權Benchmark用途，不附著在Current／Proposed／Final Target配置標的本身。`USED`時必須有proxy instrument；`AUTHORIZED`時必須有authority reference。

## Allocation Versioning
三個Slot固定stage，不可錯接。Final Target只有`CONFIRMED`才可KNOWN；未確認不得由Proposed自動升格。

## Output Self-contained Traceability
Output新增`source_references`，並使用與Input相同的完整`BenchmarkReference`。這修正v1.0.0中Output traceability只能看到source ID卻找不到source內容，以及B reference被弱化的問題。

## Schema vs Business Logic
Schema只做資料契約的結構／狀態一致性與traceability，不計算Portfolio績效、Look-through、Macro、V82／V75部署。權重守恆、FX真正換算、B Row-level Data Quality等仍依後續Work分工處理。
