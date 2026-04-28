import asyncio
import random
import time
import threading
from datetime import datetime, timedelta
from pyquotex.stable_api import Quotex

EMAIL = "wagife9306@mugstock.com"
PASSWORD = "latchi23@@"
ASSETS = ["NZDCHF_otc", "USDINR_otc", "USDBDT_otc", "USDARS_otc", "USDPKR_otc"]
BASE_AMOUNT = 1.0

class BotState:
    def __init__(self):
        self.running = False
        self.balance = 0
        self.wins = 0
        self.losses = 0
        self.signals = []
        self.status = "متوقف"

    def reset_stats(self):
        self.wins = 0
        self.losses = 0
        self.signals = []
        self.status = "تم إعادة الضبط"

    def to_dict(self):
        return {
            "running": self.running,
            "balance": self.balance,
            "wins": self.wins,
            "losses": self.losses,
            "signals": self.signals[-20:],
            "status": self.status,
        }

state = BotState()
_loop = None
_task = None

async def decide_direction(client, asset):
    try:
        call_score = 0
        put_score = 0
        candles = await client.get_candles(asset, int(time.time()), 5, 60)
        if candles:
            ups = sum(1 for c in candles if c["close"] > c["open"])
            downs = sum(1 for c in candles if c["close"] < c["open"])
            if ups >= 3: call_score += 3
            if downs >= 3: put_score += 3
            last_close = candles[-1]["close"]
        else:
            last_close = 0

        rsi = await client.calculate_indicator(asset, "RSI", {"period": 14}, history_size=3600, timeframe=60)
        if rsi and "current" in rsi and rsi["current"]:
            if float(rsi["current"]) < 35: call_score += 2
            elif float(rsi["current"]) > 65: put_score += 2

        if call_score > put_score: return "call"
        elif put_score > call_score: return "put"
        else: return random.choice(["call", "put"])
    except:
        return random.choice(["call", "put"])

async def bot_loop():
    global state
    client = Quotex(email=EMAIL, password=PASSWORD, lang="en")
    client.set_account_mode("PRACTICE")
    
    connected, reason = await client.connect()
    if not connected:
        state.status = f"فشل الاتصال: {reason}"
        state.running = False
        return

    await client.change_account("PRACTICE")
    balance = await client.get_balance()
    state.balance = balance
    state.status = "يعمل الآن"

    while state.running:
        try:
            asset = random.choice(ASSETS)
            direction = await decide_direction(client, asset)
            now = datetime.now()
            signal_time = now.strftime("%H:%M")

            signal = {
                "asset": asset.upper(),
                "direction": direction.upper(),
                "time": signal_time,
                "entry": None,
                "result": "pending",
            }
            state.signals.insert(0, signal)

            next_minute = (now + timedelta(minutes=1)).replace(second=0, microsecond=0)
            wait = (next_minute - datetime.now()).total_seconds() - 2
            if wait > 0:
                await asyncio.sleep(wait)

            if not state.running:
                break

            success, order_info = await client.buy(BASE_AMOUNT, asset, direction, 60)
            if not success or "id" not in order_info:
                signal["result"] = "fail"
                await asyncio.sleep(10)
                continue

            signal["entry"] = order_info.get("openPrice", None)

            await asyncio.sleep(75)

            profit, result_status = await client.check_win(order_info["id"])
            signal["result"] = result_status
            signal["profit"] = profit

            if result_status == "win":
                state.wins += 1
            elif result_status == "loss":
                state.losses += 1

            new_balance = await client.get_balance()
            state.balance = new_balance

            await asyncio.sleep(5)

        except Exception as e:
            state.status = f"خطأ: {str(e)}"
            await asyncio.sleep(10)

    state.status = "متوقف"
    await client.close()

def _run_loop(loop):
    asyncio.set_event_loop(loop)
    loop.run_forever()

def start_bot():
    global _loop, _task, state
    if state.running:
        return False
    state.running = True
    state.status = "جارٍ الاتصال..."

    if _loop is None or not _loop.is_running():
        _loop = asyncio.new_event_loop()
        t = threading.Thread(target=_run_loop, args=(_loop,), daemon=True)
        t.start()

    _task = asyncio.run_coroutine_threadsafe(bot_loop(), _loop)
    return True

def stop_bot():
    global state
    if not state.running:
        return False
    state.running = False
    state.status = "جارٍ الإيقاف..."
    return True