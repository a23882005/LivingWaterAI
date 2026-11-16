import json
from pathlib import Path
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
 b=p.chromium.launch(headless=True,executable_path=__import__('os').environ.get('V703_CHROMIUM'));page=b.new_page(viewport={'width':960,'height':1440},locale='zh-TW',timezone_id='Asia/Taipei'); errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 html=Path('build/site/index.html').read_text();feed=json.loads(Path('build/site/V70_macro_latest.json').read_text())
 def route(r):
  if r.request.url=='http://repair.test/':r.fulfill(content_type='text/html',body=html)
  elif r.request.url=='http://repair.test/V70_macro_latest.json':r.fulfill(json=feed)
  else:r.abort()
 page.route('**/*',route);page.goto('http://repair.test/');page.wait_for_timeout(700)
 result=page.evaluate('''() => ({formal:window.v703CanPublishFormalAllocation(),issues:window.v703DateIssues,status:document.querySelector('#family-data-status').textContent,score:window.v703MacroSnapshot?.mSafe_final,result:document.querySelector('#v703-result').textContent,cash:document.querySelector('#total-cash').textContent,bond:document.querySelector('#total-bond').textContent,stock:document.querySelector('#total-stock').textContent})''');result['errors']=errors;print(json.dumps(result,ensure_ascii=False));Path('build/site/cpi-browser.json').write_text(json.dumps(result,ensure_ascii=False))
 assert result['formal'] is True and result['score'] is not None and not errors, result
 assert all(result[k].strip() != 'NA' for k in ('cash','bond','stock')), result
 if feed['publication'].get('carriedIndicators')==['m05']:assert '沿用2026年9月' in result['result'], result
 page.screenshot(path='build/site/cpi-carry-page.png',full_page=True)
 # A forged carried value and an expired exception must both fail.
 for field,value in ([('value',0),('dataDate','2026-10-01')] if feed['indicators']['m05'].get('carryForward') else []):
  original=feed['indicators']['m05'][field];feed['indicators']['m05'][field]=value
  page.evaluate('window.v703ReloadFeed()');page.wait_for_timeout(400)
  assert page.evaluate('window.v703CanPublishFormalAllocation()') is False,field
  feed['indicators']['m05'][field]=original
 b.close()
