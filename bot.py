import asyncio
import logging
import sqlite3
import threading
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
import httpx

# Настройка логирования для отслеживания ошибок
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

TOKEN = '8882701794:AAGk3m59AeZo5wChq5zSiy0t1q3DiKm-cn4'
ADMIN_ID = "883071272"

bot = telebot.TeleBot(TOKEN)
API_URL = "https://vpn-mini-app.onrender.com"

# Глобальный словарь для отслеживания активных рассылок и их отмены
active_broadcasts = {}

# Глобальный event loop для фоновых задач asyncio в синхронном боте
try:
    loop = asyncio.get_running_loop()
except RuntimeError:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

def run_async_task(coro):
    """Безопасный запуск асинхронных функций из синхронных обработчиков telebot"""
    asyncio.run_coroutine_threadsafe(coro, loop)

# Функция для получения всех ID пользователей из базы данных vpn_users.db
def get_all_users() -> list:
    try:
        conn = sqlite3.connect('vpn_users.db')
        cursor = conn.cursor()
        cursor.execute("SELECT tg_id FROM notification_settings")
        rows = cursor.fetchall()
        conn.close()
        return [int(row[0]) for row in rows if str(row[0]).isdigit()]
    except Exception as e:
        logging.error(f"Ошибка чтения базы данных: {e}")
        return []

@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_name = message.from_user.first_name or message.from_user.username or "друг"
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
    
    markup.add(InlineKeyboardButton(text="🌐 Открыть мини-приложение", web_app=WebAppInfo(url=web_app_url)))
    markup.add(InlineKeyboardButton(text="📊 Моя подписка", callback_data="my_sub"))
    markup.add(InlineKeyboardButton(text="💳 Купить тариф", callback_data="buy_plan"))
    markup.add(InlineKeyboardButton(text="🎁 Пригласить друга", callback_data="invite_friend"))
    markup.add(InlineKeyboardButton(text="🆓 Пробный период (3 дн.)", callback_data="trial_period"))
    
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
    markup.add(InlineKeyboardButton(text="📈 Дашборд и статистика", callback_data="admin_stats"))
    markup.add(InlineKeyboardButton(text="💸 Модерация выплат", callback_data="admin_withdrawals"))
    markup.add(InlineKeyboardButton(text="🎟 Создать промокод", callback_data="admin_promo_prompt"))
    markup.add(InlineKeyboardButton(text="📢 Рассылка", callback_data="broadcast_news"))
    
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
    
    elif call.data == "admin_stats":
        if str(call.from_user.id) != ADMIN_ID: return
        try:
            r = httpx.get(f"{API_URL}/admin/stats", timeout=10.0)
            data = r.json()
            if data.get("success"):
                text = (
                    "📊 **Дашборд проекта:**\n\n"
                    f"👥 Уникальных пользователей: <b>{data['total_users']}</b>\n"
                    f"🟢 Активных подписок: <b>{data['active_subs']}</b>\n"
                    f"💰 Общая выручка: <b>{data['total_revenue']} ₽</b>"
                )
                bot.send_message(call.message.chat.id, text, parse_mode="HTML")
            else:
                bot.answer_callback_query(call.id, "Не удалось получить статистику.")
        except Exception as e:
            logging.error(f"Ошибка получения статистики: {e}")
            bot.answer_callback_query(call.id, "Ошибка связи с бэкендом.")
            
    elif call.data == "admin_withdrawals":
        if str(call.from_user.id) != ADMIN_ID: return
        try:
            r = httpx.get(f"{API_URL}/admin/withdrawals", timeout=10.0)
            data = r.json()
            items = data.get("withdrawals", [])
            if not items:
                bot.send_message(call.message.chat.id, "💸 Нет новых заявок на вывод средств.")
                return
            
            for item in items:
                markup = InlineKeyboardMarkup()
                markup.add(
                    InlineKeyboardButton(text="✅ Одобрить", callback_data=f"wd_app_{item['id']}"),
                    InlineKeyboardButton(text="❌ Отклонить", callback_data=f"wd_rej_{item['id']}")
                )
                msg_text = f"💳 Заявка ID: {item['id']}\n👤 TG ID: {item['tg_id']}\n💵 Сумма: {item['amount']} ₽\n📅 Дата: {item['date']}"
                bot.send_message(call.message.chat.id, msg_text, reply_markup=markup)
        except Exception as e:
            logging.error(f"Ошибка загрузки выплат: {e}")
            bot.answer_callback_query(call.id, "Ошибка загрузки выплат.")

    elif call.data.startswith("wd_app_") or call.data.startswith("wd_rej_"):
        if str(call.from_user.id) != ADMIN_ID: return
        parts = call.data.split("_")
        action = "approve" if parts[1] == "app" else "reject"
        wd_id = int(parts[2])
        try:
            r = httpx.post(f"{API_URL}/admin/withdrawal-action", json={"withdrawal_id": wd_id, "action": action}, timeout=10.0)
            if r.json().get("success"):
                bot.edit_message_text(f"Заявка #{wd_id} обработана ({action}).", call.message.chat.id, call.message.message_id)
            else:
                bot.answer_callback_query(call.id, "Ошибка при обработке.")
        except Exception as e:
            logging.error(f"Ошибка обработки выплаты: {e}")
            bot.answer_callback_query(call.id, "Ошибка соединения.")

    elif call.data == "admin_promo_prompt":
        if str(call.from_user.id) != ADMIN_ID: return
        msg = bot.send_message(call.message.chat.id, "Введите промокод и скидку в формате:\n`КОД СКИДКА%`\n(Например: `SALE20 20`)", parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_create_promo)

    elif call.data == "broadcast_news":
        if str(call.from_user.id) != ADMIN_ID: return
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton(text="❌ Отменить рассылку", callback_data="cancel_broadcast"))
        msg = bot.send_message(
            call.message.chat.id, 
            "📢 Отправьте текст, фото или видео для рассылки пользователям:", 
            reply_markup=markup
        )
        bot.register_next_step_handler(msg, process_broadcast)

    elif call.data == "cancel_broadcast":
        if str(call.from_user.id) != ADMIN_ID: return
        # Сбрасываем ожидание шага через очистку обработчика (если пользователь еще не отправил пост)
        bot.clear_step_handler_by_chat_id(call.message.chat.id)
        # Если рассылка уже шла в фоне — ставим флаг отмены
        active_broadcasts[ADMIN_ID] = False
        bot.edit_message_text("❌ Рассылка отменена.", call.message.chat.id, call.message.message_id)

