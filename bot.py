import asyncio
import os
import random
import threading
import time
from datetime import datetime, timedelta

import pytz
from pyquotex.stable_api import Quotex
from telethon import TelegramClient

EMAIL = os.environ.get("QUOTEX_EMAIL", "wagife9306@mugstock.com")
PASSWORD = os.environ.get("QUOTEX_PASSWORD", "latchi23@@")

API_ID = int(os.environ.get("TELEGRAM_API_ID", "33567199"))
API_HASH = os.environ.get("TELEGRAM_API_HASH", "3fdd30ef25043c39d8cc897d6251b8f1")
CHANNEL = os.environ.get("TELEGRAM_CHANNEL", "@latchidz0")

ASSETS = ["NZDCHF_otc", "USDINR_otc", "USDBDT_otc", "USDARS_otc", "USDPKR_otc"]
BASE_AMOUNT = float(os.environ.get("BASE_AMOUNT", "1.0"))

ALGIERS = pytz.timezone("Africa/Algiers")
MAX_LOG_LINES = 100
MAX_SIGNALS = 50


def now_local():
    return datetime.now(ALGIERS)


class BotState:
    def __init__(self):
        self._lock = threading.Lock()
        self.trades = 0
        self.wins = 0
        self.losses = 0
        self.balance = 0.0
        self.signals = []
        self.status = "متوقف"
        self.running = False
        self.log = []

    def reset_stats(self):
        with self._lock:
            self.trades = 0
            self.wins = 0
            self.losses = 0
            self.balance = 0.0
            self.signals = []

    def add_log(self, msg):
        ts = now_local().strftime("%H:%M:%S")
        line = f"[{ts}] {msg}"
        with self._lock:
            self.log.append(line)
            if len(self.log) > MAX_LOG_LINES:
                self.log = self.log[-MAX_LOG_LINES:]

    def add_signal(self, asset, direction, entry, result="pending", profit=None):
        sig = {
            "time": now_local().strftime("%H:%M"),
            "asset": asset.replace("_otc", "").upper(),
            "direction": direction.upper(),
            "entry": entry,
            "result": result,
            "profit": profit,
        }
        with self._lock:
            self.signals.insert(0, sig)
            if len(self.signals) > MAX_SIGNALS:
                self.signals = self.signals[:MAX_SIGNALS]
        return sig

    def update_signal(self, sig, result, profit):
        with self._lock:
            sig["result"] = result
            sig["profit"] = profit

    def to_dict(self):
        with self._lock:
            total = self.wins + self.losses
            win_rate = round(self.wins / total * 100) if total > 0 else 0
            return {
                "running": self.running,
                "status": self.status,
                "balance": round(self.balance, 2),
                "trades": self.trades,
                "wins": self.wins,
                "losses": self.losses,
                "win_rate": win_rate,
                "signals": list(self.signals),
                "log": list(self.log),
            }


state = BotState()

_bot_thread = None
_stop_event = threading.Event()


# =========================
# DECIDE DIRECTION (SMART)
# =========================
async def decide_direction(client, asset):
    call_score = 0
    put_score = 0
    last_close = 0
    try:
        candles = await client.get_candles(asset, int(time.time()), 5, 60)
        if candles:
            ups = sum(1 for c in candles if c["close"] > c["open"])
            downs = sum(1 for c in candles if c["close"] < c["open"])
            if ups >= 3:
                call_score += 3
            if downs >= 3:
                put_score += 3
            last_close = candles[-1]["close"]

        rsi = await client.calculate_indicator(asset, "RSI", {"period": 14}, history_size=3600, timeframe=60)
        if rsi and "current" in rsi and rsi["current"] is not None:
            rsi_val = float(rsi["current"])
            if rsi_val < 35:
                call_score += 2
            elif rsi_val > 65:
                put_score += 2

        ema = await client.calculate_indicator(asset, "EMA", {"period": 20}, history_size=3600, timeframe=60)
        if ema and "current" in ema and ema["current"] is not None:
            ema_val = float(ema["current"])
            if last_close > ema_val:
                call_score += 2
            elif last_close < ema_val:
                put_score += 2

        sma = await client.calculate_indicator(asset, "SMA", {"period": 20}, history_size=3600, timeframe=60)
        if sma and "current" in sma and sma["current"] is not None:
            sma_val = float(sma["current"])
            if last_close > sma_val:
                call_score += 1
            elif last_close < sma_val:
                put_score += 1

        if call_score > put_score:
            return "call"
        if put_score > call_score:
            return "put"
        return random.choice(["call", "put"])
    except Exception as e:
        state.add_log(f"DECIDE ERROR: {e}")
        return random.choice(["call", "put"])


