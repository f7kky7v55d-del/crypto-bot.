import time
import requests
import telebot
import threading

# --- НАСТРОЙКИ БОТА ---
TG_TOKEN = "9188990680:AAEmtD3P4Ej78ej8ARmpSXq6gDacq25ka44"
USER_CHAT_ID = "7965148154"
MIN_SPREAD = 1.2
CHECK_INTERVAL = 10

bot = telebot.TeleBot(TG_TOKEN)

# Глобальный флаг управления (True - включен, False - на паузе)
IS_RUNNING = True

# Монеты и их точные тикеры для официальных API-запросов
MONETS = {
    "LTC": {"bybit": "LTCUSDT", "dzengi": "LTCUSDT"},
    "XRP": {"bybit": "XRPUSDT", "dzengi": "XRPUSDT"},
    "TRX": {"bybit": "TRXUSDT", "dzengi": "TRXUSDT"}
}

def get_prices(coin_info):
    try:
        # Официальный публичный REST API Bybit V5 (категория spot)
        bybit_url = f"https://bybit.com{coin_info['bybit']}"
        bybit_res = requests.get(bybit_url, timeout=5).json()
        
        # Официальный публичный REST API Currency.com (Dzengi)
        dzengi_url = f"https://currency.com{coin_info['dzengi']}"
        dzengi_res = requests.get(dzengi_url, timeout=5).json()
        
        # Исправленный безопасный разбор ответов
        bybit_price = float(bybit_res["result"]["list"][0]["lastPrice"])
        
        # На Dzengi ответ приходит либо объектом, либо массивом из одного объекта
        if isinstance(dzengi_res, list):
            dzengi_price = float(dzengi_res[0]["askPrice"])
        else:
            dzengi_price = float(dzengi_res["askPrice"])
            
        return dzengi_price, bybit_price
    except Exception as e:
        # Если API временно недоступно или пропал интернет — бот не падает, а логирует ошибку
        print(f"Ошибка получения цен для {coin_info['bybit']}: {e}")
        return None, None

# Фоновая функция циклического мониторинга
def monitor_market():
    global IS_RUNNING
    while True:
        # Если отправили команду /stop, поток просто "спит" и ждет /start
        if not IS_RUNNING:
            time.sleep(1)
            continue
            
        for coin_name, coin_info in MONETS.items():
            # Дополнительная проверка, чтобы мгновенно прервать цикл при /stop
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
                    try:
                        bot.send_message(USER_CHAT_ID, message, parse_mode="Markdown")
                        time.sleep(60)  # Пауза, чтобы не спамить одной и той же монетой
                    except Exception as tg_err:
                        print(f"Не удалось отправить сообщение в Telegram: {tg_err}")
                        
        time.sleep(CHECK_INTERVAL)

# Обработчик команды /start в Telegram
@bot.message_handler(commands=['start'])
def start_bot(message):
    global IS_RUNNING
    if not IS_RUNNING:
        IS_RUNNING = True
        bot.send_message(USER_CHAT_ID, "▶️ Мониторинг рынка возобновлен! Ищу связки...")
    else:
        bot.send_message(USER_CHAT_ID, "🔥 Бот уже запущен и активно сканирует цены.")

# Обработчик команды /stop в Telegram
@bot.message_handler(commands=['stop'])
def stop_bot(message):
    global IS_RUNNING
    if IS_RUNNING:
        IS_RUNNING = False
        bot.send_message(USER_CHAT_ID, "🛑 Мониторинг рынка приостановлен. Для возобновления отправьте /start.")
    else:
        bot.send_message(USER_CHAT_ID, "⏸️ Мониторинг уже стоит на паузе.")

if __name__ == "__main__":
    # 1. Запуск мониторинга рынка в фоновом потоке
    threading.Thread(target=monitor_market, daemon=True).start()
    
    # Стартовое системное уведомление
    print("Бот успешно запущен на компьютере!")
    bot.send_message(USER_CHAT_ID, "🚀 Бот успешно запущен! Отправьте /stop для паузы или /start для возобновления.")
    
    # 2. Бесконечный запуск прослушивания команд Telegram (основной поток)
    bot.infinity_polling()
