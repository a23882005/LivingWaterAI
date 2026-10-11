# V75 Work4｜Deployment State Selection Contract｜正式裁決 RECHECK2 FINAL

- Canonical Contract ID：`V75_DEPLOYMENT_STATE_SELECTION_v1.0.0_RECHECK2_FINAL`
- 裁決狀態：**APPROVED／Contract Hard Fail RESOLVED／Work4 RESUME AUTHORIZED**
- 唯一範圍：frozen Global Evaluation Precedence **Step 10**：`V75 v2.7.0 asset-specific branch → deployment_state`
- 上游 frozen：`V75_PREDICATE_PARAMS_v1.0.3`
- 下游 frozen：P0-02 `deployment_state → 0／25／50／75／100`
- **Work5：NOT RELEASED**

> 本版是對上一版裁決的可施工性 RECHECK。沒有修改 Root `債券V75.md v2.7.0`、PRED v1.0.3、P0-02、remaining gap、Funding／Settlement／Account Isolation、SGOV 三語意或 Work1～Work3。

## 1. 這版修正的四個可施工缺口

1. **`TRIM_WATCH` 對新資金全面固定 `PAUSE=0%`。** 不再允許「技術性減碼觀察」同時產生 25% 新買進。
2. **`TECHNICAL_NEUTRAL + VERY_ATTRACTIVE` 固定 `SMALL_BUY=25%`**，不再直接跳到 50%；沒有 LEFT/RIGHT 技術成熟時，只允許小額部署。
3. Existing Position 的 optional policy input 若為 `null/unknown`，**固定視為「不得自動賣出」**，只影響既有部位 action，不阻塞新資金 Step10。
4. 補齊 `asset_credit_class`、duration 邊界、cap 數值、direct veto 合併、reason/rule id 與 machine-readable 864-row duration matrix；工程端不得再自行猜。

---

# 2. Step 10 唯一輸入契約

## 2.1 Predicate

Step 10 **只在 PRED-001～010 全部 `assessment_status=VALID` 時執行**。任何一個不是 VALID，沿 frozen Data Quality contract 在 Step 1 fail-closed；Step 10 不得 fallback、不得把 UNKNOWN 當 safe、不得重新聚合 `sub_states[]`。

## 2.2 `asset_credit_class`

唯一 enum：

- `TREASURY`：產品 mandate 為 U.S. Treasury／T-bill／government-only，沒有 corporate-credit mandate。
- `CORPORATE`：產品 mandate 為 corporate-bond strategy。
- `MIXED`：產品 mandate 明確同時涵蓋 government 與 corporate-credit exposures。

來源：Work4 使用的 authoritative per-asset static risk profile／Authorized Universe product metadata。**缺值或無法唯一分類＝Step 10 前 `INVALID_INPUT`；不得靠 ticker 名稱猜。**

## 2.3 `effective_duration_years`

來源固定為 PRED-003 已使用的 authoritative duration input。合法值 `d >= 0`。

| Bucket | 唯一邊界 |
|---|---|
| `LE_1Y` | `0 <= d <= 1` |
| `GT_1Y_LE_3Y` | `1 < d <= 3` |
| `GT_3Y_LE_7Y` | `3 < d <= 7` |
| `GT_7Y_LE_12Y` | `7 < d <= 12` |
| `GT_12Y_LE_18Y` | `12 < d <= 18` |
| `GT_18Y` | `d > 18` |

---

# 3. 唯一 deployment ladder（P0-02 不變）

| deployment_state | deployment_pct | `deploy_amount` |
|---|---:|---|
| `HARD_WAIT` | 0 | `0` |
| `PAUSE` | 0 | `0` |
| `SMALL_BUY` | 25 | `remaining_target_gap_amount × 0.25` |
| `LEFT_BUY` | 50 | `remaining_target_gap_amount × 0.50` |
| `DEEP_LEFT_BUY` | 75 | `remaining_target_gap_amount × 0.75` |
| `RIGHT_COMPLETE` | 100 | `remaining_target_gap_amount × 1.00` |

`HARD_WAIT` 與 `PAUSE` 金額同為 0，但語意不得合併：`HARD_WAIT` 是 safety/structural hard veto；`PAUSE` 是暫停部署。

---

# 4. Safety veto／cap table（完整）

### PRED-010｜ETF Quality

| aggregate_state | TREASURY | CORPORATE | MIXED |
|---|---|---|---|
| ETF_QUALITY_ABNORMAL | HARD_WAIT | HARD_WAIT | HARD_WAIT |
| ETF_QUALITY_REVIEW_REQUIRED | PAUSE | PAUSE | PAUSE |
| ETF_QUALITY_UNKNOWN | PAUSE | PAUSE | PAUSE |
| ETF_QUALITY_NORMAL | continue | continue | continue |

