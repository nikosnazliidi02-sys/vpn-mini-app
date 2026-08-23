import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo

# Токен вашего бота от BotFather[cite: 4]
TOKEN = '8882701794:AAGk3m59AeZo5wChq5zSiy0t1q3DiKm-cn4'

bot = telebot.TeleBot(TOKEN)

@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_name = message.from_user.first_name or message.from_user.username or "друг"[cite: 4]
    
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
    
    # Ссылка на ваш сайт на GitHub Pages
    web_app_url = "https://nikosnazliidi02-sys.github.io/vpn-mini-app/"
    
    btn_webapp = InlineKeyboardButton(
        text="🌐 Открыть мини-приложение", 
        web_app=WebAppInfo(url=web_app_url)
    )
    btn_sub = InlineKeyboardButton(text="📊 Моя подписка", callback_data="my_sub")
    btn_buy = InlineKeyboardButton(text="💳 Купить тариф", callback_data="buy_plan")
    btn_ref = InlineKeyboardButton(text="🎁 Пригласить друга", callback_data="invite_friend")
    btn_trial = InlineKeyboardButton(text="🆓 Пробный период (3 дн.)", callback_data="trial_period")
    
    markup.add(btn_webapp)
    markup.add(btn_sub)
    markup.add(btn_buy)
    markup.add(btn_ref)
    markup.add(btn_trial)
    
    # Отправка сообщения с картинкой (убедитесь, что файл logo.png лежит рядом)
    try:
        with open('logo.png', 'rb') as photo:
            bot.send_photo(
                chat_id=message.chat.id,
                photo=photo,
                caption=welcome_text,
                parse_mode='Markdown',
                reply_markup=markup
            )
    except Exception:
        # Если картинка не найдится, бот отправит просто текст, чтобы не было ошибки
        bot.send_message(
            chat_id=message.chat.id,
            text=welcome_text,
            parse_mode='Markdown',
            reply_markup=markup
        )

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

if __name__ == '__main__':
    print("Бот успешно запущен и готов к работе! 🚀")
    bot.polling(non_stop=True)