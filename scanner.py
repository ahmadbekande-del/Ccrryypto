# scanner.py
import ccxt
import pandas as pd
import numpy as np
import ta
from ta import add_all_ta_features
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

class KuCoinSuperScanner:
    def __init__(self, api_key="", secret=""):
        self.exchange = ccxt.kucoin({
            'enableRateLimit': True,
            'apiKey': api_key,
            'secret': secret,
            'options': {'defaultType': 'spot'}
        })

    def get_top_symbols(self, limit=150):
        """أفضل 150 عملة حسب حجم التداول"""
        markets = self.exchange.load_markets()
        all_symbols = [s for s in markets if s.endswith('/USDT') and markets[s]['active']]
        tickers = self.exchange.fetch_tickers()
        symbol_volume = []
        for sym in all_symbols:
            if sym in tickers and tickers[sym].get('quoteVolume'):
                symbol_volume.append((sym, tickers[sym]['quoteVolume']))
        symbol_volume.sort(key=lambda x: x[1], reverse=True)
        return [s[0] for s in symbol_volume[:limit]]

    def _calculate_all_indicators(self, df):
        """25+ مؤشر فني"""
        df = df.sort_index()
        # المتوسطات
        df['SMA_10'] = ta.trend.sma_indicator(df['close'], window=10)
        df['SMA_30'] = ta.trend.sma_indicator(df['close'], window=30)
        df['SMA_200'] = ta.trend.sma_indicator(df['close'], window=200)
        df['EMA_12'] = ta.trend.ema_indicator(df['close'], window=12)
        df['EMA_26'] = ta.trend.ema_indicator(df['close'], window=26)
        # الزخم
        df['RSI'] = ta.momentum.rsi(df['close'], window=14)
        df['Stoch_K'] = ta.momentum.stoch(df['high'], df['low'], df['close'], window=14, smooth_window=3)
        df['Stoch_D'] = ta.momentum.stoch_signal(df['high'], df['low'], df['close'], window=14, smooth_window=3)
        df['MACD'] = ta.trend.MACD(df['close']).macd()
        df['MACD_signal'] = ta.trend.MACD(df['close']).macd_signal()
        df['MACD_diff'] = ta.trend.MACD(df['close']).macd_diff()
        df['Williams_R'] = ta.momentum.williams_r(df['high'], df['low'], df['close'], lbp=14)
        df['CCI'] = ta.trend.cci(df['high'], df['low'], df['close'], window=20)
        df['ROC'] = ta.momentum.roc(df['close'], window=12)
        df['MFI'] = ta.volume.money_flow_index(df['high'], df['low'], df['close'], df['volume'], window=14)
        df['ADX'] = ta.trend.ADXIndicator(df['high'], df['low'], df['close'], window=14).adx()
        # التقلب
        bb = ta.volatility.BollingerBands(df['close'])
        df['BB_upper'] = bb.bollinger_hband()
        df['BB_middle'] = bb.bollinger_mavg()
        df['BB_lower'] = bb.bollinger_lband()
        df['ATR'] = ta.volatility.average_true_range(df['high'], df['low'], df['close'], window=14)
        # الحجم
        df['OBV'] = ta.volume.on_balance_volume(df['close'], df['volume'])
        df['CMF'] = ta.volume.chaikin_money_flow(df['high'], df['low'], df['close'], df['volume'], window=20)
        # إشارات شراء/بيع
        df['buy_signal'] = ((df['RSI'] < 30) & (df['close'] < df['BB_lower']) & (df['MACD_diff'] > 0)).astype(int)
        df['sell_signal'] = ((df['RSI'] > 70) & (df['close'] > df['BB_upper']) & (df['MACD_diff'] < 0)).astype(int)
        return df

    def fetch_multi_timeframe_data(self, symbol):
        """جلب بيانات 1h, 4h, 1d مع المؤشرات"""
        timeframes = ['1h', '4h', '1d']
        results = {}
        for tf in timeframes:
            try:
                ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe=tf, limit=150)
                if len(ohlcv) < 50:
                    continue
                df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                df.set_index('timestamp', inplace=True)
                df = self._calculate_all_indicators(df)
                results[tf] = df
            except Exception:
                continue
        return results

    def analyze_symbol(self, symbol):
        """تحليل عملة واحدة وإرجاع نتيجة نهائية"""
        tf_data = self.fetch_multi_timeframe_data(symbol)
        if not tf_data:
            return None
        analysis = {
            'symbol': symbol,
            'timeframes': {},
            'final_score': 50,
            'final_signal': 'NEUTRAL'
        }
        buy_cnt, sell_cnt = 0, 0
        for tf, df in tf_data.items():
            last = df.iloc[-1]
            analysis['timeframes'][tf] = {
                'RSI': round(last.get('RSI', 50), 2),
                'Trend': 'Bullish' if last.get('EMA_12', 0) > last.get('EMA_26', 0) else 'Bearish',
                'Buy': int(last.get('buy_signal', 0)),
                'Sell': int(last.get('sell_signal', 0)),
                'ADX': round(last.get('ADX', 20), 2)
            }
            buy_cnt += analysis['timeframes'][tf]['Buy']
            sell_cnt += analysis['timeframes'][tf]['Sell']
        if buy_cnt >= 2:
            analysis['final_signal'] = 'STRONG_BUY'
            analysis['final_score'] = 90
        elif buy_cnt == 1:
            analysis['final_signal'] = 'BUY'
            analysis['final_score'] = 75
        elif sell_cnt >= 2:
            analysis['final_signal'] = 'STRONG_SELL'
            analysis['final_score'] = 10
        elif sell_cnt == 1:
            analysis['final_signal'] = 'SELL'
            analysis['final_score'] = 25
        else:
            analysis['final_signal'] = 'NEUTRAL'
            analysis['final_score'] = 50
        # سعر الإغلاق الحالي
        first_tf = list(tf_data.keys())[0]
        analysis['price'] = tf_data[first_tf].iloc[-1]['close']
        return analysis

    def scan_all(self, limit=150):
        """مسح جميع العملات"""
        symbols = self.get_top_symbols(limit)
        results = []
        total = len(symbols)
        for i, sym in enumerate(symbols):
            print(f"\r[{i+1}/{total}] Scanning {sym}...", end="")
            res = self.analyze_symbol(sym)
            if res:
                results.append(res)
        print("\n✅ Scan completed.")
        return results
