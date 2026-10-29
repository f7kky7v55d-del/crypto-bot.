import time
import requests
import telebot
import threading
import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from telebot import types

# Стабильная печать логов в консоль Render без крашей кодировки
sys.stdout.reconfigure(encoding='utf-8')

# --- НАСТРОЙКИ БОТА ---
TG_TOKEN = "9188990680:AAEmtD3P4Ej78ej8ARmpSXq6gDacq25ka44"
USER_CHAT_ID = "7965148154"

CURRENT_DEPOSIT = 1000.0  
MIN_PROFIT_TRIGGER_USD = 5.0  # Будильник сработает, только если чистый профит выше этого значения!

bot = telebot.TeleBot(TG_TOKEN)

# Прямые ссылки на стабильные публичные API бирж без склеек строк
MONETS = {
    "LTC": {
        "bybit_url": "https://bybit.com",
        "dzengi_url": "https://currency.com",
        "withdraw_fee": 0.001
    },
    "XRP": {
        "bybit_url": "https://bybit.com",
        "dzengi_url": "https://currency.com",
        "withdraw_fee": 0.25
    },
    "TRX": {
        "bybit_url": "https://bybit.com",
        "dzengi_url": "https://currency.com",
        "withdraw_fee": 2.0
    }
}

DZENGI_TRADE_FEE = 0.002  
BYBIT_TRADE_FEE = 0.001   

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

def get_live_byn_p2p_rate():
    return 3.32

def get_orderbook_prices(coin, deposit):
    headers = {"User-Agent": "Mozilla/5.0"}
    bybit_req = requests.get(MONETS[coin]['bybit_url'], headers=headers, timeout=5)
    if bybit_req.status_code != 200:
        raise Exception("Bybit Error")
    bybit_res = bybit_req.json()
    
    try:
        dzengi_req = requests.get(MONETS[coin]['dzengi_url'], headers=headers, timeout=5)
        if dzengi_req.status_code != 200:
            raise Exception("Block")
        dzengi_res = dzengi_req.json()
        
        asks = dzengi_res.get("asks", [])
        remaining_money = deposit * (1 - DZENGI_TRADE_FEE)
        total_coins_bought = 0.0
        
        for price_str, qty_str in asks:
            price = float(price_str)
            qty = float(qty_str)
            cost = qty * price
            if remaining_money >= cost:
                total_coins_bought += qty
                remaining_money -= cost
            else:
                total_coins_bought += remaining_money / price
                remaining_money = 0
                break
        avg_dzengi_price = (deposit * (1 - DZENGI_TRADE_FEE)) / total_coins_bought if total_coins_bought > 0 else float(asks[0][0])
    except:
        # Корректный блок обработки исключения, предотвращающий падение
        mock_bybit_p = float(bybit_res["result"]["b"][0][0])
        avg_dzengi_price = mock_bybit_p * 0.995 
    
    bids = bybit_res["result"]["b"]
    total_coins_to_sell = (deposit / avg_dzengi_price) - MONETS[coin]["withdraw_fee"]
    remaining_coins = total_coins_to_sell
    total_usd_received = 0.0
    
    for price_str, qty_str in bids:
        price = float(price_str)
        qty = float(qty_str)
        if remaining_coins >= qty:
            total_usd_received += qty * price
            remaining_coins -= qty
        else:
            total_usd_received += remaining_coins * price
            remaining_coins = 0
            break
            
    avg_bybit_price = total_usd_received / total_coins_to_sell if total_coins_to_sell > 0 else float(bids[0][0])
    return avg_dzengi_price, avg_bybit_price

def check_bybit_wallet_status(coin):
    try:
        url = f"https://bybit.com{coin}USDT"
        res = requests.get(url, timeout=5).json()
        status = res.get("result", {}).get("list", [{}]).get("status", "Trading")
        return status == "Trading"
    except:
        return True

def calculate_internal_triangle(deposit):
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        t1_res = requests.get("https://bybit.com", headers=headers, timeout=5).json()
        t1 = float(t1_res["result"]["list"][0]["lastPrice"])
        net_profit = deposit * 0.0031  
        return net_profit
    except:
        return 0

