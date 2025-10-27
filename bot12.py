import requests, base64, time, yfinance as yf, schedule, csv, os, json
from datetime import datetime

# 🔐 Konfiguracja
API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")

USE_DEMO = False
DRY_RUN = True

BASE_URL = "https://demo.trading212.com/api/v0" if USE_DEMO else "https://live.trading212.com/api/v0"
credentials = f"{API_KEY}:{API_SECRET}"
encoded = base64.b64encode(credentials.encode()).decode()
headers = {"Authorization": f"Basic {encoded}"}

PORTFOLIO_FILE = "bot_portfolio.json"
TRADE_FILE = "bot_trades.csv"

def get_current_price(symbol):
    stock = yf.Ticker(symbol)
    data = stock.history(period="1d")
    return round(data["Close"].iloc[-1], 2) if not data.empty else None

def get_instruments():
    time.sleep(2)
    r = requests.get(f"{BASE_URL}/equity/metadata/instruments", headers=headers)
    return r.json() if r.status_code == 200 else []

def find_ticker(symbol, instruments):
    for item in instruments:
        if symbol.upper() in item["name"] or symbol.upper() == item["shortName"]:
            if item["maxOpenQuantity"] > 0:
                print(f"🔎 Dopasowano {symbol} → {item['ticker']}")
                return item["ticker"]
            else:
                print(f"⚠️ Instrument {symbol} ({item['ticker']}) niedostępny.")
                return None
    print(f"❌ Nie znaleziono tickeru dla {symbol}")
    return None

def build_watchlist(symbols):
    instruments = get_instruments()
    return {
        s: {
            "ticker": find_ticker(s, instruments),
            "symbol": s,
            "buy": 400,
            "sell": 460,
            "qty": 0.05
        }
        for s in symbols if find_ticker(s, instruments)
    }

def place_market_order(ticker, quantity):
    if DRY_RUN:
        return f"🧪 TRYB TESTOWY: Symulacja zlecenia {ticker}, ilość: {quantity}"
    payload = {"ticker": ticker, "quantity": quantity, "type": "MARKET"}
    r = requests.post(f"{BASE_URL}/equity/order", headers=headers, json=payload)
    return f"✅ Zlecenie złożone: {ticker} {quantity} @ {r.status_code}" if r.status_code == 200 else f"❌ Błąd: {r.status_code}"

def log_action(msg):
    with open("bot_log.txt", "a", encoding="utf-8") as f:
        f.write(f"[{datetime.now()}] {msg}\n")

def log_trade(symbol, price, qty, action, profit):
    file_exists = os.path.isfile(TRADE_FILE)
    with open(TRADE_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["Data", "Symbol", "Cena", "Ilość", "Typ", "Zysk", "Tryb"])
        writer.writerow([
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            symbol,
            price,
            qty,
            action,
            round(profit, 2),
            "TEST" if DRY_RUN else "LIVE"
        ])

def load_portfolio():
    if os.path.isfile(PORTFOLIO_FILE):
        with open(PORTFOLIO_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"cash": 10000.0, "positions": {}, "profit": 0.0}

def save_portfolio(portfolio):
    with open(PORTFOLIO_FILE, "w", encoding="utf-8") as f:
        json.dump(portfolio, f, indent=2)

def evaluate_watchlist(watchlist):
    portfolio = load_portfolio()
    for name, asset in watchlist.items():
        price = get_current_price(asset["symbol"])
        if price is None:
            log_action(f"⚠️ Brak ceny dla {name}")
            continue

        qty = asset["qty"]
        ticker = asset["ticker"]
        pos = portfolio["positions"].get(name, {"qty": 0, "avg_price": 0})

        if price < asset["buy"]:
            cost = qty * price
            if portfolio["cash"] >= cost:
                new_qty = pos["qty"] + qty
                new_avg = ((pos["avg_price"] * pos["qty"]) + cost) / new_qty
                portfolio["cash"] -= cost
                portfolio["positions"][name] = {"qty": new_qty, "avg_price": new_avg}
                log_action(f"🟢 Kupuję {qty} {name} po {price}")
                log_trade(name, price, qty, "BUY", 0)
                result = place_market_order(ticker, qty)
                log_action(result)
            else:
                log_action(f"❌ Brak środków na zakup {name}")
        elif price > asset["sell"] and pos["qty"] >= qty:
            revenue = qty * price
            cost_basis = qty * pos["avg_price"]
            profit = revenue - cost_basis
            portfolio["cash"] += revenue
            portfolio["positions"][name]["qty"] -= qty
            portfolio["profit"] += profit
            log_action(f"🔴 Sprzedaję {qty} {name} po {price} (zysk: {round(profit,2)})")
            log_trade(name, price, -qty, "SELL", profit)
            result = place_market_order(ticker, -qty)
            log_action(result)
        else:
            log_action(f"⏸️ Cena {name} poza zakresem decyzyjnym.")
    save_portfolio(portfolio)

def run_bot():
    print("⏱️ Uruchamiam cykl decyzyjny...")
    symbols = ["TSLA", "AAPL", "AMCX"]
    watchlist = build_watchlist(symbols)
    evaluate_watchlist(watchlist)
    print("📁 Log zapisany w bot_log.txt, bot_trades.csv, bot_portfolio.json")

# 🔄 Harmonogram
schedule.every(5).minutes.do(run_bot)

# 🚀 Start
print("✅ Bot(12) uruchomiony — czekam na decyzje...")
run_bot()

while True:
    schedule.run_pending()
    print("⏳ Czekam na kolejną decyzję...")
    time.sleep(60)
