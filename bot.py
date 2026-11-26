import json
import math
from pathlib import Path
from datetime import datetime
import yfinance as yf

cfg = json.loads(Path("config.json").read_text())
assert cfg["mode"] == "paper"

file = Path("results.json")
state = json.loads(file.read_text()) if file.exists() else {
    "capital": cfg["initial_capital"],
    "days": [],
    "trades": []
}

stocks = [
    "NOKIA.HE", "NESTE.HE", "FORTUM.HE",
    "KNEBV.HE", "UPM.HE", "WRT1V.HE",
    "METSO.HE", "OUT1V.HE", "SAMPO.HE"
]

def run():
    if len(state["days"]) >= cfg["test_days"]:
        print("Test completed")
        return

    data = yf.download(
        stocks, period="5d", interval="5m",
        auto_adjust=True, progress=False
    )["Close"]

    data = data.tz_convert("Europe/Helsinki")
    today = datetime.now(data.index.tz).date()
    dates = sorted(set(data.index.date))
    dates = [d for d in dates if d < today]

    if not dates:
        return

    day = dates[-1]
    if str(day) in state["days"]:
        return

    bars = data[data.index.date == day].dropna(how="all")
    if len(bars) < 60:
        return

    capital = state["capital"]
    start = capital
    fee = cfg["commission_eur"]
    position = None

    for i in range(20, len(bars)):
        prices = bars.iloc[i]

        if position:
            stock, entry, qty = position
            price = prices[stock]
            if not math.isfinite(price):
                continue

            change = price / entry - 1
            if (
                change <= -cfg["stop_loss_pct"] / 100
                or change >= cfg["take_profit_pct"] / 100
                or i == len(bars) - 1
                or capital + qty * price - fee
                <= start * (1 - cfg["max_daily_loss_pct"] / 100)
            ):
                capital += qty * price - fee
                profit = qty * (price - entry) - 2 * fee
                state["trades"].append({
                    "date": str(day),
                    "stock": stock,
                    "buy": round(entry, 3),
                    "sell": round(price, 3),
                    "profit": round(profit, 2)
                })
                position = None
            continue

        if capital <= start * (
            1 - cfg["max_daily_loss_pct"] / 100
        ):
            break

        if i >= len(bars) - 6:
            continue

        history = bars.iloc[i-20:i]
        momentum = (
            history.iloc[-1] / history.iloc[-6] - 1
        ).dropna()

        for stock in momentum.sort_values(
            ascending=False
        ).index:
            price = prices[stock]
            if not math.isfinite(price) or price <= 0:
                continue
            if not math.isfinite(bars.iloc[-1][stock]):
                continue
            if momentum[stock] < 0.005:
                break
            if history[stock].iloc[-1] <= history[stock].mean():
                continue

            entry = price
            qty = int(
                (capital * cfg["max_position_pct"] / 100
                 - fee) / entry
            )
            if qty > 0:
                capital -= qty * entry + fee
                position = (stock, entry, qty)
                break

    if position:
        raise RuntimeError("Position not closed")

    state["capital"] = round(capital, 2)
    state["days"].append(str(day))
    file.write_text(json.dumps(state, indent=2))
    print("Capital:", state["capital"], "EUR")

run()