`ETF_QUALITY_REVIEW_REQUIRED／ETF_QUALITY_UNKNOWN` 保持 **VALID semantic states**；不得轉 generic assessment failure。

### PRED-007｜System Liquidity

| state | TREASURY | CORPORATE | MIXED |
|---|---|---|---|
| SEVERE_ABNORMAL | HARD_WAIT | HARD_WAIT | HARD_WAIT |
| ABNORMAL | PAUSE | PAUSE | PAUSE |
| MIXED | cap 25% (`SMALL_BUY`) | cap 25% | cap 25% |
| NORMAL | continue | continue | continue |

### PRED-006｜Inflation

| state | TREASURY | CORPORATE | MIXED |
|---|---|---|---|
| LOSS_OF_CONTROL | PAUSE | PAUSE | PAUSE |
| INFLATION_REACCELERATION | cap 25% | cap 25% | cap 25% |
| NO_INFLATION_ALERT | continue | continue | continue |

長久期若再與 high policy + hawkish repricing + yield rise 共振，Section 5 可升級為 `HARD_WAIT`。

### PRED-004｜Credit OAS

| state | TREASURY | CORPORATE | MIXED |
|---|---|---|---|
| CREDIT_CRISIS | continue | HARD_WAIT | HARD_WAIT |
| CREDIT_STRESS | continue | PAUSE | PAUSE |
| HY_CRISIS | continue | HARD_WAIT | HARD_WAIT |
| HY_RECESSION_STRESS | continue | PAUSE | PAUSE |
| HY_WATCH | continue | cap 25% | cap 25% |
| HY_NORMAL | continue | continue | continue |

Treasury 的 `continue` 只表示「不把公司信用當成美國政府違約」；仍受 ETF quality、system liquidity、MOVE、inflation、Fed/yield path 約束。

### PRED-005｜MOVE

| state | TREASURY | CORPORATE | MIXED |
|---|---|---|---|
| EXTREME | PAUSE | PAUSE | PAUSE |
| SURGE | cap 25% | cap 25% | cap 25% |
| NORMAL | continue | continue | continue |

---

# 5. Duration-aware policy path（完整、唯一）

Helper 只在函式內計算，不是新 predicate：

```text
RATE_HIGH      = PRED-001 in {HIGH, EXTREME}
HAWKISH        = PRED-002 in {LARGE_HAWKISH_REPRICING, EXTREME_HAWKISH_REPRICING}
HAWKISH_EXTREME= PRED-002 == EXTREME_HAWKISH_REPRICING
YIELD_RISE     = PRED-003 in {SUSTAINED_SHARP_RISE, EXTREME_RISE}
YIELD_EXTREME  = PRED-003 == EXTREME_RISE
INFLATION_BAD  = PRED-006 in {INFLATION_REACCELERATION, LOSS_OF_CONTROL}
ADVERSE_COUNT  = int(RATE_HIGH)+int(HAWKISH)+int(YIELD_RISE)
```

每個 bucket 都採 **由上到下 first-match**：

### `LE_1Y`
1. `HAWKISH_EXTREME OR YIELD_EXTREME` → cap 25%
2. else → continue

### `GT_1Y_LE_3Y`
1. `HAWKISH_EXTREME AND YIELD_EXTREME` → PAUSE
2. `HAWKISH AND YIELD_RISE` → cap 25%
3. `HAWKISH OR YIELD_RISE` → cap 50%
4. else → continue

### `GT_3Y_LE_7Y`
1. `(RATE_HIGH AND HAWKISH AND YIELD_RISE) OR (HAWKISH_EXTREME AND YIELD_EXTREME)` → PAUSE
2. `HAWKISH_EXTREME OR YIELD_EXTREME OR ADVERSE_COUNT >= 2` → cap 25%
3. `ADVERSE_COUNT == 1` → cap 50%
4. else → continue

### `GT_7Y_LE_12Y`、`GT_12Y_LE_18Y`、`GT_18Y`
1. `RATE_HIGH AND HAWKISH AND YIELD_RISE AND INFLATION_BAD` → HARD_WAIT
2. `(RATE_HIGH AND HAWKISH AND YIELD_RISE) OR (HAWKISH_EXTREME AND YIELD_EXTREME)` → PAUSE
3. `HAWKISH_EXTREME OR YIELD_EXTREME OR ADVERSE_COUNT >= 2` → cap 25%
4. `ADVERSE_COUNT == 1` → cap 50%
5. else → continue

完整 864 組 duration/policy 組合已逐列固化在同包 JSON，不需要工程師把自然語言再翻一次。

---

# 6. Yield × Technical 唯一 base table

> row = PRED-009 TECHNICAL_ZONE；column = PRED-008 YIELD_ATTRACTIVENESS_ZONE。

