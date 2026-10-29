"""Source-backed structural grades, separate from current permission/thesis.

The assessed grade is reviewable analysis under the existing V82 dictionary.
It is not an owner allocation, a quality score or a current safety clearance.
"""
from copy import deepcopy
from datetime import date
from decimal import Decimal


RULE = ('`INDIVIDUAL_STOCK`：大型成熟／高品質、公司特有風險相對較低且正式證據成立 → `B`；'
        '一般正式核准個股 → `C`；高Beta／事件型／高公司特有風險 → `D`。')


def classify(symbol, catalog, rule_text):
    record = catalog.get('items', {}).get(symbol)
    if record is None or RULE not in rule_text:
        return None
    if (catalog.get('schema_version') != 'Family.W8.PublicCompanyGradeEvidence.v1'
        or record.get('symbol') != symbol
        or record.get('asset_type') != 'INDIVIDUAL_STOCK'
        or record.get('assessment_kind') != 'SOURCE_BACKED_STRUCTURAL_DEPLOYMENT_CLASSIFICATION'
        or record.get('assessment_is_owner_approval') is not False
        or record.get('assessment_is_current_safety_clearance') is not False
        or record.get('no_fixed_position_limit_or_target_inferred') is not True
        or record.get('thesis_risk_event_valuation_and_hard_gate_separate') is not True
        or not record.get('assessment_rationale') or len(record.get('excerpts', [])) < 2):
        raise ValueError('COMPANY_GRADE_STRUCTURAL_EVIDENCE_REQUIRED')
    grade = record.get('asset_grade')
    basis = {'B': 'MATURE_DIVERSIFIED_PROFITABLE_COMPANY',
             'D': 'ELEVATED_COMPANY_SPECIFIC_EXPOSURE'}.get(grade)
    if basis is None or record.get('grade_basis') != basis:
        raise ValueError('COMPANY_GRADE_ASSESSMENT_BASIS_MISMATCH')
    filing = record['filing']
    cik = record['company_cik']
    expected_url = ('https://www.sec.gov/Archives/edgar/data/' + str(cik) + '/'
                    + filing['accessionNumber'].replace('-', '') + '/' + filing['primaryDocument'])
    if (filing.get('cik') != cik or filing.get('form') != '10-K'
        or filing.get('source_url') != expected_url
        or record['sources'][0].get('source_url') != expected_url
        or record['sources'][0].get('kind') != 'OFFICIAL_SEC_ANNUAL_FILING'
        or len(record['sources'][0].get('source_sha256', '')) != 64
        or any(not e.get('text') or not e.get('search_anchor') for e in record['excerpts'])):
        raise ValueError('COMPANY_GRADE_SEC_FILING_IDENTITY_REQUIRED')
    # These observations support the reviewable assessment. Positive income
    # alone never produces a grade, Thesis state or clearance in this module.
    for name in ('net_income', 'operating_cashflow'):
        metric = record.get('financial_evidence', {}).get(name, {})
        periods = metric.get('periods', [])
        if len(periods) < 3 or metric.get('namespace') != 'us-gaap':
            raise ValueError('COMPANY_GRADE_COMPARABLE_FINANCIAL_EVIDENCE_REQUIRED')
        ends = set()
        for p in periods:
            days = (date.fromisoformat(p['end']) - date.fromisoformat(p['start'])).days
            if (p.get('accession') != filing['accessionNumber'] or p.get('form') != '10-K'
                or p.get('unit') != 'USD' or not 345 < days < 380
                or p['filed'] != filing['filingDate'] or p['end'] in ends
                or Decimal(p['value']) <= 0):
                raise ValueError('COMPANY_GRADE_COMPARABLE_FINANCIAL_EVIDENCE_REQUIRED')
            ends.add(p['end'])
    return {'asset_grade': grade, 'grade_evidence': deepcopy(record)}
