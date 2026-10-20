# W5-09 技術來源與逐欄接線規格（證據版）
查核時間：2026-10-21（台灣）。接收基線：PR22 dd248d99b16079d947d07095b3c2b26fb0eb7d0d。W5-16已完成；本文不重開16、不修改V82策略、不宣稱09正式驗收完成。


## 1. 可直接指定的既有來源
A. Yahoo數值producer：emmanuelwithme/OpenDataStockAnalysis，PR3，feature/yahoo-finance-research-20261010，commit cd1e1dbc9fd7e226a0c31efe80def9ffb5f947cb。
- yahoo_pipeline/yf_pipeline/analytics.py，Git blob 4122af35a3a38824123cfff623b0c84c4f631f1f：td9(s)、technical(df)。
- yahoo_pipeline/yf_pipeline/collector.py，Git blob a0f68540ba25981055a063cf16c37526d893b6f1：fetch/clean/run。
- 輸入period=max、interval=1d、auto_adjust=False、actions=True、repair=False；技術用Close/High/Low/Volume，績效才用Adj Close。
- 程式執行時的預期輸出路徑（非已取得本日snapshot；outputs被gitignore，repo不含產出原件）：yahoo_pipeline/outputs/technical_summary.json {generated_at_utc,records:{ticker:{market_date,high_td9_setup,low_td9_setup,kd_k_9_3,kd_d_9_3_3,macd_12_26,macd_signal_9,macd_histogram,ma5,ma10,ma20,ma50,ma60,ma200,emv_14,rsi14,atr14,volume_ratio_5,volume_ratio_20,volume_ratio_50}}}。
- 價格：outputs/latest_snapshot.json；原序列：data/history/<sanitized_ticker>.csv.gz；品質：outputs/data_status.json。
- PR3仍open/unmerged；此為已存在候選數值producer，不等於已核准當前V82正式全套producer。


B. Swing／舊TD9原函數：
Drive https://drive.google.com/file/d/1mGDibX1isqmDEVRIRP6Iv4enMNlx2LDb/view
v82_engine.py，Engine v0.5.0／Rule v1.10.0，28426bytes；SHA256 a8b6f302489ada28c637685fb0aba4cb8251c2df38db562b6fdbedb11d95a1fb。
calculate_td9(closes)、confirmed_swing_lows(lows)、confirmed_swing_highs(highs)。
已驗證正式Work21完整包內W12 RECHECK4 checkpoint也有：
SOURCE_PACKAGE/UPSTREAM_V82/A78_A79_Runtime_W12_E07_RECHECK4_QA_PASS_完整繳回包_2026-09-26_0928.zip
→ A78_A79_Runtime_W00_W01_W02_W03_W04_W05_W06_W07_W08_W09_W10_W11_W12_E07_RECHECK4_QA_PASS_Checkpoint_2026-09-26_0926.zip
→ Latest_Working/E07_Evidence/legacy_baseline_readonly/v82_engine.py
外層 https://drive.google.com/file/d/1GQHdYPwxFKZBFM1GbTAsTDXA48FYxrmA/view
只重用已核對函數與其原始語意，不導入Legacy舊策略／Boolean預設False。


C. Rule SOT：
V82.md v1.21.0，https://drive.google.com/file/d/1EObD96ptt3Io_YtTNGTWW1bms30wKguz/view
工程23 TD9、24 KD/MACD/MA、25 EMV/RSI/Volume、26多週期、原章26/27 Swing、工程42/43 Right/Runaway、Work7-A Candidate治理。
消費器：LivingWaterAI/系統工程/Family/W5/stock_engine.py::run_stock_engine；
正式聚合：系統工程/股票V80/正式Runtime/v82_runtime_greenfield/src/livingwater_v82_runtime/core_rules.py::evaluate_technical。
既有聚合必須原樣呼叫，不能另寫策略計票。