| PRED-009 \ PRED-008 | LOW_ATTRACTIVENESS | FAIR | ATTRACTIVE | VERY_ATTRACTIVE |
|---|---|---|---|---|
| TECHNICAL_NEUTRAL | PAUSE 0% | PAUSE 0% | SMALL_BUY 25% | **SMALL_BUY 25%** |
| LEFT_MATURE | PAUSE 0% | SMALL_BUY 25% | LEFT_BUY 50% | DEEP_LEFT_BUY 75% |
| RIGHT_CONFIRM | PAUSE 0% | LEFT_BUY 50% | DEEP_LEFT_BUY 75% | RIGHT_COMPLETE 100% |
| TRIM_WATCH | **PAUSE 0%** | **PAUSE 0%** | **PAUSE 0%** | **PAUSE 0%** |

這張表同時回答 Hard Fail 回報中的兩個核心問題：

- `RIGHT_CONFIRM + ATTRACTIVE`＝**DEEP_LEFT_BUY 75%**。
- `LEFT_MATURE + VERY_ATTRACTIVE`＝**DEEP_LEFT_BUY 75%**。

`TRIM_WATCH` 是減碼觀察訊號，不是新資金正向確認；因此本版直接鎖成 0%，不再留下「可能買25%」的矛盾。

---

# 7. Cap 與 direct veto 精確演算法

Machine implementation **不要解析 `cap(SMALL_BUY)` 字串**；用數字 ceiling：

```text
SMALL_BUY cap = 25
LEFT_BUY cap = 50
DEEP_LEFT_BUY cap = 75
RIGHT_COMPLETE cap = 100
```

固定演算法：

```text
1. 收集 Safety table + Duration path 產生的所有 DIRECT 與 CAP。
2. 若任一 DIRECT=HARD_WAIT => final=HARD_WAIT, pct=0。
3. else 若任一 DIRECT=PAUSE => final=PAUSE, pct=0。
4. else base = Yield×Technical table。
5. 若 base=PAUSE => final=PAUSE。
6. 否則 strictest_cap_pct = min(all active cap pct); 無 cap 則=100。
7. final_pct = min(base_pct, strictest_cap_pct)。
8. pct→state 唯一反查：25=SMALL_BUY, 50=LEFT_BUY, 75=DEEP_LEFT_BUY, 100=RIGHT_COMPLETE。
```

`continue`＝不新增 DIRECT、不新增 CAP。禁止 Slow／Normal／Fast、禁止乘第二套 multiplier。

### Reason code

每一條 rule 使用 JSON 中固定 `rule_id`。final output 至少保存：

```text
step10_rule_ids[]
step10_direct_veto_rule_ids[]
step10_cap_rule_ids[]
step10_base_rule = "C_<TECHNICAL>_<YIELD>"
```

這樣 QA 可以逐筆重現「為什麼是25%、50%或0%」。

---

# 8. Existing Position action（不再留 null 自由解讀）

唯一 enum 不變：

`HOLD | REBOUND_SMALL_SELL | TECHNICAL_TRIM | TRUE_RISK_REDUCTION | NOT_APPLICABLE`

## 8.1 必要／optional inputs

| input | type | 缺值行為 |
|---|---|---|
| `current_position_quantity` | Decimal `>=0` | required；非法值→Step10前 INVALID_INPUT |
| `capital_gain_harvest_eligible` | bool/null | null＝**false for auto-sell**；不得自行估門檻 |
| `rebound_reduction_eligible` | bool/null | null＝**false for auto-sell** |
| `investment_logic_invalidated` | bool/null | null＝**false for auto-sell** |

來源：前者為 Work3/canonical broker position；後三個必須由 authoritative Client/Portfolio policy 或 V75 rule-owner result 提供。**Work4／LLM 不得自行把 null 猜成 true。**

## 8.2 Ordered rules

1. `current_position_quantity <= 0` → `NOT_APPLICABLE`
2. `investment_logic_invalidated == true` → `TRUE_RISK_REDUCTION`
3. `asset_credit_class in {CORPORATE,MIXED} AND PRED-004 == CREDIT_CRISIS` → `TRUE_RISK_REDUCTION`
4. `capital_gain_harvest_eligible == true AND PRED-009 == TRIM_WATCH AND PRED-008 == LOW_ATTRACTIVENESS` → `TECHNICAL_TRIM`
5. `rebound_reduction_eligible == true AND PRED-009 == RIGHT_CONFIRM` → `REBOUND_SMALL_SELL`
6. else → `HOLD`

## 8.3 No-churn

- `TRUE_RISK_REDUCTION` → new-money final 強制 `HARD_WAIT=0%`
- `TECHNICAL_TRIM`／`REBOUND_SMALL_SELL` → new-money final 強制 `PAUSE=0%`
- `HOLD`／`NOT_APPLICABLE` → 不覆寫 new-money result

