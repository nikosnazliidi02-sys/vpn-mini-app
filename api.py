import sqlite3
import random
import smtplib
from email.mime.text import MIMEText
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime, timedelta
import httpx
import asyncio

SMTP_SERVER = "smtp.mail.ru"
SMTP_PORT = 465
SMTP_EMAIL = "afrovpn@mail.ru"
SMTP_PASSWORD = "yGCJ2FTxrad97gsQM60T"

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

CRYPTO_BOT_TOKEN = "625448:AAdE7FGbHENh9wL9OmqYFv9buLQoSoCQRGV"
TELEGRAM_BOT_TOKEN = "8882701794:AAGk3m59AeZo5wChq5zSiy0t1q3DiKm-cn4"

def init_db():
    with sqlite3.connect("vpn_users.db") as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS email_verifications (
                tg_id TEXT PRIMARY KEY,
                email TEXT,
                code TEXT,
                expires_at DATETIME,
                is_verified BOOLEAN DEFAULT 0
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS notification_settings (
                tg_id TEXT PRIMARY KEY,
                subscription_alerts BOOLEAN DEFAULT 1,
                news_alerts BOOLEAN DEFAULT 1,
                promo_alerts BOOLEAN DEFAULT 0
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS referrals (
                referrer_id TEXT,
                referred_id TEXT,
                PRIMARY KEY (referrer_id, referred_id)
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tg_id TEXT,
                amount REAL,
                description TEXT,
                date TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS subscriptions (
                tg_id TEXT PRIMARY KEY,
                expires_at TEXT,
                status TEXT DEFAULT 'expired'
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS promocodes (
                code TEXT PRIMARY KEY,
                discount_percent INTEGER
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS withdrawals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tg_id TEXT,
                amount REAL,
                status TEXT DEFAULT 'pending',
                date TEXT
            )
        """)
        # Таблица для отслеживания отправленных уведомлений по срокам
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sent_notifications (
                tg_id TEXT,
                notification_type TEXT,
                expires_at TEXT,
                PRIMARY KEY (tg_id, notification_type, expires_at)
            )
        """)
        cursor.execute("INSERT OR IGNORE INTO promocodes (code, discount_percent) VALUES ('PROMO10', 10)")
        conn.commit()

init_db()

# ФОНОВАЯ ЗАДАЧА: Проверка подписок и отправка уведомлений (7 дней, 3 дня, 24 часа, истечение)
async def check_subscriptions_loop():
    while True:
        try:
            now = datetime.now()
            with sqlite3.connect("vpn_users.db") as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT tg_id, expires_at, status FROM subscriptions WHERE status = 'active'")
                subs = cursor.fetchall()
                
                async with httpx.AsyncClient() as client:
                    for tg_id, expires_at_str, status in subs:
                        try:
                            exp_date = datetime.fromisoformat(expires_at_str)
                        except Exception:
                            continue
                        
                        # Проверяем настройки уведомлений пользователя
                        cursor.execute("SELECT subscription_alerts FROM notification_settings WHERE tg_id = ?", (tg_id,))
                        setting = cursor.fetchone()
                        allow_alerts = setting[0] if setting else 1
                        
                        if allow_alerts != 1:
                            continue
                            
                        total_hours = (exp_date - now).total_seconds() / 3600
                        
                        # Функция отправки с записью в БД, чтобы не спамить каждый час
                        async def send_milestone(m_type, text):
                            cursor.execute(
                                "SELECT 1 FROM sent_notifications WHERE tg_id = ? AND notification_type = ? AND expires_at = ?",
                                (tg_id, m_type, expires_at_str)
                            )
                            if not cursor.fetchone():
                                await client.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", json={
                                    "chat_id": tg_id,
                                    "text": text,
                                    "parse_mode": "Markdown"
                                })
                                cursor.execute(
                                    "INSERT OR IGNORE INTO sent_notifications (tg_id, notification_type, expires_at) VALUES (?, ?, ?)",
                                    (tg_id, m_type, expires_at_str)
                                )
                                conn.commit()

                        if total_hours <= 0:
                            await send_milestone('expired', "❌ **Подписка истекла.**\nДоступ к серверам приостановлен. Пожалуйста, оплатите тариф в мини-приложении.")
                            cursor.execute("UPDATE subscriptions SET status = 'expired' WHERE tg_id = ?", (tg_id,))
                            conn.commit()
                        elif total_hours <= 24:
                            await send_milestone('24h', "⚠️ **Внимание!** Срок вашей подписки на afroVPN истекает через 24 часа. Продлите доступ в мини-приложении.")
                        elif total_hours <= 72: # 3 дня
                            await send_milestone('3d', "⏳ **Напоминание:** До окончания вашей подписки на afroVPN осталось 3 дня.")
                        elif total_hours <= 168: # 7 дней
                            await send_milestone('7d', "🔔 **Информация:** До окончания вашей подписки на afroVPN осталась 1 неделя (7 дней).")
                                    
        except Exception as e:
            print(f"Ошибка в фоновой проверке подписок: {e}")
            
        await asyncio.sleep(3600)  # Проверка запускается раз в час

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(check_subscriptions_loop())

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
    alert_type: str

class ReferralTrack(BaseModel):
    referrer_id: str
    referred_id: str

class PromoApply(BaseModel):
    code: str

class WithdrawRequest(BaseModel):
    tg_id: str

@app.post("/send-code")
def send_code(req: EmailRequest):
    code = str(random.randint(100000, 999999))
    expires = datetime.now() + timedelta(minutes=10)
    
    with sqlite3.connect("vpn_users.db") as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO email_verifications (tg_id, email, code, expires_at, is_verified)
            VALUES (?, ?, ?, ?, 0)
            ON CONFLICT(tg_id) DO UPDATE SET 
            email=excluded.email, code=excluded.code, expires_at=excluded.expires_at, is_verified=0
        """, (req.tg_id, req.email, code, expires))
        conn.commit()

    if send_email(req.email, code):
        return {"success": True, "message": "Код отправлен"}
    else:
        raise HTTPException(status_code=500, detail="Ошибка отправки письма")

@app.post("/verify-code")
def verify_code(req: CodeVerify):
    with sqlite3.connect("vpn_users.db") as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT code, expires_at FROM email_verifications WHERE tg_id = ?", (req.tg_id,))
        row = cursor.fetchone()
    
    if not row:
        raise HTTPException(status_code=400, detail="Код не запрашивался")
    
    db_code, expires_at_str = row
    try:
        expires_at = datetime.fromisoformat(expires_at_str)
    except Exception:
        raise HTTPException(status_code=500, detail="Ошибка формата даты в базе данных")

    if datetime.now() > expires_at:
        raise HTTPException(status_code=400, detail="Срок действия кода истек")
    
    if req.code != db_code:
        raise HTTPException(status_code=400, detail="Неверный код")
    
    with sqlite3.connect("vpn_users.db") as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE email_verifications SET is_verified = 1 WHERE tg_id = ?", (req.tg_id,))
        conn.commit()

    return {"success": True, "message": "Почта подтверждена"}

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
        "paid_btn_url": "https://t.me/afroslavyanVPN_bot"
    }
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, json=payload, headers=headers)
            result = response.json()
            
            if result.get("ok"):
                invoice = result["result"]
                rub_amount = req.amount * 90
                
                with sqlite3.connect("vpn_users.db") as conn:
                    cursor = conn.cursor()
                    cursor.execute("INSERT INTO transactions (tg_id, amount, description, date) VALUES (?, ?, ?, ?)", 
                                   (req.tg_id, rub_amount, req.description, datetime.now().strftime("%Y-%m-%d %H:%M")))
                    
                    new_exp = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
                    cursor.execute("""
                        INSERT INTO subscriptions (tg_id, expires_at, status) VALUES (?, ?, 'active')
                        ON CONFLICT(tg_id) DO UPDATE SET expires_at=excluded.expires_at, status='active'
                    """, (req.tg_id, new_exp))
                    conn.commit()
                
                return {
                    "success": True,
                    "pay_url": invoice["pay_url"],
                    "invoice_id": invoice["invoice_id"]
                }
            else:
                error_msg = result.get("error", {}).get("name", "Ошибка создания счета")
                raise HTTPException(status_code=400, detail=error_msg)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

@app.post("/update-notifications")
async def update_notifications(req: NotificationSettings):
    with sqlite3.connect("vpn_users.db") as conn:
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

@app.post("/send-broadcast")
async def send_broadcast(req: BroadcastRequest):
    with sqlite3.connect("vpn_users.db") as conn:
        cursor = conn.cursor()
        if req.alert_type == "news":
            cursor.execute("SELECT tg_id FROM notification_settings WHERE news_alerts = 1")
        elif req.alert_type == "promo":
            cursor.execute("SELECT tg_id FROM notification_settings WHERE promo_alerts = 1")
        elif req.alert_type == "subscription":
            cursor.execute("SELECT tg_id FROM notification_settings WHERE subscription_alerts = 1")
        else:
            raise HTTPException(status_code=400, detail="Неверный тип уведомления")
        users = cursor.fetchall()
    
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

@app.post("/track-referral")
def track_referral(req: ReferralTrack):
    if req.referrer_id == req.referred_id:
        return {"success": False}
    with sqlite3.connect("vpn_users.db") as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO referrals (referrer_id, referred_id) VALUES (?, ?)", 
                       (req.referrer_id, req.referred_id))
        conn.commit()
    return {"success": True}

@app.get("/user-stats/{tg_id}")
def get_user_stats(tg_id: str):
    with sqlite3.connect("vpn_users.db") as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id = ?", (tg_id,))
        ref_count = cursor.fetchone()[0]
    earned = ref_count * 100
    return {
        "success": True,
        "balance": earned,
        "ref_count": ref_count,
        "total_earned": earned
    }

@app.get("/user-profile/{tg_id}")
def get_user_profile(tg_id: str):
    with sqlite3.connect("vpn_users.db") as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT expires_at, status FROM subscriptions WHERE tg_id = ?", (tg_id,))
        sub = cursor.fetchone()
    
    is_active = False
    days_left = 0
    if sub and sub[0]:
        try:
            exp_date = datetime.fromisoformat(sub[0])
            if datetime.now() < exp_date:
                is_active = True
                days_left = (exp_date - datetime.now()).days
        except:
            pass
            
    return {
        "success": True,
        "is_active": is_active,
        "days_left": days_left
    }

@app.get("/user-transactions/{tg_id}")
def get_user_transactions(tg_id: str):
    with sqlite3.connect("vpn_users.db") as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT amount, description, date FROM transactions WHERE tg_id = ? ORDER BY id DESC", (tg_id,))
        rows = cursor.fetchall()
    
    transactions = [{"amount": r[0], "description": r[1], "date": r[2]} for r in rows]
    return {"success": True, "transactions": transactions}

@app.post("/apply-promo")
def apply_promo(req: PromoApply):
    with sqlite3.connect("vpn_users.db") as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT discount_percent FROM promocodes WHERE code = ?", (req.code.strip(),))
        row = cursor.fetchone()
    if row:
        return {"success": True, "discount": row[0]}
    raise HTTPException(status_code=400, detail="Промокод не найден")

@app.post("/request-withdrawal")
async def request_withdrawal(req: WithdrawRequest):
    with sqlite3.connect("vpn_users.db") as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id = ?", (req.tg_id,))
        ref_count = cursor.fetchone()[0]
        balance = ref_count * 100
        
        if balance < 1000:
            raise HTTPException(status_code=400, detail="Недостаточно средств для вывода (минимум 1000 ₽)")
            
        cursor.execute("INSERT INTO withdrawals (tg_id, amount, date) VALUES (?, ?, ?)", 
                       (req.tg_id, balance, datetime.now().strftime("%Y-%m-%d %H:%M")))
        conn.commit()
    
    return {"success": True, "message": "Заявка на вывод создана"}