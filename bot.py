import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
import httpx

TOKEN = '8882701794:AAGk3m59AeZo5wChq5zSiy0t1q3DiKm-cn4'
ADMIN_ID = "883071272" # Замените на ваш Telegram ID администратора при необходимости

bot = telebot.TeleBot(TOKEN)
API_URL = "https://vpn-mini-app.onrender.com"

@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_name = message.from_user.first_name or message.from_user.username or "друг"[cite: 14, 17]
    welcome_text = (
        f"**Приветствуем тебя, {user_name}!**\n\n"
        f"**afroVPN** — это быстрый VPN-сервис с самыми "
        f"быстрыми серверами, который работает у "
        f"100% пользователей в России.\n\n"
        f"Открывай личный кабинет прямо из Telegram "
        f"— там можно посмотреть статус подписки, "
        f"тарифы и поддержку."
    )
    
    markup = InlineKeyboardMarkup()
    web_app_url = "https://nikosnazliidi02-sys.github.io/vpn-mini-app/"
    
    btn_webapp = InlineKeyboardButton(text="🌐 Открыть мини-приложение", web_app=WebAppInfo(url=web_app_url))
    btn_sub = InlineKeyboardButton(text="📊 Моя подписка", callback_data="my_sub")
    btn_buy = InlineKeyboardButton(text="💳 Купить тариф", callback_data="buy_plan")
    btn_ref = InlineKeyboardButton(text="🎁 Пригласить друга", callback_data="invite_friend")
    btn_trial = InlineKeyboardButton(text="🆓 Пробный период (3 дн.)", callback_data="trial_period")
    
    markup.add(btn_webapp)
    markup.add(btn_sub)
    markup.add(btn_buy)
    markup.add(btn_ref)
    markup.add(btn_trial)
    
    try:
        with open('logo.png', 'rb') as photo:
            bot.send_photo(chat_id=message.chat.id, photo=photo, caption=welcome_text, parse_mode='Markdown', reply_markup=markup)
    except Exception:
        bot.send_message(chat_id=message.chat.id, text=welcome_text, parse_mode='Markdown', reply_markup=markup)

@bot.message_handler(commands=['admin'])
def admin_panel(message):
    if str(message.from_user.id) != ADMIN_ID:
        bot.send_message(message.chat.id, "У вас нет доступа к админ-панели.")
        return
    
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton(text="📢 Сделать рассылку новостей", callback_data="broadcast_news"))
    bot.send_message(message.chat.id, "👑 **Админ-панель afroVPN**\nВыберите действие:", parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
def handle_query(call):
    if call.data == "my_sub":
        bot.answer_callback_query(call.id, "Откройте мини-приложение для просмотра подписки.")
    elif call.data == "buy_plan":
        bot.answer_callback_query(call.id, "Откройте мини-приложение для покупки тарифа.")
    elif call.data == "invite_friend":
        bot.answer_callback_query(call.id, "Ваша реферальная ссылка в мини-приложении.")
    elif call.data == "trial_period":
        bot.answer_callback_query(call.id, "Пробный период активирован!")
    elif call.data == "broadcast_news":
        bot.answer_callback_query(call.id, "Отправьте текст для рассылки через API бэкенда.")

if __name__ == '__main__':
    print("Бот успешно запущен и готов к работе! 🚀")
    bot.polling(non_stop=True)