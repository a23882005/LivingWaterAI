import os
import time
import datetime
import json
import random
import re
import requests
import urllib3
import sys
import webbrowser
import yfinance as yf
from bs4 import BeautifulSoup

# === Selenium 模組 ===
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager

# 🚫 忽略 SSL 警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- 步驟 1: 自動清場 ---
print("💀 正在清理殘留程序...")
os.system("taskkill /F /IM chrome.exe /T >nul 2>&1") 
time.sleep(2)

print("DEBUG: V66.10 (p128) - 網頁同步修正版 (移除過期判斷，強制每次都開網頁)...") 

# ==========================================
# 📂 檔案設定區
# ==========================================
INPUT_HTML = "V70_2.html"         
OUTPUT_HTML = "V70_Live.html"     
COMMERCIAL_HTML = "index.html"    
COMMERCIAL_DATA = "v70_data.js"   
COMMERCIAL_JS_CORE = "JavaScript核心處理程式.js"
REPORT_FILENAME = "變數狀況報表檔.txt"
MEMORY_FILE = "v70_memory.json"
FAIL_MSG = "N/A"

# 🌟 Logo 設定
LOGO_FOR_INDEX = "index十王國.jpg" 

# 🌟 版權聲明 HTML
COPYRIGHT_HTML = """
    <div class="max-w-5xl mx-auto px-6 py-10 mt-6 border-t border-slate-800/50">
        <div class="text-[11px] text-slate-400 text-center leading-relaxed font-sans mb-4">
            <span class="font-bold text-slate-200">免責聲明：</span>本系統僅供研究、決策輔助及教學之用，非個別化投資建議或投資顧問服務，亦不構成任何投資要約、招攬、推薦或交易指示。過去績效不保證未來結果；投資有風險且可能損失本金，投資人應審慎評估並自負盈虧。
        </div>
        
        <div class="text-[10px] text-slate-500 text-center font-mono tracking-wider">
            <p class="text-slate-400">Copyright © 2025 Josephine Morgan. All rights reserved.</p>
            <p class="mt-1 text-[9px] opacity-75">版權所有，嚴禁未經授權之轉載、改作或逆向工程 (Reverse Engineering)。</p>
        </div>

        <div class="h-8"></div>
    </div>
"""

# ==========================================
# 🔗 資料來源 URL 設定
# ==========================================
URL_PMI_HK = "https://hk.investing.com/economic-calendar/manufacturing-pmi-829"
URL_TE_CORE_CPI = "https://tradingeconomics.com/united-states/core-inflation-rate"
URL_FRED_T10Y2Y = "https://fred.stlouisfed.org/series/T10Y2Y"
URL_CME_FEDWATCH = "https://www.cmegroup.com/markets/interest-rates/cme-fedwatch-tool.html"
URL_INV_FED_MONITOR = "https://www.investing.com/central-banks/fed-rate-monitor"
URL_MMFI_TV = "https://www.tradingview.com/symbols/INDEX-MMFI/"
URL_SA_SPY = "https://stockanalysis.com/etf/spy/"
URL_SA_QQQ = "https://stockanalysis.com/etf/qqq/"
URL_SA_VT = "https://stockanalysis.com/etf/vt/"
URL_WSJ_PE = "https://www.wsj.com/market-data/stocks/pe-yields"
URL_TE_PMI = "https://tradingeconomics.com/united-states/business-confidence"
URL_INV_PMI = "https://www.investing.com/economic-calendar/ism-manufacturing-pmi-173"
URL_CNBC_PMI = "https://www.cnbc.com/quotes/USPMI"
URL_US_INFLATION = "https://www.usinflationcalculator.com/inflation/current-inflation-rates/"
URL_TE_CPI_GENERIC = "https://tradingeconomics.com/united-states/inflation-cpi"
URL_FRED_HY = "https://fred.stlouisfed.org/series/BAMLH0A0HYM2"
URL_CNN_FG = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
URL_CNBC_VIX = "https://www.cnbc.com/quotes/.VIX"
URL_CNBC_10Y2Y = "https://www.cnbc.com/quotes/10Y2YS"
URL_CNBC_OIL = "https://www.cnbc.com/quotes/@CL.1"
URL_CNBC_DXY = "https://www.cnbc.com/quotes/.DXY"
URL_CNBC_US10Y = "https://www.cnbc.com/quotes/US10Y"
URL_CNBC_US2Y = "https://www.cnbc.com/quotes/US2Y"
URL_ANUE_VIX = "https://invest.cnyes.com/index/GI/VIX"
URL_ANUE_DXY = "https://invest.cnyes.com/index/GI/DXY"
URL_ANUE_OIL = "https://invest.cnyes.com/futures/GF/CL"
URL_ANUE_US10Y = "https://invest.cnyes.com/futures/GF/US10YY"

