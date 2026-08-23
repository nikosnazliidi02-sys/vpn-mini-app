import sqlite3
import random
import smtplib
from email.mime.text import MIMEText
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime, timedelta
import httpx

# --- НАСТРОЙКИ ВАШЕЙ ПОЧТЫ ---
SMTP_SERVER = "smtp.mail.ru" # Или smtp.yandex.ru
SMTP_PORT = 465 # SSL порт
SMTP_EMAIL = "afrovpn@mail.ru" # Ваш email отправителя
SMTP_PASSWORD = "yGCJ2FTxrad97gsQM60T" # Тот самый пароль для приложений

app = FastAPI()

# Разрешаем запросы с вашего сайта на GitHub Pages (очень важно!)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Разрешаем все домены (для тестов)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Токен от @CryptoBot и токен вашего Telegram-бота для уведомлений
CRYPTO_BOT_TOKEN = "625448:AAdE7FGbHENh9wL9OmqYFv9buLQoSoCQRGV"
TELEGRAM_BOT_TOKEN = "8882701794:AAGk3m59AeZo5wChq5zSiy0t1q3DiKm-cn4"

# Подготовка Базы Данных
def init_db():
    conn = sqlite3.connect("vpn_users.db")
    cursor = conn.cursor()
    # Таблица для верификации почты
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS email_verifications (
            tg_id TEXT PRIMARY KEY,
            email TEXT,
            code TEXT,
            expires_at DATETIME,
            is_verified BOOLEAN DEFAULT 0
        )
    """)
    # Таблица для настроек уведомлений
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS notification_settings (
            tg_id TEXT PRIMARY KEY,
            subscription_alerts BOOLEAN DEFAULT 1,
            news_alerts BOOLEAN DEFAULT 1,
            promo_alerts BOOLEAN DEFAULT 0
        )
    """)
    conn.commit()
    conn.close()

init_db()

# Функция отправки письма
def send_email(to_email, code):
    msg = MIMEText(f"Ваш код подтверждения для AFROVPN: {code}")
    msg["Subject"] = "Код подтверждения AFROVPN"
    msg["From"] = SMTP_EMAIL
    msg["To"] = to_email

    try:
        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT) as server:
            server.login(SMTP_EMAIL, SMTP_PASSWORD)
            server.sendmail(SMTP_EMAIL, to_email, msg.as_string())
    except Exception as e:
        print(f"Ошибка отправки письма: {e}")
        return False
    return True

# Модели данных
class EmailRequest(BaseModel):
    tg_id: str
    email: str

class CodeVerify(BaseModel):
    tg_id: str
    code: str

class InvoiceRequest(BaseModel):
    tg_id: str
    amount: float
    description: str

class NotificationSettings(BaseModel):
    tg_id: str
    subscription_alerts: bool
    news_alerts: bool
    promo_alerts: bool

class BroadcastRequest(BaseModel):
    message: str
    alert_type: str # 'news', 'promo' или 'subscription'

