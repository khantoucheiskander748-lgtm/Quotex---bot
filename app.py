Agent
QUOTEX_EMAIL=wagife9306@mugstock.com
QUOTEX_PASSWORD=latchi23@@
TELEGRAM_API_ID=21508855
TELEGRAM_API_HASH=290e3791a95daa5fffcd1847a1b5da17
TELEGRAM_BOT_TOKEN=7632913428:AAExZwjiGmQjHyOo7muj9yiv9UBxU0doUhE
TELEGRAM_CHANNEL=@latchidz1

3 days ago
I didn't know how

3 days ago
I couldn't find it, whether it was at the bottom or the top.

3 days ago
Is it actually connected to the Qtuotex platform?

3 days ago
بعد الاتصال وتغيير الحساب للتجريبي
await client.connect()
await client.change_account("PRACTICE")

تجربة فتح صفقة فعلية
result = await client.buy("EURUSD", 1, "call", 1) # زوج EURUSD، مبلغ 1، اتجاه call، مدة 1 دقيقة

إرسال النتيجة لتيليجرام
await tg.send_message(CHANNEL, f"📊 صفقة جديدة: {result}")

3 days ago
Not content main.py

3 days ago
Not content main.py

3 days ago
Change content main.py

3 days ago
Not content main.py

3 days ago
Not content main.py

3 days ago
pip install pytz

3 days ago
The app failed to run, please debug and fix it.

16 minutes ago
https://github.com/khantoucheiskander748-lgtm/Quotex---bot لقد قمت بتغيير التيليجرام شوف الملفاتك تعرف عدل البوت

14 minutes ago
LATCHI QUOTEX VIP:
❌ فشل اتصال البوت: Websocket connection rejected.

❌ فشل اتصال البوت: Service unavailable: Unfortunately, Quotex is currently not available in your region. (United States)If you think you're seeing this message by mistake, please contact[email protected]

3 minutes ago
اعطيني الاكواد التي قمت بعملها كلها لكي شغلت هذا واعطيني وين نركب البروكسي

3 minutes ago
Let me update the bot to read a proxy from an environment variable, then show you all files clearly.

تمام، أنا أضفت دعم البروكسي. هذه كل الملفات والإعدادات اللي شغّلتها لك:

📁 الملفات
bot.py (المنطق الرئيسي للبوت)
import asyncio
import os
import random
import time
import threading
import requests
from datetime import datetime, timedelta
import pyquotex.stable_api as _qx_stable
import pyquotex.expiration as _qx_exp
from pyquotex.stable_api import Quotex
# --- إصلاح bug في pyquotex لما user_settings.offset يكون None ---
async def _patched_get_server_time(self):
    if self.api is None:
        return int(time.time())
    user_settings = await self.get_profile()
    offset_zone = 0
    if user_settings is not None and getattr(user_settings, "offset", None) is not None:
        offset_zone = user_settings.offset
    self.api.timesync.server_timestamp = _qx_exp.get_server_timer(offset_zone)
    return self.api.timesync.server_timestamp
_qx_stable.Quotex.get_server_time = _patched_get_server_time
def _env(*names, default=""):
    for n in names:
        v = (os.environ.get(n) or "").strip()
        if v:
            return v
    return default
EMAIL = _env("QX_EMAIL", "QUOTEX_EMAIL")
PASSWORD = _env("QX_PASSWORD", "QUOTEX_PASSWORD")
ASSETS = ["NZDCHF_otc", "USDINR_otc", "USDBDT_otc", "USDARS_otc", "USDPKR_otc"]
BASE_AMOUNT = 1.0
TG_TOKEN = _env("TG_TOKEN", "TELEGRAM_BOT_TOKEN", "TG_BOT_TOKEN")
TG_CHANNEL = _env("TG_CHANNEL", "TELEGRAM_CHANNEL")
def send_telegram(text):
    try:
        url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
        requests.post(
            url,
            json={"chat_id": TG_CHANNEL, "text": text, "parse_mode": "HTML"},
            timeout=10,
        )
    except Exception as e:
        print("TG ERROR:", e)
