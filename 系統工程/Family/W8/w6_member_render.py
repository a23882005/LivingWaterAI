"""W8 parameterization layer for the Owner-accepted W6 v16 visual source.

Read only original W6 CSS, cover/header images and reader master from its
verified ZIP. Render only source-backed canonical W6CurrentData plus vetted
content sections; no Joseph-specific values or old report_data ever load.
"""
from __future__ import annotations
import base64
import hashlib
import html
import io
import json
import math
import re
import shutil
import tempfile
import zipfile
from pathlib import Path

W6_ZIP_SHA256 = "b9b8d6eb1718b510f82e41e925f7a9145880caa8d3fe0a2dec4320ada515796e"
CHAPTERS = ["目錄", "重點摘要", "目前實際配置詳細餅圖", "目前實際配置條狀圖與統計",
            "目標配置詳細餅圖", "目前配置與目標配置漂移比較", "債券配置與風險",
            "現在、未來半年與三年市場情境", "六情境攻防定位", "股票與股票ETF估值研究",
            "建議執行順序", "重要風險及定期檢視頻率", "估值小教室", "總經與機構研究"]
COLORS = ("#245C50", "#D9AD55", "#446F7D", "#C98A57", "#617B56", "#8A7DA7", "#8BA5BB", "#B56958")
CONTENTS = {7:"bond", 8:"market", 9:"radar", 10:"valuation", 11:"actions",
            12:"risks", 13:"education", 14:"institutions"}


def _safe(text):
    return html.escape(str(text if text is not None else "未提供"), quote=True)


def _format_money(value):
    from decimal import Decimal
    return f"{Decimal(str(value)):,.2f}"


def _format_pct(value):
    from decimal import Decimal
    return f"{Decimal(str(value))*100:.2f}%"


def _instrument_label(row):
    code=row["代碼"]
    label=row.get("顯示名稱")
    return code+("／"+label if label and label!=code else "")


def _table(columns, rows):
    return ("<table><thead><tr>" + "".join("<th>"+_safe(x)+"</th>" for x in columns)
            + "</tr></thead><tbody>" + "".join("<tr>"+"".join("<td>"+_safe(x)+"</td>" for x in row)+"</tr>" for row in rows)
            + "</tbody></table>")


def _card(title, text):
    return "<article><h3>"+_safe(title)+"</h3><p>"+_safe(text)+"</p></article>"


def _pie(rows):
    cx,cy,r=265,270,185
    angle=-math.pi/2
    chunks=[]
    for i,item in enumerate(rows):
        w=float(item["權重"])
        if not 0<=w<=1: raise ValueError("W6_PIE_WEIGHT")
        end=angle+w*2*math.pi
        x,y=cx+r*math.cos(angle),cy+r*math.sin(angle)
        x2,y2=cx+r*math.cos(end),cy+r*math.sin(end)
        if w>=1-1e-12:
            chunks.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{COLORS[i%len(COLORS)]}" />')
        elif w>0:
            path=(f'<path d="M{cx},{cy} L{x:.2f},{y:.2f} A{r},{r} 0 '
                  f'{1 if w>0.5 else 0},1 {x2:.2f},{y2:.2f} Z" '
                  f'fill="{COLORS[i%len(COLORS)]}" stroke="#fbfaf5" stroke-width="2"/>')
            chunks.append(path)
            if w>=.032:
                mid=(angle+end)/2
                tx,ty=cx+r*.70*math.cos(mid),cy+r*.70*math.sin(mid)
                chunks.append(f'<text x="{tx:.1f}" y="{ty:.1f}" font-size="16" '
                              f'fill="white" text-anchor="middle">{i+1}</text>')
        angle=end
    return '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 530 540">'+''.join(chunks)+'</svg>'


