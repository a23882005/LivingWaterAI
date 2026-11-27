"""Issuer facts -> existing structural grade; no borrowed prices or PE scale."""
from copy import deepcopy
from hashlib import sha256
from decimal import Decimal, InvalidOperation
from pathlib import Path
import json


JAPAN_RULE='FAMILY-00956-VALUATION-20261117'
JAPAN_INDEX='Nikkei 225 High Dividend Yield Stock 50 Index'
JAPAN_RULE_HEADING='## 00956 日本高股息股票ETF正式估值映射｜2026-11-17｜v1.22.2'
JAPAN_RULE_SHA256='fffb9c5c8935022cbe50aaf50c4fd82d17753250286df52253a84301196ae5c8'
JAPAN_PE_METHOD='NIKKEI_INDEX_WEIGHTED_FISCAL_YEAR_ESTIMATE'
JAPAN_PB_METHOD='NIKKEI_INDEX_WEIGHTED_LATEST_QUARTER_BOOK'
JAPAN_HORIZON='PROVIDER_FISCAL_YEAR_ROLL'
JAPAN_ROLL='NEXT_BUSINESS_DAY_AFTER_ANNUAL_RESULTS'


def japan_profile(rule_text, product):
    """Bind the exact approved product-specific clause, never a proposal."""
    sections=rule_text.split(JAPAN_RULE_HEADING)
    if len(sections)!=2:return None
    section=(JAPAN_RULE_HEADING+sections[1].split('\n## ',1)[0]).strip()
    if sha256(section.encode()).hexdigest()!=JAPAN_RULE_SHA256:return None
    return dict(rule_id=JAPAN_RULE,rule_section_sha256=JAPAN_RULE_SHA256,
        index_name=JAPAN_INDEX,scope='INDEX_PROXY',symbol='00956',
        product_evidence=deepcopy(product),waterfall=['FORWARD_PE','PB'],
        methods={'FORWARD_PE':JAPAN_PE_METHOD,'PB':JAPAN_PB_METHOD},
        forecast_horizon=JAPAN_HORIZON,fiscal_year_roll_rule=JAPAN_ROLL,
        absolute_range_applicability=False,
        supplementary_only=['FORECAST_DIVIDEND_YIELD','ROE','FUND_DISTRIBUTION_YIELD'])


def japan_valuation_inputs(metrics, profile, *, evaluation_at=None):
    """Qualify method identity before the unchanged native waterfall.

    No valuation formula or historical series is created here. The existing
    verified Core source supplies current facts and an independently qualified
    historical-reference receipt. Invalid observations remain in the audit.
    """
    if (profile.get('rule_id')!=JAPAN_RULE or profile.get('symbol')!='00956'
        or profile.get('rule_section_sha256')!=JAPAN_RULE_SHA256):
        raise PermissionError('JAPAN_VALUATION_APPROVED_PROFILE_REQUIRED')
    accepted=[];audit=[]
    for source in metrics:
        row=deepcopy(source);name=row.get('metric_name');issues=[]
        if name not in ('FORWARD_PE','PB'):
            audit.append(dict(original=row,issues=['SUPPLEMENTARY_NOT_PRIMARY']));continue
        method=profile['methods'][name]
        if (row.get('scope')!='INDEX_PROXY' or row.get('index_name')!=JAPAN_INDEX
            or row.get('method')!=method
            or row.get('product_evidence_sha256')!=profile['product_evidence']['source_artifact_sha256']
            or row.get('methodology_reference')!='https://indexes.nikkei.co.jp/nkave/archives/file/users_guide_en.pdf'):
            issues.append('SAME_OFFICIAL_INDEX_METHOD_AND_PRODUCT_BINDING_REQUIRED')
        if name=='FORWARD_PE':
            if (row.get('forecast_horizon')!=JAPAN_HORIZON
                or row.get('fiscal_year_roll_rule')!=JAPAN_ROLL):
                issues.append('PROVIDER_FISCAL_YEAR_METHOD_REQUIRED')
            if not row.get('applicable_fiscal_year'):
                issues.append('APPLICABLE_FISCAL_YEAR_NOT_PROVIDED')
        elif not row.get('book_value_period'):
            issues.append('LATEST_QUARTER_BOOK_PERIOD_NOT_PROVIDED')
        try:
            value=Decimal(str(row.get('current')))
            if isinstance(row.get('current'),bool) or not value.is_finite() or value<=0:
                raise InvalidOperation
        except (InvalidOperation,ValueError):
            issues.append('NONPOSITIVE_OR_UNAVAILABLE_DENOMINATOR_METRIC')
        if issues:row['data_quality']='UNKNOWN'
        history=row.get('historical_basis') or {}
        # A numeric median alone is not a same-index historical receipt.
        expected=dict(index_name=JAPAN_INDEX,method=method,scope='INDEX_PROXY',
            pit_status='VERIFIED',constituent_basis='AS_KNOWN_AT_EACH_OBSERVATION')
        if name=='FORWARD_PE':expected['forecast_horizon']=JAPAN_HORIZON
        history_ok=all(history.get(k)==v for k,v in expected.items())
        original={}
        if row.get('historical_median') is not None:
            proof=history.get('proof') or {}
            history_ok=history_ok and bool(proof.get('local_path')) and bool(proof.get('sha256'))
            if history_ok:
                raw=Path(proof['local_path']).read_bytes()
                if sha256(raw).hexdigest()!=proof['sha256']:
                    raise PermissionError('JAPAN_VALUATION_HISTORY_BYTES_CHANGED')
                original=json.loads(raw)
                from member_market_source import time
                history_ok=(all(original.get(k)==v for k,v in expected.items())
                    and original.get('historical_median')==row['historical_median']
                    and original.get('qualification')=='VERIFIED_UNDER_EXISTING_V82_HISTORY_RULES'
                    and bool(original.get('source_reference'))
                    and bool(original.get('historical_publication_receipt_reference'))
                    and evaluation_at is not None and bool(original.get('available_at'))
                    and time(original['available_at'])<=time(evaluation_at))
            if not history_ok:
                issues.append('SAME_INDEX_METHOD_QUALIFIED_HISTORY_REQUIRED')
                row['historical_median']=None
        # No borrowed absolute PE range or pasted valuation label/percentile.
        # The native Core calculates the original relative-median boundaries.
        for key in ('valuation_level','expensiveness_percentile','secondary_confirmation'):
            if row.get(key) is not None:
                if (key=='valuation_level' or not history_ok
                    or original.get(key)!=row[key]
                    or key=='secondary_confirmation' and not original.get('secondary_confirmation_source_reference')):
                    row.pop(key)
                    issues.append('UNBOUND_CLASSIFICATION_OR_CONFIRMATION_NOT_USED:'+key)
        accepted.append(row)
        audit.append(dict(metric=name,original=deepcopy(source),issues=issues,
            earnings_quality_issue=deepcopy(source.get('earnings_quality_issue')),
            qualified_current=row.get('data_quality') in ('OK','FALLBACK_USED'),
            qualified_historical_reference=history_ok and row.get('historical_median') is not None))
    return accepted,audit


