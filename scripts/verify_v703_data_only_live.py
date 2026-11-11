"""Read back data-only publication in a real browser; never archive a score."""
import argparse
import json
from pathlib import Path
from playwright.sync_api import sync_playwright
try:
    from validate_v703_publication import validate_publication_gate
except ModuleNotFoundError:
    from scripts.validate_v703_publication import validate_publication_gate


def main():
    p=argparse.ArgumentParser();p.add_argument('--feed',required=True);p.add_argument('--site-url',required=True)
    args=p.parse_args()
    feed=json.loads(Path(args.feed).read_text())
    assert validate_publication_gate(feed)=='DATA_ONLY'
    with sync_playwright() as driver:
        browser=driver.chromium.launch(headless=True)
        try:
            page=browser.new_page(locale='zh-TW',timezone_id='Asia/Taipei')
            page.goto(args.site_url.rstrip('/')+'/?data-only-verify='+feed['asOf'].replace(':',''),wait_until='domcontentloaded',timeout=45000)
            page.wait_for_function('window.v703DataOnly===true && window.v703DataLoaded===true',timeout=45000)
            result=page.evaluate("""() => ({asOf:window.v703SourceBatch?.asOf,
                formal:window.v703CanPublishFormalAllocation(),latest:window.v703Latest,
                score:Number.isFinite(window.v703MacroSnapshot?.mSafe_final),
                cpi:document.querySelector('#in_m05')?.value,
                visible:document.querySelector('#family-data-status')?.textContent})""")
            assert result['asOf']==feed['asOf'],result
            assert result['formal'] is False and result['latest'] is None and result['score'] is False,result
            assert result['cpi']=='' and '官方資料不足' in result['visible'],result
            print('LIVE_DATA_ONLY_NO_SCORE_PASS',json.dumps(result,ensure_ascii=False))
        finally:
            browser.close()


if __name__=='__main__':main()
