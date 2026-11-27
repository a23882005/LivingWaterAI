"""Family 03. Menu payloads contain choices, never Drive paths or account IDs."""
import json
from hashlib import sha256
from decimal import Decimal
from pathlib import Path
import importlib.util

_spec = importlib.util.spec_from_file_location("family03_compare", Path(__file__).with_name("family03_compare.py"))
comparison = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(comparison)

QUESTIONS = json.loads(Path(__file__).with_name("family03_questions.json").read_text())
ROLES = {"民生消費":["XLP"], "國防":["NATO"], "醫藥":["PPH"], "半導體":["SOXX","SMH"]}
PRESETS = [(50,35,15),(70,20,10),(90,10,0)]
FIELDS = ["正式名稱","基礎幣別","費用率/TER","官方5Y年化報酬","官方績效截至","近10年最大回撤","資料截至日(As-of Date)"]


def question(key, options=None, **more):
    title, defaults, lesson, video = QUESTIONS[key]
    return {"status":"FAMILY03_QUESTION", "key":key, "問題":title, "選項":defaults if options is None else options,
            "影片":{"主題":lesson,"網址":"https://www.youtube.com/watch?v="+video}, **more}


def holdings(tables):
    by_key = {r["instrument_key"]:r.get("ticker") for r in tables["portfolio_instrument"]}
    latest = {}
    for r in sorted(tables["portfolio_position"],key=lambda r:r["as_of_utc"]):
        latest[(r["account_key"],r["instrument_key"])] = Decimal(r["quantity_decimal"])
    return sorted({by_key[key] for (_,key),qty in latest.items() if qty > 0 and by_key.get(key)})


def guide(snapshot, answers, bookpath, calc, extra_series=None):
    if not isinstance(answers,dict) or answers.keys()-QUESTIONS.keys()-{"trial_mix"}:
        raise ValueError("無法辨識這一題")
    remaining = dict(answers)
    def ask(key, options=None, **metadata):
        q = question(key, options, **metadata)
        if key not in remaining:
            return q
        answer = remaining.pop(key)
        if answer not in q["選項"]:
            return {**q,"提醒":"請從目前顯示的選項重新選擇。"}
        return None

    for k in ("goal","sector","returns","loss","mix"):
        md = {}
        if k=="mix":
            md["配置說明"] = "主軸用大盤指數 ETF 分散公司風險；衛星表達產業偏好；繁星容納其他產業或小額個股。"
            md["建議先比較"] = QUESTIONS[k][1][1 if answers["goal"] in (QUESTIONS["goal"][1][0],QUESTIONS["goal"][1][2]) else 0]
        q = ask(k, **md)
        if q: return q
    idx = QUESTIONS["mix"][1].index(answers["mix"])
    if idx==3:
        q = ask("core_pct", [f"{v}%" for v in range(0,101,5)])
        if q: return q
        c = int(answers["core_pct"][:-1])
        q = ask("sat_pct",[f"{v}%" for v in range(0,101-c,5)])
        if q: return q
        s = int(answers["sat_pct"][:-1])
        mix = (c,s,100-c-s)
    else:
        mix = PRESETS[idx]
        if "trial_mix" in answers:
            tested = tuple(answers["trial_mix"])
            if tested not in comparison.VARIANTS[idx]:
                raise ValueError("FAMILY03_MIX_OUTSIDE_CHOSEN_BAND")
            mix = tested
    if not bookpath.is_file():
        return {"status":"FAMILY03_SOURCE_REQUIRED","file_id":calc.BOOK_ID,"檔名":"標的績效基準資料.xlsx"}
    book, exposure = calc.workbook(bookpath)
    theme = answers["sector"]
    sector = list(dict.fromkeys(ROLES.get(theme,[])+["PPH","NATO","SOXX","SMH","XLP"]))
    weights = {}
    for k, pct in zip(("core","sat","star"),mix):
        if not pct: continue
        pool = ["VT","VOO","VWRA","0050"] if k=="core" else list(sector)
        if k=="star":
            pool += ["MSFT","NVDA"]
        pool = [v for v in pool if v not in weights]
        if k=="star" and answers.get("sat") in ROLES.get(theme, []):
            pool = sorted(pool, key=lambda symbol: symbol in ROLES[theme])
        cards = {s:{field:book[s][field] for field in FIELDS} if s in book else
                 {"來源":"B 表以外的比較候選，績效另用市場資料試算"} for s in pool}
        q = ask(k,pool, 股票桶占比=pct, 候選資料=cards, 建議先比較=pool[0],
                理由=("先用廣泛市場代表主軸。" if k=="core" else
                    "依所選產業優先顯示。繁星也可選其他產業，降低對單一題材的依賴。"))
        if q: return q
        weights[answers[k]] = pct
    q = ask("fund")
    if q: return q
    fund = QUESTIONS["fund"][1].index(answers["fund"])
    if fund in (1,3):
        q=ask("amount")
        if q: return q
    if fund in (2,3):
        q=ask("replace", ["保留全部"]+holdings(snapshot["tables"]))
        if q: return q
    market = {s:calc.series(s,book.get(s,{})) for s in weights}
    missing = [s for s in weights if market[s] is None]
    if missing and extra_series:
        market.update({s:v for s,v in extra_series(tuple(missing)).items() if s in missing})
    candidates = comparison.VARIANTS[idx] if idx < len(PRESETS) else (mix,)
    rows, best_mix, advice = comparison.compare(
        answers,candidates,mix,market,exposure,calc,
        QUESTIONS["goal"][1].index(answers["goal"]),
        QUESTIONS["returns"][1].index(answers["returns"]),
        QUESTIONS["loss"][1].index(answers["loss"]))
    chosen = next(row for row in rows if row["主軸衛星繁星"]==mix)
    result = {"主軸衛星繁星":mix, "股票桶百分比":weights, "歷史試算":chosen["歷史試算"],
              "曝險":calc.exposure(weights,exposure),"資金方式":answers["fund"],
              "本人目標":answers["goal"],"本人報酬偏好":answers["returns"],"本人跌幅偏好":answers["loss"],
              "新資金範圍":answers.get("amount"),"願意評估換出的持股":answers.get("replace"),
              "歷史報酬符合所選區間":chosen.get("符合報酬區間"),
              "歷史回撤超過本人上限":chosen.get("超過回撤上限"),
              "同期間方案比較":rows,"建議試算比例":best_mix,"家人版建議":advice}
    trials = {"先試 "+comparison.label(candidate):candidate for candidate in candidates if candidate!=mix}
    token=sha256(json.dumps([snapshot["client_id"],snapshot["source_sha256"],result],
        ensure_ascii=False,sort_keys=True,default=str).encode()).hexdigest()
    return question("review",QUESTIONS["review"][1]+list(trials), **{"方案":result,"方案識別":token,"可試比例":trials})


