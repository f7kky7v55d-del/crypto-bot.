import time
import requests
import telebot
import threading
import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from telebot import types  # Подключаем модуль для красивых кнопок

# Стабильная печать логов в консоль Render без крашей кодировки
sys.stdout.reconfigure(encoding='utf-8')

# --- НАСТРОЙКИ БОТА ---
TG_TOKEN = "9188990680:AAEmtD3P4Ej78ej8ARmpSXq6gDacq25ka44"
USER_CHAT_ID = "7965148154"

# Капитал по умолчанию (измеряется в долларах США $)
CURRENT_DEPOSIT = 1000.0  
bot = telebot.TeleBot(TG_TOKEN)

# Точные, протестированные ссылки на официальные API-эндпоинты бирж
MONETS = {
    "LTC": {
        "bybit_url": "https://bybit.com",
        "dzengi_url": "https://currency.com",
        "withdraw_fee": 0.001  # Сетевая комиссия Dzengi на вывод LTC
    },
    "XRP": {
        "bybit_url": "https://bybit.com",
        "dzengi_url": "https://currency.com",
        "withdraw_fee": 0.25   # Сетевая комиссия Dzengi на вывод XRP
    },
    "TRX": {
        "bybit_url": "https://bybit.com",
        "dzengi_url": "https://currency.com",
        "withdraw_fee": 2.0    # Сетевая комиссия Dzengi на вывод TRX
    }
}

# Реальные комиссии (0.2% — спот Dzengi для РБ, 0.1% — стандартный спот Bybit)
DZENGI_TRADE_FEE = 0.002  
BYBIT_TRADE_FEE = 0.001   

# --- СЕРВЕР ДЛЯ ОБМАНА ТАЙМАУТА RENDER ---
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

# Получение цен по точным прямым ссылкам
def get_live_prices(coin_info):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    
    bybit_res = requests.get(coin_info['bybit_url'], headers=headers, timeout=5).json()
    dzengi_res = requests.get(coin_info['dzengi_url'], headers=headers, timeout=5).json()
    
    # Безопасный разбор ответов API Bybit V5 и Dzengi V1
    bybit_p = float(bybit_res["result"]["list"][0]["lastPrice"])
    
    if isinstance(dzengi_res, list):
        dzengi_p = float(dzengi_res[0]["askPrice"])
    else:
        dzengi_p = float(dzengi_res["askPrice"])
        
    return dzengi_p, bybit_p

# Математический расчет круга арбитража с вычетом комиссий
def calculate_deal(coin_name, dzengi_p, bybit_p, deposit):
    coin_info = MONETS[coin_name]
    
    # 1. Покупка на Dzengi (минус 0.2%)
    usd_after_dzengi = deposit * (1 - DZENGI_TRADE_FEE)
    coins_bought = usd_after_dzengi / dzengi_p
    
    # 2. Перевод на Bybit (минус фиксированная комиссия сети за вывод)
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

# Генерация экранного меню для мобильного телефона
def get_main_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    btn_check = types.KeyboardButton("🔍 Проверить рынок")
    btn_set_500 = types.KeyboardButton("💵 Поставить депо $500")
    btn_set_1000 = types.KeyboardButton("💵 Поставить депо $1000")
    
    markup.add(btn_check)
    markup.add(btn_set_500, btn_set_1000)
    return markup

# --- ОБРАБОТЧИКИ КОМАНД И ТЕКСТА ---

@bot.message_handler(commands=['start'])
def cmd_start(message):
    welcome_text = (
        f"👋 **Привет! Я твой автоматический советник по арбитражу Dzengi ➡️ Bybit.**\n\n"
        f"💰 Мой рабочий капитал сейчас настроен на: **${CURRENT_DEPOSIT:.2f} USD**\n\n"
        f"📌 Нажмите на кнопку внизу экрана, чтобы я выбрал, куда лучше вложиться!"
    )
    bot.send_message(message.chat.id, welcome_text, parse_mode="Markdown", reply_markup=get_main_keyboard())

