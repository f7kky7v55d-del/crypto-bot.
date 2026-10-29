import time
import requests
import telebot

TG_TOKEN = "9188990680:AAG8uQ_jl094-AQligfEQJFDdXnHIdf48dI"
USER_CHAT_ID = "7965148154"
MIN_SPREAD = 1.2
CHECK_INTERVAL = 10

bot = telebot.TeleBot(TG_TOKEN)

# Монеты и их правильные тикеры для Bybit и Dzengi
MONETS = {
    "LTC": {"bybit": "LTCUSDT", "dzengi": "LTC/USDT"},
    "XRP": {"bybit": "XRPUSDT", "dzengi": "XRP/USDT"},
    "TRX": {"bybit": "TRXUSDT", "dzengi": "TRX/USDT"}
}

def get_prices(coin_info):
    try:
        # Прямые запросы к техническим API серверов
        bybit_res = requests.get(f"https://bybit.com{coin_info['bybit']}", timeout=5).json()
        dzengi_res = requests.get(f"https://currency.com{coin_info['dzengi']}", timeout=5).json()
        
        bybit_price = float(bybit_res["result"]["list"][0]["lastPrice"])
        dzengi_price = float(dzengi_res["ask"])
        return dzengi_price, bybit_price
    except:
        return None, None

def monitor_market():
    bot.send_message(USER_CHAT_ID, "🔥 Мульти-бот запущен! Мониторю LTC, XRP, TRX 24/7...")
    while True:
        for coin_name, coin_info in MONETS.items():
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
                    time.sleep(60) # Пауза 1 минута, чтобы не спамить одной монетой
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    monitor_market()
