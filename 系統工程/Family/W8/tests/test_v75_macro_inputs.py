"""Official series semantics, source replay and unchanged native evaluation."""
from copy import deepcopy
from datetime import datetime,date,timedelta,timezone
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from zoneinfo import ZoneInfo
import csv,io,json,sys,tempfile,unittest

HERE=Path(__file__).resolve().parents[1];ROOT=HERE.parents[2]
sys.path[:0]=[str(HERE),str(HERE.parent/'W5')]
import v75_macro_inputs as M


class MacroInputsTest(unittest.TestCase):
    def future(self):
        days=['2026-10-21','2026-10-22','2026-10-23','2026-10-26','2026-10-27','2026-10-28']
        zone=ZoneInfo('America/New_York')
        stamps=[int(datetime.fromisoformat(day+'T00:00:00').replace(tzinfo=zone).timestamp()) for day in days]
        stamps.append(int(datetime(2026,10,29,0,30,tzinfo=timezone.utc).timestamp()))
        return {'chart':{'error':None,'result':[{'meta':{'symbol':'ZQJ27.CBT','instrumentType':'FUTURE',
            'currency':'USD','exchangeTimezoneName':'America/New_York','dataGranularity':'1d'},
            'timestamp':stamps,'indicators':{'quote':[{'close':['95.5','95.4','95.3','95.5','95.6','95.6','150']}]}}]}}

    def fixture(self,folder):
        root=Path(folder);sources={};at='2026-10-29T01:00:00Z'
        def save(key,raw,url):
            path=root/(key+'.raw');path.write_bytes(raw);receipt=root/(key+'.receipt')
            h=sha256(raw).hexdigest();receipt.write_text(json.dumps({'url':url,'http_status':200,
                'sha256':h,'requested_at':'2026-10-29T00:59:00Z','available_at':at}))
            sources[key]={'local_path':str(path),'sha256':h,'receipt_path':str(receipt),
                'receipt_sha256':sha256(receipt.read_bytes()).hexdigest()}
        def series(key,rows):
            stream=io.StringIO();writer=csv.writer(stream);writer.writerow(['observation_date',key]);writer.writerows(rows)
            save(key,stream.getvalue().encode(),'https://fred.stlouisfed.org/graph/fredgraph.csv?id='+key)
        days=[];day=date(2016,10,26)
        while day<=date(2026,10,28):
            if day.weekday()<5:days.append(day)
            day+=timedelta(days=1)
        series('EFFR',[(d.isoformat(),'3.88' if d.year>=2024 else '2') for d in days])
        monthly=[]
        for i in range(21):
            index=2025*12+i;monthly.append((date(index//12,index%12+1,1).isoformat(),str(100+i)))
        for key in ['CPILFESL','PCEPILFE']:series(key,monthly)
        for key,value in [('BAMLH0A0HYM2','3.18'),('BAMLC0A0CM','0.88'),('BAMLC0A3CA','0.7'),('BAMLC0A4CBBB','1.1')]:
            series(key,[(d.isoformat(),value) for d in days if d>=date(2026,8,1)])
        header=['2026','2027','2028','2029','Longer run']*3
        rows=[['Variable','Median','Central Tendency','Range'],header,
            ['Federal funds rate','4.1','4.1','3.9','3.6','3.2']+['99']*10]
        html='<table>'+''.join('<tr>'+''.join('<td>'+x+'</td>' for x in row)+'</tr>' for row in rows)+'</table>'
        save('SEP',html.encode(),'https://www.federalreserve.gov/monetarypolicy/fomcprojtabl20260916.htm')
        save('FUTURES',json.dumps(self.future()).encode(),'https://query1.finance.yahoo.com/v8/finance/chart/ZQJ27.CBT?interval=1d')
        stream=io.StringIO();writer=csv.writer(stream);writer.writerow(['Date','3 Mo','2 Yr'])
        writer.writerows((d.strftime('%m/%d/%Y'),'4','3.5') for d in reversed(days) if d>=date(2026,8,1))
        save('TREASURY',stream.getvalue().encode(),'https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/2026/all')
        manifest=root/'manifest.json';manifest.write_text(json.dumps({'schema_version':'Family.W8.V75MacroSourceManifest.v1','sources':sources}))
        return {'local_path':str(manifest),'sha256':sha256(manifest.read_bytes()).hexdigest()},sources

    def test_realized_inflation_is_annualized_from_indices_and_target_is_not_effr(self):
        points={date(2026,1,1):Decimal('100'),date(2026,4,1):Decimal('103.0301')}
        result,basis=M.monthly(points,3)
        self.assertAlmostEqual(float(result),12.68250301319697,places=10)
        self.assertEqual(basis['comparison_date'],'2026-01-01')
        with self.assertRaisesRegex(ValueError,'FRED_IDENTITY'):
            M.fred(b'observation_date,DFEDTARL\n2026-10-27,3.75\n','EFFR',M._time('2026-10-29T01:00:00Z'))

    def test_forming_futures_quote_and_other_horizon_cannot_replace_same_contract(self):
        raw=json.dumps(self.future()).encode();at=M._time('2026-10-29T01:00:00Z')
        value,basis=M.futures(raw,at)
        self.assertEqual(Decimal(value),Decimal('-10'))
        self.assertEqual(basis['comparison_date'],'2026-10-21')
        self.assertEqual(len(basis['excluded_forming_quote_bars']),1)
        wrong=self.future();wrong['chart']['result'][0]['meta']['symbol']='ZQK27.CBT'
        with self.assertRaisesRegex(ValueError,'HORIZON'):M.futures(json.dumps(wrong).encode(),at)

    def test_missing_business_day_is_not_shifted_to_another_comparison(self):
        points={date(2026,10,28):Decimal('3.5'),date(2026,10,21):Decimal('3.4')}
        with self.assertRaisesRegex(ValueError,'SESSION_GAP'):M.window(points,5)

    def test_complete_manifest_replays_original_predicates_without_freshness_promotion(self):
        with tempfile.TemporaryDirectory() as folder:
            source,_=self.fixture(folder);at='2026-10-29T02:00:00Z';pool=M.read(source,at)
            self.assertEqual(pool['shared_metrics']['PRED-001']['effr_pct'],'3.88')
            self.assertEqual(pool['shared_metrics']['PRED-001']['sep_long_run_median_pct'],'3.2')
            self.assertEqual(pool['shared_metrics']['PRED-004']['hy_oas_bps'],'318.00')
            self.assertNotIn('core_ppi_ann3_pct',pool['shared_metrics']['PRED-006'])
            self.assertNotIn('PRED-008',pool['asset_metrics']['SPSB'])
            observations={'assets':[{'symbol':'SPSB','call_trace':[],'v75_original_predicates':{}}]}
            before=deepcopy(observations);out=M.apply(observations,pool,evaluation_at=at,repo_root=ROOT)
            self.assertEqual(observations,before)
            predicates=out['assets'][0]['v75_original_predicates']
            self.assertEqual(set(predicates),{'PRED-001','PRED-002','PRED-003','PRED-004','PRED-006'})
            self.assertTrue(all(p['original_result']['assessment_status']=='VALID' for p in predicates.values()))
            self.assertTrue(all(not p['deployment_input_eligible'] and not p['input_freshness_verified'] for p in predicates.values()))
            req={'evaluation_at':at};context={'v75_macro_source_manifest':source}
            report={'v75_macro_inputs':pool,'analysis_result':{'positions':[{'market':out['assets'][0]}]}}
            M.validate(req,context,report,ROOT)
            predicates['PRED-004']['metrics']['hy_oas_bps']='1'
            with self.assertRaisesRegex(PermissionError,'PREDICATE_REPLAY'):M.validate(req,context,report,ROOT)

    def test_changed_source_bytes_cannot_be_accepted_as_new_facts(self):
        with tempfile.TemporaryDirectory() as folder:
            source,files=self.fixture(folder);Path(files['EFFR']['local_path']).write_text('changed')
            with self.assertRaisesRegex(PermissionError,'SOURCE_CHANGED'):M.read(source,'2026-10-29T02:00:00Z')


if __name__=='__main__':unittest.main()
