"""Issuer-evidenced type and structural grade for selected equity ETFs.

Framework routing does not copy another security's prices, valuation facts or
safety status. Grades are structural deployment classes, not quality scores.
"""
from copy import deepcopy
from datetime import datetime, timezone


# Pin the reviewed original bytes, not just a well-formed hash supplied by a
# caller. Originals and HTTP receipts accompany the private PM handback.
ROUTING_SOURCES={
    'VDC':('https://workplace.vanguard.com/assets/corp/fund_communications/pdf_publish/us-products/fact-sheet/F0955.pdf',
        'a650174c963e6cbc79f61c507a3222dbb0c0066ad84864087b7d3994b61081e4',
        '2026-11-17T07:46:27.177684+00:00'),
    '2454':('https://www.mediatek.com/company/discover',
        'b1f7234bb5a2b4225831a19e2fd8b2f6379511c982c6e657ea00beb47fdcd51e',
        '2026-11-17T07:46:27.971412+00:00')}


def _time(value):
    try:
        stamp=datetime.fromisoformat(value.replace('Z','+00:00'))
        if stamp.tzinfo is None:raise ValueError('timezone required')
        return stamp
    except (ValueError,TypeError,AttributeError) as error:
        raise ValueError('ROUTING_EVIDENCE_TIME_REQUIRED') from error


def _classify_reviewed_route(symbol,product,rule_text,evaluation_at):
    url,original_sha,captured_at=ROUTING_SOURCES[symbol]
    sources=product.get('sources')
    if (product.get('schema_version')!='Family.W8.PublicIssuerIdentity.v1'
        or product.get('symbol')!=symbol
        or product.get('evidence_kind')!='OFFICIAL_ISSUER_CLASSIFICATION'
        or product.get('source_url')!=url or not product.get('excerpts')
        or not isinstance(sources,list) or len(sources)!=1 or not isinstance(sources[0],dict)
        or sources[0].get('source_url')!=url
        or sources[0].get('source_sha256')!=original_sha):
        raise ValueError('REVIEWED_ROUTING_SOURCE_IDENTITY_OR_HASH_REQUIRED')
    proof=sources[0]
    at=_time(evaluation_at) if evaluation_at is not None else datetime.now(timezone.utc)
    available=_time(proof.get('available_at'));retrieved=_time(proof.get('retrieved_at'))
    # No original publication timestamp is proven for these captures. In
    # particular, the factsheet's as-of date is not its availability date.
    if available!=retrieved or available!=_time(captured_at) or available>at:
        raise ValueError('ROUTING_EVIDENCE_NOT_AVAILABLE_AT_EVALUATION')
    if symbol=='VDC':
        required=('`SECTOR_ETF / INDUSTRY_ETF / THEME_ETF` → `C`',
            '##### PV4 9 產業 主題ETF SECTOR_THEME_ETF',
            '#### PV4A 新增有限產業路由表',
            'R4 股票ETF：官方投資目標／指數納入規則只指向一個已知sector',
            'PROFITABLE_NONFINANCIAL_GENERIC：Forward PE → EV/EBITDA → FCF Yield → EV/Sales。')
        if not all(clause in rule_text for clause in required):
            raise ValueError('FORMAL_VDC_SINGLE_SECTOR_ROUTE_REQUIRED')
        if (product.get('fund_name')!='Vanguard Consumer Staples ETF'
            or product.get('is_stock_etf') is not True
            or product.get('structure_kind')!='PASSIVE_SINGLE_SECTOR_EQUITY'
            or product.get('sector')!='Consumer Staples'
            or product.get('benchmark')!='MSCI US Investable Market Consumer Staples 25/50 Index'
            or product.get('cusip')!='92204A207'
            or product.get('listing')!={'exchange':'NYSE Arca','ticker':'VDC'}
            or product.get('strategy')!={'management':'PASSIVE',
                'replication':'FULL_REPLICATION_WHEN_POSSIBLE','current_implementation':'SAMPLING',
                'scope':'UNLEVERAGED_NON_INVERSE_EQUITY__NOT_DERIVATIVE_DOMINATED'}
            or product.get('taxonomy_provider')!='Vanguard / GICS'
            or product.get('taxonomy_version')!='F0955_092026'
            or product.get('taxonomy_version_scope')!='PROVIDER_CLASSIFICATION_SNAPSHOT__NOT_GICS_GLOBAL_RELEASE_VERSION'
            or product.get('classification_as_of')!='2026-09-30'):
            raise ValueError('VDC_OFFICIAL_SINGLE_SECTOR_CLASSIFICATION_REQUIRED')
        if _time(product.get('classification_available_at'))!=available:
            raise ValueError('VDC_CLASSIFICATION_AVAILABILITY_REQUIRED')
        result={'asset_type':'SECTOR_ETF','asset_grade':'C','primary_class':'產業／主題ETF',
            'primary_framework':'V82.md PV4 9 / PV4A R4 Consumer Staples',
            'framework_scope':'OWN_SECTOR_EQUITY_DATA__NO_BENCHMARK_VALUATION_SUBSTITUTION',
            # Reuse the existing explicit-waterfall component adapter. This
            # capability does not alter the SECTOR_ETF identity or grade.
            'analysis_capabilities':['V82_OWN_BROAD_COMPONENT_CORE'],
            'valuation_waterfall':['FORWARD_PE','EV_EBITDA','FCF_YIELD','EV_SALES'],
            'valuation_rule_source':'V82.md PV4 9 / PV4A R4 PROFITABLE_NONFINANCIAL_GENERIC',
            'valuation_route':'PROFITABLE_NONFINANCIAL_GENERIC',
            'sector':'Consumer Staples','taxonomy_provider':product['taxonomy_provider'],
            'taxonomy_version':product['taxonomy_version'],
            'taxonomy_version_scope':product['taxonomy_version_scope'],
            'classification_as_of':product['classification_as_of'],
            'classification_available_at':product['classification_available_at']}
        basis='OFFICIAL_PASSIVE_SINGLE_SECTOR_EQUITY__CANONICAL_SECTOR_GRADE'
    else:
        if (product.get('company_name')!='MediaTek Incorporated'
            or product.get('security_type')!='Common Stock'
            or product.get('listing')!={'exchange':'TWSE','ticker':'2454'}
            or product.get('industry')!='SEMICONDUCTOR' or product.get('business_model')!='FABLESS'
            or '單一上市公司之普通股／股票權益' not in rule_text
            or '## 32.8 Semiconductor｜半導體' not in rule_text
            or 'Forward P/E → EV/EBITDA → EV/Sales → P/S → FCF Yield' not in rule_text):
            raise ValueError('MEDIATEK_OFFICIAL_SEMICONDUCTOR_ROUTE_REQUIRED')
        result={'asset_type':'INDIVIDUAL_STOCK','asset_grade':'UNKNOWN','primary_class':'UNKNOWN',
            'primary_framework':'V82.md §32.8 Semiconductor',
            'framework_scope':'INDUSTRY_ROUTE_ONLY__COMPANY_QUALITY_AND_PRIMARY_CLASS_UNDETERMINED',
            'analysis_capabilities':['V82_INDIVIDUAL_COMPONENT_CORE'],
            'valuation_waterfall':['FORWARD_PE','EV_EBITDA','EV_SALES','PS','FCF_YIELD'],
            'valuation_rule_source':'V82.md §32.8 Semiconductor / PV4 10',
            'company_identity':deepcopy(product)}
        basis='PRODUCT_AND_INDUSTRY_IDENTITY_DO_NOT_ESTABLISH_COMPANY_ASSET_GRADE'
    result['grade_evidence']={'rule':'V82.md Canonical Asset Grade §2.1',
        'basis':basis,'official_sources':deepcopy(sources),'facts':deepcopy(product),
        'assessment_kind':'SOURCE_BACKED_STRUCTURAL_CLASSIFICATION' if symbol=='VDC' else 'IDENTITY_ONLY__GRADE_UNKNOWN',
        'owner_approval_or_quality_score_inferred':False,'current_safety_or_valuation_inferred':False}
    return result


