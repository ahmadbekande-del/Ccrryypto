"""
💥 ULTIMATE DESTROYER V7 — FULL INTEGRATION
- Multi-Agent Voting System
- ML Engine (XGBoost, LightGBM, RF, GB, LR)
- Sentiment Analysis (CryptoPanic + TextBlob)
- Pump & Dump Detection (Isolation Forest)
- Thompson Sampling for Agent Weights
- Telegram Alerts (HTML)
- Thread-Safe
"""

import os, time, json, threading, logging, queue as _queue
from datetime import datetime, timedelta
from flask import Flask, jsonify, request
from flask_cors import CORS
import requests
import pandas as pd
import numpy as np
import hashlib, joblib, pathlib
from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score, accuracy_score
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier, IsolationForest
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from textblob import TextBlob

logging.basicConfig(level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%H:%M:%S')
log = logging.getLogger('DESTROYER-V7')

# ── Thread Locks ────────────────────────────────────────────────
_state_lock = threading.Lock()
_signals_lock = threading.Lock()
_feed_lock = threading.Lock()
_oi_lock = threading.Lock()

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})

API_KEY = os.getenv('API_KEY', '')

def _api_key_required(f):
    from functools import wraps
    @wraps(f)
    def wrapper(*args, **kwargs):
        if API_KEY:
            key = request.headers.get('X-API-Key', '')
            if key != API_KEY:
                return jsonify({'error': 'Unauthorized'}), 401
        return f(*args, **kwargs)
    return wrapper

# ── Optional Libraries ──────────────────────────────────────────
try:
    import xgboost as xgb
    HAS_XGB = True
except ImportError:
    HAS_XGB = False

try:
    import lightgbm as lgb
    HAS_LGB = True
except ImportError:
    HAS_LGB = False

# ── Storage ─────────────────────────────────────────────────────
_BASE = pathlib.Path.home() / "destroyer_v7_data"
_CACHE_DIR = _BASE / "cache"
_MODEL_DIR = _BASE / "ml_models"
_CACHE_DIR.mkdir(parents=True, exist_ok=True)
_MODEL_DIR.mkdir(parents=True, exist_ok=True)
_CACHE_TTL = 20 * 60

# ════════════════════════════════════════════════════════════════
# 🔔 TELEGRAM & SENTIMENT CONFIG
# ════════════════════════════════════════════════════════════════
TELEGRAM_BOT_TOKEN = os.getenv('TG_TOKEN', '')
TELEGRAM_CHAT_ID = os.getenv('TG_CHAT', '')
CRYPTOPANIC_TOKEN = os.getenv('CRYPTOPANIC_TOKEN', '')  # مجاني من cryptopanic.com

CONFIG = {
    'SCAN_INTERVAL': 30,
    'MIN_SCORE_HOT': 8.0,
    'MIN_SCORE_WARM': 5.0,
    'MIN_SCORE_WATCH': 3.0,
    'LIQUIDITY_MIN': 400_000,
    'MACRO_VETO_PCT': 0.4,
    'MACRO_FREEZE_SEC': 120,
    'SIGNAL_COOLDOWN_DAYS': 7,
    'TG_TOKEN': TELEGRAM_BOT_TOKEN,
    'TG_CHAT': TELEGRAM_CHAT_ID,
    'CRYPTOPANIC_TOKEN': CRYPTOPANIC_TOKEN,
    'MACRO_VETO_ON': True,
    'LIQUIDITY_FILTER_ON': True,
    'MARKET_GUARD_ON': True,
    'AI_LEARNING_ON': True,
    'PERIODIC_REPORTS_ON': True,
    'SENTIMENT_WEIGHT': 1.5,
    'PUMP_DETECTION_ON': True,
}

COINS = [
    'BTC', 'ETH', 'SOL', 'BNB', 'XRP', 'ADA', 'AVAX', 'DOGE', 'DOT', 'LINK',
    'MATIC', 'UNI', 'ATOM', 'FIL', 'APT', 'ARB', 'OP', 'INJ', 'SUI', 'TIA',
    'JUP', 'PYTH', 'WIF', 'BONK', 'PEPE', 'SHIB', 'LTC', 'BCH', 'ETC', 'NEAR',
    'FTM', 'ALGO', 'XLM', 'VET', 'MANA', 'SAND', 'AXS', 'GALA', 'ENJ', 'CHZ',
    'CRV', 'AAVE', 'COMP', 'SNX', 'MKR', 'LDO', 'RPL', 'RUNE', 'THETA', 'ZEC',
    'DASH', 'XMR', 'ZRX', 'BAT', 'GRT', '1INCH', 'SUSHI', 'YFI', 'BAL', 'REN',
    'OCEAN', 'BAND', 'KNC', 'OMG', 'ANKR', 'HOT', 'XTZ', 'EOS', 'TRX', 'NEO',
    'ONT', 'IOTA', 'LSK', 'WAVES', 'DCR', 'SC', 'ZEN', 'QTUM', 'ICX', 'STORJ',
    'CELR', 'COTI', 'SKL', 'BNT', 'DENT', 'MTL', 'POWR', 'RLC', 'REQ', 'WAN',
    'STMX', 'TROY', 'ARPA', 'BAKE', 'BURGER', 'FRONT', 'HARD', 'VITE', 'WING', 'XVS',
    'FLOKI', 'BABYDOGE', 'TURBO', 'MEME', 'NEIRO', 'PNUT', 'MOG', 'BOME', 'POPCAT', 'ACT',
    'CHILLGUY', 'BRETT', 'PONKE', 'ELON', 'DOGS', 'HMSTR', 'CATI', 'MAJOR', 'HAMSTER', 'BLUM',
    'SEI', 'STRK', 'BLUR', 'DYDX', 'GMX', 'PENDLE', 'ONDO', 'ENA', 'ETHFI', 'JTO',
    'BICO', 'MANTA', 'ALT', 'DYM', 'AEVO', 'METIS', 'KAVA', 'ONE', 'GLMR', 'FLOW',
    'ROSE', 'CELO', 'ID', 'CYBER', 'HOOK', 'PERP', 'AXL', 'HNT', 'OSMO', 'ORCA',
]

_seen = set()
COINS = [c for c in COINS if c not in _seen and not _seen.add(c)]

STATE = {
    'running': False,
    'signals': [],
    'feed': [],
    'scan_count': 0,
    'last_scan': None,
    'next_scan': None,
    'macro_veto_active': False,
    'macro_veto_until': None,
    'market': {'btc': 0, 'eth': 0, 'btc_chg': 0},
    'performance': {'total': 0, 'win': 0, 'loss': 0},
    'ai_weights': {
        'squeeze_1d': 3.0, 'squeeze_4h': 2.5,
        'orderbook_bull': 2.0, 'squeeze_5m': 2.0,
        'obv_diverge': 1.8, 'correlation': 1.6,
        'golden_cross': 1.6, 'breakout': 1.6,
        'volume_x3': 1.7, 'macd_cross': 1.4,
        'cvd_surge': 1.5, 'funding_pos': 1.3,
        'oi_rising': 1.2, 'ichimoku': 1.4,
        'supertrend': 1.3,
    },
    'signal_cooldown': {},
    'scalp_mode': False,
    'oi_history': {},
    'telegram_available': True,
    'agents': {},
    'ml_training': False,
    '_started': False,
    'pump_alerts': [],
}

KUCOIN = 'https://api.kucoin.com/api/v1'
KUCOIN_FUT = 'https://api-futures.kucoin.com/api/v1'

_msg_queue = _queue.Queue()

# ════════════════════════════════════════════════════════════════
# 1. SENTIMENT ANALYSIS (NEW)
# ════════════════════════════════════════════════════════════════
def get_cryptopanic_news(coin, limit=10):
    """جلب آخر الأخبار من CryptoPanic"""
    if not CONFIG['CRYPTOPANIC_TOKEN']:
        return []
    try:
        url = f"https://cryptopanic.com/api/v1/posts/?auth_token={CONFIG['CRYPTOPANIC_TOKEN']}&currencies={coin}&limit={limit}"
        r = requests.get(url, timeout=10)
        data = r.json().get('results', [])
        return data
    except Exception as e:
        log.debug(f"News error for {coin}: {e}")
        return []

def analyze_sentiment(text):
    """تحليل المشاعر باستخدام TextBlob"""
    blob = TextBlob(text)
    polarity = blob.sentiment.polarity  # -1 (سلبي) إلى +1 (إيجابي)
    if polarity > 0.3:
        return 'positive', polarity
    elif polarity < -0.3:
        return 'negative', polarity
    else:
        return 'neutral', polarity

def get_coin_sentiment(coin):
    """جلب وتحليل أخبار العملة وإرجاع درجة المشاعر"""
    news = get_cryptopanic_news(coin, limit=15)
    if not news:
        return 0.0, 0, []
    
    sentiments = []
    headlines = []
    for item in news[:10]:
        title = item.get('title', '')
        if title:
            sentiment, score = analyze_sentiment(title)
            sentiments.append(score)
            headlines.append(f"{sentiment[:3]}({score:.1f}): {title[:50]}...")
    
    if not sentiments:
        return 0.0, 0, []
    
    avg_sentiment = sum(sentiments) / len(sentiments)
    # تحويل -1..+1 إلى درجة 0..1 (0.5 محايد، >0.5 إيجابي)
    sentiment_score = (avg_sentiment + 1) / 2
    return sentiment_score, len(news), headlines[:3]