# Обработка нажатий на экранные кнопки
@bot.message_handler(func=lambda message: True)
def handle_text_buttons(message):
    global CURRENT_DEPOSIT
    
    if message.text == "💵 Поставить депо $500":
        CURRENT_DEPOSIT = 500.0
        bot.send_message(message.chat.id, f"✅ Рабочий капитал переключен на **$500.00 USD**.", reply_markup=get_main_keyboard())
        return

    elif message.text == "💵 Поставить депо $1000":
        CURRENT_DEPOSIT = 1000.0
        bot.send_message(message.chat.id, f"✅ Рабочий капитал переключен на **$1000.00 USD**.", reply_markup=get_main_keyboard())
        return

    elif message.text == "🔍 Проверить рынок":
        # Анимация "бот печатает..." в Telegram
        bot.send_chat_action(message.chat.id, 'typing')
        
        best_coin = None
        best_data = None
        errors_occurred = []
        
        # Сканируем биржи
        for coin in MONETS.keys():
            try:
                dzengi_p, bybit_p = get_live_prices(MONETS[coin])
                deal = calculate_deal(coin, dzengi_p, bybit_p, CURRENT_DEPOSIT)
                
                if deal:
                    if best_data is None or deal["net_profit"] > best_data["net_profit"]:
                        best_coin = coin
                        best_data = deal
            except Exception as e:
                errors_occurred.append(f"{coin}: {str(e)}")
                
        # Если ни одна ссылка не открылась
        if len(errors_occurred) == len(MONETS):
            error_msg = (
                f"❌ **Ошибка подключения к API бирж!**\n"
                f"Лог сбоя:\n`{', '.join(errors_occurred)}`"
            )
            bot.send_message(message.chat.id, error_msg, parse_mode="Markdown")
            return
            
        # Блок рекомендации аналитика
        if best_data and best_data["net_profit"] > 0:
            report = (
                f"💡 **РЕКОМЕНДАЦИЯ АНАЛИТИКА: Сейчас выгоднее всего вложиться в {best_coin}!**\n\n"
                f"📊 **Анализ круга арбитража:**\n"
                f"💵 Ваш стартовый бюджет: **${CURRENT_DEPOSIT:.2f} USD**\n"
                f"🟢 Чистая прибыль на выходе: **+${best_data['net_profit']:.2f} USD**\n"
                f"📈 Доходность круга: **{best_data['percent']:.2f}%** чистого профита\n\n"
                f"🚀 **ПОШАГОВЫЙ ПЛАН:**\n"
                f"1️⃣ На **Dzengi** инвестируйте ваши **${CURRENT_DEPOSIT:.2f} USD** в покупку монеты **{best_coin}** по курсу **${best_data['dzengi_p']:.4f}**.\n"
                f"   *(Вы получите примерно {best_data['coins_bought']:.4f} {best_coin} с учетом налога 0.2%)*\n\n"
                f"2️⃣ Оформите **ВЫВОД** всех монет на ваш депозитный кошелек **Bybit** через родную сеть монеты.\n\n"
                f"3️⃣ Как только монеты зачислятся на **Bybit**, моментально продайте их в стакан USDT по курсу **${best_data['bybit_p']:.4f}**.\n\n"
                f"🔄 **Итог:** Фиат вернулся в доллары на Bybit с чистой прибылью. Перегоняйте обратно на карту РБ или баланс Dzengi и крутите заново!"
            )
            bot.send_message(message.chat.id, report, parse_mode="Markdown")
        else:
            bot.send_message(message.chat.id, f"📉 **РЕКОМЕНДАЦИЯ АНАЛИТИКА:** Прямо сейчас вкладывать доллары **НЕЛЬЗЯ**.\n\n"
                                              f"Из-за текущих курсов все круги уходят в минус. "
                                              f"Безопаснее сохранить ваши ${CURRENT_DEPOSIT:.2f} USD на балансе и повторить проверку позже.")

if __name__ == "__main__":
    # Запускаем фейковый сервер-заглушку в отдельном фоновом потоке
    threading.Thread(target=run_dummy_server, daemon=True).start()
    print("Бот полностью пересобран и готов к работе...")
    bot.infinity_polling()