def _radar_panels(radar):
    """Existing W6 ordinal 1-6 scores, never impute missing C output."""
    if (not isinstance(radar,dict) or not radar.get("source_reference")
            or radar.get("data_provenance")!="SOURCE_BACKED"):
        raise ValueError("W6_CANONICAL_FOUR_RADAR_REQUIRED")
    keys=radar.get("view_order",("current_defense","current_attack","target_defense","target_attack"))
    labels={"current_defense":"目前防禦","current_attack":"目前攻擊",
            "target_defense":"目標防禦","target_attack":"目標攻擊"}
    axes=("牛市初期","牛市中期","牛市末期","正常修正","景氣衰退","金融危機")
    if "axes" in radar:
        axes=tuple(x["label_zh"] for x in radar["axes"])
    views=radar.get("views",{})
    if set(views)!=set(labels) or len(keys)!=4 or set(keys)!=set(labels) or len(axes)!=6:
        raise ValueError("W6_FOUR_RADAR_INCOMPLETE")
    result=[]
    for key in keys:
        label=labels[key]
        vals=views[key].get("levels")
        if not isinstance(vals,list) or len(vals)!=6 or any(
                not (n is None and radar.get("allow_unknown") is True) and
                (type(n)!=int or n<1 or n>6) for n in vals):
            raise ValueError("W6_RADAR_SCORES_INVALID")
        color="#245C50" if "defense" in key else "#AB843A"
        cx,cy,R=225,185,110
        a=[i*math.pi/3-math.pi/2 for i in range(6)]
        pts=[(cx+R*v/6*math.cos(ang),cy+R*v/6*math.sin(ang)) for ang,v in zip(a,vals) if v is not None]
        outline=' '.join(f"{x:.1f},{y:.1f}" for x,y in pts)
        pieces=[f'<circle cx="{cx}" cy="{cy}" r="{R}" fill="none" stroke="#bfcfc3" />']
        if None not in vals:
            pieces.append(f'<polygon points="{outline}" fill="{color}" fill-opacity="0.22" stroke="{color}" stroke-width="3"/>')
        else:
            pieces.append(f'<text x="{cx}" y="{cy}" text-anchor="middle" font-size="16">UNKNOWN／待來源補齊</text>')
        for ang,axis in zip(a,axes):
            x,y=cx+(R+36)*math.cos(ang),cy+(R+36)*math.sin(ang)
            # Wrap long canonical Chinese labels without shortening/relabeling.
            lines=[axis[i:i+7] for i in range(0,len(axis),7)]
            spans=''.join(f'<tspan x="{x:.1f}" dy="{0 if i==0 else 17}">{_safe(t)}</tspan>'
                          for i,t in enumerate(lines))
            pieces.append(f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="middle" font-size="14">{spans}</text>')
        result.append('<article><h3>'+_safe(label)+'</h3><svg viewBox="0 0 450 380">'+''.join(pieces)+'</svg>'+
                      '<small>六級評等，非報酬預測；來源：'+_safe(radar["source_reference"])+"</small></article>")
    return '<div class="grid radar">'+''.join(result)+'</div>'


def _section_items(items, *, envelope=None):
    output=[]
    for item in items:
        title=_safe(item.get("heading"))
        body=_safe(item.get("body"))
        src=_safe(item.get("source_reference"))
        if envelope and envelope.get("as_of"):
            src+="；資料日期："+_safe(envelope["as_of"])
        if envelope and envelope.get("scope"):
            src+="；來源範圍："+_safe(envelope["scope"])
        output.append("<article><h3>"+title+"</h3><p>"+body+"</p><small>來源："+src+"</small></article>")
    return output


def _verified_sections(current):
    sections=current.get("verified_sections")
    if not isinstance(sections,dict) or set(sections)!=set(CONTENTS.values()):
        raise ValueError("W6_VERIFIED_CHAPTER_CONTENT_MISSING")
    for name,rows in sections.items():
        if (not isinstance(rows,list) or not rows
                or any(not isinstance(x,dict) or not x.get("heading") or not x.get("body")
                       or not x.get("source_reference") for x in rows)):
            raise ValueError("W6_VERIFIED_SECTION_MISSING:"+name)
    return sections


def _build_blocks(data):
    sections=_verified_sections(data)
    actual=data["actual"];target=data["target"];drift=data["drift"]
    if len(CHAPTERS)!=14 or len(actual)>100 or len(target)>100:
        raise ValueError("W6_UNSUPPORTED_REPORT_SIZE")
    parts={i:[] for i in range(1,15)}
    parts[1]=['<div id="toc"></div>']
    parts[2]=[_card("投資池目前已確認市值（新台幣）", "NT$"+_format_money(data["current_total_twd"])),
              _card("長期目標配置", ("依本人正式確認的 Final Target v"+_safe(data["target_version"]))
                    if data.get("target_version") is not None else "UNKNOWN；尚待核准目標來源。"),
              _card("本次投資分析", ("同輪正式計算結果" if data.get("report_scope")=="CANONICAL_CALCULATION"
                    else "來源回顧；未提供的正式計算結果保留 UNKNOWN")+"；僅供投資教育，交易由本人決定。"),
              _card("行情資料日期",data["market_as_of"]),
              _card("本人正式來源", "客戶別"+data["member_alias"]+"；DB摘要已綁定，完整來源存本輪檔案紀錄。")]
    parts[3]=['<div class="piegrid"><div>'+_pie(actual)+'</div><div>'+_table(
        ["編號","代碼／標的","目前比例","新台幣市值"],[[i+1,_instrument_label(row),_format_pct(row["權重"]),_format_money(row["市值TWD"])] for i,row in enumerate(actual)])+'</div></div>']
    parts[4]=['<div class="bars">'+''.join(
        '<div class="barrow"><span>'+_safe(_instrument_label(row))+
        '</span><div><i style="width:'+str(min(100.,float(row["權重"])*100))+
        '%"></i></div><b>'+_format_pct(row["權重"])+"</b></div>" for row in actual)+'</div>']
    parts[5]=['<div class="piegrid"><div>'+_pie(target)+'</div><div>'+_table(
        ["編號","代碼／標的","目標比例","目標金額（新台幣）"],[[i+1,_instrument_label(row),_format_pct(row["權重"]),_format_money(row["市值TWD"])] for i,row in enumerate(target)])+'</div></div>']
    for i in range(0,len(drift),9):
        dual=[]
        for row in drift[i:i+9]:
            cp=_format_pct(row["實際權重"]);tp=_format_pct(row["目標權重"])
            current_width=min(100.,float(row["實際權重"])*100)
            target_width=min(100.,float(row["目標權重"])*100)
            dual.append('<div class="barrow"><span>'+_safe(row["標的"])+
                '</span><div><small>目前 '+cp+'</small><i style="height:11px;background:#64899B;width:'+str(current_width)+
                '%"></i><small>目標 '+tp+'</small><i style="height:11px;background:#D99042;width:'+str(target_width)+
                '%"></i></div><b>NT$'+_format_money(row["差異TWD"])+"</b></div>")
            if row.get("protected"):
                dual.append('<div class="note">'+_safe(row["標的"])+
                            '：保留既有持倉（HOLD_PROTECTED）；風險說明不等於賣出指示。</div>')
        parts[6].append('<div class="bars">'+''.join(dual)+'</div>')
    parts[6].append('<div class="note">藍＝目前、金＝目標；差額＝目前－目標。逐檔呈現，無「其他」合併。</div>')
    if not target:
        parts[5]=[_card("目標配置資料狀態", "UNKNOWN；尚待核准目標來源，不以零比例表示缺值。")]
    if not drift:
        parts[6]=[_card("漂移資料狀態", "UNKNOWN；尚待正式目標及漂移來源，不以零差額表示缺值。")]
    for number,name in CONTENTS.items():
        envelope=data.get("report_source_lineage",{}).get("sections",{}).get(name)
        parts[number]=_section_items(sections[name],envelope=envelope)
    if data.get("approved_radar") is None and data.get("report_scope")=="SOURCE_REVIEW":
        parts[9].insert(0,_card("四雷達資料狀態", "UNKNOWN；本次未提供正式雷達來源，不補零或沿用舊分數。"))
    else:
        parts[9].insert(0,_radar_panels(data.get("approved_radar")))
    return [{"chapter":i,"title":CHAPTERS[i-1],"parts":parts[i]} for i in range(1,15)]


def _extract_approved(w6_zip):
    if hashlib.sha256(Path(w6_zip).read_bytes()).hexdigest()!=W6_ZIP_SHA256:
        raise ValueError("W6_APPROVED_V16_ZIP_SHA_MISMATCH")
    with zipfile.ZipFile(w6_zip) as z:
        source=z.read("sources/rebuild/src_v16/report.mjs").decode("utf-8")
        css=re.search(r"const css=\s*`([\s\S]*?)`;",source)
        if not css: raise ValueError("W6_APPROVED_CSS_MISSING")
        return (css.group(1),
                z.read("sources/rebuild/mother.html").decode("utf-8"),
                {name:z.read("assets/"+name) for name in
                 ("cover_reference.jpg","header_reference.jpg")})


def _source_html(data,css,images,blocks):
    # Exact approved W6 visual styles with only asset URIs inlined.
    for name,byte in images.items():
        mime="image/jpeg"
        css=css.replace("assets/"+name, "data:"+mime+";base64,"+base64.b64encode(byte).decode())
    css=re.sub(r"@font-face\{[^}]+\}","",css)  # do not redistribute fonts
    css=css.replace("font:21px Report,", "font:21px ")
    person=_safe(data["member_alias"])
    identity=_safe(data["run_id"])
    embedded=json.dumps(blocks,ensure_ascii=False).replace("<","\\u003c")
    cover=('<section class="page cover" id="cover"><div class="hero"></div><div class="body">'
           '<div class="name">'+person+'</div><h1>客戶資產配置訪談交付報告</h1>'
           '<p style="text-align:center">Portfolio Review & Allocation Report</p>'
           '<div class="note">一脈活水，流過歲月；讓資產在歲月裡生長。</div>'
           '<dl>報告版本　Family W6 v16　四戶動態資料版<br>分析時間　'+_safe(data["evaluation_at"])+
           '<br>資料日期　'+_safe(data["market_as_of"])+
           '<br>報告編號　'+identity+
           '<br>目的　　教育、風險與資產配置分析；由客戶自己決定是否交易</dl></div>'
           '<div class="foot"><span>活水AI理財教練・Confidential</span><span>交易授權 NONE</span></div></section>')
    return ('<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8">'
            '<title>'+person+' 配置報告</title><style>'+css+'</style></head><body>'+cover+
            '<main id="pages"></main><script type="application/json" id="blocks">'+embedded+
            '</script><script type="application/json" id="lineage">'+
            json.dumps({"client_id":data["client_id"],"source_digest":data["source_digest"],"current_digest":data["digest"],
                        "data_as_of":data["market_as_of"],"engine_sha":data["engine_result_sha256"],"run_id":data["run_id"]},
                       ensure_ascii=False).replace("<","\\u003c")+
            '</script></body></html>')

# Page assembly is the same W6 v16 dynamic block-paginator, with the member
# title passed from the authenticated caller rather than hard-coded Joseph.
PAGINATION_SCRIPT="""({client}) => {
 const blocks=JSON.parse(document.getElementById('blocks').textContent),root=document.getElementById('pages');let pages=[];
 function make(b){let p=document.createElement('section');p.className='page';p.dataset.chapter=b.chapter;p.innerHTML='<div class="mast"></div><div class="content"><h1>'+b.title+'</h1><div class="parts"></div></div><div class="foot"><span>'+client+'・活水AI理財教練・W6 v16</span><span class="num"></span></div>';root.append(p);pages.push(p);return p;}
 for(const b of blocks){let p=make(b);for(const part of b.parts){let el=document.createElement('div');el.className='part';el.innerHTML=part;p.querySelector('.parts').append(el);if(el.getBoundingClientRect().bottom>p.getBoundingClientRect().top+1390&&p.querySelector('.parts').children.length>1){el.remove();p=make(b);p.querySelector('.parts').append(el);}}}
 const chapters=[];for(let i=0;i<pages.length;i++){let p=pages[i];p.id='page-'+(i+1);p.querySelector('.num').textContent=(i+1)+' / '+pages.length;let ch=chapters.find(x=>x.chapter===Number(p.dataset.chapter));if(!ch){ch={chapter:Number(p.dataset.chapter),start:i+1,end:i+1,title:blocks.find(x=>x.chapter===Number(p.dataset.chapter)).title};chapters.push(ch);}ch.end=i+1;}
 document.querySelector('#toc').innerHTML=chapters.filter(c=>c.chapter!==1).map(c=>'<div class="tocrow"><a href="#page-'+c.start+'">'+String(c.chapter).padStart(2,'0')+'　'+c.title+'</a><span>'+c.start+(c.end===c.start?'':'–'+c.end)+'</span></div>').join('');
 document.getElementById('blocks').remove();return {chapters,numbered_pages:pages.length,physical_pages:pages.length+1};
}"""


def _reader(mother,client,result,pngs):
    s=mother.replace("{{CLIENT_NAME}}",client).replace("{{REPORT_TITLE}}","正式配置報告・W6 v16")
    physical=result["physical_pages"]
    titles=["封面"]+[
        next((x["title"] for x in result["chapters"] if x["start"]<=i<=x["end"]),"")
        for i in range(1,result["numbered_pages"]+1)]
    s=re.sub(r"const FILES=.*?;",f"const FILES=Array.from({{length:{physical}}},(_,i)=>`pages/CR-IMG-${{String(i+1).padStart(3,'0')}}.png`);",s,count=1)
    s=re.sub(r"const PAGE_TITLES=\[[\s\S]*?\];",lambda _:"const PAGE_TITLES="+json.dumps(titles,ensure_ascii=False)+";",s,count=1)
    s=s.replace("const BODY_TOTAL=19;",f"const BODY_TOTAL={result['numbered_pages']};")
    s=s.replace("return i>=2?i-1:null","return i>=1?i:null")
    toc=[{"label":x["title"],"file":f"pages/CR-IMG-{x['start']+1:03d}.png",
          "top":18.1+i*4.85} for i,x in enumerate(result["chapters"]) if x["chapter"]!=1]
    s=re.sub(r"const TOC_LINKS=.*?;",lambda _:"const TOC_LINKS="+json.dumps(toc,ensure_ascii=False)+";",s,count=1)
    inline={name:"data:image/png;base64,"+base64.b64encode(raw).decode() for name,raw in pngs.items()}
    s=s.replace("/*__INLINE_PAGES_JSON__*/{}",json.dumps(inline))
    if "{{CLIENT_NAME}}" in s or "/*__INLINE_PAGES_JSON__*/{}" in s:
        raise ValueError("W6_READER_MASTER_NOT_BOUND")
    return s.encode("utf-8")


def render_current_w6(data, w6_zip, *, executable=None):
    """Approved W6 v16 brand + page layout; run in active ChatGPT sandbox only.

    Only canonical, source-backed, fully vetted section data can be rendered.
    Return the unchanged output contract for W8 report_archive.publish_report.
    """
    if (not isinstance(data,dict) or data.get("schema_version")!="Family.W8.W6CurrentData.v1"
            or data.get("data_provenance")!="SOURCE_BACKED"
            or data.get("trade_authorization")!="NONE"
            or data.get("digest")!=hashlib.sha256(json.dumps({k:v for k,v in data.items() if k!="digest"},
                   ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()):
        raise ValueError("W6_CURRENT_CANONICAL_DATA_REQUIRED")
    if data.get("member_alias") not in ("mou","Joseph","Arthur","Lilian"):
        raise PermissionError("W6_MEMBER_REQUIRED")
    css,mother,images=_extract_approved(w6_zip)
    blocks=_build_blocks(data)
    try: from playwright.sync_api import sync_playwright
    except ImportError:raise RuntimeError("W6_ON_DEMAND_PLAYWRIGHT_MISSING") from None
    executable=executable or shutil.which("chromium") or shutil.which("google-chrome")
    if not executable: raise RuntimeError("W6_ON_DEMAND_CHROMIUM_MISSING")
    with tempfile.TemporaryDirectory(prefix="w6-on-demand-") as folder:
        out=Path(folder)
        (out/"report.html").write_text(_source_html(data,css,images,blocks),encoding="utf-8")
        (out/"pages").mkdir()
        with sync_playwright() as pw:
            browser=pw.chromium.launch(executable_path=str(executable),headless=True,args=["--no-sandbox"])
            page=browser.new_page(viewport={"width":1135,"height":1600},device_scale_factor=1)
            page.set_content((out/"report.html").read_text(encoding="utf-8"),wait_until="load");page.evaluate("document.fonts.ready")
            result=page.evaluate(PAGINATION_SCRIPT,{"client":data["member_alias"]})
            if result["physical_pages"]>45 or len(result["chapters"])!=14:
                raise ValueError("W6_PAGE_MAP_INVALID")
            qa=page.evaluate("""() => ({broken:[...document.images].filter(x=>!x.complete||!x.naturalWidth).length,
               overflow:[...document.querySelectorAll('.page')].filter(p=>[...p.querySelectorAll('.part')].some(x=>x.getBoundingClientRect().bottom>p.getBoundingClientRect().top+1400)).length})""")
            if qa["broken"] or qa["overflow"]:
                raise ValueError("W6_VISUAL_CONTENT_QA_FAILED")
            # Persist the exact paginated DOM used by PDF and page captures.
            # The source file has an empty #pages and an inert JSON block; it
            # cannot reproduce the body when opened without this browser job.
            page.evaluate("""map => {
                const node=document.createElement('script');
                node.type='application/json';node.id='page-map';
                node.textContent=JSON.stringify(map);document.body.append(node);
            }""",result)
            (out/"report.html").write_text(page.content(),encoding="utf-8")
            page.pdf(path=str(out/"report.pdf"),print_background=True,prefer_css_page_size=True)
            pngs={}
            for i in range(result["physical_pages"]):
                k=f"pages/CR-IMG-{i+1:03d}.png"
                pngs[k]=page.locator(".page").nth(i).screenshot()
            browser.close()
        reader=_reader(mother,data["member_alias"],result,pngs)
        pdf=(out/"report.pdf").read_bytes()
        if not pdf.startswith(b"%PDF-") or not pdf:
            raise ValueError("W6_PDF_INVALID")
        html_bytes=(out/"report.html").read_bytes()
        if data["member_alias"]!="Joseph" and b"Joseph" in html_bytes:
            raise ValueError("W6_OTHER_FAMILY_CONTENT_LEAK")
        zipmem=io.BytesIO()
        with zipfile.ZipFile(zipmem,"w",zipfile.ZIP_DEFLATED) as z:
            z.writestr("index.html",reader)
            z.writestr("README.txt","活水AI W6 v16・先解壓縮，再開啟 index.html。")
            for name,raw in pngs.items():z.writestr(name,raw)
            z.writestr("report.pdf",pdf)
            z.writestr("report.html",html_bytes)
        artifacts={"report.pdf":pdf,"index.html":reader,"report.html":html_bytes,
                   "report.zip":zipmem.getvalue()}
        return {"qa_passed":True,"renderer_contract":"Family.W6.v16.parameterized",
                "client_id":data["client_id"],"source_db_sha256":data["source_db_sha256"],
                "source_digest":data["source_digest"],"w6_current_digest":data["digest"],
                "run_id":data["run_id"],"data_as_of":data["market_as_of"],
                "analysis_version":"W6-v16-parameterized", "page_count":result["physical_pages"],
                "artifacts":artifacts}
