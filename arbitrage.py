import time
import requests
import telebot
import threading
import os
from http.server import BaseHTTPRequestHandler, HTTPServer

# --- НАСТРОЙКИ БОТА ---
TG_TOKEN = "9188990680:AAEmtD3P4Ej78ej8ARmpSXq6gDacq25ka44"
USER_CHAT_ID = "7965148154"

# Депозит по умолчанию (в USD, уже заведенных на Dzengi)
CURRENT_DEPOSIT = 1000.0  

bot = telebot.TeleBot(TG_TOKEN)

# Глобальный кэш цен, чтобы не спамить биржи запросами при каждом нажатии кнопки
prices_cache = {}

MONETS = {
    "LTC": {"bybit": "LTCUSDT", "dzengi": "LTCUSDT", "withdraw_fee": 0.001},
    "XRP": {"bybit": "XRPUSDT", "dzengi": "XRPUSDT", "withdraw_fee": 0.25},
    "TRX": {"bybit": "TRXUSDT", "dzengi": "TRXUSDT", "withdraw_fee": 2.0}
}

# Реальные комиссии на 2026 год
DZENGI_TRADE_FEE = 0.002  # 0.2% спот на Dzengi (Currency.com)
BYBIT_TRADE_FEE = 0.001   # 0.1% стандартный спот тейкер на Bybit

# --- КОСТЫЛЬ ДЛЯ RENDER (ФЕЙКОВЫЙ СЕРВЕР) ---
class WebhookServer(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(b"Render Web Service: Active")

def run_dummy_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), WebhookServer)
    server.serve_forever()
# ---------------------------------------------

# Поток фонового обновления цен (раз в 15 секунд собирает стаканы в кэш)
def update_prices_loop():
    global prices_cache
    while True:
        for coin_name, coin_info in MONETS.items():
            try:
                bybit_res = requests.get(f"https://bybit.com{coin_info['bybit']}", timeout=4).json()
                dzengi_res = requests.get(f"https://currency.com{coin_info['dzengi']}", timeout=4).json()
                
                bybit_p = float(bybit_res["result"]["list"][0]["lastPrice"])
                dzengi_p = float(dzengi_res["askPrice"]) if not isinstance(dzengi_res, list) else float(dzengi_res[0]["askPrice"])
                
                prices_cache[coin_name] = {"dzengi": dzengi_p, "bybit": bybit_p}
            except Exception as e:
                print(f"Ошибка обновления цен {coin_name}: {e}")
        time.sleep(15)

# Расчет математики треугольного круга арбитража
def calculate_deal(coin_name, deposit):
    if coin_name not in prices_cache:
        return None
        
    dzengi_p = prices_cache[coin_name]["dzengi"]
    bybit_p = prices_cache[coin_name]["bybit"]
    coin_info = MONETS[coin_name]
    
    # Считаем реальный круг:
    # 1. Покупка на Dzengi (минус 0.2%)
    usd_after_dzengi = deposit * (1 - DZENGI_TRADE_FEE)
    coins_bought = usd_after_dzengi / dzengi_p
    
    # 2. Вывод (минус фиксированная сеть)
    coins_on_bybit = coins_bought - coin_info["withdraw_fee"]
    if coins_on_bybit <= 0:
        return None
        
    # 3. Продажа на Bybit (минус 0.1%)
    dirty_usd_bybit = coins_on_bybit * bybit_p
    final_usd = dirty_usd_bybit * (1 - BYBIT_TRADE_FEE)
    
    net_profit = final_usd - deposit
    return {
        "dzengi_p": dzengi_p,
        "bybit_p": bybit_p,
        "coins_bought": coins_bought,
        "net_profit": net_profit,
        "percent": (net_profit / deposit) * 100
    }

# --- ОБРАБОТЧИКИ КОМАНД TELEGRAM ---

