import requests
import pandas as pd
import time
from datetime import datetime, date, timedelta
import csv
import os
import urllib.parse
import math

# ==============================================================================
# MODULE 0: AUTHENTICATION
# ==============================================================================
class Credentials:
    # Telegram Config
    TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
    TELEGRAM_CHAT_ID   = os.environ.get('TELEGRAM_CHAT_ID', '')

    @staticmethod
    def send_telegram(msg):
        if not Credentials.TELEGRAM_BOT_TOKEN or not Credentials.TELEGRAM_CHAT_ID: return
        url = f"https://api.telegram.org/bot{Credentials.TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {"chat_id": Credentials.TELEGRAM_CHAT_ID, "text": msg}
        try:
            requests.post(url, json=payload, timeout=3)
        except: pass

# ==============================================================================
# MODULE 1: CONFIGURATION
# ==============================================================================
class Config: 
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    TOKEN_FILE = os.path.join(SCRIPT_DIR, "access_token.txt")
    try:
        with open(TOKEN_FILE, "r") as f:
            ACCESS_TOKEN = f.read().strip()
    except Exception as e:
        print(f"⚠️ Could not read {TOKEN_FILE}. Error: {e}")
        ACCESS_TOKEN = ''

    API_VERSION  = '2.0'
    BASE_URL     = "https://api.upstox.com/v2"
    BASE_URL_V3  = "https://api.upstox.com/v3"
    
    DRY_RUN      = True   # True = Paper Trading, False = Real Money
    
    # --- STRATEGY SETTINGS (Multi-Stock ORB) ---
    CAPITAL_PER_STOCK = 500000  # 5 Lakh Rupees per stock
    
    # Target Trading Symbols
    NIFTY_50_SYMBOLS = [
        "ADANIENT", "TRENT", "TATASTEEL", "RELIANCE", "SBIN",
        "BAJFINANCE", "M&M", "LT", "HDFCBANK", "ICICIBANK"
    ]

    INSTRUMENT_KEYS = {
        "ADANIENT": "NSE_EQ|INE423A01024",
        "TRENT": "NSE_EQ|INE849A01020",
        "TATASTEEL": "NSE_EQ|INE081A01020",
        "RELIANCE": "NSE_EQ|INE002A01018",
        "SBIN": "NSE_EQ|INE062A01020",
        "BAJFINANCE": "NSE_EQ|INE296A01032",
        "M&M": "NSE_EQ|INE101A01026",
        "LT": "NSE_EQ|INE018A01030",
        "HDFCBANK": "NSE_EQ|INE040A01034",
        "ICICIBANK": "NSE_EQ|INE090A01021"
    }

    # --- SECTORAL INDEX MAPPING ---
    INDICES = {
        "Nifty 50": "NSE_INDEX|Nifty 50",
        "Bank Nifty": "NSE_INDEX|Nifty Bank",
        "Nifty Auto": "NSE_INDEX|Nifty Auto",
        "FinNifty": "NSE_INDEX|Nifty Fin Service",
        "Nifty Metal": "NSE_INDEX|Nifty Metal"
    }

    STOCK_INDEX_MAP = {
        "ADANIENT": "Nifty 50",
        "TRENT": "Nifty 50",
        "RELIANCE": "Nifty 50",
        "LT": "Nifty 50",
        "HDFCBANK": "Bank Nifty",
        "ICICIBANK": "Bank Nifty",
        "SBIN": "Bank Nifty",
        "TATASTEEL": "Nifty Metal",
        "BAJFINANCE": "FinNifty",
        "M&M": "Nifty Auto"
    }

    # --- RISK MANAGEMENT (Profit Based in INR) ---
    LADDER_TABLE = [
        {'trigger': -999999, 'lock': -3000}, # Initial SL (Active immediately)
        {'trigger': 2000, 'lock': 1000},
        {'trigger': 3000, 'lock': 2000},
        {'trigger': 4000, 'lock': 3000},
        {'trigger': 5000, 'lock': 4000},
        {'trigger': 6000, 'lock': 5000},
        {'trigger': 7000, 'lock': 6000},
        {'trigger': 8000, 'lock': 7000},
        {'trigger': 10000, 'lock': 8000},
        {'trigger': 12000, 'lock': 10000},
        {'trigger': 14000, 'lock': 12000},
        {'trigger': 16000, 'lock': 14000},
        {'trigger': 18000, 'lock': 16000},
        {'trigger': 20000, 'lock': 18000},
        {'trigger': 23000, 'lock': 20000},
        {'trigger': 26000, 'lock': 23000},
        {'trigger': 30000, 'lock': 26000},
        {'trigger': 35000, 'lock': 30000}
    ]
    
    HEADERS = {
        'Content-Type': 'application/json',
        'accept': 'application/json',
        'Api-Version': API_VERSION,
        'Authorization': f'Bearer {ACCESS_TOKEN}'
    }

    @classmethod
    def refresh_token(cls):
        try:
            with open(cls.TOKEN_FILE, "r") as f:
                token = f.read().strip()
                if token:
                    cls.ACCESS_TOKEN = token
                    cls.HEADERS['Authorization'] = f'Bearer {cls.ACCESS_TOKEN}'
                    print(f"🔄 Access Token refreshed at {datetime.now().strftime('%H:%M:%S')}")
        except Exception as e:
            print(f"⚠️ Error refreshing token: {e}")


    @classmethod
    def api_get_with_retry(cls, *args, **kwargs):
        try:
            import requests
            response = requests.get(*args, **kwargs)
            if response.status_code == 401:
                print("⚠️ 401 Unauthorized. Attempting to refresh token from file and retry...")
                cls.refresh_token()
                if 'headers' in kwargs:
                    kwargs['headers']['Authorization'] = f'Bearer {cls.ACCESS_TOKEN}'
                response = requests.get(*args, **kwargs)
            return response
        except Exception as e:
            print(f"⚠️ Network Error: {e}")
            class DummyResponse:
                status_code = 500
                text = str(e)
                def json(self): return {}
            return DummyResponse()

