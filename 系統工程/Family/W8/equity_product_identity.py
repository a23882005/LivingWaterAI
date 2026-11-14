"""Issuer-evidenced type and structural grade for selected equity ETFs.

Framework routing does not copy another security's prices, valuation facts or
safety status. Grades are structural deployment classes, not quality scores.
"""
from copy import deepcopy


def classify(symbol,product,rule_text):
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
