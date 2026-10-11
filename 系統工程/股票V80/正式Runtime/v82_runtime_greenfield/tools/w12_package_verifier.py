#!/usr/bin/env python3
from __future__ import annotations
import csv, hashlib, json, os, subprocess, sys, tempfile, zipfile
from pathlib import Path

def sha256(p: Path):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024), b''): h.update(b)
    return h.hexdigest()

def main():
    if len(sys.argv) < 2:
        raise SystemExit('usage: w12_package_verifier.py CHECKPOINT.zip [report.json]')
    zp=Path(sys.argv[1]).resolve()
    outp=Path(sys.argv[2]).resolve() if len(sys.argv)>2 else None
    checks=[]
    def ck(name, cond, detail): checks.append({'id':name,'pass':bool(cond),'detail':str(detail)})
    with zipfile.ZipFile(zp) as z:
        ck('ZIP_CRC', z.testzip() is None, 'zipfile.testzip')
        bad_paths=[n for n in z.namelist() if n.startswith('/') or '..' in Path(n).parts]
        ck('NO_PATH_TRAVERSAL', not bad_paths, f'bad={bad_paths[:3]}')
        nonascii=[i for i in z.infolist() if any(ord(c)>127 for c in i.filename)]
        bad_utf=[i.filename for i in nonascii if not (i.flag_bits & 0x800)]
        ck('UNICODE_FILENAME_METADATA', not bad_utf, f'nonascii={len(nonascii)} bad_utf8_flag={len(bad_utf)}')
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); z.extractall(root)
            man=root/'MANIFEST_SHA256.txt'; inv=root/'SIZE_INVENTORY.tsv'
            ck('MANIFEST_PRESENT',man.is_file(),'MANIFEST_SHA256.txt')
            ck('SIZE_INVENTORY_PRESENT',inv.is_file(),'SIZE_INVENTORY.tsv')
            m={}
            if man.is_file():
                for line in man.read_text(encoding='utf-8').splitlines():
                    if not line.strip(): continue
                    digest, rel=line.split('  ',1); rel=rel.removeprefix('./'); m[rel]=digest
            actual={str(p.relative_to(root)):sha256(p) for p in root.rglob('*') if p.is_file() and p.name!='MANIFEST_SHA256.txt'}
            bad_hash=[rel for rel,d in m.items() if rel not in actual or actual[rel]!=d]
            extra=sorted(set(actual)-set(m)); missing=sorted(set(m)-set(actual))
            ck('MANIFEST_HASHES',not bad_hash,f'entries={len(m)} bad={len(bad_hash)}')
            ck('MANIFEST_COVERAGE',not extra and not missing,f'extra={len(extra)} missing={len(missing)}')
            sizes={}
            if inv.is_file():
                for line in inv.read_text(encoding='utf-8').splitlines():
                    if not line.strip(): continue
                    size, rel=line.split('\t',1); sizes[rel.removeprefix('./')]=int(size)
            inv_actual={str(p.relative_to(root)):p.stat().st_size for p in root.rglob('*') if p.is_file() and p.name not in {'MANIFEST_SHA256.txt','SIZE_INVENTORY.tsv'}}
            bad_size=[rel for rel,s in sizes.items() if inv_actual.get(rel)!=s]
            ck('SIZE_INVENTORY',not bad_size and set(sizes)==set(inv_actual),f'entries={len(sizes)} bad={len(bad_size)} coverage={len(set(sizes)^set(inv_actual))}')
            files=[str(p.relative_to(root)) for p in root.rglob('*') if p.is_file()]
            folded={}; collisions=[]
            for f in files:
                k=f.casefold()
                if k in folded and folded[k]!=f: collisions.append((folded[k],f))
                else: folded[k]=f
            ck('NO_CASEFOLD_COLLISIONS',not collisions,f'collisions={collisions[:3]}')
            jbad=[]
            for p in root.rglob('*.json'):
                try: json.loads(p.read_text(encoding='utf-8'))
                except Exception as e: jbad.append((str(p.relative_to(root)),str(e)))
            ck('JSON_PARSE_ALL',not jbad,f'json={sum(1 for _ in root.rglob("*.json"))} bad={len(jbad)}')
            tbad=[]; tcount=0
            for p in root.rglob('*.tsv'):
                tcount+=1
                try:
                    with p.open(encoding='utf-8',newline='') as f: rows=list(csv.reader(f,delimiter='\t'))
                    widths={len(r) for r in rows if r}
                    if len(widths)>1: tbad.append((str(p.relative_to(root)),sorted(widths)))
                except Exception as e: tbad.append((str(p.relative_to(root)),str(e)))
            ck('TSV_RECTANGULAR',not tbad,f'tsv={tcount} bad={len(tbad)}')
            rt=root/'Latest_Working'/'v82_runtime_greenfield'
            env=os.environ.copy(); env['PYTHONDONTWRITEBYTECODE']='1'; env['PYTHONPATH']=str(rt/'src')+(os.pathsep+env['PYTHONPATH'] if env.get('PYTHONPATH') else '')
            cp=subprocess.run([sys.executable,'-m','compileall','-q',str(rt/'src'),str(rt/'tools')],env=env,capture_output=True,text=True)
            ck('PYTHON_COMPILE',cp.returncode==0,(cp.stderr or cp.stdout or 'PASS').strip()[-800:])
            fg=subprocess.run([sys.executable,str(rt/'tools'/'w12_final_line_gate.py')],cwd=str(rt),env=env,capture_output=True,text=True)
            fgtext=(fg.stdout or '')+'\n'+(fg.stderr or '')
            ck('FRESH_EXTRACT_FINAL_LINE_PASS',fg.returncode==0 and '"status": "PASS"' in fgtext and '78/78 PASS' in fgtext,f'exit={fg.returncode}; tail={fgtext[-500:]}')
            version=(rt/'src'/'livingwater_v82_runtime'/'version.py').read_text(encoding='utf-8').strip()
            ck('CANDIDATE_VERSION_NOT_SELF_ACTIVATED',version=='__version__ = "0.9.0"',version)
            c8=[f for f in files if 'C_Work8_RELEASE' in f or 'C8_RELEASED' in f]
            ck('C_WORK8_NOT_RELEASED',not c8,f'artifacts={c8}')
            readme=(rt/'README.md').read_text(encoding='utf-8') if (rt/'README.md').is_file() else ''
            ck('RUNTIME_README_CURRENT','W12 E07 RECHECK4' in readme and 'READY_FOR_ABC_V82_RUNTIME_READY_GATE' in readme and 'C Work8' in readme and 'not released' in readme.lower() and 'Explicitly **not implemented** here: W6' not in readme,'current runtime README must show candidate ready only for ABC gate and C8 not released')
    ok=all(x['pass'] for x in checks)
    obj={'verifier':'W12 E07 RECHECK4 Package Integrity Verifier','checkpoint':zp.name,'status':'PASS' if ok else 'FAIL','passed':sum(x['pass'] for x in checks),'total':len(checks),'checks':checks,'checkpoint_sha256':sha256(zp),'runtime_readiness':'READY_FOR_ABC_V82_RUNTIME_READY_GATE'}
    if outp:
        outp.write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf-8')
        outp.with_suffix('.txt').write_text(f"{obj['status']} {obj['passed']}/{obj['total']}\nRUNTIME_READINESS={obj['runtime_readiness']}\nSHA256={obj['checkpoint_sha256']}\n"+'\n'.join(f"{x['id']}: {'PASS' if x['pass'] else 'FAIL'} {x['detail']}" for x in checks)+'\n',encoding='utf-8')
    print(json.dumps({'status':obj['status'],'passed':obj['passed'],'total':obj['total'],'runtime_readiness':obj['runtime_readiness'],'checkpoint_sha256':obj['checkpoint_sha256']},ensure_ascii=False))
    if not ok:
        for x in checks:
            if not x['pass']: print('FAIL',x['id'],x['detail'])
        raise SystemExit(1)
if __name__=='__main__': main()