## 2. Intake envelope逐欄來源與防偽
producer：明列A的repository/module/function；version：鎖完整commit，不用latest。
source_reference：指向原始history或snapshot、digest及採集receipt，不只填「Yahoo」。
asset_id：由原symbol與W1 instrument具名對照，不猜別名。
exchange/currency：A的technical_summary沒有，必須取已核對的instrument/provider metadata；禁止從ticker後綴猜。
timeframe：A是DAILY。週/月不能把daily latest改標，需另有completed週/月序列；TD9正式僅DAILY。
adjustment：保留auto_adjust=False、公司行動欄、實際provider價格口徑與版本。auto_adjust=False不能被簡化成「從未調整」或保證分割連續；未核對公司行動/拆股處理時相關結果UNKNOWN。
parameters：逐指標記錄實際公式、平滑/seed/min_periods，不能只有9,3,3等名稱。
price_field：Close。不可拿Adj Close替換，除非原正式規則明確核准。
sample_state：僅在交易日曆＋正式收盤與正式Close可用證據成立時COMPLETE。collector只有market_date，未證明該日已收盤；不得硬填。
as_of：原bar的completed session時間，不能把market_date硬湊午夜冒充市場收盤。
available_at：原資料最早可靠可取得時間。collector的generated_at_utc在download loop之前建立，不是下載完成時間，不能直接當available_at。clean還會去timezone並normalize為日期；status=ok不證明COMPLETE。需原provider session timezone/calendar、該bar正式收盤及正式Close可用證據，另記實際fetch完成/產物寫完receipt；沒有這些原證據則時間可用性UNKNOWN，不能反推歷史PIT。
evaluated_at/run_id：W5分析envelope；原source_run/digest另外保留，禁止改寫原事實。
swings[].confirmed_at：原pivot index i對應右側第二根completed bar i+2的確認可用時間；應同時存pivot_session、confirmation_session、source available_at。缺交易日曆/availability證據不能硬推精確UTC。
所需列表不可空以規避檢驗；每個具名signal保留TRUE/FALSE/UNKNOWN與reason、依賴欄位、SOT節、來源digest。缺值不填False/0。


## 3. 基礎數值與事件，可沿既有程式＋原規則接線
記t為本timeframe最後一根合格Completed Bar；p=t-1。所有比較需同一價格口徑、同標的、同timeframe。UNKNOWN依依賴局部傳播。


TD9：直接重用td9(close)或calculate_td9，Close[t]>Close[t-4]高序列+1/低歸0，反向相反，相等兩者0，最高9，同方向持續9不重複建立completed事件。工程23要求無cache時至少13根連續交易session有效Close；缺High/Low/Volume不能污染TD9。0=INACTIVE，1..8=COUNTING，9=COMPLETED；欠資料=UNKNOWN非0。需從原序列保留首次到9事件與後續狀態，不只取最後tuple。


Swing：直接重用confirmed_swing_lows/highs。pivot Low[i]嚴格小於前2後2個Low；High對稱大於；相等不是pivot；i+2未completed則僅PROVISIONAL，不能列confirmed。以時間排序保留最近至少三個confirmed lows/highs與index/value，不能從最新摘要反推。


KD：A使用RSV9後SMA3再SMA3。正式SOT只鎖9,3,3；因KD不同平滑/seed常同名，不可僅參數名稱宣告等價，須確認此SMA版本是否為指定原公式。
已批准同一K/D序列後：golden=(K[p]<=D[p] and K[t]>D[t])；death反向；oversold=(K<20 or D<20)；overbought=(K>80 or D>80)；rising=(K[t]>K[p] and D[t]>D[p])；falling反向；分歧MIXED。


MACD：DIF=EMA12(Close)-EMA26(Close)，DEA=EMA9(DIF)，H=DIF-DEA；A用ewm(adjust=False,min_periods=相應period)。cross按p和t；同符號abs(H[t])>abs(H[p])為expanding，<為contracting；跨零先列direction switch；DIF上升=DIF[t]>DIF[p]。工程24明確相鄰completed-bar比較，不自行加連續2根。
MA：SMA最近N根completed Close，N=5/10/20/50/60/200；不足N=UNKNOWN。reclaim20=(Close[p]<=MA20[p] and Close[t]>MA20[t])；breakdown反向。ABOVE與reclaim事件分欄。Canonical全alignment為5>10>20>50>200，但Runaway Up原清單中的3MA signal只比較5>10>20，不能擴大為5MA門檻。
EMV：SOT3,3；A目前emv_14，不可直接映射。需指定原3,3公式/平台/seed才啟用EMV數值；之後positive=E[t]>0，negative<0，rising/falling比p，轉正為E[p]<=0且E[t]>0。不得把14改名3,3。
RSI：A rsi14採ewm(alpha=1/14,adjust=False,min_periods=14)並處理全漲100/全跌0/平50；鎖方法後保留值與range；<30 oversold、>70 overbought；>70→<=70為EXIT_OVERBOUGHT。背離另見第5節。
ATR：A atr14=EWMA(alpha1/14) of max(H-L,abs(H-Cprev),abs(L-Cprev))，min14；可保存數值，但「快速擴張」沒有已核准速度門檻不能由數值自行造。
Volume：5/20均量，必要時50；A ratio_N=V[t]/SMA_N(V)。正式比較不足N=UNKNOWN。不得以ratio>1直接等價「爆量」；量價方向與突破結構需分開保留。


