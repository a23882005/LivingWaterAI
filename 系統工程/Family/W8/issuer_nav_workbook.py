"""Read issuer-published NAV tables as dated observations of the bound share class."""
from datetime import date, datetime
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from urllib.parse import parse_qs

from etf_structure_source import ISSUER_PRODUCT_PATHS, https_url, matches_product_path
from member_market_source import time
from v75_handoff_inputs import excel_day, xlsx_rows, xml


def _official_url(reference, symbol):
    url = https_url(reference)
    if url is None:
        return False
    if symbol == 'NATO':
        return (url.hostname == 'hanetf.com'
                and url.path == '/wp-content/assets/upload/NAV_history-NATO-IE000OJ5TQP4-all-all.xlsx'
                and not url.query)
    if symbol == 'SOXX':
        query = parse_qs(url.query)
        return (url.hostname == 'www.blackrock.com'
                and url.path == '/varnish-api/blk-one01-product-data/product-data/api/v1/get-fund-document'
                and query.get('portfolioId') == ['239705']
                and query.get('appSubType') == ['ISHARES']
                and query.get('targetSite') == ['us-ishares'])
    if symbol == 'PPH':
        return (url.hostname == 'www.vaneck.com'
                and url.path == '/us/en/investments/pharmaceutical-etf-pph/downloads/fundhistoprices/')
    return symbol == 'VWRA' and matches_product_path(url, ISSUER_PRODUCT_PATHS['VWRA'])


def _soxx_rows(raw):
    book = xml(raw, repair_ampersands=True)
    name = '{urn:schemas-microsoft-com:office:spreadsheet}Name'
    sheets = {sheet.attrib[name]: sheet for sheet in book.findall('{*}Worksheet')}
    performance = sheets['Performance'].find('{*}Table/{*}Row/{*}Cell/{*}Data')
    if performance is None or performance.text != 'iShares Semiconductor ETF':
        raise ValueError('ISSUER_NAV_WORKBOOK_PRODUCT')
    records = [[cell.findtext('{*}Data') for cell in row]
               for row in sheets['Historical'].findall('{*}Table/{*}Row')]
    if not records or records[0][:4] != ['As Of', 'NAV per Share', 'Ex-Dividends', 'Shares Outstanding']:
        raise ValueError('ISSUER_NAV_WORKBOOK_HEADER')
    return [(index, row[0], row[1], {'ex_dividend_usd': row[2], 'shares_outstanding': row[3]})
            for index, row in enumerate(records[1:], 2)], '%b %d, %Y'


def _xlsx_records(raw, symbol):
    rows = xlsx_rows(raw)
    if symbol == 'NATO':
        if (rows[1].get('B') != 'Future of Defence UCITS ETF' or rows[2].get('B') != 'NATO'
                or rows[3].get('B') != 'IE000OJ5TQP4'):
            raise ValueError('ISSUER_NAV_WORKBOOK_PRODUCT')
        header, expected = 4, {'A':'Date','B':'NAV','C':'AuM','D':'Shares Outstanding','E':'Dividend'}
        columns = {'aum_usd':'C','shares_outstanding':'D','ex_dividend_usd':'E'}
        date_format = None
    elif symbol == 'PPH':
        if rows[1].get('A') != 'VanEck Pharmaceutical ETF - PPH':
            raise ValueError('ISSUER_NAV_WORKBOOK_PRODUCT')
        header, expected = 2, {'A':'Date','B':'NAV','E':'Last Trade','I':'AUM'}
        columns = {'last_trade_usd':'E','aum_usd':'I'}
        date_format = '%m/%d/%Y'
    else:
        if rows[4].get('A') != 'Vanguard FTSE All-World UCITS ETF (USD) Accumulating':
            raise ValueError('ISSUER_NAV_WORKBOOK_PRODUCT')
        header, expected = 9, {'A':'Date','B':'NAV (USD)','C':'Market price (GBP)'}
        columns = {'market_price_reference_gbp':'C'}
        date_format = '%d %b %Y'
    if any(rows[header].get(k) != value for k, value in expected.items()):
        raise ValueError('ISSUER_NAV_WORKBOOK_HEADER')
    return [(i, row['A'], row['B'], {name:row.get(column) for name,column in columns.items()})
            for i,row in rows.items() if i > header and row.get('A')], date_format


def _number(raw):
    if raw in (None, '', '--'):
        return None
    value = Decimal(raw.removeprefix('US$').removeprefix('£').replace(',', ''))
    if not value.is_finite() or value < 0:
        raise ValueError('ISSUER_NAV_WORKBOOK_VALUE')
    return str(value)


def read(source, symbol, evaluation_at):
    if source is None:
        return None
    raw = Path(source['local_path']).read_bytes()
    if sha256(raw).hexdigest() != source['sha256'] or not _official_url(source['source_url'], symbol):
        raise PermissionError('ISSUER_NAV_WORKBOOK_IDENTITY_OR_BYTES')
    available = time(source['available_at'])
    if available > time(evaluation_at):
        return None
    records, date_format = _soxx_rows(raw) if symbol == 'SOXX' else _xlsx_records(raw, symbol)
    observations = {}
    for index, source_day, nav, additional in records:
        if symbol == 'VWRA':
            source_day = source_day.replace(' Sept ', ' Sep ')
        day = (datetime.strptime(source_day, date_format).date() if date_format
               else date.fromisoformat(excel_day(source_day)))
        if day > available.date() or day in observations:
            raise ValueError('ISSUER_NAV_WORKBOOK_DATE_OR_DUPLICATE')
        observations[day] = {'source_row':index,'observed_date':day.isoformat(),
                             'fund_nav_usd':_number(nav),**{name:_number(v) for name,v in additional.items()}}
    if not observations:
        raise ValueError('ISSUER_NAV_WORKBOOK_EMPTY')
    return {'symbol':symbol,'source_url':source['source_url'],'source_sha256':source['sha256'],
            'available_at':source['available_at'],'original_dated_rows':len(observations),
            'first_observed_date':min(observations).isoformat(),'latest_observed_date':max(observations).isoformat(),
            'latest_observations':[observations[day] for day in sorted(observations, reverse=True)[:2]],
            'scope':'ISSUER_NAV_OBSERVATION_ONLY',
            'creation_redemption_flows_verified':False,'canonical_price_or_pit_wealth_qualified':False}