# ==============================================================================
# MODULE: INSTRUMENT MANAGER
# ==============================================================================
class InstrumentManager:
    @staticmethod
    def fetch_nifty50_instruments():
        print(f"⏳ Loading Nifty 50 Instruments from Config...")
        instruments = []
        for sym in Config.NIFTY_50_SYMBOLS:
            key = Config.INSTRUMENT_KEYS.get(sym)
            if key:
                instruments.append({'symbol': sym, 'instrument_key': key})
        print(f"✅ Loaded {len(instruments)} Nifty 50 Instruments.")
        return instruments

# ==============================================================================
# MODULE: VIRTUAL TRADEBOOK
# ==============================================================================
class TradeBook:
    FILE_NAME = "tradebook8.csv"
    HEADERS = ["Entry_Time", "Symbol", "Token", "Type", "Qty", "Entry_Price", "Status", "Exit_Price", "Exit_Time", "PnL"]

    def __init__(self):
        if not os.path.exists(self.FILE_NAME):
            with open(self.FILE_NAME, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(self.HEADERS)

    def _get_ltp(self, instrument_key):
        url = f"{Config.BASE_URL}/market-quote/ltp"
        params = {'instrument_key': instrument_key}
        try:
            resp = Config.api_get_with_retry(url, headers=Config.HEADERS, params=params, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                for k, v in data['data'].items():
                    return v['last_price']
        except: pass
        return 0.0

    def add_position(self, symbol, token, qty, txn_type):
        entry_price = self._get_ltp(token)
        if entry_price == 0.0:
            print(f"❌ [PAPER] Error fetching LTP for {symbol}. Entry aborted.")
            return
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        row = [timestamp, symbol, token, txn_type, qty, entry_price, "OPEN", 0.0, "", 0.0]
        
        with open(self.FILE_NAME, 'a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(row)
            
        print(f"📝 [PAPER TRADE] Opened {txn_type} {symbol} @ {entry_price} (Qty: {qty})")

    def close_position(self, token, qty):
        exit_price = self._get_ltp(token)
        exit_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        rows = []
        updated = False
        
        with open(self.FILE_NAME, 'r') as f:
            reader = csv.reader(f)
            rows = list(reader)
            
        for i in range(1, len(rows)): 
            row = rows[i]
            if row[2] == token and row[6] == "OPEN":
                entry_price = float(row[5])
                txn_type = row[3]

                # Graceful Fallback: If API fails, use last known LTP (index 7) or entry price
                if exit_price == 0.0:
                    last_known_ltp = float(row[7]) if len(row) > 7 and row[7] else 0.0
                    exit_price = last_known_ltp if last_known_ltp > 0 else entry_price
                    print(f"⚠️ [PAPER] LTP fetch failed for {row[1]}. Forced exit @ {exit_price}")
                
                # Long/Short PnL calculation
                if txn_type == "BUY":
                    pnl = (exit_price - entry_price) * int(row[4])
                else:
                    pnl = (entry_price - exit_price) * int(row[4])
                
                rows[i][6] = "CLOSED"
                rows[i][7] = exit_price
                rows[i][8] = exit_time
                rows[i][9] = round(pnl, 2)
                updated = True
                print(f"📝 [PAPER TRADE] Closed {row[1]} @ {exit_price} | PnL: {round(pnl, 2)}")
                break 
        
        if updated:
            with open(self.FILE_NAME, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerows(rows)

    def update_ltp(self, token, ltp, pnl):
        if not os.path.exists(self.FILE_NAME): return
        rows = []
        updated = False
        with open(self.FILE_NAME, 'r') as f:
            reader = csv.reader(f)
            rows = list(reader)
        for i in range(1, len(rows)): 
            row = rows[i]
            if row[2] == token and row[6] == "OPEN":
                rows[i][7] = ltp
                rows[i][9] = round(pnl, 2)
                updated = True
                break 
        if updated:
            with open(self.FILE_NAME, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerows(rows)

    def get_realized_pnl(self):
        total = 0.0
        if not os.path.exists(self.FILE_NAME): return total
        today_str = datetime.now().strftime("%Y-%m-%d")
        with open(self.FILE_NAME, 'r') as f:
            reader = csv.reader(f)
            try:
                next(reader)
                for row in reader:
                    if len(row) > 9 and row[6] == "CLOSED" and row[8].startswith(today_str):
                        total += float(row[9])
            except StopIteration: pass
        return total

    def get_virtual_positions(self):
        virtual_positions = []
        if not os.path.exists(self.FILE_NAME): return []
        with open(self.FILE_NAME, 'r') as f:
            reader = csv.reader(f)
            try:
                next(reader)
                for row in reader:
                    if len(row) > 6 and row[6] == "OPEN":
                        token = row[2]
                        ltp = self._get_ltp(token)
                        if ltp == 0: ltp = float(row[5])
                        pos_dict = {
                            'trading_symbol': row[1], 'instrument_token': row[2],
                            'quantity': int(row[4]), 'buy_price': float(row[5]),
                            'last_price': ltp, 'transaction_type': row[3]
                        }
                        virtual_positions.append(pos_dict)
            except StopIteration: pass
        return virtual_positions

# ==============================================================================
# MODULE 2: POSITION MANAGER
# ==============================================================================
class PositionManager:
    def __init__(self):
        self.sl_map = {} 
        self.paper_book = TradeBook()
        
    def log(self, msg):
        formatted_msg = f"[{datetime.now().strftime('%H:%M:%S')}] [MANAGER] {msg}"
        print(formatted_msg)
        Credentials.send_telegram(formatted_msg)

    def get_positions(self):
        if Config.DRY_RUN:
            return self.paper_book.get_virtual_positions()
        
        url = f"{Config.BASE_URL}/portfolio/short-term-positions"
        try:
            resp = Config.api_get_with_retry(url, headers=Config.HEADERS, timeout=5)
            if resp.status_code == 200:
                all_pos = resp.json()['data']
                active = [p for p in all_pos if int(p['quantity']) != 0]
                return active
        except Exception as e:
            self.log(f"❌ Error fetching positions: {e}")
        return []

    def get_realized_pnl(self):
        if Config.DRY_RUN:
            return self.paper_book.get_realized_pnl()
        
        url = f"{Config.BASE_URL}/portfolio/short-term-positions"
        try:
            resp = Config.api_get_with_retry(url, headers=Config.HEADERS, timeout=5)
            if resp.status_code == 200:
                return sum(float(p['realized_profit']) for p in resp.json()['data'])
        except: pass
        return 0.0

    def check_and_trail(self):
        active_positions = self.get_positions()
        if not active_positions: return
        total_running_pnl = 0.0

        for pos in active_positions:
            symbol = pos['trading_symbol']
            key    = pos['instrument_token']
            qty    = int(pos['quantity'])
            buy_avg = float(pos['buy_price'])
            ltp    = float(pos['last_price'])
            
            # PnL Logic for Long/Short 
            if Config.DRY_RUN:
                txn_type = pos.get('transaction_type', 'BUY')
                if txn_type == "BUY":
                    current_profit_inr = (ltp - buy_avg) * qty
                else:
                    current_profit_inr = (buy_avg - ltp) * qty
            else:
                # Real Upstox API: quantity is negative for short positions
                if qty > 0:
                    current_profit_inr = (ltp - buy_avg) * qty
                else:
                    current_profit_inr = (buy_avg - ltp) * abs(qty)
            
            total_running_pnl += current_profit_inr
            # Log Live Status
            self.log(f"📊 {symbol} | Entry: {buy_avg:.2f} | LTP: {ltp:.2f} | PnL: ₹{current_profit_inr:.2f}")
            if Config.DRY_RUN:
                self.paper_book.update_ltp(key, ltp, current_profit_inr)

            # ---------------------------------------------------------
            # LADDER TRAILING LOGIC (Profit Based)
            # ---------------------------------------------------------
            current_locked_profit = self.sl_map.get(key, -999999)
            
            for step in Config.LADDER_TABLE:
                if current_profit_inr >= step['trigger']:
                    if step['lock'] > current_locked_profit:
                        self.sl_map[key] = step['lock']
                        self.log(f"🪜 LADDER CLIMBED for {symbol}! Locked Profit: ₹{step['lock']}")
                        current_locked_profit = step['lock']

            if current_locked_profit > -999999 and current_profit_inr < current_locked_profit:
                self.log(f"📉 TRAILING SL HIT for {symbol}! PnL: ₹{current_profit_inr:.2f} < Locked ₹{current_locked_profit}. Exiting...")
                self.square_off(key, qty, pos, "TrailingSL")
                
        realized = self.get_realized_pnl()
        combined = total_running_pnl + realized
        self.log(f"💰 TOTAL DAY PnL: ₹{combined:.2f} (Running: {total_running_pnl:.2f} + Booked: {realized:.2f})")

    def square_off(self, instrument_key, quantity, pos_data, tag="EXIT"):
        if Config.DRY_RUN:
            self.log(f"⚠️ [PAPER] Triggering Exit for {tag}")
            self.paper_book.close_position(instrument_key, quantity)
            if instrument_key in self.sl_map:
                del self.sl_map[instrument_key]
                self.log(f"🔄 SL Ladder cleared for {instrument_key}")
            return

        # Real API Exit: To close a BUY, we SELL. To close a SELL, we BUY.
        if quantity > 0:
            exit_txn_type = "SELL"
        else:
            exit_txn_type = "BUY"

        url = f"{Config.BASE_URL}/order/place"
        payload = {
            "quantity": abs(quantity), "product": "D", "validity": "DAY", "price": 0,
            "tag": tag, "instrument_token": instrument_key, "order_type": "MARKET", 
            "transaction_type": exit_txn_type, "disclosed_quantity": 0, "trigger_price": 0, "is_amo": False
        }
        try:
            requests.post(url, headers=Config.HEADERS, json=payload)
            self.log(f"📤 Square Off Order Placed for {tag}")
            if instrument_key in self.sl_map:
                del self.sl_map[instrument_key]
                self.log(f"🔄 SL Ladder cleared for {instrument_key}")
        except Exception as e:
            self.log(f"❌ Square Off Failed: {e}")

    def close_all_positions(self):
        self.log("🚨 Closing ALL positions...")
        active = self.get_positions()
        for pos in active:
            self.square_off(pos['instrument_token'], int(pos['quantity']), pos, "EOD_Exit")

# ==============================================================================
# MODULE 3: STRATEGY ENGINE (Multi-Stock ORB Logic)
# ==============================================================================
class StrategyEngine:
    def __init__(self):
        self.instruments = InstrumentManager.fetch_nifty50_instruments()
        self.manager = PositionManager()
        self.paper_book = TradeBook()
        
        # Dictionary to store ORB state per stock
        self.stock_states = {}
        self.index_states = {} # Caches the calculated Tone for indices
        self.sector_summary_logged = False

    def log(self, msg):
        formatted_msg = f"[{datetime.now().strftime('%H:%M:%S')}] [ENGINE] {msg}"
        print(formatted_msg)
        Credentials.send_telegram(formatted_msg)

    def fetch_candles(self, instrument_key):
        """Fetches today's 5-minute candles for ORB parsing."""
        encoded_key = urllib.parse.quote(instrument_key)
        url_intra = f"{Config.BASE_URL_V3}/historical-candle/intraday/{encoded_key}/minutes/5"
        
        try:
            resp = Config.api_get_with_retry(url_intra, headers=Config.HEADERS, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                if 'data' in data and 'candles' in data['data']:
                    candles = data['data']['candles']
                    df = pd.DataFrame(candles, columns=['Ts', 'Open', 'High', 'Low', 'Close', 'Vol', 'OI'])
                    df['Ts'] = pd.to_datetime(df['Ts'])
                    if df['Ts'].dt.tz is not None: df['Ts'] = df['Ts'].dt.tz_localize(None)
                    df.set_index('Ts', inplace=True)
                    df.sort_index(inplace=True)
                    return df
        except Exception as e:
            pass # Suppress standard fetching errors to keep logs clean during loops
        return None

    def calculate_index_tone(self, index_name):
        """Calculates Tone of Day for a Sectoral Index from 09:15 to 09:30 candles."""
        index_key = Config.INDICES.get(index_name)
        if not index_key: return False

        df = self.fetch_candles(index_key)
        if df is None or df.empty: return False

        now = datetime.now()

        today = now.date()
        df_today = df[df.index.date == today]

        ts_915 = pd.Timestamp(datetime.combine(today, datetime.strptime("09:15", "%H:%M").time()))
        ts_920 = pd.Timestamp(datetime.combine(today, datetime.strptime("09:20", "%H:%M").time()))
        ts_925 = pd.Timestamp(datetime.combine(today, datetime.strptime("09:25", "%H:%M").time()))

        if ts_915 in df_today.index and ts_920 in df_today.index and ts_925 in df_today.index:
            c1 = df_today.loc[ts_915]
            c2 = df_today.loc[ts_920]
            c3 = df_today.loc[ts_925]

            red_count = sum([c1['Close'] < c1['Open'], c2['Close'] < c2['Open'], c3['Close'] < c3['Open']])
            green_count = sum([c1['Close'] > c1['Open'], c2['Close'] > c2['Open'], c3['Close'] > c3['Open']])

            if red_count >= 2:
                tone = "BEARISH"
            elif green_count >= 2:
                tone = "BULLISH"
            else:
                tone = "NEUTRAL"

            self.index_states[index_name] = tone
            self.log(f"🧭 Sector Index [{index_name}] Tone Calculated: {tone}")
            return True
            
        return False

    def calculate_orb(self, df, state, symbol):
        """Calculates ORB boundaries from stock candles and assigns mapped Sector Tone."""
        index_name = Config.STOCK_INDEX_MAP.get(symbol, "Nifty 50")
        if index_name not in self.index_states:
            if not self.calculate_index_tone(index_name):
                return # Wait until the index 09:30 candles are available

        now = datetime.now()

        today = now.date()
        df_today = df[df.index.date == today]

        ts_915 = pd.Timestamp(datetime.combine(today, datetime.strptime("09:15", "%H:%M").time()))
        ts_920 = pd.Timestamp(datetime.combine(today, datetime.strptime("09:20", "%H:%M").time()))
        ts_925 = pd.Timestamp(datetime.combine(today, datetime.strptime("09:25", "%H:%M").time()))

        if ts_915 in df_today.index and ts_920 in df_today.index and ts_925 in df_today.index:
            c1 = df_today.loc[ts_915]
            c2 = df_today.loc[ts_920]
            c3 = df_today.loc[ts_925]

            state['orb_high'] = max(c1['High'], c2['High'], c3['High'])
            state['orb_low']  = min(c1['Low'], c2['Low'], c3['Low'])
            state['orb_mid']  = (state['orb_high'] + state['orb_low']) / 2.0

            # Assign Tone directly from the Sectoral Index
            state['tone'] = self.index_states[index_name]

            self.log(f"🌅 {symbol} ORB: High={state['orb_high']:.2f}, Low={state['orb_low']:.2f}, Mid={state['orb_mid']:.2f} | Tone: {state['tone']} (from {index_name})")
            state['orb_calculated'] = True

    def analyze_market(self):
        all_active_positions = self.manager.get_positions()
        
        for instr in self.instruments:
            symbol = instr['symbol']
            key = instr['instrument_key']
            
            if key not in self.stock_states:
                self.stock_states[key] = {
                    'orb_high': 0.0, 'orb_low': 0.0, 'orb_mid': 0.0,
                    'tone': "NEUTRAL", 'orb_calculated': False,
                    'last_processed_candle_time': None
                }
            
            state = self.stock_states[key]
            
            df = self.fetch_candles(key)
            if df is None or df.empty: continue
            
            # 1. Calculate ORB if not done
            if not state['orb_calculated']:
                self.calculate_orb(df, state, symbol)
                if not state['orb_calculated']:
                    continue # Waiting for 9:30 candles
            
            if state['tone'] == "NEUTRAL":
                continue # Don't trade this stock today
                
            # 2. Get Current Market Data
            current_candle = df.iloc[-1]
            now = datetime.now()

            
            if now >= current_candle.name + timedelta(minutes=5):
                confirmed_candle = df.iloc[-1]
            else:
                if len(df) > 1: confirmed_candle = df.iloc[-2]
                else: continue
                
            live_ltp = current_candle['Close']
            
            # 3. Mid Line Exit & Position Check
            active_pos_for_stock = [p for p in all_active_positions if p['instrument_token'] == key]
            if active_pos_for_stock:
                pos = active_pos_for_stock[0]
                qty = int(pos['quantity'])
                is_long = pos.get('transaction_type', 'BUY') == 'BUY' if Config.DRY_RUN else qty > 0
                
                if is_long and live_ltp < state['orb_mid']:
                    self.log(f"🚨 {symbol} Mid Line SL Hit ({live_ltp:.2f} < {state['orb_mid']:.2f}). Exiting Long.")
                    self.manager.square_off(key, qty, pos, "MidLine_Exit")
                elif not is_long and live_ltp > state['orb_mid']:
                    self.log(f"🚨 {symbol} Mid Line SL Hit ({live_ltp:.2f} > {state['orb_mid']:.2f}). Exiting Short.")
                    self.manager.square_off(key, qty, pos, "MidLine_Exit")
                
                continue # Already in a trade, skip entry logic

            self.log(f"Live {symbol}: {live_ltp:.2f} | ORB: {state['orb_high']:.2f}/{state['orb_low']:.2f} | Mid: {state['orb_mid']:.2f} | Tone: {state['tone']}")

            # 4. Entry Logic
            if state['last_processed_candle_time'] != confirmed_candle.name:
                # --- New Breakout Logic ---
                # A valid breakout candle must cross the ORB boundary, not form entirely outside it.
                # Bullish: Must close > ORB High, but its Open must have been <= ORB High.
                is_bullish_breakout = (
                    state['tone'] == "BULLISH" and
                    confirmed_candle['Close'] > state['orb_high'] and
                    confirmed_candle['Open'] <= state['orb_high']
                )

                # Bearish: Must close < ORB Low, but its Open must have been >= ORB Low.
                is_bearish_breakout = (
                    state['tone'] == "BEARISH" and
                    confirmed_candle['Close'] < state['orb_low'] and
                    confirmed_candle['Open'] >= state['orb_low']
                )
                
                if is_bullish_breakout:
                    self.execute_entry("BUY", key, symbol, live_ltp)
                    state['last_processed_candle_time'] = confirmed_candle.name
                elif is_bearish_breakout:
                    self.execute_entry("SELL", key, symbol, live_ltp)
                    state['last_processed_candle_time'] = confirmed_candle.name

            # Rate limiting protection
            time.sleep(0.1) 
            
        # Output Sector Tones Summary once all are calculated
        if not getattr(self, 'sector_summary_logged', False):
            required_indices = set(Config.STOCK_INDEX_MAP.values())
            if all(idx in self.index_states for idx in required_indices):
                summary_msg = "🧭 SECTOR TONES SUMMARY: " + " | ".join([f"{idx}: {self.index_states[idx]}" for idx in required_indices])
                self.log(summary_msg)
                self.sector_summary_logged = True

    def execute_entry(self, txn_type, key, symbol, spot_price):
        qty = math.floor(Config.CAPITAL_PER_STOCK / spot_price)
        if qty <= 0:
            self.log(f"⚠️ Cannot trade {symbol}. Price ({spot_price:.2f}) too high for Capital ({Config.CAPITAL_PER_STOCK}).")
            return
            
        self.log(f"🚀 {symbol} {txn_type} Breakout Confirmed! Executing Entry. Qty: {qty}")
        tag = f"EQ_{symbol}_{txn_type}"
        
        if Config.DRY_RUN:
            self.paper_book.add_position(symbol, key, qty, txn_type)
            return
        
        url = 'https://api-hft.upstox.com/v3/order/place'
        payload = {
            "quantity": qty, "product": "D", "validity": "DAY", "price": 0,
            "tag": tag, "instrument_token": key, "order_type": "MARKET", 
            "transaction_type": txn_type, "disclosed_quantity": 0, 
            "trigger_price": 0, "is_amo": False, 'slice': False
        }
        try:
            requests.post(url, headers=Config.HEADERS, json=payload)
            self.log(f"✅ Order Placed: {tag}")
        except Exception as e: self.log(f"❌ Order Failed: {e}")

    def wait_for_next_tick(self):
        now = datetime.now()

        minutes_to_next = 5 - (now.minute % 5)
        seconds_to_sleep = (minutes_to_next * 60) - now.second
        
        if seconds_to_sleep <= 0: seconds_to_sleep = 1
        
        next_run = now + timedelta(seconds=seconds_to_sleep)
        self.log(f"💤 Sleeping {int(seconds_to_sleep)}s until {next_run.strftime('%H:%M:%S')}...")
        time.sleep(seconds_to_sleep)

    
    def run(self):
        self.log("🚀 Bot Engine Started...")

        holiday_checked_today = False
        holiday_ltp_1 = None
        last_date_processed = None
        
        while True:
            now = datetime.now()

            if last_date_processed != now.date():
                holiday_checked_today = False
                holiday_ltp_1 = None
                last_date_processed = now.date()

            # Refresh Token at 9:00 AM strictly
            if now.hour == 9 and now.minute == 0:
                Config.refresh_token()
                time.sleep(60)


            # Reset daily state
            if getattr(self, 'current_trading_day', None) != now.date():
                self.log(f"🔄 New day detected. Resetting states for {now.date()}")
                self.stock_states = {}
                self.index_states = {}
                self.manager.sl_map = {}
                self.sector_summary_logged = False
                self.current_trading_day = now.date()

            # Refresh Token at 9:00 AM

            # --- WEEKEND CHECK ---
            if now.weekday() >= 5: 
                self.log(f"📅 Today is {now.strftime('%A')} (Weekend). Market Closed.")
                next_9am = now.replace(hour=8, minute=59, second=50, microsecond=0)
                if now >= next_9am: next_9am += timedelta(days=1)
                seconds_to_sleep = (next_9am - now).total_seconds()
                if seconds_to_sleep > 0: time.sleep(seconds_to_sleep)
                continue

            market_open = now.replace(hour=9, minute=16, second=0, microsecond=0)
            market_close = now.replace(hour=15, minute=31, second=0, microsecond=0)

            if market_open <= now <= market_close:
                # --- HOLIDAY CHECKER LOGIC ---
                if not holiday_checked_today:
                    if holiday_ltp_1 is None:
                        holiday_ltp_1 = self.paper_book._get_ltp('NSE_INDEX|Nifty 50')
                        print(f"🌅 Holiday Check - Snapshot 1 ({now.strftime('%H:%M')}): {holiday_ltp_1:.2f}")
                    else:
                        holiday_ltp_2 = self.paper_book._get_ltp('NSE_INDEX|Nifty 50')
                        print(f"🌅 Holiday Check - Snapshot 2 ({now.strftime('%H:%M')}): {holiday_ltp_2:.2f}")
                        if round(holiday_ltp_1, 2) == round(holiday_ltp_2, 2):
                            msg = "🚨 MARKET IS NOT MOVING! (Holiday Detected). Bot going to sleep."
                            self.log(msg)
                            holiday_checked_today = True
                            next_run = (now + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
                            seconds_to_sleep = (next_run - now).total_seconds()
                            if seconds_to_sleep > 0: time.sleep(seconds_to_sleep)
                            continue
                        else:
                            print("📈 Market is moving normally.")
                            holiday_checked_today = True


                self.log(f"🔔 Tick at {now.strftime('%H:%M:%S')}. Market is OPEN.")

                if self.manager.get_positions():
                    self.manager.check_and_trail()
                
                # Auto Square-off at 3:25 PM
                if now.hour == 15 and now.minute >= 25:
                    self.log("⏰ 3:25 PM: Auto-squaring off all positions.")
                    self.manager.close_all_positions()
                    
                    market_close_sleep = now.replace(hour=15, minute=31, second=0, microsecond=0)
                    seconds_to_sleep = (market_close_sleep - now).total_seconds()
                    if seconds_to_sleep > 0:
                        self.log(f"💤 Sleeping until market close at {market_close_sleep.strftime('%H:%M:%S')}...")
                        time.sleep(seconds_to_sleep)
                    continue

                # Analyze Market (Entry/Reversal)
                if now.hour < 15 or (now.hour == 15 and now.minute < 25):
                    self.analyze_market()
                else:
                    self.log("⏸️ Trading paused after 3:25 PM.")

                self.wait_for_next_tick()
            else:
                if now < market_open:
                    next_run = market_open
                    self.log(f"🌙 Market not open yet. Sleeping until {next_run.strftime('%H:%M:%S')}...")
                else:
                    next_run = (now + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
                    self.log(f"🌙 Market Closed. Sleeping until {next_run.strftime('%Y-%m-%d %H:%M:%S')}...")
                
                seconds_to_sleep = (next_run - now).total_seconds()
                if seconds_to_sleep > 0:
                    time.sleep(seconds_to_sleep)
                else:
                    time.sleep(60)

# ==============================================================================
# MAIN EXECUTION
# ==============================================================================
def check_connection():
    url = "https://api.upstox.com/v2/user/profile"
    try:
        response = Config.api_get_with_retry(url, headers=Config.HEADERS, timeout=5)
        if response.status_code == 200:
            print(f"✅ Connected: {response.json()['data']['user_name']}")
            return True
        else:
            print(f"❌ Connection Failed. Status: {response.status_code}")
    except Exception as e:
        print(f"❌ Connection Error: {e}")
    return False

if __name__ == "__main__":
    print("⏳ Connecting to Upstox...")
    if check_connection():
        bot = StrategyEngine()
        bot.run()