## 4. V82五個向量的具名映射
固定順序可由adapter manifest指定，但每項名稱及來源必須獨立保留；同一底層事件別名不可重複計票。下列「可映射」指原規則明確；不是聲稱現有technical_summary已直接提供所有向量。


right_signals（10項原清單）
R1 higher_low：最近兩個已確認同週期Swing Low的後者value>前者value；保留兩個pivot/confirmed_at。語意直接比較可映射；是否額外要求「明顯」不得新增幅度。
R2 kd_golden_cross：依第3節。
R3 macd_bear_hist_shrinking_or_positive：空方柱縮短H[t]<0且同負號abs下降；「翻正」可由H[p]<=0,H[t]>0事件映射。Legacy名稱包含or_positive而原規則寫「或翻正」，不得默認所有持續H>0永遠算新翻正；需明確採事件或持續state的原接口裁定。
R4 dif_up：DIF[t]>DIF[p]。
R5 emv_positive：清單原文「轉正」；consumer舊名positive不等同cross事件。待原3,3序列與state/event語意核定，不填emv14。
R6 rsi_improving_or_near_50：正式有30～50持續回升，但「附近」容差及「持續」根數未量化；不能自行設48/49或2/3根。原正式producer證據未提供則UNKNOWN。
R7 above_ma20／站回MA20：正式reclaim20事件可算，above state另存；不得靜默將舊名above等同站回。
R8 volume_breakout：需要下降趨勢線/突破原件與量能判定；數值producer沒有趨勢線。UNKNOWN，不新建回歸線/lookback。
R9 pressure_breakout：若上游明指該壓力=特定confirmed Swing High，可記Close越過該level事件；未指定近期壓力選取/有效性時UNKNOWN，不能自行用20日高替換。
R10 breakout_retest_success：需原episode/突破level/回踩成功證據；容差、持續期間未核定時UNKNOWN。
Right是threshold_truth(signals,3)，但工程42完整Right entry還有離開最低點及安全條件；不要把純技術count冒充完整買進許可。


up_price（3項）
U1 new_20d_close_high：SOT明定20日收盤新高；可依同市場日K保留20日窗口與最高值，但窗口「前20根不含t」vs「含t的20根」以及tie處理須由原producer定義核定，不能無聲選一種。
U2 break_confirmed_swing_high：原文收盤突破前一confirmed Swing High。需指定所用level及其confirmed_at≤分析時點；價格跨越事件可比較Close[p]<=level,Close[t]>level；state Close[t]>level另列。若套noise band只能UNKNOWN，0.25ATR不是正式值。
U3 higher_high_higher_low：最近兩個confirmed highs後者較高且兩個lows後者較高可生成基礎structure facts；「明顯」以及HH/HL是否需交錯同episode沒有完整定義時，不把基礎facts強升此predicate。


up_confirm（8項）
C1 kd_high_strong_not_breaking：高檔可保存K/D>80等原狀態與death_cross；「鈍化」「非死叉崩落」無完整持續／崩落定義，不能用overbought AND NOT death自創等價，UNKNOWN。
C2 macd_bull_hist_expanding：H[t]>0，H[p]>0，abs(H[t])>abs(H[p])。
C3 ma5_gt_ma10_gt_ma20：三個已知SMA嚴格鏈。
C4 emv_positive_or_improving：在3,3原序列核定後 E[t]>0 OR E[t]>E[p]；目前EMV14不接。
C5 price_volume_healthy：四象限事實可提供；「健康」未完整機械定義，不能任選象限=TRUE。
C6 high_td9_then_new_high：有TD9首次9事件及其後新高事實可提供；原事件有效期／新高參照點未指定則UNKNOWN，不能拿當前td9==9取代after事件。
C7 rsi_high_no_divergence：高檔>70事實可算；沒有可比較confirmed Swing不代表「無背離」而是UNKNOWN；詳第5節。
C8 eps_guidance_not_worse：非技術來源，不由OHLCV合成；沿原基本面producer，缺則UNKNOWN。
RunawayUp=AND(threshold(up_price,1),threshold(up_confirm,3),ma20_ok)。