## 8.4 Numeric sell amount

`existing_reduction_pct = null` **仍然固定**。這不是缺漏，而是上游明令禁止 Work4 自創 10%／20% 等賣出比例。Work4 可以 deterministic 決定 semantic action，但不得產生不存在於 SOT 的 numeric sell amount。

---

# 9. Root 有提到、但本 Step10 不得偷偷新增的訊號

Root 另討論 real yield、term premium、Treasury supply 等因素；但 frozen PRED-001～010 **沒有獨立 machine predicate** 對應它們。

因此本次裁決：

> **Work4 不得自行新增 PRED-011、不得自行發明 term-premium／real-yield threshold。**

它們可留在報告解釋／未來治理版本，但不能在本次 Step10 成為隱藏條件，否則又會破壞「零自由解讀」。

---

# 10. Canonical Step10 pseudocode

```text
assert all(PRED-001..010 assessment_status == VALID)
assert asset_credit_class in {TREASURY,CORPORATE,MIXED}
assert effective_duration_years >= 0

safety_actions  = lookup_A_tables(...)
duration_action = lookup_864_row_duration_matrix(...)
base_state       = lookup_C_matrix(PRED-009, PRED-008)

directs = safety_actions.directs + duration_action.direct
caps     = safety_actions.caps    + duration_action.cap

if HARD_WAIT in directs:
    new_money_state = HARD_WAIT
elif PAUSE in directs or base_state == PAUSE:
    new_money_state = PAUSE
else:
    cap_pct = min(caps) if caps else 100
    final_pct = min(P0_02_pct(base_state), cap_pct)
    new_money_state = pct_to_state(final_pct)

existing_action = evaluate_existing_position_ordered_rules(...)
apply_no_churn(existing_action, new_money_state)

return exactly_one(deployment_state), exactly_one(ExistingPositionAction)
```

---

# 11. Work4 Resume mandatory tests

至少包含以下 assertion；JSON＋驗證程式另做完整 coverage：

1. `ETF_QUALITY_REVIEW_REQUIRED`／`ETF_QUALITY_UNKNOWN` 都是 VALID semantic，downstream=`PAUSE=0`。
2. Treasury + CREDIT_CRISIS 不因公司信用直接 hard wait。
3. Corporate/Mixed + CREDIT_CRISIS=`HARD_WAIT=0`。
4. System liquidity SEVERE=`HARD_WAIT=0`；ABNORMAL=`PAUSE=0`；MIXED cap=25。
5. Inflation LOSS=`PAUSE=0`；REACCEL cap=25。
6. MOVE EXTREME=`PAUSE=0`；SURGE cap=25。
7. `1<d<=3` + LARGE_HAWKISH + SUSTAINED_SHARP_RISE → cap 25。
8. `1<d<=3` + EXTREME_HAWKISH + EXTREME_RISE → PAUSE。
9. `3<d<=7` + HIGH + LARGE_HAWKISH + SUSTAINED_SHARP_RISE → PAUSE。
10. `d>7` + HIGH + HAWKISH + YIELD_RISE + INFLATION_BAD → HARD_WAIT。
11. TECH_NEUTRAL + VERY_ATTRACTIVE=`SMALL_BUY=25`。
12. LEFT_MATURE + VERY_ATTRACTIVE=`DEEP_LEFT_BUY=75`。
13. RIGHT_CONFIRM + ATTRACTIVE=`DEEP_LEFT_BUY=75`。
14. RIGHT_CONFIRM + VERY_ATTRACTIVE=`RIGHT_COMPLETE=100`。
15. 任意 TRIM_WATCH × 任意 yield zone=`PAUSE=0`。
16. cap50 + cap25 → cap25。
17. direct PAUSE + bullish base → PAUSE。
18. direct HARD_WAIT + anything → HARD_WAIT。
19. optional existing sell flag=null → 不得自動 sell。
20. Existing TRUE_RISK_REDUCTION → new money HARD_WAIT；trim/rebound sell → new money PAUSE。
21. `existing_reduction_pct` 永遠 null。
22. 任一 legal Step10 input combination 必須 exactly-one deployment_state，且只能為 frozen 六態之一。

---

# 12. Formal decision

**RECHECK2 FINAL：APPROVED。**

- Contract Hard Fail＝**RESOLVED**
- Work4＝**RESUME AUTHORIZED**
- Work1～Work3＝維持 CLOSED
- Work5＝**NOT RELEASED**

Work4 應直接使用本 MD＋同包 machine-readable JSON 實作，不得再回頭自由解讀 Root 自然語言；QA PASS 前不得進 Work5。
