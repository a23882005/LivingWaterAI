"""Read back data-only publication in a real browser; verify provisional calculation without a formal score."""
import argparse
import json
import math
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
                provisional:window.v703ProvisionalSnapshot,
                m13Risk:v703RiskForConfig(macroConfig.find(c=>c.id==='m13'),Number(document.querySelector('#in_m13')?.value)),
                resultText:document.querySelector('#v703-result')?.textContent,
                cpi:document.querySelector('#in_m05')?.value,
                visible:document.querySelector('#family-data-status')?.textContent})""")
            assert result['asOf']==feed['asOf'],result
            assert result['formal'] is False and result['latest'] is None and result['score'] is False,result
            assert result['cpi']=='' and '官方資料不足' in result['visible'],result
            provisional=result['provisional']
            assert provisional and provisional['asOf']==feed['asOf'],result
            assert provisional['status']=='PROVISIONAL_CPI_EXCLUDED',provisional
            assert provisional['calculationPolicy']=='CPI_EXCLUDED_WITHIN_GROUP_MEAN',provisional
            assert provisional['excludedIndicators']==['m05'],provisional
            assert provisional['effectiveWeights']=={'m05':0,'m13':12.6},provisional
            assert provisional['originalWeights']=={'m05':6.3,'m13':6.3},provisional
            assert provisional['formalAllocationAllowed'] is False and provisional['formalArchiveAllowed'] is False,provisional
            assert provisional['requiredIndicatorsAvailable']==21 and provisional['requiredIndicatorsTotal']==22,provisional
            weights={'panic_vol':16.2,'credit':14.4,'inflation':12.6,'rates_curve':10.8,'liquidity_fc':14.4,'growth':12.6,'valuation':9,'breadth':10}
            assert provisional['groupWeights']==weights and provisional['denominator']==100,provisional
            assert math.isclose(provisional['groupRisk']['inflation'],result['m13Risk'],abs_tol=1e-8),result
            base=sum(provisional['groupRisk'][key]*weight for key,weight in weights.items())/100
            assert math.isclose(base,provisional['avgRiskBase'],abs_tol=1e-8),provisional
            raw=(10-min(10,max(0,base+provisional['accelAdd'])))*10
            final=min(raw,provisional['cap_panic'],provisional['cap_crisis'],provisional['cap_recession'])
            assert math.isfinite(final) and math.isclose(final,provisional['mSafe_final'],abs_tol=1e-8),provisional
            assert '暫行總分' in result['visible'] and '暫行總分' in result['resultText'],result
            assert '6.3%' in result['resultText'] and '12.6%' in result['resultText'],result
            print('LIVE_CPI_EXCLUDED_PROVISIONAL_PASS',json.dumps(result,ensure_ascii=False))
        finally:
            browser.close()


if __name__=='__main__':main()