# ════════════════════════════════════════════════════════════════
# 2. PUMP & DUMP DETECTION (NEW)
# ════════════════════════════════════════════════════════════════
class PumpDetector:
    def __init__(self):
        self.model = IsolationForest(contamination=0.1, random_state=42)
        self.trained = False
        self.feature_names = ['volume_spike', 'price_spike', 'cvd_change', 'orderbook_imbalance']
    
    def extract_features(self, df, ticker, ob):
        """استخراج ميزات لاكتشاف التلاعب"""
        if df is None or len(df) < 20:
            return None
        
        # تغير الحجم المفاجئ
        vol_avg = df['volume'].tail(20).mean()
        vol_now = df['volume'].iloc[-1]
        volume_spike = vol_now / vol_avg if vol_avg > 0 else 1.0
        
        # تغير السعر المفاجئ
        price_now = df['close'].iloc[-1]
        price_20_ago = df['close'].iloc[-20] if len(df) >= 20 else price_now
        price_spike = price_now / price_20_ago if price_20_ago > 0 else 1.0
        
        # تغير CVD
        _, cvd_change = calc_cvd(df)
        
        # عدم توازن دفتر الطلبات
        ob_ratio = ob.get('ratio', 1.0)
        orderbook_imbalance = abs(ob_ratio - 1.0)
        
        return [volume_spike, price_spike, abs(cvd_change) / 1e6, orderbook_imbalance]
    
    def train_on_history(self, symbols, exchange):
        """تدريب النموذج على بيانات تاريخية"""
        features_list = []
        for sym in symbols[:30]:  # استخدم أول 30 عملة للتدريب
            try:
                df = get_klines_cached(sym, '1hour', 100)
                ticker = get_ticker(sym)
                ob = get_orderbook(sym)
                if df is not None and len(df) > 20:
                    feats = self.extract_features(df, ticker, ob)
                    if feats and all(not np.isnan(f) for f in feats):
                        features_list.append(feats)
                time.sleep(0.2)
            except:
                continue
        
        if len(features_list) > 20:
            self.model.fit(features_list)
            self.trained = True
            log.info(f"✅ PumpDetector trained on {len(features_list)} samples")
            return True
        log.warning("⚠️ PumpDetector: insufficient data for training")
        return False
    
    def predict(self, df, ticker, ob):
        """اكتشاف ما إذا كانت العملة في وضع Pump & Dump"""
        if not self.trained:
            return False, 0.0
        
        feats = self.extract_features(df, ticker, ob)
        if feats is None or any(np.isnan(f) for f in feats):
            return False, 0.0
        
        # Isolation Forest يعود -1 للشذوذ
        result = self.model.predict([feats])[0]
        anomaly_score = -self.model.score_samples([feats])[0]  # كلما زاد، زاد الشذوذ
        
        is_anomaly = (result == -1)
        return is_anomaly, round(anomaly_score, 3)

PUMP_DETECTOR = PumpDetector()

# ════════════════════════════════════════════════════════════════
# 3. THOMPSON SAMPLING AGENT (IMPROVED)
# ════════════════════════════════════════════════════════════════
class ThompsonAgent:
    """Agent with Thompson Sampling (Beta distribution)"""
    def __init__(self, name, weight=1.0):
        self.name = name
        self.weight = weight
        self.alpha = 1.0  # النجاحات
        self.beta = 1.0   # الإخفاقات
        self.history = []
    
    def sample(self):
        """أخذ عينة من توزيع بيتا الحالي"""
        return np.random.beta(self.alpha, self.beta)
    
    def update(self, success: bool):
        """تحديد التوزيع بناءً على النتيجة"""
        if success:
            self.alpha += 1
        else:
            self.beta += 1
        self.history.append(success)
        # تحديث الوزن بناءً على متوسط الدقة
        if len(self.history) >= 10:
            accuracy = (self.alpha - 1) / (self.alpha + self.beta - 2)
            self.weight = round(0.5 + accuracy * 1.5, 2)
    
    def get_probability(self):
        """احتمالية النجاح المقدرة"""
        return self.alpha / (self.alpha + self.beta)

# ════════════════════════════════════════════════════════════════
# 4. KuCoin Data Layer (unchanged)
# ════════════════════════════════════════════════════════════════
def _interval_seconds(tf):
    return {'5min': 300, '15min': 900, '1hour': 3600, '4hour': 14400, '1day': 86400, '1week': 604800}.get(tf, 3600)

def get_klines(symbol, interval='1hour', limit=200):
    kc_tf = {'5min': '5min', '15min': '15min', '1hour': '1hour', '4hour': '4hour', '1day': '1day', '1week': '1week'}.get(interval, '1hour')
    try:
        end = int(time.time())
        start = end - limit * _interval_seconds(kc_tf)
        url = f"{KUCOIN}/market/candles?type={kc_tf}&symbol={symbol}-USDT&startAt={start}&endAt={end}"
        r = requests.get(url, timeout=10)
        data = r.json().get('data', [])
        if not data:
            return None
        df = pd.DataFrame(data, columns=['time', 'open', 'close', 'high', 'low', 'volume', 'turnover'])
        df = df.astype({'open': float, 'close': float, 'high': float, 'low': float, 'volume': float})
        df['time'] = pd.to_datetime(df['time'].astype(int), unit='s')
        return df.sort_values('time').reset_index(drop=True)
    except Exception as e:
        log.debug(f"klines error {symbol}: {e}")
        return None

def _cache_path(symbol, tf, limit):
    key = f"{symbol}__{tf}__{limit}"
    h = hashlib.md5(key.encode()).hexdigest()
    return _CACHE_DIR / f"{h}.pkl"

def get_klines_cached(symbol, tf='1hour', limit=200):
    fp = _cache_path(symbol, tf, limit)
    if fp.exists():
        age = time.time() - fp.stat().st_mtime
        if age < _CACHE_TTL:
            try:
                return joblib.load(fp)
            except:
                pass
    df = get_klines(symbol, tf, limit)
    if df is not None:
        try:
            joblib.dump(df, fp)
        except:
            pass
    return df

def clear_cache():
    import shutil
    shutil.rmtree(_CACHE_DIR, ignore_errors=True)
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)

def get_ticker(symbol):
    try:
        r = requests.get(f"{KUCOIN}/market/stats?symbol={symbol}-USDT", timeout=8)
        return r.json().get('data', {})
    except:
        return {}

def get_orderbook(symbol):
    try:
        r = requests.get(f"{KUCOIN}/market/orderbook/level2_20?symbol={symbol}-USDT", timeout=8)
        d = r.json().get('data', {})
        bids = sum(float(b[0]) * float(b[1]) for b in d.get('bids', [])[:10])
        asks = sum(float(a[0]) * float(a[1]) for a in d.get('asks', [])[:10])
        return {'bids': bids, 'asks': asks, 'ratio': bids / asks if asks > 0 else 1.0}
    except:
        return {'bids': 0, 'asks': 0, 'ratio': 1.0}

def get_funding_rate(symbol):
    try:
        r = requests.get(f"{KUCOIN_FUT}/funding-rate/{symbol}USDTM/current", timeout=8)
        return float(r.json().get('data', {}).get('value', 0))
    except:
        return 0.0

def get_open_interest(symbol):
    try:
        r = requests.get(f"{KUCOIN_FUT}/contracts/{symbol}USDTM", timeout=8)
        return float(r.json().get('data', {}).get('openInterest', 0))
    except:
        return 0.0

# ════════════════════════════════════════════════════════════════
# 5. Technical Indicators (35+)
# ════════════════════════════════════════════════════════════════
def calc_rsi(df, period=14):
    delta = df['close'].diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).iloc[-1]

def calc_macd(df):
    ema12 = df['close'].ewm(span=12, adjust=False).mean()
    ema26 = df['close'].ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    return macd.iloc[-1], signal.iloc[-1], (macd - signal).iloc[-1]

def calc_bollinger(df, period=20):
    mid = df['close'].rolling(period).mean()
    std = df['close'].rolling(period).std()
    upper = mid + 2 * std
    lower = mid - 2 * std
    pct_b = (df['close'].iloc[-1] - lower.iloc[-1]) / (upper.iloc[-1] - lower.iloc[-1] + 1e-10)
    width = (upper.iloc[-1] - lower.iloc[-1]) / mid.iloc[-1]
    return pct_b, width

def calc_stoch_rsi(df, period=14, smooth_k=3, smooth_d=3):
    delta = df['close'].diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi_s = 100 - 100 / (1 + rs)
    mn = rsi_s.rolling(period).min()
    mx = rsi_s.rolling(period).max()
    stoch = (rsi_s - mn) / (mx - mn + 1e-10) * 100
    k = stoch.rolling(smooth_k).mean()
    d = k.rolling(smooth_d).mean()
    return k.iloc[-1], d.iloc[-1]

def calc_ema(df, periods=[9, 21, 50, 200]):
    price = df['close'].iloc[-1]
    result = {}
    for p in periods:
        if len(df) >= p:
            ema = df['close'].ewm(span=p, adjust=False).mean().iloc[-1]
            result[p] = (price > ema, ema)
    return result

def calc_squeeze(df):
    length = 20
    if len(df) < length + 5:
        return False, 0
    mid = df['close'].rolling(length).mean()
    std = df['close'].rolling(length).std()
    bb_up = mid + 2 * std
    bb_lo = mid - 2 * std
    atr = (df['high'] - df['low']).rolling(length).mean()
    kc_up = mid + 1.5 * atr
    kc_lo = mid - 1.5 * atr
    squeeze = (bb_up.iloc[-1] < kc_up.iloc[-1]) and (bb_lo.iloc[-1] > kc_lo.iloc[-1])
    momentum = df['close'].iloc[-1] - mid.iloc[-1]
    return squeeze, momentum

def calc_obv(df):
    obv = [0]
    for i in range(1, len(df)):
        if df['close'].iloc[i] > df['close'].iloc[i - 1]:
            obv.append(obv[-1] + df['volume'].iloc[i])
        elif df['close'].iloc[i] < df['close'].iloc[i - 1]:
            obv.append(obv[-1] - df['volume'].iloc[i])
        else:
            obv.append(obv[-1])
    obv_s = pd.Series(obv)
    obv_ma = obv_s.rolling(20).mean()
    return obv_s.iloc[-1] > obv_ma.iloc[-1], obv_s.iloc[-1] - obv_ma.iloc[-1]

def calc_atr(df, period=14):
    hl = df['high'] - df['low']
    hc = (df['high'] - df['close'].shift()).abs()
    lc = (df['low'] - df['close'].shift()).abs()
    tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
    return tr.rolling(period).mean().iloc[-1]

