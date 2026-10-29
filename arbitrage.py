import time
import requests
import telebot
import threading
import os
from http.server import BaseHTTPRequestHandler, HTTPServer

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

# --- КОСТЫЛЬ ДЛЯ RENDER (ФЕЙКОВЫЙ СЕРВЕР) ---
class WebhookServer(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(b"Bot is running smoothly!")

def run_dummy_server():
    # Render автоматически передает номер порта в переменную PORT.
    # Если ее нет, по умолчанию возьмется порт 10000.
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), WebhookServer)
    print(f"Фейковый сервер запущен на порту {port} для обмана Render")
    server.serve_forever()
# ---------------------------------------------

def get_prices(coin_info):
    try:
        # Официальный публичный REST API Bybit V5 (категория spot)
        bybit_url = f"https://bybit.com{coin_info['bybit']}"
        bybit_res = requests.get(bybit_url, timeout=5).json()
        
        # Официальный публичный REST API Currency.com (Dzengi)
        dzengi_url = f"https://currency.com{coin_info['dzengi']}"
        dzengi_res = requests.get(dzengi_url, timeout=5).json()
        
        # Безопасный разбор ответов
        bybit_price = float(bybit_res["result"]["list"][0]["lastPrice"])
        
        if isinstance(dzengi_res, list):
            dzengi_price = float(dzengi_res[0]["askPrice"])
        else:
            dzengi_price = float(dzengi_res["askPrice"])
            
        return dzengi_price, bybit_price
    except Exception as e:
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
                        print(f"Ошибка Telegram: {tg_err}")
                        
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
    # 1. Запуск фейкового веб-сервера в отдельном потоке (для прохождения проверки Render)
    threading.Thread(target=run_dummy_server, daemon=True).start()
    
    # 2. Запуск мониторинга рынка во второстепенном потоке
    threading.Thread(target=monitor_market, daemon=True).start()
    
    print("Бот успешно запущен на компьютере!")
    
    # Стартовый сигнал в чат
    try:
        bot.send_message(USER_CHAT_ID, "🚀 Бот успешно запущен на Render с обходом портов! Отправьте /stop для паузы или /start для запуска.")
    except Exception as e:
        print(f"Ошибка отправки стартового сообщения: {e}")
    
    # 3. Основной поток отдаем под бесконечный опрос Telegram-команд
    bot.infinity_polling()
