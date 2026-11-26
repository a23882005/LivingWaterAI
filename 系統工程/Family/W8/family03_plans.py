"""Member-created equity plans. The common catalogue and personal workbook live in Drive."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
import json
from decimal import Decimal
import os
import subprocess
import tempfile
import uuid

ROLES = ("主軸", "衛星", "繁星")
SLOTS = ("方案一", "方案二", "方案三")
BENCH = ("VT", "VOO", "QQQ")
POOL_NAME = "家人版03_股票配置候選池_主軸衛星繁星_20261122.xlsx"
POOL_ID = "19iRgc-lwC_xp3lvYMqsq_b0zmA2E02Cn"
HISTORY = "查詢舊方案"
COMPARE = "三個方案與三組指數一起比較"
RESET = "重新設計這一案"
SAVE = "儲存這個版本"
THEMES = {"民生消費": ("VDC",), "醫療保健": ("XLV","PPH"), "半導體": ("SOXX","SMH"),
          "國防": ("NATO",), "工業": ("XLI",), "金融": ("XLF",), "日本高股息": ("00956",),
          "那斯達克大型股": ("QQQ",), "主動選股策略": ("DYNF","CPAI"), "寵物照護": ("PAWZ","ZTS")}
BANDS = ((0,0),(1,9),(10,20),(21,29),(30,40),(41,60),(61,80),(81,100))


def digest(obj):
    return sha256(json.dumps(obj, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()


def pool_rows(path):
    from openpyxl import load_workbook
    book = load_workbook(path, read_only=True, data_only=True)
    result, seen = {}, set()
    try:
        for role in ROLES:
            rows = book[role].iter_rows(min_col=1,max_col=7,values_only=True)
            for row in rows:
                if row[:3] == ("代碼","名稱或投資範圍","來源"):
                    break
            else:
                raise ValueError("候選表欄位已變更")
            cards = {}
            for row in rows:
                if len(row)<7:
                    continue
                symbol, name, origin, reason, risk, benchmark, url = row
                if not origin:
                    continue
                if not isinstance(symbol,str) or symbol in seen or not (name and reason and url):
                    raise ValueError("候選表內的代碼或資料需核對")
                seen.add(symbol)
                cards[symbol] = {"名稱":name,"理由":reason,"注意":risk,"資料來源":url}
            if not cards:
                raise ValueError("候選池空白")
            result[role] = cards
    finally:
        book.close()
    return result


def blank():
    return {"prefs":{}, "targets":{}, "layers":{r:{} for r in ROLES}}


def weights(plan):
    return {s:v for layer in plan["layers"].values() for s,v in layer.items()}


def complete(plan):
    return sum(weights(plan).values()) == 100 and all(
        sum(plan["layers"][r].values()) == plan["targets"].get(r) for r in ROLES)


def old_versions(history):
    versions=[]
    for e in history:
        raw=json.loads(e["作答後有效答案"])
        if raw.get("schema")==2:
            if e["題目代碼"] not in ("save","final"):
                continue
            i=raw["slot"]
            p=raw["plans"][i]
        elif e["題目代碼"]=="review" and e.get("方案識別"):
            result=json.loads(e["系統建議與結果"]).get("方案",{})
            if not result.get("股票桶百分比"):
                continue
            p=blank()
            p["prefs"]={k:raw[k] for k in ("goal","returns","loss","fund","amount","replace") if k in raw}
            for role,key,v in zip(ROLES,("core","sat","star"),result["主軸衛星繁星"]):
                p["targets"][role]=v
                if v:
                    p["layers"][role][raw[key]]=v
            i=0
        else:
            continue
        time_text = str(e["台灣時間"])
        try:
            when = datetime.fromisoformat(time_text.replace("Z", "+00:00"))
            if when.tzinfo is not None:
                time_text = when.astimezone(timezone(timedelta(hours=8))).isoformat(timespec="seconds")
        except ValueError:
            pass  # Older workbooks may already contain a localized display string.
        versions.append({"版本":e["事件識別"],"時間":time_text,"當時方案":SLOTS[i],
                         "狀態":e["選擇狀態"],"配置":p})
    return versions[::-1]


def history_page(versions, catalog, payload, revision):
    if set(payload) - {"action", "search", "offset", "role", "stage"}:
        raise ValueError("歷史查詢只接受搜尋、篩選與翻頁")
    role = payload.get("role", "全部")
    stage = payload.get("stage", "全部")
    stages = ("全部", "本人已儲存版本", "本人指定最後方案")
    offset = payload.get("offset", 0)
    if role not in ("全部", *ROLES) or stage not in stages:
        raise ValueError("請從配置角色與版本狀態選項中選擇")
    if type(offset) != int or offset < 0:
        raise ValueError("查詢起點需為非負整數")
    terms = str(payload.get("search", "")).casefold().split()
    hits = []
    for version in versions:
        if stage != "全部" and version["狀態"] != stage:
            continue
        layers = version["配置"]["layers"]
        selected = ROLES if role == "全部" else (role,)
        parts = [str(version[k]) for k in ("時間", "當時方案", "狀態", "版本")]
        summary = []
        for layer in selected:
            items = layers.get(layer, {})
            if items:
                summary.append(layer + " " + "、".join(f"{s} {w}%" for s, w in items.items()))
                parts.extend(catalog[layer].get(s, {}).get("名稱", "") for s in items)
        if role != "全部" and not summary:
            continue
        parts.extend(summary)
        parts.extend(str(value) for value in version["配置"].get("prefs", {}).values())
        description = " ".join(parts).casefold()
        if all(word in description for word in terms):
            hits.append({**version, "配置摘要": "｜".join(summary)})
    page_size = 10
    page = hits[offset:offset + page_size]
    result = {"status": "FAMILY03_HISTORY", "唯讀": True, "共幾筆": len(hits), "起點": offset,
              "版本": page, "revision": revision, "角色選項": ["全部", *ROLES], "狀態選項": list(stages),
              "操作說明": "選角色或狀態縮小範圍，也能輸入代碼、名稱或日期。選好版本，再選要複製到哪一案。"}
    if offset:
        result["上一頁"] = {**payload, "offset": max(0, offset - page_size)}
    if offset + page_size < len(hits):
        result["下一頁"] = {**payload, "offset": offset + page_size}
    return result


def initial(history):
    if history:
        last=json.loads(history[-1]["作答後有效答案"])
        if last.get("schema")==2:
            return last
    return {"schema":2,"plans":[blank() for _ in SLOTS],"slot":0,"step":"home","saved":{},
            "final":None}


def current_symbols(projection):
    latest={}
    for row in projection["ledger_only_positions"]:
        key=row["account_key"],row["symbol"]
        if key not in latest or row["observed_at"]>latest[key]["observed_at"]:
            latest[key]=row
    rows=[*latest.values(),*projection["analysis_security_positions"]]
    return {r["symbol"] for r in rows if r.get("symbol") and
            ((r.get("quantity") is not None and Decimal(str(r["quantity"]))>0) or
             (r.get("quantity") is None and r.get("source_fields",{}).get("reported_market_value_twd")))}


def available_bands(maximum):
    return {f"{lo}–{min(hi,maximum)}%" if lo!=min(hi,maximum) else f"{lo}%":
            (lo,min(hi,maximum)) for lo,hi in BANDS if lo<=maximum}


def next_layer(st):
    p=st["plans"][st["slot"]]
    for r in ROLES:
        if sum(p["layers"][r].values()) < p["targets"][r]:
            st.update(role=r,step="theme" if r=="衛星" else "symbol")
            return
    st["step"]="fund" if "fund" not in p["prefs"] else "review"


def explain_choices(plans, rows, guide):
    """Apply one member-selected preference set at a time to all six common-period rows."""
    reports=[]
    questions=guide.QUESTIONS
    for slot,plan in zip(SLOTS,plans):
        prefs=plan["prefs"]
        goal=prefs.get("goal")
        returns=prefs.get("returns")
        loss=prefs.get("loss")
        if any(v not in questions[k][1] for k,v in (("goal",goal),("returns",returns),("loss",loss))):
            continue
        band=questions["returns"][1].index(returns)
        low,high=guide.comparison.RETURN_BANDS[band] if band<4 else (None,None)
        idx=questions["loss"][1].index(loss)
        cap=(.1,.2,.3,.4)[idx] if idx<4 else None
        details=[]
        eligible=[]
        for r in rows:
            h=r["歷史試算"]
            ret=h.get("年化報酬率")
            dd=h.get("最大回撤幅度")
            excess=max(0,dd-cap) if cap is not None and dd is not None else None
            risk=("未設硬上限" if cap is None else "待補共同歷史" if excess is None else
                  f"超出 {excess*100:.2f} 個百分點" if excess>1e-10 else "在上限內")
            match=("先看歷史結果" if low is None else "年化資料不足" if ret is None else
                   "低於區間" if ret<low else "高於區間" if ret>=high else "在區間內")
            details.append({"名稱":r["名稱"],"報酬對照":match,"回撤對照":risk})
            if (r["名稱"] in SLOTS and ret is not None and dd is not None and
                    (cap is None or dd<=cap+1e-10) and (low is None or low<=ret<high)):
                eligible.append(r)
        if not eligible:
            advice="先看各案與本人區間的差距，再選要微調哪一案。"
        elif goal==questions["goal"][1][2]:
            advice="先比較符合區間的方案："+ "、".join(r["名稱"] for r in eligible)+"。逐項看共同成分與已知比重，資料涵蓋不同時保留判斷。"
        else:
            index=questions["goal"][1].index(goal)
            metric,op={0:("最大回撤幅度",min),1:("年化報酬率",max),3:("Sharpe",max)}[index]
            measured=[r for r in eligible if r["歷史試算"].get(metric) is not None]
            advice="風險調整後報酬資料不足，先看原始報酬與跌幅。"
            if measured:
                best=op(r["歷史試算"][metric] for r in measured)
                names="、".join(r["名稱"] for r in measured if abs(r["歷史試算"][metric]-best)<1e-10)
                value=f"{best:.2f}" if metric=="Sharpe" else f"{best:.2%}"
                advice=f"依本人目標，符合所選區間的自選方案中，先比較{names}（歷史{metric} {value}）。"
        reports.append({"偏好來自":slot,"目標":goal,"年報區間":returns,"跌幅偏好":loss,
                        "六組對照":details,"家人版建議":advice})
    return reports


def six(plans, prices, exposures, calc, single_stocks=()):
    allocation=[weights(p) for p in plans]+[{s:100} for s in BENCH]
    relevant=set().union(*allocation)
    missing=sorted(s for s in relevant if not prices.get(s))
    common={}
    if not missing and len({prices[s][0] for s in relevant})==1:
        dates=set.intersection(*(set(prices[s][1]) for s in relevant))
        common={s:(prices[s][0],{d:prices[s][1][d] for d in dates}) for s in relevant}
    rows=[]
    for label,w in zip((*SLOTS,*BENCH),allocation):
        h=(calc.simulate(w,common) if common else {"狀態":"待補六組共同幣別與共同日線","缺行情":missing})
        look=calc.exposure(w,exposures)
        biggest=max(w,key=w.get)
        rows.append({"名稱":label,"股票桶百分比":w,"歷史試算":h,"共同曝險":look,
                     "最大直接部位":f"{biggest} {w[biggest]}%",
                     "取捨":"以單一指數作為全額對照" if label in BENCH else
                     f"分配於 {len(w)} 檔，直接持有個股合計 {sum(w.get(s,0) for s in single_stocks)}%。"})
    ready=all(r["歷史試算"].get("狀態")=="歷史粗估" for r in rows)
    if ready:
        for key,lab,op in (("年化報酬率","年化報酬最高",max),("最大回撤幅度","歷史跌幅最小",min),
                           ("年化波動率","年化波動最高",max)):
            extreme=op(r["歷史試算"][key] for r in rows)
            for r in rows:
                if r["歷史試算"][key]==extreme:
                    r.setdefault("六組相對特點",[]).append(lab)
    reference=rows[3]["歷史試算"]
    for r in rows:
        h=r["歷史試算"]
        pros,cons=[],[]
        for key,title,sign in (("年化報酬率","年化報酬",1),("期間報酬率","期間報酬",1),
                               ("最大回撤幅度","最大跌幅",-1),("年化波動率","年化波動",-1)):
            if key not in h or key not in reference:
                continue
            gap=h[key]-reference[key]
            if abs(gap)<.00005:
                continue
            note=f"比 VT {'高' if gap>0 else '低'} {abs(gap)*100:.2f} 個百分點（{title}）"
            (pros if sign*gap>0 else cons).append(note)
        r["相對優點"]=pros
        r["相對代價"]=cons
        r["比較基準"]="同期間全 VT；只描述歷史差異"
    return rows


def menu_handler(entry, member, folder, calc, guide, project_holdings, *, market_reader=None, document_source=None):
    folder=Path(folder)
    progress=folder/(member+"_03_股票配置選擇進度.xlsx")
    pool=folder/POOL_NAME
    bench=folder/"標的績效基準資料.xlsx"
    legacy=guide.menu_handler(entry,member,folder,calc,market_reader=market_reader)
    def run(payload):
        snapshot=entry.current_snapshot()
        if not progress.is_file():
            return {"status":"FAMILY03_SOURCE_REQUIRED","檔名":progress.name,"本人":member}
        raw=progress.read_bytes()
        revision=sha256(raw).hexdigest()
        book=calc.reader_module().read_xlsx(progress)
        history=book.sheets["選擇歷程"].rows
        if book.sheets["選擇進度"].headers[:2]!=["股票配置・選擇進度",member] or any(
                e["家人"]!=member for e in history):
            raise PermissionError("FAMILY03_PROGRESS_OWNER_MISMATCH")
        action=payload.get("action")
        if action == "progress_receipt":
            event_id = payload.get("event_id")
            source_revision = payload.get("source_revision")
            if set(payload) != {"action", "event_id", "source_revision"} or not all(
                    isinstance(value, str) and len(value) == 64
                    and all(char in "0123456789abcdef" for char in value)
                    for value in (event_id, source_revision)):
                raise ValueError("FAMILY03_INVALID_PROGRESS_RECEIPT_REQUEST")
            matches = [index for index, row in enumerate(history, 1)
                       if row["事件識別"] == event_id]
            if len(matches) > 1:
                raise ValueError("FAMILY03_DUPLICATE_PROGRESS_EVENT")
            status = ("FAMILY03_PROGRESS_EVENT_FOUND" if matches else
                      "FAMILY03_PROGRESS_NOT_SAVED" if revision == source_revision else
                      "FAMILY03_PROGRESS_SOURCE_CHANGED")
            return {"status": status, "本人": member, "檔名": progress.name,
                    "事件識別": event_id, "事件序號": matches[0] if matches else None,
                    "歷程筆數": len(history), "revision": revision, "唯讀": True}
        for f,file_id in ((pool,POOL_ID),(bench,calc.BOOK_ID)):
            if not f.is_file():
                return {"status":"FAMILY03_SOURCE_REQUIRED","檔名":f.name,"file_id":file_id}
        catalog=pool_rows(pool)
        versions=old_versions(history)
        st=initial(history)
        if history and json.loads(history[-1]["作答後有效答案"]).get("schema")!=2 and action not in ("history","start_plans","restore","lookup","account_preview"):
            # Preserve resumability of older partial interviews.
            if "review" not in json.loads(history[-1]["作答後有效答案"]):
                q=legacy(payload)
                q["新版入口"]={"action":"start_plans"}
                q["查詢入口"]={"action":"history"}
                return q
        if action == "account_preview":
            if set(payload) != {"action"}:
                raise ValueError("請從本人的最後指定方案讀取")
            import importlib.util
            spec = importlib.util.spec_from_file_location("family03_target", Path(__file__).with_name("family03_target.py"))
            target = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(target)
            final = st.get("final")
            return target.account_preview(snapshot, final, weights(final["配置"]) if final else {},
                                          catalog, pool, revision, document_source)
        if action=="lookup":
            symbol=str(payload.get("symbol","")).strip().upper()
            if set(payload)!={"action","symbol"} or not 1<=len(symbol)<=25 or any(
                    c not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.=-^" for c in symbol):
                raise ValueError("請使用核實掛牌的商品代碼")
            meta,_=calc.workbook(bench)
            prices=market_data([symbol],meta)
            return {"status":"FAMILY03_RESEARCH","代碼":symbol,"唯讀":True,
                    "單檔歷史":calc.simulate({symbol:100},prices),
                    "候選池":[r for r in ROLES if symbol in catalog[r]],
                    "補入方式":"想列入共用名單時，依核准分類更新 B 候選表，重新開啟 03 即會讀入。"}
        if action=="history":
            return history_page(versions, catalog, payload, revision)
        if action=="restore":
            if set(payload)!={"action","version","slot","revision"} or payload["revision"]!=revision:
                raise ValueError("請重新查詢最新版本")
            version=next((v for v in versions if v["版本"]==payload["version"]),None)
            if not version or payload["slot"] not in SLOTS:
                raise ValueError("請選本戶歷史與目的方案")
            i=SLOTS.index(payload["slot"])
            st["plans"][i]=deepcopy(version["配置"])
            st.get("resume",{}).pop(str(i),None)
            st.update(slot=i,step="review")
            key,choice="restore",version["版本"]
            prompt={"問題":"把選定歷史複製到"+SLOTS[i],"選項":[choice],"影片":{}}
        else:
            if set(payload)-{"key","reply","revision","question_id","action"} or action not in (None,"start_plans"):
                raise ValueError("未知的家人 03 操作")
            owned=current_symbols(project_holdings(snapshot))
            p=st["plans"][st["slot"]]
            key=st["step"]
            role=st.get("role","主軸")
            oldprefs=guide.QUESTIONS
            info={"方案":SLOTS[st["slot"]]}
            lesson="mix"
            if key=="home":
                title,options="你想設計或查看哪一個方案？",list(SLOTS)
                if all(st["saved"].get(str(i))==digest(a) for i,a in enumerate(st["plans"])):
                    options.append(COMPARE)
                options.append(HISTORY)
                info["三案進度"]={s:{"已配":sum(weights(a).values()),"已儲存":st["saved"].get(str(i))==digest(a)}
                                   for i,(s,a) in enumerate(zip(SLOTS,st["plans"]))}
                info["本人最後指定"]=st.get("final")
                if st.get("final"):
                    info["查看全帳戶目標"] = {"action":"account_preview"}
                info["操作"]="每次選擇後自動儲存；查詢支援代碼、角色或日期。找到版本後，選擇複製到哪一案。"
            elif key in ("goal","returns","loss","fund","amount","replace"):
                title,options,*_=oldprefs[key]
                if key=="replace":
                    picked=p["prefs"].get("replace",[])
                    if not isinstance(picked,list):picked=[picked]
                    options=["完成換出選擇" if picked else "保留全部"]+sorted(owned-set(picked))
                    info["已勾選"]=picked
                lesson=key
            elif key=="band":
                limit=100 if role=="主軸" else 100-p["targets"]["主軸"]
                title=f"{role}想占股票部位的哪個範圍？"
                options=list(available_bands(limit))
            elif key=="exact":
                title=f"在選定範圍內，{role}確定要配多少？"
                options=[f"{v}%" for v in range(st["band"][0],st["band"][1]+1)]
            elif key=="theme":
                title="衛星這一筆想先看哪個方向？"
                options=[k for k,syms in THEMES.items() if any(s in catalog[role] and s not in p["layers"][role] for s in syms)]+["看全部"]
                lesson="sector"
            elif key=="symbol":
                allowed=THEMES.get(st.get("theme"),()) if role=="衛星" else ()
                opts=[s for s in catalog[role] if s not in p["layers"][role] and (not allowed or s in allowed)]
                options=sorted(opts,key=lambda s:s not in owned)
                title=f"{role}還有 {p['targets'][role]-sum(p['layers'][role].values())}% 可分配，想選哪一檔？"
                info["候選資料"]={s:{**catalog[role][s],"本人現有":s in owned} for s in options}
                meta,_=calc.workbook(bench)
                prices=market_data(options,meta)
                for s,card in info["候選資料"].items():
                    card["B 基準資料"]={k:(v.isoformat() if hasattr(v,"isoformat") else v) for k in guide.FIELDS if (v:=meta[s].get(k)) is not None} if s in meta else {}
                    card["單檔歷史"]=calc.simulate({s:100},{s:prices[s]})
                lesson={"主軸":"core","衛星":"sat","繁星":"star"}[role]
            elif key=="weight_band":
                left=p["targets"][role]-sum(p["layers"][role].values())
                title=f"{st['symbol']} 想占整個股票部位的哪個範圍？"
                options=[f"全數 {left}%"]+[f"{lo}–{min(lo+9,left-1)}%" for lo in range(1,left,10)]
            elif key=="weight":
                left=p["targets"][role]-sum(p["layers"][role].values())
                title=f"{st['symbol']} 要占整個股票部位多少？這層還有 {left}%。"
                more=len(catalog[role])>len(p["layers"][role])+1
                low,high=st.get("weight_range",(1 if more else left,left))
                options=[f"{v}%" for v in range(low,high+1)]
            elif key in ("reduce","increase","shift"):
                if key=="reduce":
                    title,options="想從哪一檔移出一些比例？",list(weights(p))
                elif key=="increase":
                    title,options="要把這些比重移到哪一檔？",[s for s in weights(p) if s!=st["from"]]
                else:
                    title=f"從 {st['from']} 移到 {st['to']} 多少個百分點？"
                    options=[f"{v}%" for v in range(1,weights(p)[st["from"]]+1)]
            elif key=="review":
                title,options="這個方案的標的與比例如下，你想怎麼做？",[SAVE,*["調整"+r for r in ROLES if p["targets"].get(r)],RESET,"回三方案"]
                if len(weights(p))>1:
                    options.insert(1,"微調兩檔比例")
                info["配置"]=p
                info["整組試算"]=evaluate([p],False)
                hist=info["整組試算"]["歷史試算"]
                if hist.get("狀態")=="歷史粗估" and all(k in p["prefs"] for k in ("returns","loss")):
                    band=oldprefs["returns"][1].index(p["prefs"]["returns"])
                    loss=oldprefs["loss"][1].index(p["prefs"]["loss"])
                    if band<4:
                        lo,hi=guide.comparison.RETURN_BANDS[band]
                        info["整組試算"]["年報是否在目標區間"]=lo<=hist["年化報酬率"]<hi
                    if loss<4:
                        cap=(.1,.2,.3,.4)[loss]
                        info["整組試算"]["超過跌幅上限百分點"]=round(100*max(0,hist["最大回撤幅度"]-cap),2)
                lesson="review"
            elif key=="compare":
                title="六組使用共同觀察日。看過結果後，你想修改哪一案，或指定最後方案？"
                options=["調整"+s for s in SLOTS]+["指定"+s for s in SLOTS]+["回三方案"]
                info["六組比較"]=evaluate(st["plans"],True)
                info["本人偏好對照"]=explain_choices(st["plans"],info["六組比較"],guide)
                lesson="review"

            else:
                raise ValueError("進度步驟無法辨認")
            if key not in ("home","review","compare"):
                options=[*options,"暫存並回三方案"]
            video=guide.question(lesson)["影片"]
            prompt={"status":"FAMILY03_QUESTION","key":key,"問題":title,"選項":options,"影片":video,**info}
            stamp=digest([revision,snapshot["source_sha256"],prompt])
            prompt.update(revision=revision,question_id=stamp,查詢入口={"action":"history"})
            if "reply" not in payload:
                return prompt
            choice=payload["reply"]
            if (payload.get("revision"),payload.get("question_id"),payload.get("key"))!=(revision,stamp,key) or choice not in options:
                raise ValueError("FAMILY03_RELOAD_QUESTION")
            if choice==HISTORY:
                return run({"action":"history"})
            if choice=="暫存並回三方案":
                st.setdefault("resume",{})[str(st["slot"])]={
                    k:st[k] for k in ("step","role","band","theme","symbol","weight_range","from","to") if k in st}
                st["step"]="home"
            elif key=="home":
                if choice==COMPARE:
                    st["step"]="compare"
                else:
                    st["slot"]=SLOTS.index(choice)
                    resumed=st.get("resume",{}).pop(str(st["slot"]),{})
                    if resumed:
                        st.pop("weight_range",None)
                        st.update(resumed)
                    else: st["step"]="review" if complete(st["plans"][st["slot"]]) else "goal"
            elif key in ("goal","returns","loss"):
                p["prefs"][key]=choice
                st["step"]={"goal":"returns","returns":"loss","loss":"band"}[key]
                if key=="loss":
                    st["role"]="主軸"
            elif key=="band":
                st["band"]=available_bands(limit)[choice]
                st["step"]="exact"
            elif key=="exact":
                p["targets"][role]=int(choice[:-1])
                if role=="主軸":
                    st.update(role="衛星",step="band")
                else:
                    p["targets"]["繁星"]=100-sum(p["targets"][r] for r in ROLES[:2])
                    next_layer(st)
            elif key=="theme":
                st.update(theme=choice,step="symbol")
            elif key=="symbol":
                st.pop("weight_range",None)
                left=p["targets"][role]-sum(p["layers"][role].values())
                more=len(catalog[role])>len(p["layers"][role])+1
                st.update(symbol=choice,step="weight_band" if left>10 and more else "weight")
            elif key=="weight_band":
                if choice.startswith("全數"):
                    p["layers"][role][st["symbol"]]=int(choice.split()[1][:-1])
                    next_layer(st)
                else:
                    st.update(weight_range=list(map(int,choice[:-1].split("–"))),step="weight")
            elif key=="weight":
                p["layers"][role][st["symbol"]]=int(choice[:-1])
                next_layer(st)
            elif key in ("fund","amount","replace"):
                if key=="replace":
                    if choice not in ("完成換出選擇","保留全部"):
                        p["prefs"].setdefault("replace",[]).append(choice)
                else:
                    p["prefs"][key]=choice
                funding=oldprefs["fund"][1].index(p["prefs"]["fund"])
                if key=="replace" and choice not in ("完成換出選擇","保留全部"):
                    st["step"]="replace"
                elif key=="fund" and funding in (1,3):
                    st["step"]="amount"
                elif key!="replace" and funding in (2,3):
                    st["step"]="replace"
                else:
                    st["step"]="review"
            elif choice=="回三方案":
                st["step"]="home"
            elif choice==RESET:
                st["plans"][st["slot"]]=blank()
                st["step"]="goal"
            elif key=="reduce":
                st.update(step="increase", **{"from":choice})
            elif key=="increase":
                st.update(step="shift",to=choice)
            elif key=="shift":
                amount=int(choice[:-1])
                for symbol,delta in ((st["from"],-amount),(st["to"],amount)):
                    r=next(r for r in ROLES if symbol in p["layers"][r])
                    p["layers"][r][symbol]+=delta
                    p["targets"][r]+=delta
                    if not p["layers"][r][symbol]: del p["layers"][r][symbol]
                st["step"]="review"
            elif key=="review":
                if choice=="微調兩檔比例":
                    st["step"]="reduce"
                elif choice==SAVE:
                    key="save"
                    st["saved"][str(st["slot"])]=digest(p)
                    st["step"]="home"
                else:
                    role=choice[2:]
                    p["layers"][role]={}
                    next_layer(st)
            elif key=="compare":
                st["slot"]=SLOTS.index(choice[2:])
                if choice.startswith("指定"):
                    key="final"
                    st["final"]={"方案":SLOTS[st["slot"]],"配置":deepcopy(st["plans"][st["slot"]])}
                    st["step"]="home"
                else:
                    st["step"]="review"
        return write(st,prompt,choice,key,history,revision,snapshot,progress,folder,member,calc)

    def evaluate(plans, all_six):
        meta,exposures=calc.workbook(bench)
        symbols=set().union(*(weights(p) for p in plans))
        if all_six:
            symbols.update(BENCH)
        prices=market_data(symbols,meta)
        prices=calc.common_currency(prices,market_reader)
        catalog=pool_rows(pool)
        stocks={s for s in catalog["繁星"] if "ETF" not in catalog["繁星"][s]["名稱"]} | {"ZTS"}
        exposures=calc.direct_exposures(symbols,stocks,exposures)
        if all_six:
            return six(plans,prices,exposures,calc,stocks)
        w=weights(plans[0])
        return {"歷史試算":calc.simulate(w,prices),"共同曝險":calc.exposure(w,exposures)}

    def market_data(symbols,meta):
        prices={s:calc.series(s,meta.get(s,{})) for s in sorted(symbols)}
        if market_reader:
            supplied=market_reader(tuple(sorted(symbols)))
            for s in symbols:
                newer=supplied.get(s)
                if newer and newer[1] and (not prices[s] or max(newer[1])>max(prices[s][1])):
                    prices[s]=newer
        return prices
    return run


def write(st,q,choice,key,history,revision,snapshot,progress,folder,member,calc):
    event_id=digest([revision,snapshot["source_sha256"],key,choice,st])
    stage={"save":"本人已儲存版本","final":"本人指定最後方案","restore":"從歷史複製"}.get(key,"本人暫選")
    now=datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")
    event={"id":event_id,"time":now,"key":key,"title":q["問題"],"options":q["選項"],
           "advice":{k:q[k] for k in ("整組試算","六組比較","本人偏好對照") if k in q},
           "choice":choice,"url":q.get("影片",{}).get("網址",""),"stage":stage,"answers":st,
           "next":st["step"],"previous":len(history),"token":digest(st["plans"][st["slot"]])}
    candidate=folder/("03-"+uuid.uuid4().hex+".xlsx")
    with tempfile.TemporaryDirectory(dir=folder) as tmp:
        arg=Path(tmp)/"event.json"
        arg.write_text(json.dumps(dict(member=member,input=str(progress),output=str(candidate),event=event),
                                  ensure_ascii=False,default=str))
        subprocess.run([os.environ.get("CODEX_PRIMARY_RUNTIME_NODE","node"),
                        str(Path(__file__).with_name("family03_book.mjs")),str(arg)],check=True,capture_output=True)
    log=calc.reader_module().read_xlsx(candidate).sheets["選擇歷程"].rows
    if len(log)!=len(history)+1 or log[-1]["事件識別"]!=event_id:
        raise ValueError("進度回讀與本次選擇不符")
    return {"status":"FAMILY03_PROGRESS_WRITEBACK_REQUIRED","本人":member,"檔名":progress.name,
            "原檔摘要":revision,"新檔摘要":sha256(candidate.read_bytes()).hexdigest(),"候選檔":str(candidate),
            "事件識別":event_id,
            "讀回入口":{"action":"progress_receipt","event_id":event_id,"source_revision":revision},
            "保存步驟":"核對本人雲端原檔摘要，備份、原 ID 更新，下載核對後再呼叫選單 03 續答。"}