@bot.message_handler(commands=['start'])
def cmd_start(message):
    welcome_text = (
        f"👋 **Привет! Я твой приватный калькулятор арбитража Dzengi ➡️ Bybit.**\n\n"
        f"💰 Текущий рабочий депозит: **${CURRENT_DEPOSIT}**\n\n"
        f"📋 **Доступные команды:**\n"
        f"🔍 `/check` — Запросить самую прибыльную связку прямо сейчас\n"
        f"✍️ `/set X` — Изменить сумму депозита (например: `/set 500`)\n"
    )
    bot.send_message(message.chat.id, welcome_text, parse_mode="Markdown")

@bot.message_handler(commands=['set'])
def cmd_set_deposit(message):
    global CURRENT_DEPOSIT
    try:
        # Извлекаем число после команды /set
        args = message.text.split()
        if len(args) < 2:
            bot.send_message(message.chat.id, "❌ Укажите сумму. Пример: `/set 1500`", parse_mode="Markdown")
            return
            
        new_dep = float(args[1])
        if new_dep <= 0:
            raise ValueError
            
        CURRENT_DEPOSIT = new_dep
        bot.send_message(message.chat.id, f"✅ Рабочий депозит успешно изменен на **${CURRENT_DEPOSIT}**!", parse_mode="Markdown")
    except ValueError:
        bot.send_message(message.chat.id, "❌ Введите корректное положительное число после команды.")

@bot.message_handler(commands=['check'])
def cmd_check_market(message):
    if not prices_cache:
        bot.send_message(message.chat.id, "⏳ База данных цен еще обновляется, подождите 5 секунд и повторите команду.")
        return
        
    best_coin = None
    best_data = None
    
    # Ищем лучшую монету среди доступных
    for coin in MONETS.keys():
        deal = calculate_deal(coin, CURRENT_DEPOSIT)
        if deal:
            if best_data is None or deal["net_profit"] > best_data["net_profit"]:
                best_coin = coin
                best_data = deal
                
    if best_data and best_data["net_profit"] > 0:
        report = (
            f"🔥 **ТОЧНЫЙ РАСЧЕТ КРУГА ПО {best_coin}**\n"
            f"💰 Депозит в работе: **${CURRENT_DEPOSIT:.2f}**\n"
            f"💵 Чистая прибыль: **+${best_data['net_profit']:.2f}** ({best_data['percent']:.2f}%)\n\n"
            f"📐 **Алгоритм действий (Белый треугольник):**\n"
            f"1️⃣ На **Dzengi** покупаем монету **{best_coin}** по курсу **${best_data['dzengi_p']:.4f}**.\n"
            f"   *(Выйдет примерно: {best_data['coins_bought']:.4f} {best_coin} после комиссии 0.2%)*\n\n"
            f"2️⃣ Переводим **всё до копейки** на кошелек **Bybit** через родную сеть монеты.\n"
            f"   *(Комиссия сети спишется автоматически при выводе)*\n\n"
            f"3️⃣ На **Bybit** продаем монеты в стакан USDT по курсу **${best_data['bybit_p']:.4f}**.\n\n"
            f"✅ Фиат (доллары) вернулся на Bybit. Можно выводить на карту или пускать на следующий круг."
        )
        bot.send_message(message.chat.id, report, parse_mode="Markdown")
    else:
        # Если везде минусы из-за комиссий бирж
        bot.send_message(message.chat.id, f"📉 Прямо сейчас прибыльных связок с учетом всех комиссий для депозита ${CURRENT_DEPOSIT} не найдено. Попробуйте позже.")

if __name__ == "__main__":
    # 1. Поток-обманка портов для Render
    threading.Thread(target=run_dummy_server, daemon=True).start()
    
    # 2. Поток фонового обновления цен в памяти
    threading.Thread(target=update_prices_loop, daemon=True).start()
    
    print("Внутренние системы запущены. Ожидание команд Telegram...")
    bot.infinity_polling()
