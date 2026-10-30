"""Issuer facts -> existing structural grade; no borrowed prices or PE scale."""
from copy import deepcopy


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
    return result