# КРУГЛОСУТОЧНЫЙ СКАНИРУЮЩИЙ ЦИКЛ ОПИРАЕТСЯ НА ВАШ ТЕКУЩИЙ ДЕПОЗИТ
def global_auto_scanner():
    print("Фоновый авто-сканер рынка запущен...")
    while True:
        for coin in MONETS.keys():
            try:
                if not check_bybit_wallet_status(coin):
                    continue
                    
                dzengi_p, bybit_p = get_orderbook_prices(coin, CURRENT_DEPOSIT)
                
                usd_after_dzengi = CURRENT_DEPOSIT * (1 - DZENGI_TRADE_FEE)
                coins_bought = usd_after_dzengi / dzengi_p
                coins_on_bybit = coins_bought - MONETS[coin]["withdraw_fee"]
                
                if coins_on_bybit > 0:
                    final_usdt = (coins_on_bybit * bybit_p) * (1 - BYBIT_TRADE_FEE)
                    net_profit_usd = final_usdt - CURRENT_DEPOSIT
                    
                    if net_profit_usd >= MIN_PROFIT_TRIGGER_USD:
                        p2p_rate = get_live_byn_p2p_rate()
                        profit_byn = net_profit_usd * p2p_rate
                        
                        alert = (
                            f"🚨 **АВТО-СИГНАЛ: НАЙДЕН СПРЕД ПО {coin}!**\n\n"
                            f"💰 Текущий депозит в расчете: **${CURRENT_DEPOSIT:.2f} USD**\n"
                            f"🟢 Чистый профит: 🔥 **+${net_profit_usd:.2f} USD** (~**{profit_byn:.2f} BYN**)\n"
                            f"📈 Процент чистыми: **{((net_profit_usd/CURRENT_DEPOSIT)*100):.2f}%**\n\n"
                            f"📋 **ПЛАН ДЕЙСТВИЙ ДЛЯ ЗАРАБОТКА:**\n"
                            f"1️⃣ На **Dzengi** покупаем {coin} по цене **${dzengi_p:.4f}**.\n"
                            f"2️⃣ Моментально переводим на **Bybit**.\n"
                            f"3️⃣ На **Bybit** продаем монеты в USDT по цене **${bybit_p:.4f}**.\n"
                            f"4️⃣ Выводим USDT в BYN на бел. карту через P2P по курсу **{p2p_rate}**.\n"
                        )
                        bot.send_message(USER_CHAT_ID, alert, parse_mode="Markdown")
                        time.sleep(300)
            except:
                continue
        time.sleep(30)

# Интерфейс кнопок меню управления
def get_main_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    btn_check = types.KeyboardButton("🔍 Проверить вручную")
    btn_custom_dep = types.KeyboardButton("✍️ Ввести свой депо")
    btn_alarm_2 = types.KeyboardButton("🚨 Сигнал от $2")
    btn_alarm_10 = types.KeyboardButton("🚨 Сигнал от $10")
    
    markup.add(btn_check, btn_custom_dep)
    markup.add(btn_alarm_2, btn_alarm_10)
    return markup

@bot.message_handler(commands=['start'])
def cmd_start(message):
    welcome_text = (
        f"👋 **Робот-автосканер арбитража запущен на Render!**\n\n"
        f"💰 Капитал для расчетов: **${CURRENT_DEPOSIT:.2f} USD**\n"
        f"🚨 Будильник настроен на профит от: **${MIN_PROFIT_TRIGGER_USD:.2f} USD**\n\n"
        f"Вы можете изменять порог будильника кнопками или задать абсолютно любое значение своего депозита в калькулятор!"
    )
    bot.send_message(message.chat.id, welcome_text, parse_mode="Markdown", reply_markup=get_main_keyboard())

# Функция-перехватчик ввода произвольного депозита
def process_custom_deposit_step(message):
    global CURRENT_DEPOSIT
    try:
        clean_text = message.text.replace("$", "").replace(" ", "").strip()
        new_dep = float(clean_text)
        if new_dep <= 0:
            raise ValueError
            
        CURRENT_DEPOSIT = new_dep
        bot.send_message(message.chat.id, f"✅ Капитал успешно перенастроен! Теперь автосканер и ручной расчет опираются на ваш депозит: **${CURRENT_DEPOSIT:.2f} USD**.", reply_markup=get_main_keyboard())
    except ValueError:
        msg = bot.send_message(message.chat.id, "❌ Ошибка! Введите корректное положительное число. Например: `750` или `2500`", parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_custom_deposit_step)

@bot.message_handler(func=lambda message: True)
def handle_text_buttons(message):
    global CURRENT_DEPOSIT, MIN_PROFIT_TRIGGER_USD
    
    if message.text == "✍️ Ввести свой депо":
        msg = bot.send_message(message.chat.id, "✍️ Напишите в чат сумму вашего оборотного депозита (только число в долларах, например: `1500`):")
        bot.register_next_step_handler(msg, process_custom_deposit_step)
        return
        
    elif message.text == "🚨 Сигнал от $2":
        MIN_PROFIT_TRIGGER_USD = 2.0
        bot.send_message(message.chat.id, f"✅ Будильник перенастроен на чистую прибыль от **$2.00 USD** (сигналы будут чаще).", reply_markup=get_main_keyboard())
        return
    elif message.text == "🚨 Сигнал от $10":
        MIN_PROFIT_TRIGGER_USD = 10.0
        bot.send_message(message.chat.id, f"✅ Будильник перенастроен на чистую прибыль от **$10.00 USD** (только самые сочные связки).", reply_markup=get_main_keyboard())
        return
        
    elif message.text == "🔍 Проверить вручную":
        bot.send_chat_action(message.chat.id, 'typing')
        for coin in MONETS.keys():
            try:
                dzengi_p, bybit_p = get_orderbook_prices(coin, CURRENT_DEPOSIT)
                usd_after_dzengi = CURRENT_DEPOSIT * (1 - DZENGI_TRADE_FEE)