def calc_supertrend(df, period=10, multiplier=3.0):
    atr = calc_atr(df, period)
    hl2 = (df['high'] + df['low']) / 2
    lower = hl2.iloc[-1] - multiplier * atr
    return df['close'].iloc[-1] > lower

def calc_ichimoku(df):
    if len(df) < 52:
        return False
    high9 = df['high'].rolling(9).max()
    low9 = df['low'].rolling(9).min()
    tenkan = (high9 + low9) / 2
    high26 = df['high'].rolling(26).max()
    low26 = df['low'].rolling(26).min()
    kijun = (high26 + low26) / 2
    senkou_a = ((tenkan + kijun) / 2).shift(26)
    high52 = df['high'].rolling(52).max()
    low52 = df['low'].rolling(52).min()
    senkou_b = ((high52 + low52) / 2).shift(26)
    price = df['close'].iloc[-1]
    return price > max(senkou_a.iloc[-1] or 0, senkou_b.iloc[-1] or 0)

def calc_adx(df, period=14):
    high, low, close = df['high'], df['low'], df['close']
    tr = pd.concat([high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(axis=1)
    dm_p = (high.diff()).clip(lower=0)
    dm_m = (-low.diff()).clip(lower=0)
    atr14 = tr.rolling(period).mean()
    di_p = 100 * dm_p.rolling(period).mean() / atr14.replace(0, np.nan)
    di_m = 100 * dm_m.rolling(period).mean() / atr14.replace(0, np.nan)
    dx = 100 * (di_p - di_m).abs() / (di_p + di_m + 1e-10)
    adx = dx.rolling(period).mean()
    return adx.iloc[-1], di_p.iloc[-1], di_m.iloc[-1]

def calc_cci(df, period=20):
    tp = (df['high'] + df['low'] + df['close']) / 3
    ma = tp.rolling(period).mean()
    md = (tp - ma).abs().rolling(period).mean()
    return (tp.iloc[-1] - ma.iloc[-1]) / (0.015 * md.iloc[-1] + 1e-10)

def calc_williams_r(df, period=14):
    hh = df['high'].rolling(period).max()
    ll = df['low'].rolling(period).min()
    return -100 * (hh.iloc[-1] - df['close'].iloc[-1]) / (hh.iloc[-1] - ll.iloc[-1] + 1e-10)

def calc_mfi(df, period=14):
    tp = (df['high'] + df['low'] + df['close']) / 3
    mf = tp * df['volume']
    pos = (mf.where(tp > tp.shift(), 0)).rolling(period).sum()
    neg = (mf.where(tp < tp.shift(), 0)).rolling(period).sum()
    return (100 - 100 / (1 + pos / (neg.replace(0, np.nan)))).iloc[-1]

def calc_vwap(df):
    tp = (df['high'] + df['low'] + df['close']) / 3
    vwap = (tp * df['volume']).cumsum() / df['volume'].cumsum()
    return df['close'].iloc[-1] > vwap.iloc[-1], vwap.iloc[-1]

def calc_cvd(df):
    buy_vol = df['volume'].where(df['close'] >= df['open'], 0)
    sell_vol = df['volume'].where(df['close'] < df['open'], 0)
    cvd = (buy_vol - sell_vol).cumsum()
    cvd_ma = cvd.rolling(20).mean()
    return cvd.iloc[-1] > cvd_ma.iloc[-1] * 1.2, cvd.iloc[-1] - cvd_ma.iloc[-1]

def detect_candle_patterns(df):
    patterns = []
    o, h, l, c = df['open'].iloc[-1], df['high'].iloc[-1], df['low'].iloc[-1], df['close'].iloc[-1]
    body = abs(c - o)
    upper_wick = h - max(c, o)
    lower_wick = min(c, o) - l
    total = h - l + 1e-10
    if lower_wick > body * 2 and upper_wick < body * 0.5 and c > o:
        patterns.append('Hammer')
    if len(df) > 1:
        po, pc = df['open'].iloc[-2], df['close'].iloc[-2]
        if pc < po and c > o and c > po and o < pc:
            patterns.append('Engulfing')
    if c > o and body / total > 0.7:
        patterns.append('Strong Bull')
    return patterns

def calc_price_structure(df, lookback=20):
    highs = df['high'].tail(lookback)
    lows = df['low'].tail(lookback)
    return (highs.iloc[-1] > highs.iloc[-2]) and (lows.iloc[-1] > lows.iloc[-2])

# ════════════════════════════════════════════════════════════════
# 6. Agents with Thompson Sampling
# ════════════════════════════════════════════════════════════════
class TechnicalAgent(ThompsonAgent):
    def __init__(self):
        super().__init__('Technical', weight=1.5)
    
    def analyze(self, symbol, dfs, ticker, extra):
        score = 0.0
        signals = []
        w = STATE['ai_weights']
        for tf, df in dfs.items():
            sq, mom = calc_squeeze(df)
            if sq and mom > 0:
                s = w.get(f'squeeze_{tf}', w.get('squeeze_4h', 2.0))
                score += s
                signals.append(f'💥 Squeeze {tf}')
            rsi = calc_rsi(df)
            if 55 < rsi < 78:
                score += 0.8
                signals.append(f'RSI {rsi:.0f} ({tf})')
            _, _, hist = calc_macd(df)
            if hist > 0:
                score += 0.6
            adx_val, di_p, di_m = calc_adx(df)
            if adx_val > 25 and di_p > di_m:
                score += 0.9
                signals.append(f'ADX {adx_val:.0f}')
            if adx_val > 35:
                score += 0.5
            k, d = calc_stoch_rsi(df)
            if k > 50 and k > d:
                score += 0.5
        if '1day' in dfs:
            emas = calc_ema(dfs['1day'], [9, 21, 50, 200])
            if all(v[0] for v in emas.values()) and len(emas) >= 3:
                score += w.get('golden_cross', 1.6)
                signals.append('✨ Golden Cross')
            if calc_supertrend(dfs['1day']):
                score += 1.2
                signals.append('Supertrend ✅')
            if calc_ichimoku(dfs['1day']):
                score += 1.2
                signals.append('Ichimoku ✅')
        return {'score': round(score, 2), 'signals': signals, 'confidence': round(min(1.0, score / 12.0), 2)}

class SentimentAgent(ThompsonAgent):
    def __init__(self):
        super().__init__('Sentiment', weight=1.2)
    
    def analyze(self, symbol, dfs, ticker, extra):
        score = 0.0
        signals = []
        w = STATE['ai_weights']
        ob = extra.get('ob', {})
        funding = extra.get('funding', 0)
        ratio = ob.get('ratio', 1.0)
        if ratio > 1.5:
            score += w.get('orderbook_bull', 2.0)
            signals.append(f'📗 Orderbook ×{ratio:.1f}')
        elif ratio > 1.2:
            score += 0.8
        for tf, df in dfs.items():
            cvd_s, _ = calc_cvd(df)
            if cvd_s:
                score += w.get('cvd_surge', 1.5) * 0.6
                signals.append(f'CVD Surge ({tf})')
            obv_bull, _ = calc_obv(df)
            if obv_bull:
                score += w.get('obv_diverge', 1.8) * 0.5
        for tf, df in dfs.items():
            vol_avg = df['volume'].tail(20).mean()
            vol_now = df['volume'].iloc[-1]
            if vol_now > vol_avg * 3:
                score += w.get('volume_x3', 1.7)
                signals.append(f'💥 حجم ×{vol_now / vol_avg:.1f} ({tf})')
                break
        if -0.005 < funding < 0.03:
            score += 0.8
            signals.append(f'Funding {funding:.4f}')
        elif funding < -0.01:
            score += 1.2
            signals.append('🔥 Negative Funding')
        for df in dfs.values():
            mfi = calc_mfi(df)
            if mfi > 60:
                score += 0.7
            break
        
        # ========== NEW: Sentiment Analysis ==========
        sentiment_score, news_count, headlines = get_coin_sentiment(symbol)
        if news_count > 0:
            sentiment_weight = CONFIG.get('SENTIMENT_WEIGHT', 1.5)
            # تحويل 0..1 إلى -1..+1 تأثير
            sentiment_impact = (sentiment_score - 0.5) * 2 * sentiment_weight
            score += sentiment_impact
            if sentiment_impact > 0.5:
                signals.append(f'📰 أخبار إيجابية ({news_count} خبر)')
            elif sentiment_impact < -0.5:
                signals.append(f'📰 أخبار سلبية ({news_count} خبر)')
        
        return {'score': round(score, 2), 'signals': signals, 'confidence': round(min(1.0, score / 8.0), 2)}

class RiskAgent(ThompsonAgent):
    def __init__(self):
        super().__init__('Risk', weight=1.8)
    
    def analyze(self, symbol, dfs, ticker, extra):
        score = 0.0
        signals = []
        price = float(ticker.get('last', 0))
        chg24h = float(ticker.get('changeRate', 0)) * 100
        vol24h = float(ticker.get('volValue', 0))
        if vol24h < CONFIG['LIQUIDITY_MIN']:
            score -= 3.0
            signals.append('⚠️ سيولة منخفضة')
        elif vol24h > CONFIG['LIQUIDITY_MIN'] * 5:
            score += 1.0
            signals.append('✅ سيولة ممتازة')
        btc_chg = STATE['market'].get('btc_chg', 0)
        if btc_chg < -2.0:
            score -= 2.5
            signals.append(f'⚠️ BTC هابط {btc_chg:.1f}%')
        elif btc_chg > 1.0:
            score += 0.8
            signals.append('BTC صاعد ✅')
        if dfs:
            df_ref = dfs.get('1hour', list(dfs.values())[0])
            atr = calc_atr(df_ref)
            atr_pct = atr / price * 100 if price > 0 else 0
            if atr_pct > 8.0:
                score -= 1.5
                signals.append(f'⚠️ تقلب مفرط ATR {atr_pct:.1f}%')
            elif atr_pct < 5.0:
                score += 0.6
        if chg24h > 20:
            score -= 2.0
            signals.append(f'⚠️ ارتفع {chg24h:.0f}% — متأخر')
        elif chg24h > 10:
            score -= 0.8
        
        # Pump & Dump detection
        if CONFIG['PUMP_DETECTION_ON'] and dfs:
            df_ref = dfs.get('1hour', list(dfs.values())[0])
            ob = extra.get('ob', {})
            is_pump, anomaly_score = PUMP_DETECTOR.predict(df_ref, ticker, ob)
            if is_pump:
                score -= 4.0
                signals.append(f'🚨 تحذير: نشاط غير طبيعي مكتشف! (Pump & Dump محتمل)')
        
        return {'score': round(score, 2), 'signals': signals, 'confidence': round(min(1.0, max(0.0, (score + 5) / 10.0)), 2)}

class MomentumAgent(ThompsonAgent):
    def __init__(self):
        super().__init__('Momentum', weight=1.3)
    
    def analyze(self, symbol, dfs, ticker, extra):
        score = 0.0
        signals = []
        w = STATE['ai_weights']
        price = float(ticker.get('last', 0))
        chg24h = float(ticker.get('changeRate', 0)) * 100
        oi = extra.get('oi', 0)
        btc_chg = STATE['market'].get('btc_chg', 0)
        if 0 < chg24h < btc_chg * 0.7 and symbol != 'BTC' and btc_chg > 0:
            score += w.get('correlation', 1.6)
            signals.append('🔗 متأخرة عن BTC')
        if '1day' in dfs:
            df_d = dfs['1day']
            high20 = df_d['high'].tail(20).max()
            if price > high20 * 0.98:
                score += w.get('breakout', 1.6)
                signals.append('🚀 كسر مقاومة 20 يوم')
            if calc_price_structure(df_d):
                score += 0.9
                signals.append('📈 بنية صاعدة HH/HL')
        for df in list(dfs.values())[:2]:
            cci = calc_cci(df)
            wr = calc_williams_r(df)
            if 100 < cci < 300:
                score += 0.7
                signals.append(f'CCI {cci:.0f}')
            if -40 < wr < -10:
                score += 0.6
            break
        for df in dfs.values():
            above, _ = calc_vwap(df)
            if above:
                score += 0.7
                signals.append('فوق VWAP')
            break
        oi_key = f'oi_{symbol}'
        with _oi_lock:
            prev_oi = STATE.get('oi_history', {}).get(oi_key, 0)
            STATE['oi_history'][oi_key] = oi
        if oi > 0 and prev_oi > 0:
            oi_chg = (oi - prev_oi) / prev_oi * 100
            if oi_chg > 5:
                score += w.get('oi_rising', 1.2)
                signals.append(f'📈 OI +{oi_chg:.1f}%')
        if '1hour' in dfs:
            patterns = detect_candle_patterns(dfs['1hour'])
            for p in patterns:
                score += 0.8
                signals.append(f'شمعة: {p}')
        return {'score': round(score, 2), 'signals': signals, 'confidence': round(min(1.0, score / 8.0), 2)}

# ════════════════════════════════════════════════════════════════
# 7. ML Engine (unchanged but integrated)
# ════════════════════════════════════════════════════════════════
class MLEngine:
    TRAIN_COINS = ['BTC', 'ETH', 'SOL', 'BNB', 'XRP', 'ADA', 'AVAX', 'DOT', 'LINK', 'MATIC', 'UNI', 'ATOM', 'NEAR', 'ARB', 'OP', 'INJ']
    TRAIN_TF = '4hour'
    TRAIN_LIMIT = 500
    HORIZON = 6
    THRESHOLD = 0.0025
    
    def __init__(self):
        self.models = {}
        self.features = []
        self.scaler = StandardScaler()
        self.trained = False
        self._load_if_exists()
    
    def _build_features(self, df):
        d = df.copy().astype(float)
        c = d['close']
        for p in [1, 3, 6, 12]:
            d[f'ret{p}'] = c.pct_change(p)
        d['logret1'] = np.log(c).diff(1)
        d['body'] = (d['close'] - d['open']) / d['open']
        d['hl_pct'] = (d['high'] - d['low']) / d['close']
        d['upper_wick'] = (d['high'] - d[['close', 'open']].max(axis=1)) / d['close']
        d['lower_wick'] = (d[['close', 'open']].min(axis=1) - d['low']) / d['close']
        d['vol_chg'] = d['volume'].pct_change(1)
        d['vol_ma20'] = d['volume'].rolling(20).mean()
        d['vol_ratio'] = d['volume'] / d['vol_ma20'].replace(0, np.nan)
        hl = d['high'] - d['low']
        hc = (d['high'] - d['close'].shift()).abs()
        lc = (d['low'] - d['close'].shift()).abs()
        tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
        dm_p = d['high'].diff().clip(lower=0)
        dm_m = (-d['low'].diff()).clip(lower=0)
        atr14 = tr.rolling(14).mean()
        d['adx'] = (100 * (dm_p.rolling(14).mean() - dm_m.rolling(14).mean()).abs() / (dm_p.rolling(14).mean() + dm_m.rolling(14).mean() + 1e-10)).rolling(14).mean()
        d['di_plus'] = 100 * dm_p.rolling(14).mean() / atr14
        d['di_minus'] = 100 * dm_m.rolling(14).mean() / atr14
        for p in [9, 21, 50, 200]:
            d[f'ema{p}'] = d['close'].ewm(p, adjust=False).mean()
            d[f'vs_ema{p}'] = (d['close'] - d[f'ema{p}']) / d[f'ema{p}'] * 100
        d['macd_hist'] = d['close'].ewm(12, adjust=False).mean() - d['close'].ewm(26, adjust=False).mean()
        d['macd_hist'] = d['macd_hist'] - d['macd_hist'].ewm(9, adjust=False).mean()
        mid = d['close'].rolling(20).mean()
        std = d['close'].rolling(20).std()
        d['bb_pct'] = (d['close'] - (mid - 2 * std)) / (4 * std + 1e-10)
        d['bb_width'] = 4 * std / mid
        d['atr14'] = tr.rolling(14).mean()
        d['atr_pct'] = d['atr14'] / d['close'] * 100
        obv = [0]
        for i in range(1, len(d)):
            obv.append(obv[-1] + d['volume'].iloc[i] if d['close'].iloc[i] > d['close'].iloc[i - 1] else obv[-1] - d['volume'].iloc[i])
        d['obv'] = obv
        d['obv_ma20'] = pd.Series(obv).rolling(20).mean().values
        d['obv_diff'] = d['obv'] - d['obv_ma20']
        tp = (d['high'] + d['low'] + d['close']) / 3
        mf = tp * d['volume']
        pos = mf.where(tp > tp.shift(), 0).rolling(14).sum()
        neg = mf.where(tp < tp.shift(), 0).rolling(14).sum()
        d['mfi'] = 100 - 100 / (1 + pos / (neg.replace(0, np.nan)))
        d['vol20'] = d['ret1'].rolling(20).std()
        d['vol60'] = d['ret1'].rolling(60).std()
        rsi_s = 100 - 100 / (1 + (d['close'].diff().clip(lower=0).rolling(14).mean() / (-d['close'].diff().clip(upper=0)).rolling(14).mean()))
        rsi_min = rsi_s.rolling(14).min()
        rsi_max = rsi_s.rolling(14).max()
        d['stoch_k'] = (rsi_s - rsi_min) / (rsi_max - rsi_min + 1e-10) * 100
        d.replace([np.inf, -np.inf], np.nan, inplace=True)
        d.dropna(inplace=True)
        exclude = {'open', 'high', 'low', 'close', 'volume', 'time'}
        feat_cols = [c for c in d.columns if c not in exclude]
        return d, feat_cols
    
    def build_dataset(self):
        X_list, y_list = [], []
        for coin in self.TRAIN_COINS:
            try:
                df = get_klines_cached(coin, self.TRAIN_TF, self.TRAIN_LIMIT)
                if df is None or len(df) < 150:
                    continue
                d, feat_cols = self._build_features(df)
                if len(d) < 80:
                    continue
                fut = d['close'].shift(-self.HORIZON) / d['close'] - 1.0
                y = (fut > self.THRESHOLD).astype(int)
                d = d.iloc[:-self.HORIZON].copy()
                y = y.iloc[:-self.HORIZON].copy()
                if not self.features:
                    self.features = feat_cols
                common = [f for f in self.features if f in d.columns]
                X_list.append(d[common])
                y_list.append(y)
                time.sleep(0.3)
            except:
                pass
        if not X_list:
            return None, None
        X = pd.concat(X_list, ignore_index=True)
        y = pd.concat(y_list, ignore_index=True)
        self.features = list(X.columns)
        return X, y
    
    def train(self):
        with _state_lock:
            STATE['ml_training'] = True
        log.info("🧠 بدء ML Training...")
        X, y = self.build_dataset()
        if X is None:
            with _state_lock:
                STATE['ml_training'] = False
            log.warning("⚠️ ML Training فشل: لا توجد بيانات كافية")
            add_feed('system', '⚠️', 'ML Training فشل', 'لا توجد بيانات كافية لتدريب النماذج')
            return False
        split = int(len(X) * 0.8)
        X_tr, X_val = X.iloc[:split], X.iloc[split:]
        y_tr, y_val = y.iloc[:split], y.iloc[split:]
        X_tr_s = self.scaler.fit_transform(X_tr)
        X_val_s = self.scaler.transform(X_val)
        pool = [
            ('LR', LogisticRegression(max_iter=500, solver='liblinear')),
            ('RF', RandomForestClassifier(n_estimators=300, max_depth=15, class_weight='balanced', random_state=42, n_jobs=-1)),
            ('GB', GradientBoostingClassifier(n_estimators=200, learning_rate=0.05, max_depth=4, random_state=42)),
        ]
        if HAS_XGB:
            pool.append(('XGB', xgb.XGBClassifier(n_estimators=400, max_depth=7, learning_rate=0.05, subsample=0.8, random_state=42, eval_metric='logloss', verbosity=0)))
        if HAS_LGB:
            pool.append(('LGB', lgb.LGBMClassifier(n_estimators=500, max_depth=9, learning_rate=0.05, num_leaves=64, subsample=0.8, random_state=42, verbose=-1)))
        self.models = {}
        for name, model in pool:
            try:
                model.fit(X_tr_s, y_tr)
                proba = model.predict_proba(X_val_s)[:, 1]
                auc = roc_auc_score(y_val, proba) if len(np.unique(y_val)) > 1 else 0.5
                acc = accuracy_score(y_val, (proba >= 0.5).astype(int))
                self.models[name] = {'model': model, 'auc': auc, 'acc': acc, 'weight': max(0.5, auc)}
                log.info(f"  ✅ {name}: AUC={auc:.3f}")
            except Exception as e:
                log.error(f"  ❌ {name}: {e}")
        if not self.models:
            with _state_lock:
                STATE['ml_training'] = False
            log.warning("⚠️ لم يتم تدريب أي نموذج ML")
            return False
        self.trained = True
        self._save()
        with _state_lock:
            STATE['ml_training'] = False
        add_feed('system', '🧠', 'ML Training اكتمل', f'النماذج: {list(self.models.keys())}')
        return True
    
    def predict(self, symbol):
        if not self.trained or not self.features:
            return {'score': 0, 'signals': [], 'confidence': 0, 'prob_up': 0.5}
        try:
            df = get_klines_cached(symbol, '4hour', 300)
            if df is None or len(df) < 150:
                return {'score': 0, 'signals': [], 'confidence': 0, 'prob_up': 0.5}
            d, _ = self._build_features(df)
            common = [f for f in self.features if f in d.columns]
            if len(common) < len(self.features) * 0.8:
                return {'score': 0, 'signals': [], 'confidence': 0, 'prob_up': 0.5}
            last = d[common].iloc[[-1]]
            last_s = self.scaler.transform(last)
            probas, weights, per_model = [], [], {}
            for name, data in self.models.items():
                try:
                    p = float(data['model'].predict_proba(last_s)[:, 1][0])
                    per_model[name] = round(p, 3)
                    probas.append(p)
                    weights.append(data['weight'])
                except:
                    pass
            if not probas:
                return {'score': 0, 'signals': [], 'confidence': 0, 'prob_up': 0.5}
            w = np.array(weights)
            w = w / w.sum()
            prob_up = float(np.dot(np.array(probas), w))
            # New scoring: 0-10 based on probability
            score = min(10.0, max(0.0, prob_up * 10))
            signals = []
            if prob_up > 0.65:
                signals.append(f'🤖 ML صعود قوي {prob_up:.0%}')
            elif prob_up > 0.55:
                signals.append(f'🤖 ML صعود {prob_up:.0%}')
            elif prob_up < 0.35:
                signals.append(f'🤖 ML هبوط {prob_up:.0%}')
            return {'score': round(score, 2), 'signals': signals, 'confidence': round(abs(prob_up - 0.5) * 2, 2), 'prob_up': round(prob_up, 3), 'per_model': per_model}
        except Exception as e:
            log.debug(f"ML predict error {symbol}: {e}")
            return {'score': 0, 'signals': [], 'confidence': 0, 'prob_up': 0.5}
    
    def _save(self):
        try:
            meta = {'features': self.features, 'models': {k: {'auc': v['auc'], 'acc': v['acc'], 'weight': v['weight']} for k, v in self.models.items()}}
            joblib.dump(meta, _MODEL_DIR / 'meta.pkl')
            joblib.dump(self.scaler, _MODEL_DIR / 'scaler.pkl')
            for name, data in self.models.items():
                joblib.dump(data['model'], _MODEL_DIR / f'{name}.pkl')
        except Exception as e:
            log.error(f"Save error: {e}")
    
    def _load_if_exists(self):
        try:
            meta_fp = _MODEL_DIR / 'meta.pkl'
            if not meta_fp.exists():
                return
            meta = joblib.load(meta_fp)
            self.features = meta['features']
            self.scaler = joblib.load(_MODEL_DIR / 'scaler.pkl')
            for name in meta['models']:
                fp = _MODEL_DIR / f'{name}.pkl'
                if fp.exists():
                    self.models[name] = {'model': joblib.load(fp), **meta['models'][name]}
            if self.models:
                self.trained = True
                log.info(f"✅ ML Models محملة: {list(self.models.keys())}")
        except Exception as e:
            log.debug(f"Load models: {e}")

ML_ENGINE = MLEngine()

class MLAgent(ThompsonAgent):
    def __init__(self):
        super().__init__('ML_Models', weight=2.0)
    
    def analyze(self, symbol, dfs, ticker, extra):
        result = ML_ENGINE.predict(symbol)
        score = result['score']
        sigs = result['signals']
        conf = result['confidence']
        for name, prob in result.get('per_model', {}).items():
            if prob > 0.62:
                sigs.append(f'  {name}: ↑{prob:.0%}')
        return {'score': score, 'signals': sigs, 'confidence': conf}

class MultiAgentVotingSystem:
    def __init__(self):
        self.agents = [TechnicalAgent(), SentimentAgent(), RiskAgent(), MomentumAgent(), MLAgent()]
        with _state_lock:
            STATE['agents'] = {a.name: {'weight': a.weight, 'alpha': a.alpha, 'beta': a.beta} for a in self.agents}
    
    def vote(self, symbol, dfs, ticker, extra):
        votes = {}
        all_signals = []
        total_weighted = 0.0
        total_weights = 0.0
        for agent in self.agents:
            try:
                result = agent.analyze(symbol, dfs, ticker, extra)
                votes[agent.name] = result
                all_signals += result['signals']
                # Thompson Sampling: use agent probability as weight
                agent_prob = agent.get_probability()
                combined_weight = agent.weight * (0.7 + 0.3 * agent_prob)
                total_weighted += result['score'] * combined_weight * result['confidence']
                total_weights += combined_weight
            except Exception as e:
                log.debug(f"Agent {agent.name} error on {symbol}: {e}")
                votes[agent.name] = {'score': 0, 'signals': [], 'confidence': 0}
        final_score = round(total_weighted / max(total_weights, 1), 2)
        risk_score = votes.get('Risk', {}).get('score', 0)
        if risk_score < -2.0:
            final_score *= 0.4
            all_signals.insert(0, f'🛡️ Risk Veto ({risk_score:.1f})')
        positive_agents = sum(1 for v in votes.values() if v['score'] > 1.0)
        consensus = positive_agents / len(self.agents)
        if consensus >= 0.75:
            final_score *= 1.2
            all_signals.insert(0, f'🤝 إجماع {positive_agents}/{len(self.agents)} Agents')
        elif consensus <= 0.25:
            final_score *= 0.7
        seen = set()
        unique_signals = []
        for s in all_signals:
            if s not in seen:
                seen.add(s)
                unique_signals.append(s)
        return {'final_score': round(final_score, 2), 'consensus': round(consensus, 2),
                'votes': {k: {'score': v['score'], 'confidence': v['confidence']} for k, v in votes.items()},
                'signals': unique_signals, 'risk_score': risk_score}
    
    def update_weights(self, coin, outcome_correct: bool):
        for agent in self.agents:
            agent.update(outcome_correct)
        with _state_lock:
            STATE['agents'] = {a.name: {'weight': a.weight, 'alpha': a.alpha, 'beta': a.beta} for a in self.agents}

VOTING_SYSTEM = MultiAgentVotingSystem()

# ════════════════════════════════════════════════════════════════
# 8. Core Analysis Engine
# ════════════════════════════════════════════════════════════════
def add_feed(type_, icon, title, sub=''):
    with _feed_lock:
        STATE['feed'].insert(0, {'type': type_, 'icon': icon, 'title': title, 'sub': sub, 'time': datetime.now().isoformat()})
        if len(STATE['feed']) > 200:
            STATE['feed'] = STATE['feed'][:200]

def analyze_coin(symbol):
    timeframes = ['5min', '1hour', '4hour', '1day']
    ticker = get_ticker(symbol)
    price = float(ticker.get('last', 0))
    vol24h = float(ticker.get('volValue', 0))
    chg24h = float(ticker.get('changeRate', 0)) * 100
    if price == 0:
        return None
    if CONFIG['LIQUIDITY_FILTER_ON'] and vol24h < CONFIG['LIQUIDITY_MIN']:
        return None
    funding = get_funding_rate(symbol)
    oi = get_open_interest(symbol)
    ob = get_orderbook(symbol)
    dfs = {}
    for tf in timeframes:
        df = get_klines_cached(symbol, tf, 200)
        if df is not None and len(df) > 50:
            dfs[tf] = df
    if not dfs:
        return None
    
    w = STATE['ai_weights']
    total_score = 0.0
    signals_found = []
    
    for tf, df in dfs.items():
        sq, sq_mom = calc_squeeze(df)
        if sq and sq_mom > 0:
            s = w.get(f'squeeze_{tf}', w.get('squeeze_4h', 1.0))
            total_score += s
            signals_found.append(f'💥 Squeeze {tf}')
        rsi = calc_rsi(df)
        if 55 < rsi < 80:
            total_score += 0.8
            signals_found.append(f'RSI {rsi:.0f} ({tf})')
        macd_v, sig_v, hist = calc_macd(df)
        if hist > 0 and macd_v > 0:
            total_score += w.get('macd_cross', 1.4) * 0.5
            signals_found.append(f'MACD+ ({tf})')
        obv_bull, _ = calc_obv(df)
        if obv_bull:
            total_score += w.get('obv_diverge', 1.8) * 0.6
            signals_found.append(f'OBV انفجار ({tf})')
        adx_val, di_p, di_m = calc_adx(df)
        if adx_val > 25 and di_p > di_m:
            total_score += 0.9
            signals_found.append(f'ADX {adx_val:.0f} ({tf})')
        if adx_val > 35:
            total_score += 0.5
        if len(df) > 20:
            vol_avg = df['volume'].tail(20).mean()
            vol_now = df['volume'].iloc[-1]
            if vol_now > vol_avg * 3:
                total_score += w.get('volume_x3', 1.7)
                signals_found.append(f'💥 حجم ×{vol_now / vol_avg:.1f} ({tf})')
        mfi = calc_mfi(df)
        if mfi > 60:
            total_score += 0.7
        above_vwap, _ = calc_vwap(df)
        if above_vwap:
            total_score += 0.5
        cvd_surge, _ = calc_cvd(df)
        if cvd_surge:
            total_score += w.get('cvd_surge', 1.5) * 0.7
            signals_found.append(f'CVD Surge ({tf})')
    
    if '1day' in dfs:
        df_d = dfs['1day']
        emas = calc_ema(df_d, [9, 21, 50, 200])
        if all(v[0] for v in emas.values()) and len(emas) >= 3:
            total_score += w.get('golden_cross', 1.6)
            signals_found.append('✨ Golden Cross')
        if calc_ichimoku(df_d):
            total_score += w.get('ichimoku', 1.4) * 0.8
            signals_found.append('Ichimoku ✅')
        if calc_supertrend(df_d):
            total_score += w.get('supertrend', 1.3) * 0.8
            signals_found.append('Supertrend ✅')
        if calc_price_structure(df_d):
            total_score += 0.8
            signals_found.append('بنية صاعدة')
        high20 = df_d['high'].tail(20).max()
        if price > high20 * 0.98:
            total_score += w.get('breakout', 1.6)
            signals_found.append('🚀 كسر مقاومة')
    
    if ob['ratio'] > 1.5:
        total_score += w.get('orderbook_bull', 2.0)
        signals_found.append(f'📗 Orderbook ×{ob["ratio"]:.1f}')
    if -0.01 < funding < 0.05:
        total_score += w.get('funding_pos', 1.3) * 0.5
        signals_found.append(f'Funding {funding:.4f}')
    
    oi_key = f'oi_{symbol}'
    with _oi_lock:
        prev_oi = STATE.get('oi_history', {}).get(oi_key, 0)
        STATE['oi_history'][oi_key] = oi
    if oi > 0 and prev_oi > 0:
        oi_chg_pct = (oi - prev_oi) / prev_oi * 100
        if oi_chg_pct > 5:
            total_score += w.get('oi_rising', 1.2)
            signals_found.append(f'📈 OI +{oi_chg_pct:.1f}%')
        elif oi_chg_pct > 2:
            total_score += w.get('oi_rising', 1.2) * 0.5
        elif oi_chg_pct < -10:
            total_score += 0.8
            signals_found.append(f'🔥 Short Squeeze؟ OI {oi_chg_pct:.1f}%')
    
    if '1hour' in dfs:
        for p in detect_candle_patterns(dfs['1hour']):
            total_score += 0.6
            signals_found.append(f'شمعة: {p}')
    
    btc_chg = STATE['market']['btc_chg']
    if chg24h > 0 and chg24h < btc_chg * 0.8 and symbol != 'BTC':
        total_score += w.get('correlation', 1.6) * 0.7
        signals_found.append('🔗 متأخرة عن BTC')
    
    total_score = round(total_score, 2)
    extra = {'ob': ob, 'funding': funding, 'oi': oi}
    vote_result = VOTING_SYSTEM.vote(symbol, dfs, ticker, extra)
    final_score = round(vote_result['final_score'] * 0.6 + total_score * 0.4, 2)
    
    final_score = max(0.0, min(10.0, final_score))
    total_score = max(0.0, min(10.0, total_score))
    
    if final_score < CONFIG['MIN_SCORE_WATCH']:
        return None
    signal_type = 'WATCH'
    if final_score >= CONFIG['MIN_SCORE_HOT']:
        signal_type = 'HOT'
    elif final_score >= CONFIG['MIN_SCORE_WARM']:
        signal_type = 'WARM'
    
    atr_val = calc_atr(dfs.get('1day', list(dfs.values())[0])) if dfs else price * 0.02
    target = round(price + 2.0 * atr_val, 6)
    stop = round(price - 1.0 * atr_val, 6)
    
    return {
        'coin': symbol, 'price': price, 'change24h': round(chg24h, 2), 'vol24h': vol24h,
        'type': signal_type, 'score': final_score, 'raw_score': total_score,
        'signals': vote_result['signals'], 'target': target, 'stop': stop,
        'target_pct': round((target - price) / price * 100, 2), 'stop_pct': round((price - stop) / price * 100, 2),
        'funding': funding, 'open_interest': oi, 'ob_ratio': ob['ratio'],
        'timestamp': datetime.now().isoformat(),
        'agent_votes': vote_result['votes'], 'consensus': vote_result['consensus'], 'risk_score': vote_result['risk_score'],
    }

# ════════════════════════════════════════════════════════════════
# 9. Macro Guard, Telegram, Scan Loop
# ════════════════════════════════════════════════════════════════
def check_macro_veto():
    if not CONFIG['MACRO_VETO_ON']:
        return False
    now = datetime.now()
    if STATE['macro_veto_until'] and now < STATE['macro_veto_until']:
        return True
    btc = get_ticker('BTC')
    chg = float(btc.get('changeRate', 0)) * 100
    with _state_lock:
        STATE['market']['btc_chg'] = chg
        STATE['market']['btc'] = float(btc.get('last', 0))
    if chg <= -CONFIG['MACRO_VETO_PCT']:
        with _state_lock:
            STATE['macro_veto_active'] = True
            STATE['macro_veto_until'] = now + timedelta(seconds=CONFIG['MACRO_FREEZE_SEC'])
        add_feed('system', '⚠️', f'Macro Veto — BTC {chg:.2f}%', f'تجميد {CONFIG["MACRO_FREEZE_SEC"]}ث')
        return True
    with _state_lock:
        STATE['macro_veto_active'] = False
    return False

def send_telegram(text, token=None, chat=None, retries=3):
    t = token or CONFIG['TG_TOKEN']
    c = chat or CONFIG['TG_CHAT']
    if not t or not c:
        return False
    url = f"https://api.telegram.org/bot{t}/sendMessage"
    payload = {'chat_id': c, 'text': text, 'parse_mode': 'HTML'}
    for attempt in range(retries):
        try:
            r = requests.post(url, json=payload, timeout=30)
            result = r.json()
            if result.get('ok'):
                with _state_lock:
                    STATE['telegram_available'] = True
                return True
            else:
                log.error(f"Telegram API error: {result.get('description')}")
                return False
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError):
            with _state_lock:
                STATE['telegram_available'] = False
            time.sleep(5 * (attempt + 1))
        except Exception as e:
            log.error(f"Telegram send error: {e}")
            return False
    return False

def format_signal_msg(sig):
    emoji = '🔴🚨' if sig['type'] == 'HOT' else '🟡' if sig['type'] == 'WARM' else '👀'
    votes = sig.get('agent_votes', {})
    consensus = sig.get('consensus', 0)
    filled = round(consensus * 4)
    consensus_bar = '🟢' * filled + '⚪' * (4 - filled)
    lines = [
        f"{emoji} <b>{sig['type']} — {sig['coin']}/USDT</b>",
        "━━━━━━━━━━━━━━━━━━",
        f"💵 ${sig['price']:.4f}  {'+' if sig['change24h'] > 0 else ''}{sig['change24h']}%",
        f"🎯 +{sig['target_pct']}%  |  🛑 -{sig['stop_pct']}%",
        f"📊 OB: ×{sig['ob_ratio']:.1f}  |  Funding: {sig['funding']:.4f}",
        f"🧠 Score: <b>{sig['score']}</b> | اتفاق: {consensus_bar} {int(consensus * 100)}%",
        "",
        "<b>🤖 أصوات الـ Agents:</b>",
    ]
    for name, v in votes.items():
        em = {'Technical': '📈', 'Sentiment': '💬', 'Risk': '🛡️', 'Momentum': '⚡'}.get(name, '🤖')
        bars = min(5, max(0, int(abs(v['score']))))
        bar = ('▓' if v['score'] >= 0 else '░') * bars + '░' * (5 - bars)
        lines.append(f"{em} {name}: {bar} {v['score']:+.1f}")
    lines += ['', f"✅ الإشارات ({len(sig['signals'])})"]
    for s in sig['signals'][:7]:
        lines.append(f"• {s}")
    lines += ['', f"⏰ {sig['timestamp'][:19].replace('T', ' ')}", "<i>⚠️ تحليل فني فقط</i>"]
    return '\n'.join(lines)

def run_scan():
    with _state_lock:
        STATE['scan_count'] += 1
    add_feed('system', '🔄', f'فحص #{STATE["scan_count"]} بدأ', f'فحص {len(COINS)} عملة...')
    log.info(f"🔄 بدء الفحص #{STATE['scan_count']}")
    if check_macro_veto():
        add_feed('system', '⚠️', 'Macro Veto فعّال', 'تم تخطي الفحص')
        return
    new_signals = 0
    for coin in COINS:
        if not STATE['running']:
            break
        try:
            with _state_lock:
                last = STATE['signal_cooldown'].get(coin)
            if last and (datetime.now() - last).days < CONFIG['SIGNAL_COOLDOWN_DAYS']:
                continue
            result = analyze_coin(coin)
            if result:
                with _signals_lock:
                    prev = next((s for s in STATE['signals'] if s['coin'] == coin), None)
                    STATE['signals'] = [s for s in STATE['signals'] if s['coin'] != coin]
                    STATE['signals'].insert(0, result)
                    STATE['signals'] = STATE['signals'][:100]
                if result['type'] in ('HOT', 'WARM'):
                    with _state_lock:
                        last_sent = STATE['signal_cooldown'].get(coin)
                    prev_type = prev['type'] if prev else None
                    type_improved = (result['type'] == 'HOT' and prev_type in (None, 'WARM', 'WATCH'))
                    cooldown_ok = not last_sent or (datetime.now() - last_sent).total_seconds() > CONFIG['SIGNAL_COOLDOWN_DAYS'] * 86400
                    if cooldown_ok or type_improved:
                        with _state_lock:
                            STATE['signal_cooldown'][coin] = datetime.now()
                        new_signals += 1
                        add_feed(result['type'].lower(), '🔴' if result['type'] == 'HOT' else '🟡',
                                 f"{result['type']}: {coin}/USDT", f"Score: {result['score']}")
                        send_telegram(format_signal_msg(result))
                        log.info(f"🚀 {result['type']}: {coin} | Score={result['score']}")
            time.sleep(0.3)
        except Exception as e:
            log.debug(f"Error {coin}: {e}")
    with _state_lock:
        STATE['last_scan'] = datetime.now().isoformat()
        hot = sum(1 for s in STATE['signals'] if s['type'] == 'HOT')
        warm = sum(1 for s in STATE['signals'] if s['type'] == 'WARM')
    add_feed('system', '✅', f'اكتمل الفحص #{STATE["scan_count"]}', f'إشارات جديدة: {new_signals} | HOT: {hot} | WARM: {warm}')
    log.info(f"✅ انتهى الفحص | HOT:{hot} WARM:{warm}")

def scan_loop():
    while STATE['running']:
        try:
            run_scan()
        except Exception as e:
            log.error(f"Scan error: {e}")
        interval_s = CONFIG['SCAN_INTERVAL'] * 60
        with _state_lock:
            STATE['next_scan'] = (datetime.now() + timedelta(seconds=interval_s)).isoformat()
        time.sleep(interval_s)

# ════════════════════════════════════════════════════════════════
# 10. Flask API Routes
# ════════════════════════════════════════════════════════════════
@app.route('/api/healthz')
def api_healthz():
    return jsonify({'status': 'ok', 'running': STATE['running']})

@app.route('/api/status')
@_api_key_required
def api_status():
    with _state_lock:
        hot = sum(1 for s in STATE['signals'] if s['type'] == 'HOT')
        warm = sum(1 for s in STATE['signals'] if s['type'] == 'WARM')
        watch = sum(1 for s in STATE['signals'] if s['type'] == 'WATCH')
        p = STATE['performance']
        wr = round(p['win'] / p['total'] * 100, 1) if p['total'] > 0 else 0
        return jsonify({
            'running': STATE['running'], 'scan_count': STATE['scan_count'],
            'last_scan': STATE['last_scan'], 'next_scan': STATE['next_scan'],
            'macro_veto': STATE['macro_veto_active'], 'hot': hot, 'warm': warm, 'watch': watch,
            'total': len(STATE['signals']), 'win_rate': wr, 'market': STATE['market'],
            'telegram_ok': STATE.get('telegram_available', True),
            'scalp_mode': STATE.get('scalp_mode', False), 'ml_trained': ML_ENGINE.trained
        })

@app.route('/api/signals')
@_api_key_required
def api_signals():
    sig_type = request.args.get('type', 'all')
    limit = int(request.args.get('limit', 50))
    with _signals_lock:
        sigs = STATE['signals']
    if sig_type != 'all':
        sigs = [s for s in sigs if s['type'] == sig_type.upper()]
    return jsonify(sigs[:limit])

@app.route('/api/feed')
@_api_key_required
def api_feed():
    limit = int(request.args.get('limit', 100))
    with _feed_lock:
        feed = STATE['feed'][:limit]
    return jsonify(feed)

@app.route('/api/start', methods=['POST'])
@_api_key_required
def api_start():
    if STATE['running']:
        return jsonify({'ok': False, 'msg': 'البوت يعمل بالفعل'})
    with _state_lock:
        STATE['running'] = True
    threading.Thread(target=scan_loop, daemon=True).start()
    threading.Thread(target=keep_alive_loop, daemon=True).start()
    add_feed('system', '🚀', 'البوت بدأ', f'فحص {len(COINS)} عملة كل {CONFIG["SCAN_INTERVAL"]} دقيقة')
    log.info('🚀 البوت بدأ')
    return jsonify({'ok': True, 'msg': 'البوت يعمل'})

@app.route('/api/stop', methods=['POST'])
@_api_key_required
def api_stop():
    with _state_lock:
        STATE['running'] = False
    add_feed('system', '⏹', 'تم إيقاف البوت', '')
    log.info('⏹ البوت متوقف')
    return jsonify({'ok': True, 'msg': 'البوت توقف'})

@app.route('/api/ml/train', methods=['POST'])
@_api_key_required
def api_ml_train():
    if STATE.get('ml_training'):
        return jsonify({'ok': False, 'msg': 'التدريب جاري بالفعل'})
    threading.Thread(target=ML_ENGINE.train, daemon=True).start()
    return jsonify({'ok': True, 'msg': 'بدأ التدريب في الخلفية — قد يأخذ 5-10 دقائق'})

@app.route('/api/ml/status')
@_api_key_required
def api_ml_status():
    models_info = {name: {'auc': data.get('auc', 0), 'acc': data.get('acc', 0), 'weight': data.get('weight', 0)} for name, data in ML_ENGINE.models.items()}
    return jsonify({'trained': ML_ENGINE.trained, 'training': STATE.get('ml_training', False),
                    'models': models_info, 'features': len(ML_ENGINE.features), 'train_coins': MLEngine.TRAIN_COINS})

@app.route('/api/pump/status')
@_api_key_required
def api_pump_status():
    return jsonify({'trained': PUMP_DETECTOR.trained, 'enabled': CONFIG['PUMP_DETECTION_ON']})

@app.route('/api/pump/train', methods=['POST'])
@_api_key_required
def api_pump_train():
    threading.Thread(target=lambda: PUMP_DETECTOR.train_on_history(COINS[:30], None), daemon=True).start()
    return jsonify({'ok': True, 'msg': 'بدأ تدريب نموذج كشف التلاعب'})

@app.route('/api/whale/scan', methods=['POST'])
@_api_key_required
def api_whale_scan():
    data = request.json or {}
    coin = data.get('coin', 'BTC')
    whales = detect_whales(coin, threshold_usd=data.get('threshold', 200000))
    return jsonify({'ok': True, 'coin': coin, 'whales': whales})

@app.route('/api/scalp/toggle', methods=['POST'])
@_api_key_required
def api_scalp_toggle():
    STATE['scalp_mode'] = not STATE.get('scalp_mode', False)
    if STATE['scalp_mode']:
        threading.Thread(target=scalp_loop, daemon=True).start()
        add_feed('system', '⚡', 'وضع Scalping فعّال', 'فحص كل دقيقتين')
    else:
        add_feed('system', '⏹', 'وضع Scalping متوقف', '')
    return jsonify({'ok': True, 'scalp_mode': STATE['scalp_mode']})

@app.route('/api/scalp/status')
@_api_key_required
def api_scalp_status():
    return jsonify({'scalp_mode': STATE.get('scalp_mode', False)})

@app.route('/api/backtest', methods=['POST'])
@_api_key_required
def api_backtest():
    data = request.json or {}
    symbol = data.get('symbol', 'BTC')
    tf = data.get('tf', '1day')
    result = run_backtest(symbol, tf)
    if result:
        return jsonify({'ok': True, 'result': result})
    return jsonify({'ok': False, 'msg': 'بيانات غير كافية'})

@app.route('/api/report/daily', methods=['POST'])
@_api_key_required
def api_daily_report():
    threading.Thread(target=send_daily_report, daemon=True).start()
    return jsonify({'ok': True, 'msg': 'جاري إرسال التقرير'})
    
# ════════════════════════════════════════════════════════════════
# 11. Startup
# ════════════════════════════════════════════════════════════════
def keep_alive_loop():
    time.sleep(60)
    port_ka = int(os.environ.get('PORT', 8080))
    url = os.environ.get('RENDER_EXTERNAL_URL', f'http://localhost:{port_ka}')
    log.info(f"🏓 Keep-Alive بدأ → {url}/health")
    while True:
        try:
            requests.get(f"{url}/health", timeout=10)
            log.debug("🏓 ping OK")
        except Exception as e:
            log.debug(f"🏓 ping error: {e}")
        time.sleep(600)

def _auto_start():
    if STATE.get('_started'):
        return
    with _state_lock:
        STATE['_started'] = True
        STATE['running'] = True
    log.info("🚀 Auto-start: بدء تشغيل جميع الـ threads...")
    threading.Thread(target=scan_loop, daemon=True).start()
    threading.Thread(target=keep_alive_loop, daemon=True).start()
    # Train Pump Detector in background
    threading.Thread(target=lambda: PUMP_DETECTOR.train_on_history(COINS[:30], None), daemon=True).start()
    if not ML_ENGINE.trained:
        log.info("🧠 بدء ML Training في الخلفية...")
        threading.Thread(target=ML_ENGINE.train, daemon=True).start()
    log.info("✅ جميع الـ threads بدأت")

_startup_done = False

@app.before_request
def startup_hook():
    global _startup_done
    if not _startup_done:
        _startup_done = True
        _auto_start()

# ===================== WHALE DETECTOR =====================
WHALE_COINS = ['BTC','ETH','SOL','BNB','XRP','ADA','AVAX','DOGE','DOT','LINK','MATIC','UNI','ATOM','ARB','OP','INJ','SUI','NEAR','FTM','LTC']

def detect_whales(symbol, threshold_usd=200000):
    try:
        r = requests.get(f"{KUCOIN}/market/orderbook/level2_100?symbol={symbol}-USDT", timeout=8)
        d = r.json().get('data', {})
        whales = []
        for bid in d.get('bids', []):
            p, s = float(bid[0]), float(bid[1])
            v = p * s
            if v >= threshold_usd:
                whales.append({'side': 'BUY', 'price': p, 'size': s, 'value': v})
        for ask in d.get('asks', []):
            p, s = float(ask[0]), float(ask[1])
            v = p * s
            if v >= threshold_usd:
                whales.append({'side': 'SELL', 'price': p, 'size': s, 'value': v})
        return sorted(whales, key=lambda x: x['value'], reverse=True)[:5]
    except:
        return []

def whale_scan_loop():
    time.sleep(30)
    while STATE['running']:
        try:
            for coin in WHALE_COINS:
                if not STATE['running']:
                    break
                whales = detect_whales(coin, threshold_usd=500000)
                buy_whales = [w for w in whales if w['side'] == 'BUY']
                if buy_whales:
                    total_buy = sum(w['value'] for w in buy_whales)
                    msg = (f"🐋 <b>حوت شراء — {coin}/USDT</b>\n💰 قيمة: ${total_buy:,.0f}\n"
                           f"📊 أكبر: ${buy_whales[0]['value']:,.0f} @ ${buy_whales[0]['price']:.4f}\n"
                           f"⏰ {datetime.now().strftime('%H:%M:%S')}")
                    add_feed('hot', '🐋', f'حوت شراء {coin}', f'${total_buy:,.0f}')
                    send_telegram(msg)
                time.sleep(1)
        except Exception as e:
            log.debug(f"Whale scan error: {e}")
        time.sleep(300)

# ===================== TP TRACKER =====================
def tp_tracker_loop():
    time.sleep(60)
    notified = set()
    while STATE['running']:
        try:
            with _signals_lock:
                active = [s for s in STATE['signals'] if s['type'] in ('HOT', 'WARM')]
            for sig in active:
                key = f"{sig['coin']}_{sig['timestamp']}"
                if key in notified:
                    continue
                ticker = get_ticker(sig['coin'])
                price_now = float(ticker.get('last', 0))
                if price_now == 0:
                    continue
                pnl_pct = (price_now - sig['price']) / sig['price'] * 100
                if price_now >= sig['target']:
                    send_telegram(f"✅ <b>تحقق الهدف! — {sig['coin']}/USDT</b>\n🎯 دخول: ${sig['price']:.4f} → الآن: ${price_now:.4f}\n💰 <b>الربح: +{pnl_pct:.2f}%</b>")
                    add_feed('hot', '✅', f'هدف {sig["coin"]} تحقق!', f'+{pnl_pct:.2f}%')
                    notified.add(key)
                    with _state_lock:
                        STATE['performance']['win'] += 1
                        STATE['performance']['total'] += 1
                    VOTING_SYSTEM.update_weights(sig['coin'], True)
                elif price_now <= sig['stop']:
                    send_telegram(f"🛑 <b>وصل الوقف — {sig['coin']}/USDT</b>\n❌ دخول: ${sig['price']:.4f} → الآن: ${price_now:.4f}\n📉 <b>الخسارة: {pnl_pct:.2f}%</b>")
                    add_feed('system', '🛑', f'وقف {sig["coin"]}', f'{pnl_pct:.2f}%')
                    notified.add(key)
                    with _state_lock:
                        STATE['performance']['loss'] += 1
                        STATE['performance']['total'] += 1
                    VOTING_SYSTEM.update_weights(sig['coin'], False)
        except Exception as e:
            log.debug(f"TP tracker error: {e}")
        time.sleep(60)

# ===================== DAILY REPORT =====================
def send_daily_report():
    with _signals_lock:
        hot_sigs = sorted([s for s in STATE['signals'] if s['type'] == 'HOT'], key=lambda x: x['score'], reverse=True)[:5]
    with _state_lock:
        p = STATE['performance']
        btc = STATE['market'].get('btc', 0)
        btc_chg = STATE['market'].get('btc_chg', 0)
    wr = round(p['win'] / p['total'] * 100, 1) if p['total'] > 0 else 0
    lines = [
        f"☀️ <b>تقرير الصباح — Destroyer V7</b>",
        f"📅 {datetime.now().strftime('%Y-%m-%d')}",
        "━━━━━━━━━━━━━━━━━━",
        f"₿ BTC: ${btc:,.0f} ({'+' if btc_chg > 0 else ''}{btc_chg:.2f}%)",
        f"📊 Win Rate: {wr}% | ✅{p['win']} ❌{p['loss']}",
        "",
        "🔥 <b>أفضل 5 فرص الآن:</b>"
    ]
    for i, s in enumerate(hot_sigs, 1):
        lines.append(f"{i}. <b>{s['coin']}</b> — Score:{s['score']} | +{s['change24h']}%")
    if not hot_sigs:
        lines.append("لا توجد إشارات HOT حالياً")
    with _signals_lock:
        hot_count = sum(1 for s in STATE['signals'] if s['type'] == 'HOT')
        warm_count = sum(1 for s in STATE['signals'] if s['type'] == 'WARM')
    lines += [
        "",
        f"🔴 HOT: {hot_count}",
        f"🟡 WARM: {warm_count}",
        "━━━━━━━━━━━━━━━━━━",
        "<i>Destroyer V7 | تحليل فني + ذكاء اصطناعي</i> ⚠️"
    ]
    send_telegram('\n'.join(lines))
    add_feed('system', '☀️', 'تم إرسال التقرير اليومي', '')

def daily_report_loop():
    time.sleep(120)
    while STATE['running']:
        now = datetime.now()
        target_hour = 8
        next_run = now.replace(hour=target_hour, minute=0, second=0) + (timedelta(days=1) if now.hour >= target_hour else timedelta(0))
        wait_sec = (next_run - now).total_seconds()
        time.sleep(wait_sec)
        try:
            send_daily_report()
        except Exception as e:
            log.error(f"Daily report error: {e}")

# ===================== SCALPING MODE =====================
SCALP_COINS = ['BTC','ETH','SOL','BNB','XRP','ADA','AVAX','DOGE','DOT','LINK','MATIC','ARB','OP','INJ','SUI','NEAR','APT','TIA','WIF','PEPE']

def scalp_loop():
    time.sleep(90)
    while STATE.get('scalp_mode', False):
        try:
            for coin in SCALP_COINS:
                if not STATE.get('scalp_mode'):
                    break
                df5 = get_klines(coin, '5min', 100)
                df15 = get_klines(coin, '15min', 60)
                if df5 is None or df15 is None:
                    continue
                score = 0
                signals = []
                sq5, mom5 = calc_squeeze(df5)
                if sq5 and mom5 > 0:
                    score += 2.5
                    signals.append('💥 Squeeze 5m')
                sq15, mom15 = calc_squeeze(df15)
                if sq15 and mom15 > 0:
                    score += 2.0
                    signals.append('💥 Squeeze 15m')
                rsi5 = calc_rsi(df5)
                if 55 < rsi5 < 80:
                    score += 1.0
                    signals.append(f'RSI {rsi5:.0f}')
                vol_avg = df5['volume'].tail(20).mean()
                vol_now = df5['volume'].iloc[-1]
                if vol_now > vol_avg * 2.5:
                    score += 1.5
                    signals.append(f'📊 حجم ×{vol_now/vol_avg:.1f}')
                _, _, hist = calc_macd(df5)
                if hist > 0:
                    score += 0.8
                    signals.append('MACD+')
                cvd_s, _ = calc_cvd(df5)
                if cvd_s:
                    score += 1.2
                    signals.append('CVD Surge')
                if score >= 5:
                    ticker = get_ticker(coin)
                    price = float(ticker.get('last', 0))
                    chg = float(ticker.get('changeRate', 0)) * 100
                    msg = (f"⚡ <b>SCALP — {coin}/USDT</b>\n💵 ${price:.4f} | {'+' if chg > 0 else ''}{chg:.2f}%\n"
                           f"🧠 Score: {score:.1f}\n✅ {' | '.join(signals[:4])}\n⚡ <i>وضع Scalping — إطار 5-15 دقيقة</i>")
                    send_telegram(msg)
                    add_feed('hot', '⚡', f'SCALP: {coin}', f'Score:{score:.1f}')
                time.sleep(0.5)
        except Exception as e:
            log.error(f"Scalp loop error: {e}")
        time.sleep(120)

# ===================== BACKTESTING =====================
def run_backtest(symbol, tf='1day', periods=90):
    df = get_klines(symbol, tf, periods + 50)
    if df is None or len(df) < periods:
        return None
    trades = []
    for i in range(50, len(df) - 5):
        chunk = df.iloc[:i].copy()
        try:
            rsi = calc_rsi(chunk)
            sq, sq_mom = calc_squeeze(chunk)
            _, _, hist = calc_macd(chunk)
            obv_bull, _ = calc_obv(chunk)
            score = 0
            if sq and sq_mom > 0:
                score += 3
            if rsi > 55:
                score += 1
            if hist > 0:
                score += 1
            if obv_bull:
                score += 1
            if score >= 4:
                entry = df['close'].iloc[i]
                atr = calc_atr(chunk)
                target = entry + 2 * atr
                stop = entry - 1 * atr
                future = df['close'].iloc[i+1:i+6]
                hit_tp = any(future >= target)
                hit_sl = any(future <= stop)
                if hit_tp and not hit_sl:
                    trades.append({'result': 'WIN', 'pnl': (target - entry) / entry * 100})
                elif hit_sl:
                    trades.append({'result': 'LOSS', 'pnl': (stop - entry) / entry * 100})
        except:
            continue
    if not trades:
        return None
    wins = sum(1 for t in trades if t['result'] == 'WIN')
    total = len(trades)
    return {
        'symbol': symbol, 'tf': tf, 'total': total, 'wins': wins, 'losses': total - wins,
        'win_rate': round(wins / total * 100, 1),
        'avg_pnl': round(sum(t['pnl'] for t in trades) / total, 2),
        'periods': periods
    }

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    log.info('━' * 50)
    log.info('💥 ULTIMATE DESTROYER V7 — التشغيل الكامل')
    log.info(f'   العملات: {len(COINS)} | المؤشرات: 35+ | المنفذ: {port}')
    log.info('━' * 50)
    if CONFIG['TG_TOKEN'] and CONFIG['TG_CHAT']:
        log.info('📱 تيليغرام مُعدّ — الإشارات ستُرسل تلقائياً')
    else:
        log.info('⚠️ تيليغرام غير مُعدّ — أضف Token من لوحة الويب')
    if CONFIG['CRYPTOPANIC_TOKEN']:
        log.info('📰 تحليل المشاعر (CryptoPanic) مُفعّل')
    else:
        log.info('📰 تحليل المشاعر غير مُفعّل (أضف CRYPTOPANIC_TOKEN)')
    if API_KEY:
        log.info('🔐 تم تفعيل حماية API Key')
    else:
        log.info('🔓 حماية API Key غير مفعلة')
    
    _auto_start()
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
