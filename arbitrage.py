import time
import requests
import telebot
import threading

TG_TOKEN = "9188990680:AAEmtD3P4Ej78ej8ARmpSXq6gDacq25ka44"
USER_CHAT_ID = "7965148154"
MIN_SPREAD = 1.2
CHECK_INTERVAL = 10

bot = telebot.TeleBot(TG_TOKEN)

# Глобальный флаг для управления работой мониторинга (True - работает, False - на паузе)
IS_RUNNING = True

MONETS = {
    "LTC": {"bybit": "LTCUSDT", "dzengi": "LTC/USDT"},
    "XRP": {"bybit": "XRPUSDT", "dzengi": "XRP/USDT"},
    "TRX": {"bybit": "TRXUSDT", "dzengi": "TRX/USDT"}
}

def get_prices(coin_info):
    try:
        bybit_res = requests.get(f"https://bybit.com{coin_info['bybit']}", timeout=5).json()
        dzengi_res = requests.get(f"https://currency.com{coin_info['dzengi']}", timeout=5).json()
        
        bybit_price = float(bybit_res["result"]["list"][0]["lastPrice"])
        dzengi_price = float(dzengi_res["ask"])
        return dzengi_price, bybit_price
    except:
        return None, None

# Фоновая функция мониторинга рынка
def monitor_market():
    global IS_RUNNING
    while True:
        # Если флаг выключен (/stop), мониторинг просто ждет и ничего не отправляет
        if not IS_RUNNING:
            time.sleep(1)
            continue
            
        for coin_name, coin_info in MONETS.items():
            # Дополнительная проверка внутри цикла, чтобы мгновенно среагировать на /stop
            if not IS_RUNNING:
                break
                
            dzengi_p, bybit_p = get_prices(coin_info)
            
            if dzengi_p and bybit_p and dzengi_p < bybit_p:
                spread = ((bybit_p - dzengi_p) / dzengi_p) * 100
                if spread >= MIN_SPREAD:
                    message = (
                        f"🚨 **НАЙДЕНА СВЯЗКА ПО {coin_name}!**\n\n"
                        f"🔹 Dzengi (РБ): **${dzengi_p:.4f}**\n"
                        f"🔸 Bybit: **${bybit_p:.4f}**\n\n"
                        f"📈 Спред: 🔥 **{spread:.2f}%**\n"
                        f"💼 Профит с $1000: ~**${(1000 * spread / 100):.2f}**\n"
                    )
                    bot.send_message(USER_CHAT_ID, message, parse_mode="Markdown")
                    time.sleep(60) 
        time.sleep(CHECK_INTERVAL)

# Обработчик команды /start
@bot.message_handler(commands=['start'])
def start_bot(message):
    global IS_RUNNING
    if not IS_RUNNING:
        IS_RUNNING = True
        bot.send_message(USER_CHAT_ID, "▶️ Мониторинг рынка возобновлен!")
    else:
        bot.send_message(USER_CHAT_ID, "🔥 Бот уже запущен и активно мониторит LTC, XRP, TRX...")

# Обработчик команды /stop
@bot.message_handler(commands=['stop'])
def stop_bot(message):
    global IS_RUNNING
    if IS_RUNNING:
        IS_RUNNING = False
        bot.send_message(USER_CHAT_ID, "🛑 Мониторинг рынка приостановлен. Для возобновления отправьте /start.")
    else:
        bot.send_message(USER_CHAT_ID, "⏸️ Мониторинг уже находится на паузе.")

if __name__ == "__main__":
    # 1. Запускаем функцию monitor_market в отдельном фоновом потоке
    threading.Thread(target=monitor_market, daemon=True).start()
    
    # Сообщение о первом старте
    bot.send_message(USER_CHAT_ID, "🚀 Бот успешно запущен! Отправьте /stop для паузы или /start для проверки статуса.")
    
    # 2. Запускаем постоянный опрос команд Telegram в основном потоке
    bot.infinity_polling()

