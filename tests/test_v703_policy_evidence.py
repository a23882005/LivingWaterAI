import copy
import datetime as dt
import importlib.util
import pathlib
import unittest

spec = importlib.util.spec_from_file_location('builder', pathlib.Path(__file__).resolve().parents[1] / 'scripts/build_daily_v703_site.py')
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)
NOW = dt.datetime(2026, 10, 22, 3, tzinfo=dt.timezone.utc)


def policy():
    row = dict(value=4.125, status='OK', unit='%', method='official target midpoint',
               observation_date='2026-07-30', effective_date='2026-07-30', publication_date='2026-07-29',
               source_url='https://www.federalreserve.gov/monetarypolicy/openmarket.htm',
               policy_schema=b.POLICY_SCHEMA, retrieval_time='2026-10-22T02:00:00Z',
               last_verified_at='2026-10-22T02:05:00Z',
               lower_bound=dict(value=4.0, effective_date='2026-07-30'),
               upper_bound=dict(value=4.25, effective_date='2026-07-30'))
    row['source_evidence'] = {k: copy.deepcopy(row[k]) for k in ('value','effective_date','publication_date','lower_bound','upper_bound')}
    row['source_evidence'].update(url=row['source_url'], checked_at=row['last_verified_at'],
                                  result='CURRENT_CONFIRMED', excerpt='Synthetic fixture only: current target interval', response_sha256='a'*64)
    row['candidate_checks'] = [dict(site=str(i), url=row['source_url'], metric_or_horizon='Fed target', status='FOUND', checked_at=row['last_verified_at']) for i in range(4)]
    return row


class PolicyEvidenceTests(unittest.TestCase):
    def valid(self, row, now=NOW):
        return b._validate('m06_rate', row, now.date(), {}, now)

    def test_old_effective_recent_evidence(self):
        self.assertEqual(self.valid(policy()), [])

    def test_old_retrieval_cannot_refresh_verification(self):
        r=policy(); r["retrieval_time"]="2026-10-20T02:00:00Z"
        self.assertTrue(self.valid(r))

    def test_wrong_unit(self):
        r=policy(); r["unit"]="basis points"; self.assertTrue(self.valid(r))

    def test_missing_evidence(self):
        r=policy(); del r['source_evidence']; self.assertTrue(self.valid(r))

    def test_exact_expiry_boundary(self):
        r=policy(); t=b._aware_time(r['retrieval_time'])+dt.timedelta(hours=26)
        self.assertEqual(self.valid(r,t-dt.timedelta(microseconds=1)), [])
        self.assertTrue(self.valid(r,t))

    def test_future_effective(self):
        r=policy(); r['effective_date']='2026-10-23'; self.assertTrue(self.valid(r))

    def test_bound_date_and_midpoint(self):
        for field in ('date','midpoint'):
            r=policy()
            if field=='date': r['upper_bound']['effective_date']='2026-07-31'
            else: r['value']=4.2
            self.assertTrue(self.valid(r))

    def test_timezone_future_and_clock_order(self):
        for field, value in [('last_verified_at','2026-10-22T02:05:00'),('last_verified_at','2026-10-23T02:05:00Z'),('retrieval_time','2026-10-22T02:06:00Z')]:
            r=policy(); r[field]=value; self.assertTrue(self.valid(r))

    def test_changed_source_evidence_or_value(self):
        for field, value in [('source_url','https://example.com'),('value',4.2),('publication_date','2026-07-28')]:
            r=policy(); r[field]=value; self.assertTrue(self.valid(r))
        r=policy(); r['source_evidence']['result']='CACHE_READ'; self.assertTrue(self.valid(r))

    def test_normalization_preserves_evidence_no_new_clock(self):
        r=policy(); n=b._normalize(r,'m06_rate')
        self.assertEqual(n['lastVerifiedAt'], r['last_verified_at'])
        self.assertEqual(n['sourceEvidence'], r['source_evidence'])
        self.assertEqual(n['dataDate'],r['effective_date'])

    def test_four_children_fully_checked(self):
        rows={'m06_rate':policy()}
        for key,date in [('m06_inf','2026-09-30'),('m06_rstar','2026-06-30'),('m06_output_gap','2026-06-30')]:
            rows[key]=dict(value=2.0, status='OK', observation_date=date, source_url='https://example.com/fixture',method='fixture',candidate_checks=policy()['candidate_checks'])
        self.assertEqual(b._m06_component_issues(rows,NOW.date(),{},NOW),[])
        for key in rows:
            with self.subTest(key=key):
                bad=copy.deepcopy(rows);bad[key]['observation_date']='2020-01-01'
                self.assertTrue(b._m06_component_issues(bad,NOW.date(),{},NOW))
                bad=copy.deepcopy(rows);bad[key]['candidate_checks']=[]
                self.assertTrue(b._m06_component_issues(bad,NOW.date(),{},NOW))

    def test_malformed_numeric_is_rejected(self):
        for value in (True, None, 'not-a-number', float('nan')):
            r=policy(); r['value']=value; self.assertTrue(self.valid(r))


if __name__=='__main__': unittest.main()