# =========================
# RESOLVE OPEN ASSETS
# =========================
async def get_open_assets(client):
    candidates = list(ASSETS)
    random.shuffle(candidates)
    open_list = []
    for asset in candidates:
        try:
            asset_name, asset_data = await client.get_available_asset(asset, force_open=False)
            if asset_data and asset_data[2]:
                open_list.append(asset_name)
        except Exception as e:
            state.add_log(f"ASSET CHECK ({asset}): {e}")
    return open_list if open_list else list(ASSETS)


# =========================
# EXECUTE + RESULT ENGINE
# =========================
async def trade_once(client, candidates, amount, direction, duration, target_time):
    now_alg = now_local()
    wait_seconds = (target_time - now_alg).total_seconds() - 1.5
    if wait_seconds > 0:
        await asyncio.sleep(wait_seconds)

    try:
        before_balance = float(await client.get_balance())
    except Exception as e:
        state.add_log(f"PRE-BUY BALANCE ERROR: {e}")
        before_balance = 0.0

    used_asset = None
    order_id = None
    after_buy_balance = before_balance

    for asset in candidates:
        state.add_log(f"BUY ATTEMPT: {asset} | {direction.upper()} | ${amount}")
        try:
            success, order_info = await client.buy(amount, asset, direction, duration, time_mode="TIME")
        except Exception as e:
            state.add_log(f"BUY ERROR ({asset}): {e}")
            continue

        if success and isinstance(order_info, dict) and "id" in order_info:
            order_id = order_info["id"]
            after_buy_balance = float(order_info.get("accountBalance", before_balance))
            used_asset = asset
            state.add_log(f"ORDER OK: {asset} | ID={order_id}")
            break
        else:
            state.add_log(f"BUY FAILED for {asset}, trying next...")

    if used_asset is None:
        return None, None, None, "none", 0.0

    await asyncio.sleep(duration + 2)

    final_balance = before_balance
    for _ in range(15):
        try:
            bal = await client.get_balance()
            if float(bal) != float(after_buy_balance):
                final_balance = float(bal)
                break
        except Exception:
            pass
        await asyncio.sleep(0.7)

    profit_val = round(final_balance - before_balance, 2)
    result = "win" if final_balance > before_balance else "loss"

    return order_id, used_asset, direction, result, profit_val


# =========================
# SAFE TELEGRAM SEND
# =========================
async def safe_tg_send(tg, text):
    for attempt in range(3):
        try:
            if not tg.is_connected():
                state.add_log(f"TG reconnecting (attempt {attempt + 1})...")
                await tg.connect()
            await tg.send_message(CHANNEL, text)
            return True
        except Exception as e:
            state.add_log(f"TG SEND FAILED (attempt {attempt + 1}): {e}")
            try:
                await tg.disconnect()
            except Exception:
                pass
            await asyncio.sleep(1.5)
    state.add_log("TG SEND GIVE UP")
    return False


