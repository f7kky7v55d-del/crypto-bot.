import time
import requests
import telebot
import threading
import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from telebot import types

sys.stdout.reconfigure(encoding='utf-8')

# --- НАСТРОЙКИ БОТА ---
TG_TOKEN = "9188990680:AAEmtD3P4Ej78ej8ARmpSXq6gDacq25ka44"
USER_CHAT_ID = "7965148154"

CURRENT_DEPOSIT = 1000.0  
MIN_PROFIT_TRIGGER_USD = 5.0  

bot = telebot.TeleBot(TG_TOKEN)

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
    try:
        port = int(os.environ.get("PORT", 10000))
        server = HTTPServer(("0.0.0.0", port), WebhookServer)
        server.serve_forever()
    except:
        pass

def get_live_byn_p2p_rate():
    return 3.32

def get_orderbook_prices(coin, deposit):
    headers = {"User-Agent": "Mozilla/5.0"}
    bybit_req = requests.get(MONETS[coin]['bybit_url'], headers=headers, timeout=5)
    bybit_res = bybit_req.json()
    
    try:
        dzengi_req = requests.get(MONETS[coin]['dzengi_url'], headers=headers, timeout=5)
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
        avg_dzengi_price = (deposit * (1 - DZENGI_TRADE_FEE)) / total_coins_bought if total_coins_bought > 0 else mock_bybit_p
    except:
        mock_bybit_p = float(bybit_res.get("result", {}).get("b", [["0"]])[0][0])
        avg_dzengi_price = mock_bybit_p * 0.995 
    
    bids = bybit_res.get("result", {}).get("b", [["0"]])
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
        status = res.get("result", {}).get("list", [{}])[0].get("status", "Trading")
        return status == "Trading"
    except:
        return True

# АВТОМАТИЧЕСКИЙ СКАНИРУЮЩИЙ ЦИКЛ БЕЗ КОНФЛИКТА ПОТОКОВ
def scan_market_step():
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
                        f"💰 Депозит: **${CURRENT_DEPOSIT:.2f} USD**\n"
                        f"🟢 Профит: 🔥 **+${net_profit_usd:.2f} USD** (~**{profit_byn:.2f} BYN**)\n\n"
                        f"1️⃣ На **Dzengi** покупаем {coin} по цене **${dzengi_p:.4f}**.\n"
                        f"2️⃣ Переводим на **Bybit**.\n"
                        f"3️⃣ Продаем монеты в USDT по цене **${bybit_p:.4f}**.\n"
                    )
                    bot.send_message(USER_CHAT_ID, alert, parse_mode="Markdown")
                    return True
        except:
            continue
    return False

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
        f"👋 **Робот-автосканер запущен!**\n\n"
        f"💰 Капитал: **${CURRENT_DEPOSIT:.2f} USD**\n"
        f"🚨 Будильник: **${MIN_PROFIT_TRIGGER_USD:.2f} USD**"
    )
    bot.send_message(message.chat.id, welcome_text, parse_mode="Markdown", reply_markup=get_main_keyboard())

def process_custom_deposit_step(message):
    global CURRENT_DEPOSIT
    try:
        clean_text = message.text.replace("$", "").replace(" ", "").strip()
        CURRENT_DEPOSIT = float(clean_text)
        bot.send_message(message.chat.id, f"✅ Депозит изменен на: **${CURRENT_DEPOSIT:.2f} USD**.", reply_markup=get_main_keyboard())
    except:
        msg = bot.send_message(message.chat.id, "❌ Введите только число долларов:")
        bot.register_next_step_handler(msg, process_custom_deposit_step)

@bot.message_handler(func=lambda message: True)
def handle_text_buttons(message):
    global CURRENT_DEPOSIT, MIN_PROFIT_TRIGGER_USD
    
    if message.text == "✍️ Ввести свой депо":
        msg = bot.send_message(message.chat.id, "✍️ Напишите сумму депозита в долларах (например, `1500`):")
        bot.register_next_step_handler(msg, process_custom_deposit_step)
    elif message.text == "🚨 Сигнал от $2":
        MIN_PROFIT_TRIGGER_USD = 2.0
        bot.send_message(message.chat.id, "✅ Сигнал переключен от $2.")
    elif message.text == "🚨 Сигнал от $10":
        MIN_PROFIT_TRIGGER_USD = 10.0
        bot.send_message(message.chat.id, "✅ Сигнал переключен от $10.")
    elif message.text == "🔍 Проверить вручную":
        bot.send_chat_action(message.chat.id, 'typing')
        if not scan_market_step():
            bot.send_message(message.chat.id, "📉 Прибыльных связок прямо сейчас нет. Ищу в фоне...")

# УМНЫЙ ЦИКЛ ЗАПУСКА: ОДИН ПОТОК ДЛЯ СЕРВЕРА, ОДИН ДЛЯ ТЕЛЕГРАМА
if __name__ == "__main__":
    threading.Thread(target=run_dummy_server, daemon=True).start()
    
    # Запускаем бесконечный опрос, Render теперь примет его без крашей
    while True:
        try:
            # Делаем один легкий шаг фонового сканирования перед опросом
            scan_market_step()
            bot.polling(none_stop=True, interval=3, timeout=20)
        except Exception as e:
            time.sleep(5)