def classify(symbol,product,rule_text,*,evaluation_at=None):
    if symbol in ROUTING_SOURCES:
        return _classify_reviewed_route(symbol,product,rule_text,evaluation_at)
    if symbol not in ('CPAI','DYNF','DRAM'):return None
    if (product.get('schema_version')!='Family.W8.PublicIssuerIdentity.v1'
        or product.get('symbol')!=symbol or product.get('is_stock_etf') is not True
        or product.get('evidence_kind')!='OFFICIAL_ISSUER_OBJECTIVE_AND_STRUCTURE'
        or not product.get('excerpts') or not product.get('sources')
        or any(not p.get('source_url') or len(p.get('source_sha256',''))!=64 for p in product['sources'])):
        raise ValueError('EQUITY_PRODUCT_STRUCTURE_EVIDENCE_REQUIRED')
    required='中度集中／成長或大型權值集中，但仍屬Broad核心曝險 → `B`'
    if symbol in ('CPAI','DYNF') and required not in rule_text:
        raise ValueError('FORMAL_MODERATELY_CONCENTRATED_BROAD_GRADE_REQUIRED')
    if symbol=='CPAI':
        if (product.get('fund_name')!='Counterpoint Quantitative Equity ETF'
            or product.get('source_url')!='https://counterpointfunds.com/cpai/'
            or product.get('structure_kind')!='ACTIVE_BROAD_EQUITY_SELECTION'
            or product.get('security_universe')!='US_LISTED_COMMON_STOCKS_AND_ADRS_ANY_CAP'
            or product.get('minimum_equity_name_count')!=50
            or product.get('maximum_sector_weight_percent')!=35
            or product.get('maximum_industry_weight_percent')!=25):
            raise ValueError('CPAI_OFFICIAL_BROAD_SELECTION_STRUCTURE_REQUIRED')
        result={'asset_type':'BROAD_ETF','asset_grade':'B','primary_class':'美國大型核心ETF',
            'primary_framework':'V82.md §32.2 美國股票核心／因子選股（Broad ETF Core）',
            'framework_scope':'ANALYSIS_ROUTING_PROXY__ALL_CAP_US_LISTED_EQUITY_NOT_LARGE_CAP_MANDATE',
            'secondary_framework':'V82.md §32.2 美國中小型ETF（all-cap selection cross-check）',
            'analysis_capabilities':['V82_BROAD_EQUITY_CORE'],
            'grade_basis':'MODERATELY_CONCENTRATED_BROAD_CORE__ACTIVE_MINIMUM_50_EQUITY_SELECTION'}
    elif symbol=='DYNF':
        if (product.get('fund_name')!='iShares U.S. Equity Factor Rotation Active ETF'
            or product.get('source_url')!='https://www.blackrock.com/us/individual/products/307283/blackrock-us-equity-factor-rotation-etf'
            or product.get('structure_kind')!='ACTIVE_BROAD_EQUITY_FACTOR_ROTATION'
            or product.get('benchmark')!='MSCI USA Index'
            or set(product.get('factors',[]))!={'value','quality','momentum','size','growth','minimum volatility'}):
            raise ValueError('DYNF_OFFICIAL_FACTOR_ROTATION_STRUCTURE_REQUIRED')
        result={'asset_type':'BROAD_ETF','asset_grade':'B','primary_class':'美國大型核心ETF',
            'primary_framework':'V82.md §32.2 美國大型核心ETF（active factor rotation）',
            'framework_scope':'US_EQUITY_FACTOR_ROTATION__NOT_A_VT_OR_QQQ_IDENTITY',
            'analysis_capabilities':['V82_BROAD_EQUITY_CORE'],
            'grade_basis':'MODERATELY_CONCENTRATED_BROAD_CORE__ACTIVE_FACTOR_SELECTED_US_EQUITY'}
    else:
        if (product.get('fund_name')!='Roundhill Memory ETF'
            or product.get('source_url')!='https://www.roundhillinvestments.com/etf/dram/'
            or product.get('structure_kind')!='MEMORY_SEMICONDUCTOR_EQUITY_INDUSTRY'
            or product.get('minimum_memory_revenue_or_profit_percent')!=50
            or product.get('minimum_memory_exposure_percent')!=80
            or product.get('may_use_swaps_and_forwards') is not True
            or product.get('non_diversified') is not True
            or '`SECTOR_ETF / INDUSTRY_ETF / THEME_ETF` → `C`' not in rule_text
            or '## 32.8 Semiconductor｜半導體' not in rule_text
            or 'Forward P/E → EV/EBITDA → EV/Sales → P/S → FCF Yield' not in rule_text):
            raise ValueError('DRAM_OFFICIAL_MEMORY_INDUSTRY_STRUCTURE_REQUIRED')
        result={'asset_type':'INDUSTRY_ETF','asset_grade':'C','primary_class':'半導體ETF',
            'primary_framework':'V82.md §32.8 Semiconductor（memory industry exposure）',
            'framework_scope':'EXISTING_INDUSTRY_FRAMEWORK_WITH_OWN_SECURITY_DATA',
            'analysis_capabilities':['V82_SEMICONDUCTOR_CORE'],
            'valuation_waterfall':['FORWARD_PE','EV_EBITDA','EV_SALES','PS','FCF_YIELD'],
            'valuation_rule_source':'V82.md §32.8 Semiconductor',
            'secondary_style_tags':['NONDIVERSIFIED','DERIVATIVE_LOOKTHROUGH_REQUIRED'],
            'grade_basis':'OFFICIAL_MEMORY_INDUSTRY_OBJECTIVE__CANONICAL_INDUSTRY_GRADE'}
    result['grade_evidence']={'rule':'V82.md Canonical Asset Grade §2.1',
        'basis':result.pop('grade_basis'),'official_sources':deepcopy(product['sources']),
        'facts':deepcopy(product),'assessment_kind':'SOURCE_BACKED_STRUCTURAL_CLASSIFICATION',
        'owner_approval_or_quality_score_inferred':False,'current_safety_or_valuation_inferred':False}
    return result