session = requests.Session()
session.verify = False 

# ==========================================
# 🧠 智慧記憶模組
# ==========================================
def load_memory():
    if os.path.exists(MEMORY_FILE):
        try:
            with open(MEMORY_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except: return {}
    return {}

def save_memory(data):
    try:
        with open(MEMORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
    except: pass

def smart_input_prompt(driver, key, label_text, update_days_limit, example_val, target_url=None):
    """
    UI 優化版輸入提示：強制切換網頁
    """
    mem = load_memory()
    record = mem.get(key, {})
    last_val = record.get('value')
    last_date_str = record.get('date')
    
    today = datetime.date.today()
    is_expired = False
    days_diff = 0
    
    # 🎨 顏色代碼
    C_RED = "\033[91m"
    C_GREEN = "\033[92m"
    C_YELLOW = "\033[93m"
    C_CYAN = "\033[96m"
    C_RESET = "\033[0m"
    C_BOLD = "\033[1m"

    if last_val is not None and last_date_str:
        last_date = datetime.datetime.strptime(last_date_str, "%Y-%m-%d").date()
        days_diff = (today - last_date).days
        if days_diff >= update_days_limit:
            is_expired = True
    else:
        is_expired = True

    # --- 1. 自動切換網頁 (關鍵修正：移除 is_expired 判斷，每次都開) ---
    if target_url and driver:
        try:
            print(f"         🌐 正在載入參照網頁: {target_url}")
            driver.get(target_url) 
            time.sleep(2.0) # 給網頁一點時間載入
        except Exception as e: 
            print(f"         ❌ 網頁載入失敗: {e}")

    # --- 2. 介面繪製 (UI) ---
    print("\n" + "-"*60)
    
    if is_expired:
        print(f"   狀態: {C_RED}⚠️  需要更新{C_RESET} (上次: {days_diff} 天前)")
    else:
        print(f"   狀態: {C_GREEN}✅ 資料很新{C_RESET} (上次: {days_diff} 天前)")

    # 🌟 巨大的紅字標題
    print(f"\n   請輸入 {C_RED}{C_BOLD}{label_text}{C_RESET} :")
    
    # 提示預設值
    def_txt = f"{last_val}" if last_val is not None else f"{example_val}"
    print(f"   (若無變動，按 Enter 使用預設值: {def_txt})")

    # 🌟 獨立換行的輸入游標
    user_in = input(f"\n   👉 ").strip()
    
    # --- 3. 處理輸入 (含整數自動轉小數) ---
    final_val_str = user_in if user_in else str(def_txt)
    final_val_float = float(final_val_str)

    # 特殊處理：自動除以 100
    if "fed" in key:
        if final_val_float > 20: 
            print(f"   💡 偵測到整數輸入 {final_val_float}，自動轉換為 {final_val_float/100}%")
            final_val_float = final_val_float / 100
            final_val_str = str(final_val_float) 

    # 儲存記憶
    mem[key] = { 'value': final_val_str, 'date': today.strftime("%Y-%m-%d") }
    save_memory(mem)
    
    return final_val_float

# ==========================================
# 🛠️ 基礎工具
# ==========================================
def get_headers(referer=None):
    return {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Connection': 'keep-alive',
    }

def fetch_url_content(url, specific_headers=None):
    try:
        h = specific_headers if specific_headers else get_headers()
        time.sleep(random.uniform(0.5, 1.5))
        r = session.get(url, headers=h, timeout=20)
        if r.status_code == 200: return BeautifulSoup(r.text, 'html.parser')
    except: pass
    return None

def clean_text(text):
    if not text: return None
    clean_str = text.replace(',', '').replace('%', '').strip()
    match = re.search(r"(-?\d+\.?\d*)", clean_str)
    if match: return float(match.group(1))
    return None

# ==========================================
# 🔍 核心解析器
# ==========================================
def parse_te_core_cpi(url, **kwargs):
    soup = fetch_url_content(url)
    if soup:
        for row in soup.find_all('tr'):
            text = row.get_text().strip().lower()
            if "core inflation rate" in text:
                cols = row.find_all('td')
                for col in cols:
                    val = clean_text(col.text)
                    if val is not None and 1.0 < val < 10.0: return val
    return None

def parse_us_inflation(url, **kwargs):
    soup = fetch_url_content(url)
    if soup:
        rows = soup.find_all('tr')
        if rows:
            for row in reversed(rows):
                cols = row.find_all('td')
                if len(cols)>0: 
                    val = clean_text(cols[-1].text)
                    if val is not None and 0<val<20: return val
    return None

def parse_te_by_keyword(url, keyword=""):
    soup = fetch_url_content(url)
    if soup:
        for row in soup.find_all('tr'):
            if keyword.lower() in row.get_text().strip().lower():
                for col in row.find_all('td')[1:]:
                    val = clean_text(col.text)
                    if val is not None and 10<val<90: return val
    return None

def parse_stock_analysis_pe(url, **kwargs):
    soup = fetch_url_content(url)
    if soup:
        for row in soup.find_all('tr'):
            if "PE Ratio" in row.text:
                cols = row.find_all('td')
                if len(cols)>1: return clean_text(cols[1].text)
        cards = soup.find_all('div', class_='px-4')
        for card in cards:
            if "PE Ratio" in card.text:
                val = card.find('div', class_='text-xl')
                if val: return clean_text(val.text)
    return None

def parse_wsj_pe(url, **kwargs):
    soup = fetch_url_content(url)
    if soup:
        for row in soup.find_all('tr'):
            if "S&P 500" in row.get_text() and "Estimate" not in row.get_text():
                for col in row.find_all('td'):
                    val = clean_text(col.text)
                    if val and 10<val<100: return val
    return None

def parse_cnbc_quote(url, **kwargs):
    soup = fetch_url_content(url)
    if soup:
        val = soup.select_one('.QuoteStrip-lastPrice') or soup.select_one('span.QuoteStrip-last')
        if val: return clean_text(val.text)
    return None

def parse_investing_smart(url, **kwargs):
    soup = fetch_url_content(url)
    if soup:
        val = soup.select_one('#last_last') or soup.select_one('[data-test="instrument-price-last"]')
        if val: return clean_text(val.text)
    return None

def get_cnn_fear_greed(url):
    try:
        r = session.get(url, headers=get_headers(), timeout=10)
        if r.status_code == 200: return float(round(r.json()['fear_and_greed']['score']))
    except: pass
    return None

def get_fred_value(url, **kwargs):
    soup = fetch_url_content(url)
    if soup:
        val = soup.select_one('.series-meta-observation-value')
        if val: return clean_text(val.text)
    return None

def calculate_yahoo_pe(ticker):
    try:
        t = yf.Ticker(ticker); info = t.info
        if 'trailingPE' in info and info['trailingPE']: return round(info['trailingPE'], 2)
    except: pass
    return None

def get_cnbc_data(url): return parse_cnbc_quote(url)
def get_anue_data(url):
    soup = fetch_url_content(url)
    if soup:
        val = soup.select_one('div[class*="info-price"] span')
        if val: return clean_text(val.text)
    return None

def fetch_smart(name, primary_func, primary_url, backup_sources, min_val=None, max_val=None, **kwargs):
    def check(val):
        if val is None: return False
        if min_val is not None and val < min_val: return False
        if max_val is not None and val > max_val: return False
        return True
    kw = kwargs.get('keyword', None)
    try:
        val = primary_func(primary_url, keyword=kw) if kw else primary_func(primary_url)
        if check(val): 
            print(f"    ✅ {name} 成功: {val}")
            return val
    except: pass
    print(f"    ⚠️ {name} 主來源異常，啟動備援...")
    for item in backup_sources:
        try:
            func, url = item[0], item[1]
            k = item[2] if len(item) > 2 else None
            val = func(url, keyword=k) if k else func(url)
            if check(val):
                print(f"      🚑 備援成功: {val}")
                return val
        except: pass
    print(f"    ❌ {name} 全部失敗")
    return None

def fetch_quote_smart(name, yahoo_ticker, backups):
    try:
        t = yf.Ticker(yahoo_ticker)
        hist = t.history(period="1d")
        if not hist.empty:
            val = round(hist['Close'].iloc[-1], 2)
            print(f"    ✅ Yahoo {name}: {val}")
            return val
    except: pass
    print(f"    ⚠️ Yahoo {name} 失敗，啟動備援...")
    for func, url in backups:
        try:
            val = func(url)
            if val is not None:
                print(f"      🚑 備援成功: {val}")
                return val
        except: pass
    print(f"    ❌ {name} 全部失敗")
    return None

# ==========================================
# 🚀 瀏覽器自動化 & 智慧輸入
# ==========================================
def get_selenium_data():
    print(f"    🔍 啟動 Selenium 機器人 (CME -> Investing -> PMI -> MMFI)...")
    
    # 🌟 1. 提早啟動 Driver
    base_path = os.path.dirname(os.path.abspath(__file__))
    bot_profile_path = os.path.join(base_path, "chrome_bot_profile")
    if not os.path.exists(bot_profile_path): os.makedirs(bot_profile_path)

    options = Options()
    prefs = {"profile.managed_default_content_settings.images": 2}
    options.add_experimental_option("prefs", prefs)
    
    options.add_argument("--disable-dev-shm-usage") 
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-session-crashed-bubble")
    options.add_argument("--disable-infobars")
    options.add_argument("--disable-gpu")
    
    options.add_argument(f"--user-data-dir={bot_profile_path}")
    options.page_load_strategy = 'eager' 

    driver = None
    try:
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
        driver.set_page_load_timeout(30)
        try: driver.get("about:blank")
        except: pass
    except Exception as e:
        print(f"      ❌ Driver 啟動失敗: {e}")
        driver = None

    # 🌟 2. 依序問問題 (網頁會自動跳轉)
    
    # --- 現在利率 (Current) ---
    val_c = smart_input_prompt(driver, 'fed_current', '現在利率', 30, 437, target_url=URL_CME_FEDWATCH)
    current_rate_avg = (val_c + (val_c + 0.25)) / 2

    # --- 明年同月利率 (Target) ---
    val_t = smart_input_prompt(driver, 'fed_target', '明年同月利率', 30, 350, target_url=URL_INV_FED_MONITOR)
    target_rate_avg = (val_t + (val_t + 0.25)) / 2
    
    diff = target_rate_avg - current_rate_avg
    fed_res = (round(diff / 0.25, 1), f"Manual {val_t:.2f}")

    # --- 製造業 PMI ---
    pmi_val = smart_input_prompt(driver, 'pmi', '製造業PMI', 30, 52.0, target_url=URL_PMI_HK)

    # --- 核心通膨 CPI ---
    cpi_val = smart_input_prompt(driver, 'cpi', '核心通膨CPI', 30, 2.6, target_url=URL_TE_CORE_CPI)

    # 🌟 3. 自動抓取 MMFI
    mmfi_val = None
    if driver:
        print(f"\n    🤖 正在背景抓取 MMFI (請勿關閉視窗)...")
        try:
            driver.get(URL_MMFI_TV)
            time.sleep(3)
            price_text = driver.execute_script("""
                let els = document.querySelectorAll('span[class*="last-"], div[class*="last-"], span[class*="price-"]');
                for(let el of els) { if(el.innerText && el.innerText.match(/^\d+\.?\d*$/)) return el.innerText; }
                return document.title;
            """)
            if price_text:
                match = re.search(r"(\d+\.?\d*)", price_text)
                if match: 
                    mmfi_val = float(match.group(1))
                    print(f"         ✅ MMFI 抓取成功: {mmfi_val}")
        except: pass
        try: driver.quit()
        except: pass
    
    results = {
        "fed": fed_res,
        "mmfi": mmfi_val,
        "pmi": pmi_val,
        "cpi": cpi_val
    }
    return results

# ==========================================
# 🏗️ 主程式邏輯
# ==========================================
def get_all_data():
    print("🚀 啟動 p130_同步修正版 (V66.10) ...")
    data = {}

    data['vix'] = fetch_quote_smart('VIX', '^VIX', [(get_cnbc_data, URL_CNBC_VIX), (get_anue_data, URL_ANUE_VIX)])
    data['dxy'] = fetch_quote_smart('DXY', 'DX-Y.NYB', [(get_cnbc_data, URL_CNBC_DXY), (get_anue_data, URL_ANUE_DXY)])
    data['oil'] = fetch_quote_smart('Oil', 'CL=F', [(get_cnbc_data, URL_CNBC_OIL), (get_anue_data, URL_ANUE_OIL)])
    data['yield_10y'] = fetch_quote_smart('US10Y', '^TNX', [(get_cnbc_data, URL_CNBC_US10Y), (get_anue_data, URL_ANUE_US10Y)])
    
    fred_curve = get_fred_value(URL_FRED_T10Y2Y)
    if fred_curve is not None:
        data['yield_curve'] = fred_curve
    else:
        y2 = fetch_quote_smart('US2Y', '^IRX', [(get_cnbc_data, URL_CNBC_US2Y)])
        if data['yield_10y'] and y2: data['yield_curve'] = round(data['yield_10y'] - y2, 2)
        else: data['yield_curve'] = None

    data['pe'] = fetch_smart('SPY PE', parse_stock_analysis_pe, URL_SA_SPY, [(parse_wsj_pe, URL_WSJ_PE)], min_val=5, max_val=100)
    data['pe_qqq'] = fetch_smart('QQQ PE', parse_stock_analysis_pe, URL_SA_QQQ, [], min_val=5, max_val=200)
    data['pe_vt'] = fetch_smart('VT PE', parse_stock_analysis_pe, URL_SA_VT, [], min_val=5, max_val=100)

    data['hy'] = fetch_smart('High Yield', get_fred_value, URL_FRED_HY, [])
    data['real_y_fred'] = get_fred_value("https://fred.stlouisfed.org/series/DFII10")
    data['fear'] = fetch_smart('Fear&Greed', get_cnn_fear_greed, URL_CNN_FG, [])
    
    # 取得含有人工輸入的數據
    bot_res = get_selenium_data()
    
    data['fed'] = bot_res['fed']
    data['fed_val'] = bot_res['fed'][0] if bot_res['fed'] else None
    
    data['mmfi'] = bot_res['mmfi']
    data['pmi'] = bot_res['pmi']
    data['cpi'] = bot_res['cpi']

    return data

# ==========================================
# 📄 更新個人版 HTML (V30_Live.html)
# ==========================================
def update_personal_html(D):
    if not os.path.exists(INPUT_HTML):
        with open(INPUT_HTML, 'w', encoding='utf-8') as f: f.write("<html><body>Template Not Found.</body></html>")
    
    print(f"\n💾 [1/2] 更新個人版 {OUTPUT_HTML} ...")
    with open(INPUT_HTML, 'r', encoding='utf-8') as f: content = f.read()

    def replace_val(id_str, new_val):
        val = new_val if new_val is not None else FAIL_MSG
        pattern = r"({ id: '" + id_str + r"',.*?val: )([\d\.-]+|'.*?')"
        repl = f"\\g<1>'{val}'" if isinstance(val, str) else f"\\g<1>{val}"
        return re.sub(pattern, repl, content)

    content = replace_val('m02', D['hy'])
    content = replace_val('m07', D['vix'])
    content = replace_val('s03', D['vix'])
    content = replace_val('m09', D['dxy'])
    content = replace_val('m10', D['oil'])
    content = replace_val('s04', D['fear'])
    content = replace_val('m03_spy', D['pe'])
    content = replace_val('m03_qqq', D['pe_qqq'])
    content = replace_val('m03_vt', D['pe_vt'])
    content = replace_val('s05', D['mmfi'])
    content = replace_val('m04', D['pmi'])
    content = replace_val('m05', D['cpi'])
    content = replace_val('m01', D['yield_curve'])
    content = replace_val('m08', D['real_y_fred'])
    if D['fed_val'] is not None: content = replace_val('m06', D['fed_val'])

    if D['yield_10y']: content = re.sub(r"(>10Y Yield</a>\s+<span>: )([\d\.]+|N/A)%", f"\\g<1>{D['yield_10y']}%", content)
    if D['cpi']: content = re.sub(r"(>Core CPI</a>\s+<span>: )([\d\.]+|N/A)%", f"\\g<1>{D['cpi']}%", content)
    real = D['real_y_fred']
    if real is None and D['yield_10y'] and D['cpi']: real = round(D['yield_10y'] - D['cpi'], 2)
    if real is not None:
        content = re.sub(r"(=</span>\s+<span.*?>)([\d\.-]+|N/A)%", f"\\g<1>{real}%", content)
        content = re.sub(r'(id="bond-raw".*?value=")([\d\.-]+|N/A)"', f'\\g<1>{real}"', content)
        content = re.sub(r"(updateBond\(')([\d\.-]+|N/A)('\))", f"\\g<1>{real}\\g<3>", content)

    today = datetime.date.today().strftime("%Y/%m/%d")
    content = re.sub(r"Updated: \d{4}/\d{1,2}/\d{1,2}", f"Updated: {today}", content)

    # 🌟 [個人版 Logo 策略] 繼承來源檔 (不換圖)
    print("   🛡️  Logo 模式: 繼承來源檔樣式 (不進行替換)")

    # 🌟 插入版權聲明
    if "</body>" in content:
        content = content.replace("</body>", COPYRIGHT_HTML + "\n</body>")
    else:
        content = content + COPYRIGHT_HTML

    with open(OUTPUT_HTML, 'w', encoding='utf-8') as f: f.write(content)
    print("✅ 個人版更新完成")

# ==========================================
# 🔐 生成商業版 HTML (index.html)
# ==========================================
def generate_commercial_and_index(data):
    print("\n🔐 [2/2] 生成商業版 ...")
    
    payload = {
        "updated_at": datetime.date.today().strftime("%Y/%m/%d"),
        "values": {
            "m07": data['vix'], "m01": data['yield_curve'], "m09": data['dxy'],
            "m10": data['oil'], "s03": data['vix'], "s04": data['fear'],
            "m03_spy": data['pe'], "m03_qqq": data['pe_qqq'], "m03_vt": data['pe_vt'], "s05": data['mmfi'],
            "m04": data['pmi'], "m05": data['cpi'],
            "m02": data['hy'], "m08": data.get('real_y_fred'),
            "m06": data['fed_val'] if data['fed_val'] is not None else 0,
            "yield_10y": data['yield_10y']
        }
    }
    with open(COMMERCIAL_DATA, "w", encoding="utf-8") as f:
        f.write(f"window.LIVEDATA = {json.dumps(payload, indent=4)};")
    print(f"   ✅ 數據檔 {COMMERCIAL_DATA} 已生成")

    raw_js = """
    document.addEventListener("DOMContentLoaded", function() {
        if (typeof window.LIVEDATA === 'undefined') { console.warn("V30 Data Error"); return; }
        var vals = window.LIVEDATA.values;
        var date = window.LIVEDATA.updated_at;
        for (var key in vals) {
            var inputEl = document.getElementById('in_' + key);
            if (inputEl) {
                inputEl.value = vals[key];
                inputEl.dispatchEvent(new Event('input', { bubbles: true }));
                if (typeof window.handleInput === 'function') { window.handleInput(key); }
            }
            var el = document.getElementById(key);
            if (el) { 
                if(el.tagName === 'INPUT') { 
                    el.value = vals[key]; 
                    el.dispatchEvent(new Event('input')); 
                } else { el.innerText = vals[key]; }
            }
            var el2 = document.getElementById('val_' + key);
            if (el2) el2.innerText = vals[key];
        }
        var dateEl = document.getElementById('update_date') || document.getElementById('updated_at');
        if (dateEl) dateEl.innerText = date;
    });
    """
    encoded_js = "".join([f"%{ord(c):02x}" for c in raw_js])
    obfuscated_content = f"eval(unescape('{encoded_js}'));"

    with open(COMMERCIAL_JS_CORE, "w", encoding="utf-8") as f:
        f.write(obfuscated_content)
    print(f"   🛡️  核心邏輯檔 {COMMERCIAL_JS_CORE} 已混淆加密")

    if not os.path.exists(INPUT_HTML):
        print(f"   ⚠️ 找不到模板 {INPUT_HTML}")
        return

    with open(INPUT_HTML, 'r', encoding='utf-8') as f:
        template_content = f.read()

    # 🌟 Logo 替換 (index.html 換成圖片)
    new_logo_html = f'<img src="{LOGO_FOR_INDEX}" class="w-12 h-16 rounded-lg mr-3 shadow-lg object-cover border border-slate-600 cursor-pointer hover:scale-105 transition-transform">'
    logo_pattern = r'<div class="[^"]*?rounded-lg mr-3[^"]*?">\s*<i class="[^"]*?"></i>\s*</div>'

    if re.search(logo_pattern, template_content):
        template_content = re.sub(logo_pattern, new_logo_html, template_content, count=1)
        print(f"   🖼️  index.html Logo (Div) 已替換為 {LOGO_FOR_INDEX}")
    else:
        template_content = re.sub(r'<img src=".*?" class="w-12 h-16.*?>', new_logo_html, template_content)
        print(f"   🖼️  index.html Logo (Img) 已更新")

    security_script = """
    <script>
    document.addEventListener('contextmenu', event => event.preventDefault());
    document.onkeydown = function(e) {
        if(e.keyCode == 123) { return false; }
        if(e.ctrlKey && e.shiftKey && e.keyCode == 'I'.charCodeAt(0)) { return false; }
        if(e.ctrlKey && e.shiftKey && e.keyCode == 'C'.charCodeAt(0)) { return false; }
        if(e.ctrlKey && e.shiftKey && e.keyCode == 'J'.charCodeAt(0)) { return false; }
        if(e.ctrlKey && e.keyCode == 'U'.charCodeAt(0)) { return false; }
    }
    </script>
    """
    injector_script = f"""
    {security_script}
    <script src="{COMMERCIAL_DATA}"></script>
    <script src="{COMMERCIAL_JS_CORE}"></script>
    """
    
    final_injection = COPYRIGHT_HTML + "\n" + injector_script + "\n</body>"
    if "</body>" in template_content:
        new_html = template_content.replace("</body>", final_injection)
    else:
        new_html = template_content + COPYRIGHT_HTML + injector_script

    with open(COMMERCIAL_HTML, "w", encoding="utf-8") as f:
        f.write(new_html)
    
    print(f"   🛡️  商業版網頁 {COMMERCIAL_HTML} 已生成")

def generate_status_report(data):
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    report_lines = []
    report_lines.append(f"⏰ 更新時間: {now_str}")
    report_lines.append("="*60)

    report_items = [
        ("m07/s03", "VIX", 'vix', "CNBC / Anue / Yahoo", URL_CNBC_VIX),
        ("m01", "殖利率曲線 (T10Y2Y)", 'yield_curve', "FRED (Official)", URL_FRED_T10Y2Y),
        ("m06", "Fed 預期 (明年同月)", 'fed_val', "CME + Investing (Manual)", URL_INV_FED_MONITOR),
        ("m08", "10Y 實質利率 (DFII10)", 'real_y_fred', "FRED CSV", "https://fred.stlouisfed.org/series/DFII10"),
        ("m02", "信用利差 HY (BAMLH0A0HYM2)", 'hy', "FRED CSV", URL_FRED_HY),
        ("m04", "PMI 製造業", 'pmi', "Investing (Manual)", URL_PMI_HK),
        ("m05", "核心 CPI (Core)", 'cpi', "TradingEconomics (Manual)", URL_TE_CORE_CPI),
        ("m09", "美元 DXY", 'dxy', "CNBC / Anue / Yahoo", URL_CNBC_DXY),
        ("m10", "油價 WTI", 'oil', "CNBC / Anue / Yahoo", URL_CNBC_OIL),
        ("m03_spy", "SPY 估值 (P/E)", 'pe', "StockAnalysis", URL_SA_SPY),
        ("m03_qqq", "QQQ 估值 (P/E)", 'pe_qqq', "StockAnalysis", URL_SA_QQQ),
        ("m03_vt", "VT 估值 (P/E)", 'pe_vt', "StockAnalysis", URL_SA_VT),
        ("s04", "CNN 貪婪恐懼", 'fear', "CNN Dataviz JSON", URL_CNN_FG),
        ("s05", "MMFI 廣度", 'mmfi', "TradingView (Selenium)", URL_MMFI_TV)
    ]

    for item in report_items:
        r_id, r_name, r_key, r_source, r_url = item
        val = data.get(r_key)
        status_icon = "✅ 成功" if val is not None else "❌ 失敗"
        val_display = str(val) if val is not None else "N/A"
        report_lines.append(f"🔹 [{r_id}] {r_name}")
        report_lines.append(f"   狀態: {status_icon}")
        report_lines.append(f"   數值: {val_display}")
        report_lines.append(f"   資料日期: {today_str} (Live/Latest)")
        report_lines.append(f"   來源: {r_source}")
        report_lines.append(f"   連結: {r_url}")
        report_lines.append("-" * 60)

    final_report = "\n".join(report_lines)
    print("\n" + final_report)
    try:
        with open(REPORT_FILENAME, "w", encoding="utf-8") as f: f.write(final_report)
        print(f"\n📄 報表已成功儲存至檔案: {REPORT_FILENAME}")
    except Exception as e:
        print(f"\n⚠️ 存檔失敗: {e}")

if __name__ == "__main__":
    data = get_all_data()
    update_personal_html(data)
    generate_commercial_and_index(data)
    generate_status_report(data)
    print("\n🎉 p130_同步修正版 (V66.10) 執行完畢！")