# =========================
# MAIN BOT LOOP
# =========================
async def _run_bot():
    state.status = "جاري الاتصال..."
    state.add_log("Bot starting...")

    quotex_client = Quotex(email=EMAIL, password=PASSWORD, lang="en")
    quotex_client.set_account_mode("PRACTICE")
    connected, reason = await quotex_client.connect()
    if not connected:
        state.add_log(f"Quotex connection failed: {reason}")
        state.status = "فشل الاتصال"
        state.running = False
        return

    await quotex_client.change_account("PRACTICE")

    try:
        state.balance = float(await quotex_client.get_balance())
    except Exception:
        pass

    tg = TelegramClient("session_pc", API_ID, API_HASH)
    await tg.start()
    await safe_tg_send(tg, "LATCHI DZ BOT STARTED")

    state.status = "يعمل"
    state.add_log("Bot connected. Trading loop started.")

    while not _stop_event.is_set():
        try:
            open_assets = await get_open_assets(quotex_client)
            primary_asset = open_assets[0]
            direction = await decide_direction(quotex_client, primary_asset)

            now_alg = now_local()
            next_minute = now_alg.replace(second=0, microsecond=0) + timedelta(minutes=1)
            if (next_minute - now_alg).total_seconds() < 4:
                next_minute += timedelta(minutes=1)
            target_time = next_minute
            entry_str = target_time.strftime("%H:%M")

            sig = state.add_signal(primary_asset, direction, entry_str)

            order_id, asset_used, dir_used, result, profit = await trade_once(
                quotex_client, open_assets, BASE_AMOUNT, direction, 60, target_time
            )

            if dir_used is None:
                state.update_signal(sig, "fail", None)
                await safe_tg_send(tg, f"Trade not executed | {primary_asset.upper()}")
                state.add_log(f"Trade not executed for {primary_asset}")
                if not _stop_event.is_set():
                    await asyncio.sleep(3)
                continue

            sig["asset"] = asset_used.replace("_otc", "").upper()
            sig["direction"] = dir_used.upper()

            preview_msg = (
                f"New Signal LATCHI DZ VIP:\n\n"
                f"{asset_used.upper()} | M1 | {entry_str} | "
                f"{'CALL' if dir_used == 'call' else 'PUT'}\n\n#QUOTEX"
            )
            await safe_tg_send(tg, preview_msg)

            with state._lock:
                state.trades += 1

            if result == "win":
                with state._lock:
                    state.wins += 1
                state.update_signal(sig, "win", profit)
                state.add_log(f"WIN | {asset_used.upper()} | {dir_used.upper()} | +{profit}")
                await safe_tg_send(tg, f"WIN | {asset_used.upper()} | {dir_used.upper()} | +{profit}")
            elif result == "loss":
                with state._lock:
                    state.losses += 1
                state.update_signal(sig, "loss", profit)
                state.add_log(f"LOSS | {asset_used.upper()} | {dir_used.upper()} | {profit}")
                await safe_tg_send(tg, f"LOSS | {asset_used.upper()} | {dir_used.upper()} | {profit}")
            else:
                state.update_signal(sig, "equal", 0.0)
                state.add_log(f"EQUAL | {asset_used.upper()} | {dir_used.upper()}")

            try:
                state.balance = float(await quotex_client.get_balance())
            except Exception:
                pass

            if not _stop_event.is_set():
                await asyncio.sleep(10)

        except Exception as e:
            state.add_log(f"LOOP ERROR: {e}")
            if not _stop_event.is_set():
                await asyncio.sleep(5)

    state.add_log("Bot stopped.")
    await safe_tg_send(tg, "LATCHI DZ BOT STOPPED")
    try:
        await tg.disconnect()
    except Exception:
        pass
    try:
        quotex_client.close()
    except Exception:
        pass

    state.status = "متوقف"
    state.running = False


def _thread_target():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_run_bot())
    finally:
        loop.close()


def start_bot():
    global _bot_thread
    if state.running:
        return False
    _stop_event.clear()
    state.running = True
    state.status = "جاري التشغيل..."
    _bot_thread = threading.Thread(target=_thread_target, daemon=True)
    _bot_thread.start()
    return True


def stop_bot():
    if not state.running:
        return False
    state.status = "جاري الإيقاف..."
    _stop_event.set()
    return True