# 1. Эндпоинт: ОТПРАВИТЬ КОД
@app.post("/send-code")
def send_code(req: EmailRequest):
    code = str(random.randint(100000, 999999)) # Генерируем 6 цифр
    expires = datetime.now() + timedelta(minutes=10) # Код живет 10 минут
    
    conn = sqlite3.connect("vpn_users.db")
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO email_verifications (tg_id, email, code, expires_at, is_verified)
        VALUES (?, ?, ?, ?, 0)
        ON CONFLICT(tg_id) DO UPDATE SET 
        email=excluded.email, code=excluded.code, expires_at=excluded.expires_at, is_verified=0
    """, (req.tg_id, req.email, code, expires))
    conn.commit()
    conn.close()

    if send_email(req.email, code):
        return {"success": True, "message": "Код отправлен"}
    else:
        raise HTTPException(status_code=500, detail="Ошибка отправки письма")

# 2. Эндпоинт: ПРОВЕРИТЬ КОД
@app.post("/verify-code")
def verify_code(req: CodeVerify):
    conn = sqlite3.connect("vpn_users.db")
    cursor = conn.cursor()
    cursor.execute("SELECT code, expires_at FROM email_verifications WHERE tg_id = ?", (req.tg_id,))
    row = cursor.fetchone()
    
    if not row:
        raise HTTPException(status_code=400, detail="Код не запрашивался")
    
    db_code, expires_at = row
    expires_at = datetime.strptime(expires_at, "%Y-%m-%d %H:%M:%S.%f")

    if datetime.now() > expires_at:
        raise HTTPException(status_code=400, detail="Срок действия кода истек")
    
    if req.code != db_code:
        raise HTTPException(status_code=400, detail="Неверный код")
    
    cursor.execute("UPDATE email_verifications SET is_verified = 1 WHERE tg_id = ?", (req.tg_id,))
    conn.commit()
    conn.close()

    return {"success": True, "message": "Почта подтверждена"}

# 3. Эндпоинт: СОЗДАТЬ СЧЕТ В CRYPTOBOT
@app.post("/create-crypto-invoice")
async def create_crypto_invoice(req: InvoiceRequest):
    url = "https://pay.crypt.bot/api/createInvoice"
    
    headers = {
        "Crypto-Pay-API-Token": CRYPTO_BOT_TOKEN,
        "Content-Type": "application/json"
    }
    
    payload = {
        "asset": "USDT",
        "amount": str(req.amount),
        "description": req.description,
        "payload": str(req.tg_id),
        "paid_btn_name": "callback",
        "paid_btn_url": "https://t.me/afroVPN_bot"
    }
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, json=payload, headers=headers)
            result = response.json()
            
            if result.get("ok"):
                invoice = result["result"]
                return {
                    "success": True,
                    "pay_url": invoice["pay_url"],
                    "invoice_id": invoice["invoice_id"]
                }
            else:
                error_msg = result.get("error", {}).get("name", "Ошибка создания счета")
                raise HTTPException(status_code=400, detail=error_msg)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))[cite: 4]

# 4. Эндпоинт: СОХРАНЕНИЕ НАСТРОЕК УВЕДОМЛЕНИЙ И ОТПРАВКА В TELEGRAM
@app.post("/update-notifications")
async def update_notifications(req: NotificationSettings):
    conn = sqlite3.connect("vpn_users.db")
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO notification_settings (tg_id, subscription_alerts, news_alerts, promo_alerts)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(tg_id) DO UPDATE SET 
        subscription_alerts=excluded.subscription_alerts, 
        news_alerts=excluded.news_alerts, 
        promo_alerts=excluded.promo_alerts
    """, (req.tg_id, req.subscription_alerts, req.news_alerts, req.promo_alerts))
    conn.commit()
    conn.close()

    # Отправляем пользователю сообщение в Telegram о том, что настройки применились
    text = (
        "⚙️ **Настройки уведомлений обновлены:**\n"
        f"• Окончание подписки: {'✅ Вкл' if req.subscription_alerts else '❌ Выкл'}\n"
        f"• Новости и обновления: {'✅ Вкл' if req.news_alerts else '❌ Выкл'}\n"
        f"• Акции и предложения: {'✅ Вкл' if req.promo_alerts else '❌ Выкл'}"
    )
    
    async with httpx.AsyncClient() as client:
        try:
            await client.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", json={
                "chat_id": req.tg_id,
                "text": text,
                "parse_mode": "Markdown"
            })
        except Exception as e:
            print(f"Не удалось отправить уведомление в Telegram: {e}")

    return {"success": True}

# 5. Эндпоинт: СДЕРИТЬ РАССЫЛКУ УВЕДОМЛЕНИЙ ПО ПОЛЬЗОВАТЕЛЯМ
@app.post("/send-broadcast")
async def send_broadcast(req: BroadcastRequest):
    conn = sqlite3.connect("vpn_users.db")
    cursor = conn.cursor()
    
    # Выбираем только тех пользователей, у которых включен соответствующий тумблер
    if req.alert_type == "news":
        cursor.execute("SELECT tg_id FROM notification_settings WHERE news_alerts = 1")
    elif req.alert_type == "promo":
        cursor.execute("SELECT tg_id FROM notification_settings WHERE promo_alerts = 1")
    elif req.alert_type == "subscription":
        cursor.execute("SELECT tg_id FROM notification_settings WHERE subscription_alerts = 1")
    else:
        conn.close()
        raise HTTPException(status_code=400, detail="Неверный тип уведомления")
        
    users = cursor.fetchall()
    conn.close()
    
    async with httpx.AsyncClient() as client:
        sent_count = 0
        for row in users:
            tg_id = row[0]
            try:
                await client.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", json={
                    "chat_id": tg_id,
                    "text": req.message,
                    "parse_mode": "Markdown"
                })
                sent_count += 1
            except Exception as e:
                print(f"Не удалось отправить сообщение пользователю {tg_id}: {e}")
                
    return {"success": True, "sent_count": sent_count}