def classify(symbol,product,rule_text):
    if symbol not in ('0050','VOO','VEA','00956'):return None
    contracts={
        '0050':('https://www.yuantaetfs.com/product/detail/0050/Basic_information','FTSE TWSE Taiwan 50 Index',50),
        'VOO':('https://advisors.vanguard.com/investments/products/voo/vanguard-sp-500-etf','S&P 500 Index',None),
        'VEA':('https://advisors.vanguard.com/investments/products/vea/vanguard-ftse-developed-markets-etf','FTSE Developed All Cap ex US Index',None),
        '00956':('https://www.twse.com.tw/zh/ETFortune/newsDetail/8a8216d6913637e4019158f3101b0093','Nikkei 225 High Dividend Yield Stock 50 Index',50)}
    url,index,count=contracts[symbol]
    if (product.get('schema_version')!='Family.W8.PublicIssuerIdentity.v1'
        or product.get('symbol')!=symbol or product.get('source_url')!=url
        or product.get('benchmark')!=index or product.get('is_stock_etf') is not True
        or product.get('replication')!='INDEX_REPLICATION'
        or not product.get('evidence_reference') or not product.get('source_artifact_sha256')
        or len(product['source_artifact_sha256'])!=64 or not product.get('excerpts')
        or count is not None and product.get('index_company_count')!=count):
        raise ValueError('BROAD_PRODUCT_INDEPENDENT_ISSUER_EVIDENCE_REQUIRED')
    grade='B' if symbol in ('0050','00956') else 'A'
    phrase='中度集中／成長或大型權值集中，但仍屬Broad核心曝險 → `B`' if grade=='B' else '廣泛分散核心市場結構 → `A`'
    if phrase not in rule_text:raise ValueError('BROAD_PRODUCT_CANONICAL_GRADE_CONTRACT_REQUIRED')
    framework={'0050':'第五十章｜0050型','VOO':'第四十八章｜S&P 500／VOO型'}.get(symbol)
    if framework and '# '+framework not in rule_text:raise ValueError('BROAD_PRODUCT_FORMAL_FRAMEWORK_REQUIRED')
    result={'asset_type':'BROAD_ETF','asset_grade':grade,
        'primary_class':{'0050':'台灣大型權值ETF','VOO':'美國大型核心ETF'}.get(symbol,'UNKNOWN'),
        'primary_framework':framework,'product_evidence':deepcopy(product),
        'grade_evidence':{'rule':'V82.md Canonical Asset Grade §2.1',
            'basis':'OFFICIAL_INDEX_STRUCTURE_AND_FORMAL_GRADE_MAPPING',
            'facts':deepcopy(product),'current_safety_or_valuation_inferred':False},
        'analysis_capabilities':[{'0050':'V82_TAIWAN_CORE','VOO':'V82_US_LARGE_CORE','VEA':'V82_OWN_BROAD_COMPONENT_CORE','00956':'V82_OWN_BROAD_COMPONENT_CORE'}[symbol]],
        'valuation_waterfall':{'0050':['FORWARD_PE','PB','FCF_YIELD'],
            'VOO':['FORWARD_PE','CAPE','TRAILING_PE','FCF_YIELD','PB'],'VEA':[],'00956':[]}[symbol]}
    if symbol=='VEA':
        # A developed ex-US index is not a VT/World allocation. The source
        # establishes identity and diversification, not an authorized VT scale.
        result.update(valuation_waterfall=[],framework_resolution='DEVELOPED_EX_US_PRIMARY_PROFILE_REQUIRES_FORMAL_MAPPING',
            framework_resolution_kind='FORMAL_PRODUCT_PROFILE_MAPPING_REQUIRED')
    if symbol=='00956':
        result.update(framework_resolution='JAPAN_HIGH_DIVIDEND_PRIMARY_PROFILE_REQUIRES_FORMAL_MAPPING',
            framework_resolution_kind='FORMAL_PRODUCT_PROFILE_MAPPING_REQUIRED')
        profile=japan_profile(rule_text,product)
        if profile is not None:
            result.update(primary_class='日本高股息股票ETF',primary_framework=JAPAN_RULE,
                valuation_waterfall=['FORWARD_PE','PB'],valuation_profile=profile,
                framework_resolution='APPROVED_PRODUCT_SPECIFIC_MAPPING',
                framework_resolution_kind='RULE_APPROVED_FOR_IMPLEMENTATION')
    return result