def process_create_promo(message):
    if str(message.from_user.id) != ADMIN_ID: return
    parts = message.text.split()
    if len(parts) != 2:
        bot.send_message(message.chat.id, "Неверный формат. Попробуйте снова через админ-панель.")
        return
    
    code = parts[0]
    try:
        discount = int(parts[1].replace('%', ''))
        r = httpx.post(f"{API_URL}/admin/create-promo", json={"code": code, "discount_percent": discount}, timeout=10.0)
        if r.json().get("success"):
            bot.send_message(message.chat.id, f"✅ Промокод <b>{code.upper()}</b> на <b>{discount}%</b> успешно добавлен!")
        else:
            bot.send_message(message.chat.id, "Ошибка создания промокода на сервере.")
    except ValueError:
        bot.send_message(message.chat.id, "Скидка должна быть числом.")
    except Exception as e:
        logging.error(f"Ошибка запроса промокода: {e}")
        bot.send_message(message.chat.id, "Ошибка соединения с сервером.")

# Асинхронная фоновая рассылка с поддержкой отмены
async def background_broadcast(users: list, message_to_copy):
    success = 0
    blocked = 0
    active_broadcasts[ADMIN_ID] = True  дф  # Включаем флаг активности рассылки
    
    for user_id in users:
        # Проверяем, не отменил ли админ рассылку во время процесса
        if not active_broadcasts.get(ADMIN_ID, False):
            try:
                bot.send_message(ADMIN_ID, "⚠️ Рассылка была прервана (отменена администратором).")
            except Exception:
                pass
            return

        try:
            bot.copy_message(chat_id=user_id, from_chat_id=message_to_copy.chat.id, message_id=message_to_copy.message_id)
            success += 1
            await asyncio.sleep(0.05)  # Пауза против лимитов Telegram (FloodWait)
        except Exception:
            blocked += 1

    active_broadcasts[ADMIN_ID] = False

    try:
        bot.send_message(
            ADMIN_ID,
            f"📊 **Рассылка завершена!**\n\n"
            f"✅ Успешно доставлено: {success}\n"
            f"❌ Заблокировали бота: {blocked}",
            parse_mode="Markdown"
        )
    except Exception:
        pass

def process_broadcast(message):
    if str(message.from_user.id) != ADMIN_ID: return
    
    users = get_all_users()
    if not users:
        bot.send_message(message.chat.id, "⚠️ В базе данных не найдено ни одного пользователя для рассылки.")
        return
    
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton(text="🛑 Остановить рассылку", callback_data="cancel_broadcast"))
    
    bot.send_message(message.chat.id, f"🚀 Рассылка запущена для {len(users)} пользователей. Ожидайте отчет.", reply_markup=markup)
    
    # Запуск фонового процесса
    run_async_task(background_broadcast(users, message))

if __name__ == '__main__':
    # Запуск фонового потока для asyncio, чтобы бот не блокировался
    def start_loop(loop):
        asyncio.set_event_loop(loop)
        loop.run_forever()

    t = threading.Thread(target=start_loop, args=(loop,), daemon=True)
    t.start()

    print("Бот успешно запущен и готов к работе! 🚀")
    bot.infinity_polling(timeout=60, long_polling_timeout=60)