class BotState:
    def __init__(self):
        self.running = False
        self.balance = 0
        self.wins = 0
        self.losses = 0
        self.trades = 0
        self.signals = []
        self.status = "متوقف"
    def reset_stats(self):
        self.wins = 0
        self.losses = 0
        self.trades = 0
        self.signals = []
        self.status = "تم إعادة الضبط"
    def to_dict(self):
        return {
            "running": self.running,
            "balance": self.balance,
            "wins": self.wins,
            "losses": self.losses,
            "trades": self.trades,
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
        last_close = 0
        candles = await client.get_candles(asset, int(time.time()), 5, 60)
        if candles:
            ups = sum(1 for c in candles if c["close"] > c["open"])
            downs = sum(1 for c in candles if c["close"] < c["open"])
            if ups >= 3:
                call_score += 3
            if downs >= 3:
                put_score += 3
            last_close = candles[-1]["close"]
        rsi = await client.calculate_indicator(
            asset, "RSI", {"period": 14}, history_size=3600, timeframe=60
        )
        if rsi and "current" in rsi and rsi["current"]:
            rsi_val = float(rsi["current"])
            if rsi_val < 35:
                call_score += 2
            elif rsi_val > 65:
                put_score += 2
        ema = await client.calculate_indicator(
            asset, "EMA", {"period": 20}, history_size=3600, timeframe=60
        )
        if ema and "current" in ema and ema["current"]:
            ema_val = float(ema["current"])
            if last_close > ema_val:
                call_score += 2
            elif last_close < ema_val:
                put_score += 2
        if call_score > put_score:
            return "call"
        elif put_score > call_score:
            return "put"
        else:
            return random.choice(["call", "put"])
    except Exception:
        return random.choice(["call", "put"])
async def bot_loop():
    global state
    # 👇👇👇 هنا يُركَّب البروكسي 👇👇👇
    proxy_url = _env("QX_PROXY", "PROXY_URL")
    proxies = {"http": proxy_url, "https": proxy_url} if proxy_url else None
    client = Quotex(email=EMAIL, password=PASSWORD, lang="en", proxies=proxies)
    # 👆👆👆 يكفي تضيف QX_PROXY في Secrets 👆👆👆
    client.set_account_mode("PRACTICE")
    connected, reason = await client.connect()
    if not connected:
        state.status = f"فشل الاتصال: {reason}"
        state.running = False
        send_telegram(f"❌ فشل اتصال البوت: {reason}")
        return
    await client.change_account("PRACTICE")
    balance = await client.get_balance()
    state.balance = float(balance)
    state.status = "يعمل الآن"
    send_telegram(
        f"🚀 <b>LATCHI DZ BOT</b> بدأ التشغيل\n"
        f"💰 الرصيد التجريبي: <b>${state.balance:.2f}</b>\n"
        f"📊 وضع: تجريبي (PRACTICE)"
    )
    while state.running:
        try:
            asset = random.choice(ASSETS)
            direction = await decide_direction(client, asset)
            now = datetime.now()
            signal_time = now.strftime("%H:%M")
            next_minute = (now + timedelta(minutes=1)).replace(second=0, microsecond=0)
            wait = (next_minute - datetime.now()).total_seconds() - 2
            if wait > 0:
                await asyncio.sleep(wait)
            if not state.running:
                break
            direction_text = "CALL 🔼" if direction == "call" else "PUT 🔽"
            send_telegram(
                f"📊 <b>إشارة جديدة — LATCHI DZ VIP</b>\n\n"
                f"🎯 الأصل: <b>{asset.upper()}</b>\n"
                f"📈 الاتجاه: <b>{direction_text}</b>\n"
                f"⏱ التوقيت: <b>M1</b> | {next_minute.strftime('%H:%M')}\n"
                f"💵 المبلغ: <b>${BASE_AMOUNT}</b>\n\n"
                f"#QUOTEX #LATCHIDZ"
            )
            success, order_info = await client.buy(BASE_AMOUNT, asset, direction, 60)
            signal = {
                "asset": asset.upper(),
                "direction": direction,
                "time": signal_time,
                "result": "pending",
                "profit": 0,
            }
            state.signals.insert(0, signal)
            state.trades += 1
            if not success or not isinstance(order_info, dict) or "id" not in order_info:
                signal["result"] = "fail"
                send_telegram(f"⚠️ فشل تنفيذ الصفقة على {asset.upper()}")
                await asyncio.sleep(10)
                continue
            await asyncio.sleep(75)
            profit, result_status = await client.check_win(order_info["id"])
            signal["result"] = result_status
            signal["profit"] = round(float(profit), 2) if profit else 0
            new_balance = await client.get_balance()
            state.balance = float(new_balance)
            if result_status == "win":
                state.wins += 1
                send_telegram(
                    f"✅ <b>ربح!</b>\n"
                    f"🎯 {asset.upper()} | {direction_text}\n"
                    f"💰 الربح: <b>+${signal['profit']}</b>\n"
                    f"💳 الرصيد: <b>${state.balance:.2f}</b>"
                )
            elif result_status == "loss":
                state.losses += 1
                send_telegram(
                    f"❌ <b>خسارة</b>\n"
                    f"🎯 {asset.upper()} | {direction_text}\n"
                    f"💸 الخسارة: <b>-${BASE_AMOUNT}</b>\n"
                    f"💳 الرصيد: <b>${state.balance:.2f}</b>"
                )
            await asyncio.sleep(5)
        except Exception as e:
            state.status = f"خطأ: {str(e)}"
            print("BOT ERROR:", e)
            await asyncio.sleep(10)
    state.status = "متوقف"
    send_telegram("🛑 <b>LATCHI DZ BOT</b> تم الإيقاف")
    try:
        await client.close()
    except Exception:
        pass
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
app.py (واجهة Flask للتحكم في البوت)
from flask import Flask, jsonify
from flask_cors import CORS
import bot
app = Flask(__name__)
CORS(app)
@app.route("/")
def index():
    return jsonify({"status": "ok", "message": "Quotex Bot API"})
@app.route("/api/state")
def api_state():
    return jsonify(bot.state.to_dict())
@app.route("/api/start", methods=["POST"])
def api_start():
    started = bot.start_bot()
    return jsonify({"ok": started, "state": bot.state.to_dict()})
@app.route("/api/stop", methods=["POST"])
def api_stop():
    stopped = bot.stop_bot()
    return jsonify({"ok": stopped, "state": bot.state.to_dict()})
@app.route("/api/reset", methods=["POST"])
def api_reset():
    bot.state.reset_stats()
    return jsonify({"ok": True, "state": bot.state.to_dict()})
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)