def menu_handler(entry, member, folder, calc, *, market_reader=None, progress_path=None):
    """ChatGPT binds a private working directory containing the exact Drive downloads."""
    from datetime import datetime, timezone, timedelta
    from tempfile import TemporaryDirectory
    import os
    import subprocess
    import uuid
    folder = Path(folder)
    progress_name = member + "_03_股票配置選擇進度.xlsx"
    progress = Path(progress_path) if progress_path is not None else folder / progress_name
    bench = folder/"標的績效基準資料.xlsx"

    def run(payload):
        if set(payload)-{"reply","key","revision","question_id","edit"}:
            raise ValueError("FAMILY03_INVALID_INPUT")
        snapshot = entry.current_snapshot()
        if not progress.is_file():
            return {"status":"FAMILY03_SOURCE_REQUIRED","檔名":progress.name,
                    "來源":"本人專案子目錄的正式進度檔","本人":member}
        raw=progress.read_bytes()
        revision=sha256(raw).hexdigest()
        book=calc.reader_module().read_xlsx(progress)
        if book.sheets["選擇進度"].headers[:2]!=["股票配置・選擇進度",member]:
            raise PermissionError("FAMILY03_PROGRESS_OWNER_MISMATCH")
        history=book.sheets["選擇歷程"].rows
        if any(e["家人"]!=member for e in history):
            raise PermissionError("FAMILY03_HISTORY_OWNER_MISMATCH")
        answers=json.loads(history[-1]["作答後有效答案"]) if history else {}
        def before(k):
            return {key:value for key,value in answers.items()
                    if key in QUESTIONS and list(QUESTIONS).index(key)<list(QUESTIONS).index(k)}
        edit=payload.get("edit")
        if edit:
            if edit not in QUESTIONS or edit not in answers or edit=="review":
                raise ValueError("FAMILY03_UNKNOWN_EARLIER_ANSWER")
            answers=before(edit)
        q=guide(snapshot,answers,bench,calc,market_reader)
        if q.get("key")=="review" and answers.get("review"):
            q["上次決定"]=answers["review"]
            if history and history[-1]["方案識別"] != q["方案識別"]:
                q["提醒"]="試算資料或方案已更新，請看本次數字再決定。"
            if answers["review"] == QUESTIONS["review"][1][1]:
                q["重選提示"]="想先換哪一項？從可重選題目選一個，其他仍適用的答案會保留。"
        if q["status"]!="FAMILY03_QUESTION": return q
        stamp=sha256(json.dumps([revision,snapshot["source_sha256"],q],
            ensure_ascii=False,sort_keys=True,default=str).encode()).hexdigest()
        q.update(revision=revision,question_id=stamp,可重選題目={k:QUESTIONS[k][0] for k in answers if k in QUESTIONS and k!="review"})
        if "reply" not in payload:
            if edit:
                q["作答入口"] = {"edit": edit}
            return q
        if (payload.get("revision")!=revision or payload.get("question_id")!=stamp
                or payload.get("key")!=q["key"] or payload["reply"] not in q["選項"]):
            raise ValueError("FAMILY03_RELOAD_QUESTION")
        key, choice=q["key"],payload["reply"]
        if edit:
            saved=json.loads(history[-1]["作答後有效答案"])
            invalidate={"mix":{"core_pct","sat_pct","core","sat","star"},
                        "core_pct":{"sat_pct","core","sat","star"}, "sat_pct":{"sat","star"},
                        "sector":{"sat","star"}, "sat":{"star"}, "fund":{"amount","replace"}}
            answers={k:v for k,v in saved.items() if k not in invalidate.get(edit,set())|({"trial_mix"} if edit in {"mix","core_pct","sat_pct"} else set())|{"review"}}
        answers[key]=choice
        stage="本人暫選"
        if key=="review":
            if choice in q["可試比例"]:
                answers["trial_mix"]=q["可試比例"][choice]
                answers.pop("review")
                stage="本人選擇試算比例"
            else:
                stage=["保留草案","待重選","本人確認股票配置草案"][QUESTIONS[key][1].index(choice)]
        after=guide(snapshot,answers,bench,calc,market_reader)
        mix=None
        if "mix" in answers:
            idx=QUESTIONS["mix"][1].index(answers["mix"])
            if idx<3: mix=answers.get("trial_mix",PRESETS[idx])
            elif "sat_pct" in answers:
                c,s=int(answers["core_pct"][:-1]),int(answers["sat_pct"][:-1])
                mix=(c,s,100-c-s)
        event_id=sha256((stamp+choice).encode()).hexdigest()
        event={"id":event_id,"time":datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds"),
               "key":key,"title":q["問題"],"options":q["選項"],"advice":{k:q[k] for k in
               ("建議先比較","理由","候選資料","配置說明","股票桶占比","方案") if k in q},
               "choice":choice,"url":q["影片"]["網址"],"stage":stage,"answers":answers,
               "next":after.get("問題","取得 B 基準資料後接續"),"mix":mix,"previous":len(history),
               "token":q.get("方案識別","")}
        candidate=folder/("03-"+uuid.uuid4().hex+".xlsx")
        with TemporaryDirectory(dir=folder) as tmp:
            arg=Path(tmp)/"event.json"
            arg.write_text(json.dumps(dict(member=member,input=str(progress),output=str(candidate),
                                           event=event),ensure_ascii=False,default=str))
            subprocess.run([os.environ.get("CODEX_PRIMARY_RUNTIME_NODE","node"),
                str(Path(__file__).with_name("family03_book.mjs")),str(arg)],check=True,capture_output=True)
        journal=calc.reader_module().read_xlsx(candidate).sheets["選擇歷程"].rows
        if len(journal)!=len(history)+1 or journal[-1]["事件識別"]!=event_id:
            raise RuntimeError("FAMILY03_PROGRESS_WRITE_VALIDATION_FAILED")
        return {"status":"FAMILY03_PROGRESS_WRITEBACK_REQUIRED","本人":member,"檔名":progress.name,
                "原檔摘要":revision,"新檔摘要":sha256(candidate.read_bytes()).hexdigest(),
                "候選檔":str(candidate),"事件識別":event_id,"下一題":after,
                "讀回入口":{"action":"progress_receipt","event_id":event_id,"source_revision":revision},
                "保存步驟":"先重讀本人雲端原檔並核對原檔摘要，備份後沿原 ID 更新，再下載核對新檔摘要。原檔已更新時先讀取最新作答，並保留不同選擇。"}
    return run
