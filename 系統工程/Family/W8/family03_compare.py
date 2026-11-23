"""Compare a small set of equity-sleeve illustrations inside the member's selected band."""
from math import inf

# Every compared mix uses exactly the same instruments and historical observation dates.
# The third band starts with no star selected, so keep it at zero in those comparisons.
VARIANTS = (
    ((50,35,15),(60,30,10),(40,40,20)),
    ((70,20,10),(80,15,5),(60,25,15)),
    ((90,10,0),(95,5,0),(80,20,0)),
)
RETURN_BANDS = ((-inf,.05),(.05,.08),(.08,.12),(.12,inf))
ROLE_KEYS = ("core","sat","star")


def label(mix):
    return "／".join(str(part) for part in mix)


def attachment(mix, answers):
    return {answers[key]:pct for key,pct in zip(ROLE_KEYS,mix) if pct}


def compare(answers, mixes, active, prices, exposures, calc, goal, band, loss):
    cap = (.10,.20,.30,.40,None,None)[loss]
    low,high = RETURN_BANDS[band] if band<4 else (-inf,inf)
    records = []
    for mix in mixes:
        weights = attachment(mix,answers)
        hist = calc.simulate(weights, prices)
        lookthrough = calc.exposure(weights, exposures)
        row = {"主軸衛星繁星":mix,"股票桶百分比":weights,"歷史試算":hist}
        mutual = [x for x in lookthrough["共同曝險"] if x["項目"].startswith("HOLDING.")]
        row["重複成分股範例"] = mutual[:3]
        if hist["狀態"]=="歷史粗估":
            ret,dd=hist["年化報酬率"],hist["最大回撤幅度"]
            row["符合報酬區間"]=low<=ret<high if band<4 else None
            row["超過回撤上限"]=dd>cap if cap is not None else None
        records.append(row)
    current = next(row for row in records if row["主軸衛星繁星"]==active)
    if any(row["歷史試算"]["狀態"]!="歷史粗估" for row in records):
        return records,None,"先補齊所選標的的共同幣別與還原行情，再比較方案。"
    if len(records)==1:
        return records,None,"這是您逐層指定的比例。先看這組的歷史報酬與回撤，再決定是否調整。"
    if goal==2 and not current["重複成分股範例"]:
        return records,None,"您重視分散。現有 B 表不足以比較這幾組的共同成分股，建議先查這些基金的持股明細。"
    # First respect the user's drawdown ceiling. Compare the stated objective within
    # equally feasible choices. No forecast, optimizer or invented utility weights.
    def rank(row):
        h=row["歷史試算"]
        dd,ret=h["最大回撤幅度"],h["年化報酬率"]
        excess=max(dd-cap,0) if cap is not None else 0
        if goal==2:
            primary=max(x["已知合計百分點"] for x in row["重複成分股範例"])
        elif goal==0:
            primary=dd
        elif goal==1:
            primary=-ret
        else:
            primary=-(h["Sharpe"] if h["Sharpe"] is not None else -inf)
        # Staying closest to a requested band is meaningful for a balanced goal.
        # For an explicit growth goal, a larger historical return is not penalized.
        gap=max(low-ret,ret-high,0) if goal==3 else 0
        return (excess,gap,primary, row is not current)
    best=min(records,key=rank)
    h=best["歷史試算"]
    reason=["這幾組中優先比較最大跌幅較小的方案","您願承受波動，優先比較歷史年化報酬",
            "優先降低 B 表已知共同成分股中最大的合計比重，完整曝險仍需基金持股明細",
            "先看報酬區間及跌幅上限，再比較每單位波動換到的歷史報酬"][goal]
    warning=""
    exceeds = best["超過回撤上限"] is True
    if exceeds:
        warning=(f"三組都超過您選的 {cap:.0%} 跌幅上限。這組跌幅最小，仍超出 "
                 f"{(h['最大回撤幅度']-cap)*100:.2f} 個百分點。建議先保留草案，再換一組標的比較。")
    if best["符合報酬區間"] is False:
        warning+="這組歷史年化報酬落在您選的區間以外。"
    action="建議先保留" if best is current else "建議先試"
    if exceeds:
        action="最接近跌幅上限的是"
    advice=(f"{reason}。{action} {label(best['主軸衛星繁星'])}。"
            f"{h['起日']} 至 {h['迄日']} 年化報酬 {h['年化報酬率']:.2%}，"
            f"最大跌幅 {h['最大回撤幅度']:.2%}。{warning}")
    return records,None if exceeds else best["主軸衛星繁星"],advice
