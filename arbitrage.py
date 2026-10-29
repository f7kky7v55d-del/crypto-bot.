import time
import requests
import telebot

# --- НАСТРОЙКИ БОТА ---
# Токен очищен от невидимых символов, пробелов и русской буквы Х
TG_TOKEN = "9188990680:AAG8uQ_jl094-AQligfEQJFDdXnHIdf48dI"
USER_CHAT_ID = "7965148154"
MIN_SPREAD = 1.2  # Минимальный спред в %
CHECK_INTERVAL = 15  # Проверка каждые 15 секунд

bot = telebot.TeleBot(TG_TOKEN)


def get_bybit_price():
    """Получает актуальную цену LTC/USDT на Bybit через технический API"""
    try:
        url = "https://bybit.com"
        response = requests.get(url, timeout=5).json()
        price = float(response["result"]["list"][0]["lastPrice"])
        return price
    except Exception:
        return None


def get_dzengi_price():
    """Получает цену Ask LTC/USDT на Dzengi через технический API"""
    try:
        url = "https://currency.com"
        response = requests.get(url, timeout=5).json()
        price = float(response["ask"])
        return price
    except Exception:
        return None


def monitor_market():
    # Отправляем тестовое сообщение, чтобы убедиться, что токен живой
    bot.send_message(
        USER_CHAT_ID,
        "🚀 Бот-информатор запущен и мониторит рынок РБ ⇄ Bybit!",
    )

    while True:
        bybit_ltc = get_bybit_price()
        dzengi_ltc = get_dzengi_price()

        if bybit_ltc and dzengi_ltc:
            if dzengi_ltc < bybit_ltc:
                spread = ((bybit_ltc - dzengi_ltc) / dzengi_ltc) * 100

                if spread >= MIN_SPREAD:
                    message = (
                        f"🚨 **НАЙДЕНА СВЯЗКА LTC!**\n\n"
                        f"🔹 Цена Dzengi (РБ): **${dzengi_ltc:.2f}**\n"
                        f"🔸 Цена Bybit: **${bybit_ltc:.2f}**\n\n"
                        f"📈 Чистый спред: 🔥 **{spread:.2f}%**\n"
                        f"💼 Профит с $1000: ~**${(1000 * spread / 100):.2f}**\n\n"
                        f"ℹ️ *Купи LTC на Dzengi, переведи на Bybit и продай в USDT!*"
                    )
                    bot.send_message(
                        USER_CHAT_ID, message, parse_mode="Markdown"
                    )
                    # Засыпаем на 3 минуты после сигнала, чтобы не спамить
                    time.sleep(180)

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    monitor_market()