down_break（3項）
D1 keeps_breaking_lows：可提供confirmed lows的下降結構，但「持續」有效期/根數與比較對象未定時UNKNOWN。
D2 break_confirmed_swing_low：與U2對稱，Close[p]>=level且Close[t]<level為跨越事件；state另存，使用原指定confirmed Swing Low。
D3 break_support_no_quick_reclaim：重要支撐來源、明顯跌破及快速收復時窗都須具名；未給不自己填天數或ATR比例，UNKNOWN。


down_accel（8項）
A1 macd_bear_hist_expanding：H[t]<0,H[p]<0,abs(H[t])>abs(H[p])。
A2 kd_low_weak：oversold與falling可供事實；原「續弱」持續條件無正式數值，UNKNOWN，不自創組合。
A3 emv_worsening：3,3同序列相鄰下降可供事實；「持續惡化」期間未核定則UNKNOWN。
A4 rsi_falling：RSI[t]<RSI[p]是相鄰下降事實；若原「續跌」要求持續，期間未核定前不擅加，原predicate保持UNKNOWN。
A5 price_down_volume_up：Close[t]<Close[p]且Volume相對指定同口徑baseline增大；須由原source指定是前bar還是MA5/20，不能看到ratio20>1便稱原語意已核定。
A6 atr_expanding_fast：ATR數值存在，fast門檻缺，UNKNOWN。
A7 decline_accelerating：跌速比較窗口/報酬口徑未定，UNKNOWN。
A8 rebounds_weaker：反彈episode/Swing配對/弱化標準未定，UNKNOWN。
RunawayDown=AND(threshold(down_break,1),threshold(down_accel,2))。


ma20_ok：「未明顯跌破MA20」非必然等於Close>=MA20。可提供ABOVE/AT/BELOW及cross事件，但不能私填明顯的band。consumer雖預設TRUE，W5應explicit傳UNKNOWN直到原口徑核定，不能用default掩蓋資料缺口。


## 5. 背離／突破剩餘窄裁定（不是重新發明全算法）
RSI背離：正式只允許價格與RSI具有可比較的confirmed Swing結構。可交付候選配對的兩個price pivot、對應RSI值、各自時間與確認時間。價格創高/RSI未創高是可觀察事實，但「取價格pivot時的RSI」或「獨立RSI swing配對」、嚴格/非嚴格、配對窗口未明文確定，不能自行核定完整divergence。缺可比較pair=UNKNOWN，不是NO_DIVERGENCE。
突破：可提供指定Swing level的Close cross；「近期壓力」「下降趨勢」「回踩成功」「快速收復」缺原level/episode/lookback時保持具名UNKNOWN。
硬禁止：Work7-A明定B-3的MACD連續2完成bar、0.25×ATR noise band仍為NON-EXECUTABLE Candidate。即使其他章重複提到，不可擅自用以封口。這不是可用正式閾值。


## 6. W5可立即做與不可冒稱
可立即做：鎖A/B來源版本與hash；保留原碼；讀取完整history不是僅summary；包裝原TD9/Swing結果；以manifest具名輸出metadata和partial known facts；在原threshold_truth中保留UNKNOWN而非捏造；加入受影響時間/拆股/同一底層不重複計票驗證。這是來源與接線工作，不必重造TD9/Swing。
未完成：A的KD平滑正式相容確認、EMV3,3正式源、listed narrative predicates窄裁定、完整time/PIT/calendar/split metadata。不能只把source_reference改名便稱完整producer核准。
合成full-positive與真實partial-data兩條證據分離；保留Production HOLD/NO_TRADE。本文不是新策略核定，也不聲稱所有TRUE/FALSE已可從真實行情取得。
