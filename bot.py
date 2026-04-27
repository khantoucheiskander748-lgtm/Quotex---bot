import asyncio
import random
import time
from datetime import datetime, timedelta

import pytz
from pyquotex.stable_api import Quotex
from telethon import TelegramClient

EMAIL = "wagife9306@mugstock.com"
PASSWORD = "latchi23@@"

API_ID = 33567199
API_HASH = "3fdd30ef25043c39d8cc897d6251b8f1"
CHANNEL = "@latchidz0"

ASSETS = ["NZDCHF_otc", "USDINR_otc", "USDBDT_otc", "USDARS_otc", "USDPKR_otc"]
BASE_AMOUNT = 1.0

ALGIERS = pytz.timezone("Africa/Algiers")

bot_state = {"trades": 0, "wins": 0, "losses": 0, "balance": 0.0, "signals": [], "status_msg": ""}


def now_local():
    """Return timezone-aware current time in Algeria."""
    return datetime.now(ALGIERS)


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
        print("DECIDE ERROR:", e)
        return random.choice(["call", "put"])


# =========================
# RESOLVE A TRULY OPEN ASSET
# =========================
async def get_open_assets(client):
    """Return a list of OPEN assets from our OTC list (no _otc swap)."""
    candidates = list(ASSETS)
    random.shuffle(candidates)
    open_list = []
    for asset in candidates:
        try:
            asset_name, asset_data = await client.get_available_asset(asset, force_open=False)
            if asset_data and asset_data[2]:
                open_list.append(asset_name)
        except Exception as e:
            print(f"ASSET CHECK ERROR ({asset}):", e)
    return open_list if open_list else list(ASSETS)


# =========================
# EXECUTE + RESULT ENGINE
# =========================
async def trade_once(client, candidates, amount, direction, duration, target_time):
    """جرّب الشراء على عدة أصول حتى ينجح واحد."""
    # ندخل قبل بداية الشمعة بـ 1.5 ثانية عشان البوي تبعت في الوقت
    now_alg = now_local()
    wait_seconds = (target_time - now_alg).total_seconds() - 1.5
    if wait_seconds > 0:
        await asyncio.sleep(wait_seconds)

    try:
        before_balance = float(await client.get_balance())
    except Exception as e:
        print("PRE-BUY BALANCE ERROR:", e)
        before_balance = 0.0

    used_asset = None
    order_id = None
    after_buy_balance = before_balance

    for asset in candidates:
        print(f"🟡 BUY ATTEMPT: asset={asset} dir={direction} amount={amount} dur={duration} | before_bal={before_balance}")
        try:
            success, order_info = await client.buy(amount, asset, direction, duration, time_mode="TIME")
        except Exception as e:
            print(f"BUY ERROR ({asset}):", e)
            continue

        print(f"🟢 BUY RESPONSE [{asset}]: success={success} info={order_info}")
        if success and isinstance(order_info, dict) and "id" in order_info:
            order_id = order_info["id"]
            after_buy_balance = float(order_info.get("accountBalance", before_balance))
            used_asset = asset
            print(f"✅ ORDER ID: {order_id} | ASSET: {asset} | AFTER BUY BALANCE: {after_buy_balance}")
            break
        else:
            print(f"❌ BUY FAILED for {asset}, trying next...")

    if used_asset is None:
        return None, None, None, "none", 0.0

    await asyncio.sleep(duration + 2)

    final_balance = before_balance
    for i in range(15):
        try:
            bal = await client.get_balance()
            print(f"💵 CHECK BALANCE [{i+1}]:", bal)
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
# SAFE TELEGRAM SEND (مع reconnect)
# =========================
async def safe_tg_send(tg, text):
    for attempt in range(3):
        try:
            if not tg.is_connected():
                print(f"📡 TG reconnecting (attempt {attempt+1})…")
                await tg.connect()
            await tg.send_message(CHANNEL, text)
            print(f"📨 TG SENT: {text[:60]}")
            return True
        except Exception as e:
            print(f"⚠️ TG SEND FAILED (attempt {attempt+1}):", e)
            try:
                await tg.disconnect()
            except Exception:
                pass
            await asyncio.sleep(1.5)
    print("❌ TG SEND GIVE UP:", text[:60])
    return False


# =========================
# MAIN BOT
# =========================
async def main():
    quotex_client = Quotex(email=EMAIL, password=PASSWORD, lang="en")
    quotex_client.set_account_mode("PRACTICE")
    connected, reason = await quotex_client.connect()
    if not connected:
        print("❌ فشل الاتصال:", reason)
        return
    await quotex_client.change_account("PRACTICE")

    try:
        bot_state["balance"] = float(await quotex_client.get_balance())
    except Exception:
        pass

    tg = TelegramClient("session_pc", API_ID, API_HASH)
    await tg.start()
    await safe_tg_send(tg, "🚀 LATCHI DZ BOT STABLE SMART STARTED")

    while True:
        try:
            # نأخذ كل الأصول المفتوحة من قائمتنا الـ OTC
            open_assets = await get_open_assets(quotex_client)
            primary_asset = open_assets[0]
            direction = await decide_direction(quotex_client, primary_asset)

            # الوقت يحسب بتوقيت الجزائر
            now_alg = now_local()
            next_minute = now_alg.replace(second=0, microsecond=0) + timedelta(minutes=1)
            if (next_minute - now_alg).total_seconds() < 4:
                next_minute += timedelta(minutes=1)
            target_time = next_minute

            # نحاول الشراء — لو فشل الأصل الأول يحاول التالي تلقائياً
            order_id, asset_used, dir_used, result, profit = await trade_once(
                quotex_client, open_assets, BASE_AMOUNT, direction, 60, target_time
            )

            if dir_used is None:
                await safe_tg_send(tg, f"⚠️ الصفقة لم تنفذ | {primary_asset.upper()}")
                await asyncio.sleep(3)
                continue

            # المعاينة تُرسل بعد نجاح الشراء بالأصل المستعمل فعلاً
            preview_msg = f"""📊 صفقة جديدة LATCHI DZ VIP 🌟:

{asset_used.upper()} | M1 | {target_time.strftime('%H:%M')} | {"CALL 🔼" if dir_used=="call" else "PUT ⬇️"}

#QUOTEX"""
            await safe_tg_send(tg, preview_msg)

            bot_state["trades"] += 1
            if result == "win":
                bot_state["wins"] += 1
                await safe_tg_send(tg, f"🟢 ربح ✅ | {asset_used.upper()} | {dir_used.upper()} | +{profit}")
            elif result == "loss":
                bot_state["losses"] += 1
                await safe_tg_send(tg, f"🔴 خسارة ❌ | {asset_used.upper()} | {dir_used.upper()} | {profit}")
            else:
                await safe_tg_send(tg, f"⚪ النتيجة غير محددة | {asset_used.upper()} | {dir_used.upper()}")

            try:
                bot_state["balance"] = float(await quotex_client.get_balance())
            except Exception:
                pass

            await asyncio.sleep(10)

        except Exception as e:
            print("MAIN LOOP ERROR:", e)
            await asyncio.sleep(5)


if __name__ == "__main__":
    asyncio.run(main())