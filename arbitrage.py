import time
import requests
import telebot
import threading
import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

# Смена кодировки для стабильной печати логов в консоль Render
sys.stdout.reconfigure(encoding='utf-8')

# --- НАСТРОЙКИ БОТА ---
TG_TOKEN = "9188990680:AAEmtD3P4Ej78ej8ARmpSXq6gDacq25ka44"
USER_CHAT_ID = "7965148154"

# Депозит изначально измеряется и отображается в долларах США ($)
CURRENT_DEPOSIT = 1000.0  
bot = telebot.TeleBot(TG_TOKEN)

MONETS = {
    "LTC": {"bybit": "LTCUSDT", "dzengi": "LTCUSDT", "withdraw_fee": 0.001},
    "XRP": {"bybit": "XRPUSDT", "dzengi": "XRPUSDT", "withdraw_fee": 0.25},
    "TRX": {"bybit": "TRXUSDT", "dzengi": "TRXUSDT", "withdraw_fee": 2.0}
}

# Актуальные комиссии для пользователей из РБ (Dzengi спот и Bybit тейкер)
DZENGI_TRADE_FEE = 0.002  # 0.2% комиссия Dzengi
BYBIT_TRADE_FEE = 0.001   # 0.1% комиссия Bybit

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

# Запрос цен без фоновых потоков (прямо в момент нажатия кнопки)
def get_live_prices(coin_info):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    
    bybit_url = f"https://bybit.com{coin_info['bybit']}"
    dzengi_url = f"https://currency.com{coin_info['dzengi']}"
    
    bybit_res = requests.get(bybit_url, headers=headers, timeout=5).json()
    dzengi_res = requests.get(dzengi_url, headers=headers, timeout=5).json()
    
    bybit_p = float(bybit_res["result"]["list"][0]["lastPrice"])
    
    if isinstance(dzengi_res, list):
        dzengi_p = float(dzengi_res["askPrice"])
    else:
        dzengi_p = float(dzengi_res["askPrice"])
        
    return dzengi_p, bybit_p

# Математический расчет круга
def calculate_deal(coin_name, dzengi_p, bybit_p, deposit):
    coin_info = MONETS[coin_name]
    
    usd_after_dzengi = deposit * (1 - DZENGI_TRADE_FEE)
    coins_bought = usd_after_dzengi / dzengi_p
    
    coins_on_bybit = coins_bought - coin_info["withdraw_fee"]
    if coins_on_bybit <= 0:
        return None
        
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

# --- ОБРАБОТЧИКИ КОМАНД ---

@bot.message_handler(commands=['start'])
def cmd_start(message):
    welcome_text = (
        f"👋 **Привет! Я твой автоматический советник по арбитражу Dzengi ➡️ Bybit.**\n\n"
        f"💰 Мой рабочий капитал сейчас настроен на: **${CURRENT_DEPOSIT:.2f} USD**\n\n"
        f"📌 **Как мной управлять:**\n"
        f"🔍 `/check` — Дать команду проанализировать биржи и выбрать, куда лучше вложиться прямо сейчас.\n"
        f"✍️ `/set X` — Сменить сумму оборотного капитала (например: `/set 500` или `/set 2000`)."
    )
    bot.send_message(message.chat.id, welcome_text, parse_mode="Markdown")

@bot.message_handler(commands=['set'])
def cmd_set_deposit(message):
    global CURRENT_DEPOSIT
    try:
        args = message.text.split()
        if len(args) < 2:
            bot.send_message(message.chat.id, "❌ Укажите сумму в $. Пример: `/set 750`", parse_mode="Markdown")
            return
        new_dep = float(args[1])
        if new_dep <= 0:
            raise ValueError
        CURRENT_DEPOSIT = new_dep
        bot.send_message(message.chat.id, f"✅ Рабочий капитал успешно изменен! Теперь расчет идет под сумму **${CURRENT_DEPOSIT:.2f} USD**.", parse_mode="Markdown")
    except ValueError:
        bot.send_message(message.chat.id, "❌ Введите корректное положительное число долларов после команды.")

@bot.message_handler(commands=['check'])
def cmd_check_market(message):
    bot.send_chat_action(message.chat.id, 'typing')
    
    best_coin = None
    best_data = None
    errors_occurred = []
    
    # Прямой опрос всех заложенных монет
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
            
    # Если хостинг намертво заблокирован Cloudflare-ом со стороны бирж
    if len(errors_occurred) == len(MONETS):
        error_msg = (
            f"❌ **Биржи заблокировали запрос от Render!**\n"
            f"Защитные системы Cloudflare отклоняют сетевой адрес хостинга.\n"
            f"Технический лог сбоя:\n`{', '.join(errors_occurred)}`"
        )
        bot.send_message(message.chat.id, error_msg, parse_mode="Markdown")
        return
        
    # Блок принятия решений: советуем, куда лучше инвестировать
    if best_data and best_data["net_profit"] > 0:
        report = (
            f"💡 **РЕКОМЕНДАЦИЯ АНАЛИТИКА: Лучше всего вложиться в {best_coin}!**\n\n"
            f"📊 **Анализ круга арбитража:**\n"
            f"💵 Ваш стартовый бюджет: **${CURRENT_DEPOSIT:.2f} USD**\n"
            f"🟢 Чистая прибыль на выходе: **+${best_data['net_profit']:.2f} USD**\n"
            f"📈 Доходность с одного круга: **{best_data['percent']:.2f}%** чистого профита\n\n"
            f"🚀 **ИНСТРУКЦИЯ ПО ВЫПОЛНЕНИЮ КРУГА:**\n"
            f"1️⃣ Зайдите на **Dzengi** и инвестируйте ваши **${CURRENT_DEPOSIT:.2f} USD** в покупку монеты **{best_coin}** по курсу **${best_data['dzengi_p']:.4f}**.\n"
            f"   *(Вы получите примерно {best_data['coins_bought']:.4f} {best_coin} уже с вычетом налога 0.2%)*\n\n"
            f"2️⃣ Скопируйте ваш адрес кошелька для {best_coin} на бирже Bybit, вернитесь на Dzengi и оформите **ВЫВОД** всех монет туда.\n"
            f"   *(Сеть вычтет мелкую фиксированную комиссию за транзакцию автоматом)*\n\n"
            f"3️⃣ Как только депозит отобразится на **Bybit**, моментально продайте {best_coin} в стакан к USDT по цене **${best_data['bybit_p']:.4f}**.\n\n"
            f"🔄 **Финал:** Деньги вернулись в баксы на Bybit с плюсом. Перегоняйте их обратно на Dzengi (на карту РБ или через доступные шлюзы) и повторяйте!"
        )
        bot.send_message(message.chat.id, report, parse_mode="Markdown")
    else:
        # Если все монеты дают минус из-за комиссий вывода
        bot.send_message(message.chat.id, f"📉 **РЕКОМЕНДАЦИЯ АНАЛИТИКА:** Прямо сейчас вкладывать доллары **НЕЛЬЗЯ**.\n\n"
                                          f"Из-за текущих курсов и комиссий на биржах все круги по LTC, XRP и TRX уходят в минус. "
                                          f"Сохраняйте ваши ${CURRENT_DEPOSIT:.2f} USD на балансе и повторите команду `/check` чуть позже, когда рынок изменится.")

if __name__ == "__main__":
    threading.Thread(target=run_dummy_server, daemon=True).start()
    print("Бот запущен. Ожидание сигналов...")
    bot.infinity_polling()
