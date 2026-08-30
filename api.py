import uuid
import sqlite3
import random
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime, timedelta
import httpx
from apscheduler.schedulers.background import BackgroundScheduler

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

YOOKASSA_SHOP_ID = "1444358"
YOOKASSA_SECRET_KEY = "live_7YgYIW8xKJsRDfqlSt2P-fqubRhw4Fs8eUr-R5wJYq4"

def init_db():
    with sqlite3.connect("vpn_users.db") as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                tg_id TEXT PRIMARY KEY,
                joined_at TEXT
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
                status TEXT,
                auto_renewal INTEGER DEFAULT 0,
                payment_token TEXT,
                card_last4 TEXT
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
            CREATE TABLE IF NOT EXISTS withdrawals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tg_id TEXT,
                amount REAL,
                status TEXT DEFAULT 'pending',
                date TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS promocodes (
                code TEXT PRIMARY KEY,
                discount_percent INTEGER DEFAULT 0,
                bonus_days INTEGER DEFAULT 0
            )
        """)
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
            CREATE TABLE IF NOT EXISTS referrals (
                referrer_id TEXT,
                referred_id TEXT PRIMARY KEY
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS devices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tg_id TEXT,
                device_name TEXT,
                icon_type TEXT,
                last_active TEXT
            )
        """)
        conn.commit()

init_db()

@app.get("/user-profile/{tg_id}")
def get_user_profile(tg_id: str):
    with sqlite3.connect("vpn_users.db") as conn:
        cursor = conn.cursor()
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("INSERT OR IGNORE INTO users (tg_id, joined_at) VALUES (?, ?)", (tg_id, now_str))
        conn.commit()
        
        cursor.execute("SELECT joined_at FROM users WHERE tg_id = ?", (tg_id,))
        user_row = cursor.fetchone()
        joined_at = datetime.strptime(user_row[0], "%Y-%m-%d %H:%M:%S") if user_row and user_row[0] else datetime.now()
        days_with_us = (datetime.now() - joined_at).days
        
        if days_with_us > 90:
            loyalty_status = "VIP-клиент"
        elif days_with_us > 30:
            loyalty_status = "Продвинутый пользователь"
        else:
            loyalty_status = f"С нами {max(1, days_with_us)} дн."

        cursor.execute("SELECT expires_at, status, auto_renewal, card_last4 FROM subscriptions WHERE tg_id = ?", (tg_id,))
        sub = cursor.fetchone()
        
        cursor.execute("SELECT email, is_verified FROM email_verifications WHERE tg_id = ?", (tg_id,))
        email_data = cursor.fetchone()
        
    return {
        "success": True,
        "subscription": {
            "expires_at": sub[0] if sub else None,
            "status": sub[1] if sub else "inactive",
            "auto_renewal": bool(sub[2]) if sub else False,
            "card_last4": sub[3] if sub and sub[3] else None
        } if sub else None,
        "is_active": bool(sub and sub[1] == 'active'),
        "days_left": (datetime.strptime(sub[0], "%Y-%m-%d %H:%M:%S") - datetime.now()).days if sub and sub[1] == 'active' else 0,
        "email": email_data[0] if email_data else None,
        "is_verified": bool(email_data[1]) if email_data else False,
        "loyalty_status": loyalty_status
    }

@app.get("/user-stats/{tg_id}")
def get_user_stats(tg_id: str):
    with sqlite3.connect("vpn_users.db") as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT SUM(amount) FROM transactions WHERE tg_id = ?", (tg_id,))
        rev = cursor.fetchone()[0]
        balance = rev if rev else 0.0

        cursor.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id = ?", (tg_id,))
        ref_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM devices WHERE tg_id = ?", (tg_id,))
        active_devices = cursor.fetchone()[0] + 1

    return {
        "success": True,
        "balance": balance,
        "ref_count": ref_count,
        "total_earned": balance,
        "traffic_used": "0 MB",
        "active_devices": active_devices
    }

@app.get("/user-transactions/{tg_id}")
def get_user_transactions(tg_id: str):
    with sqlite3.connect("vpn_users.db") as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT amount, description, date FROM transactions WHERE tg_id = ? ORDER BY id DESC", (tg_id,))
        rows = cursor.fetchall()
    transactions = [{"amount": r[0], "description": r[1], "date": r[2]} for r in rows]
    return {"success": True, "transactions": transactions}

class PromoActivateRequest(BaseModel):
    tg_id: str
    code: str

@app.post("/activate-promo")
def activate_promo(req: PromoActivateRequest):
    code = req.code.strip().upper()
    with sqlite3.connect("vpn_users.db") as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT discount_percent, bonus_days FROM promocodes WHERE code = ?", (code,))
        promo = cursor.fetchone()
        if not promo:
            raise HTTPException(status_code=400, detail="Промокод не найден или недействителен")
        
        discount_percent = promo[0] if promo[0] is not None else 0
        bonus_days = promo[1] if promo[1] is not None else 0
        
        if discount_percent > 0 and bonus_days == 0:
            raise HTTPException(status_code=400, detail="Этот промокод дает скидку при оплате, введите его в окне оплаты")
        
        if bonus_days <= 0:
            raise HTTPException(status_code=400, detail="Этот промокод не содержит бонусных дней")
        
        cursor.execute("SELECT expires_at, status FROM subscriptions WHERE tg_id = ?", (req.tg_id,))
        sub = cursor.fetchone()
        
        base_date = datetime.now()
        if sub and sub[1] == 'active' and sub[0]:
            try:
                exp = datetime.strptime(sub[0], "%Y-%m-%d %H:%M:%S")
                if exp > base_date:
                    base_date = exp
            except ValueError:
                pass
        
        new_exp = (base_date + timedelta(days=bonus_days)).strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("""
            INSERT INTO subscriptions (tg_id, expires_at, status) VALUES (?, ?, 'active')
            ON CONFLICT(tg_id) DO UPDATE SET expires_at = ?, status = 'active'
        """, (req.tg_id, new_exp, new_exp))
        
        cursor.execute("INSERT INTO transactions (tg_id, amount, description, date) VALUES (?, 0, ?, ?)",
                       (req.tg_id, f"Активация промокода: {code} (+{bonus_days} дн.)", datetime.now().strftime("%Y-%m-%d %H:%M")))
        conn.commit()
    return {"success": True, "message": f"Промокод успешно активирован! Добавлено дней: {bonus_days}"}

class CheckPromoRequest(BaseModel):
    code: str

@app.post("/check-promo")
def check_promo(req: CheckPromoRequest):
    code = req.code.strip().upper()
    with sqlite3.connect("vpn_users.db") as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT discount_percent, bonus_days FROM promocodes WHERE code = ?", (code,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=400, detail="Промокод не найден")
    return {"success": True, "discount_percent": row[0], "bonus_days": row[1]}

@app.post("/unlink-card/{tg_id}")
def unlink_card(tg_id: str):
    with sqlite3.connect("vpn_users.db") as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE subscriptions SET payment_token = NULL, card_last4 = NULL, auto_renewal = 0 WHERE tg_id = ?", (tg_id,))
        conn.commit()
    return {"success": True}

@app.post("/revoke-all-devices/{tg_id}")
def revoke_all_devices(tg_id: str):
    with sqlite3.connect("vpn_users.db") as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM devices WHERE tg_id = ?", (tg_id,))
        conn.commit()
    return {"success": True}

@app.get("/devices/{tg_id}")
def get_devices(tg_id: str):
    with sqlite3.connect("vpn_users.db") as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, device_name, icon_type, last_active FROM devices WHERE tg_id = ?", (tg_id,))
        rows = cursor.fetchall()
    devices = [{"id": r[0], "device_name": r[1], "icon_type": r[2], "last_active": r[3]} for r in rows]
    return {"success": True, "devices": devices}

class DeviceAddRequest(BaseModel):
    tg_id: str
    device_name: str
    icon_type: str = "monitor"

@app.post("/devices")
def add_device(req: DeviceAddRequest):
    with sqlite3.connect("vpn_users.db") as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM devices WHERE tg_id = ?", (req.tg_id,))
        count = cursor.fetchone()[0]
        if count >= 3:
            raise HTTPException(status_code=400, detail="Достигнут лимит устройств")
        
        last_active = datetime.now().strftime("сегодня, %H:%M")
        cursor.execute("""
            INSERT INTO devices (tg_id, device_name, icon_type, last_active)
            VALUES (?, ?, ?, ?)
        """, (req.tg_id, req.device_name, req.icon_type, last_active))
        conn.commit()
    return {"success": True}

@app.delete("/devices/{device_id}")
def delete_device(device_id: int):
    with sqlite3.connect("vpn_users.db") as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM devices WHERE id = ?", (device_id,))
        conn.commit()
    return {"success": True}

class EmailVerifyRequest(BaseModel):
    tg_id: str
    email: str

@app.post("/send-code")
def send_email_code(req: EmailVerifyRequest):
    code = str(random.randint(1000, 9999))
    expires_at = datetime.now() + timedelta(minutes=10)
    
    with sqlite3.connect("vpn_users.db") as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO email_verifications (tg_id, email, code, expires_at, is_verified)
            VALUES (?, ?, ?, ?, 0)
            ON CONFLICT(tg_id) DO UPDATE SET email=excluded.email, code=excluded.code, expires_at=excluded.expires_at
        """, (req.tg_id, req.email, code, expires_at))
        conn.commit()
    
    return {"success": True, "message": "Код отправлен"}

class VerifyCodeRequest(BaseModel):
    tg_id: str
    code: str

@app.post("/verify-code")
def verify_email_code(req: VerifyCodeRequest):
    with sqlite3.connect("vpn_users.db") as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT code FROM email_verifications WHERE tg_id = ?", (req.tg_id,))
        row = cursor.fetchone()
        if not row or row[0] != req.code:
            raise HTTPException(status_code=400, detail="Неверный код подтверждения")
        
        cursor.execute("UPDATE email_verifications SET is_verified = 1 WHERE tg_id = ?", (req.tg_id,))
        conn.commit()
    return {"success": True}

class ReferralTrackRequest(BaseModel):
    referrer_id: str
    referred_id: str

@app.post("/track-referral")
def track_referral(req: ReferralTrackRequest):
    if req.referrer_id == req.referred_id:
        return {"success": False}
    with sqlite3.connect("vpn_users.db") as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("INSERT OR IGNORE INTO referrals (referrer_id, referred_id) VALUES (?, ?)", (req.referrer_id, req.referred_id))
            conn.commit()
        except Exception:
            pass
    return {"success": True}

class YooKassaRequest(BaseModel):
    tg_id: str
    amount: float
    description: str
    auto_renewal: bool = False
    promo_code: str = None

@app.post("/create-yookassa-invoice")
async def create_yookassa_invoice(req: YooKassaRequest):
    final_amount = req.amount
    if req.promo_code:
        with sqlite3.connect("vpn_users.db") as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT discount_percent FROM promocodes WHERE code = ?", (req.promo_code.strip().upper(),))
            row = cursor.fetchone()
            if row and row[0] > 0:
                final_amount = req.amount * (1 - row[0] / 100)

    url = "https://api.yookassa.ru/v3/payments"
    payload = {
        "amount": {"value": f"{final_amount:.2f}", "currency": "RUB"},
        "capture": True,
        "confirmation": {"type": "redirect", "return_url": "https://t.me/afroslavyanVPN_bot"},
        "description": req.description,
        "metadata": {"tg_id": str(req.tg_id)}
    }
    if req.auto_renewal:
        payload["save_payment_method"] = True
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                url, json=payload, 
                auth=(YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY),
                headers={"Idempotence-Key": str(uuid.uuid4()), "Content-Type": "application/json"}
            )
            result = response.json()
            if response.status_code in [200, 201]:
                confirmation_url = result["confirmation"]["confirmation_url"]
                payment_id = result["id"]
                with sqlite3.connect("vpn_users.db") as conn:
                    cursor = conn.cursor()
                    cursor.execute("INSERT INTO transactions (tg_id, amount, description, date) VALUES (?, ?, ?, ?)", 
                                   (req.tg_id, final_amount, req.description, datetime.now().strftime("%Y-%m-%d %H:%M")))
                    new_exp = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
                    cursor.execute("""
                        INSERT INTO subscriptions (tg_id, expires_at, status, auto_renewal, card_last4) VALUES (?, ?, 'active', ?, '4242')
                        ON CONFLICT(tg_id) DO UPDATE SET expires_at=excluded.expires_at, status='active', auto_renewal=excluded.auto_renewal, card_last4='4242'
                    """, (req.tg_id, new_exp, int(req.auto_renewal)))
                    conn.commit()
                return {"success": True, "pay_url": confirmation_url, "payment_id": payment_id}
            else:
                raise HTTPException(status_code=400, detail=result.get("description", "Ошибка платежа"))
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

class CryptoRequest(BaseModel):
    tg_id: str
    amount: float
    description: str
    auto_renewal: bool = False
    promo_code: str = None

@app.post("/create-crypto-invoice")
async def create_crypto_invoice(req: CryptoRequest):
    final_amount = req.amount
    if req.promo_code:
        with sqlite3.connect("vpn_users.db") as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT discount_percent FROM promocodes WHERE code = ?", (req.promo_code.strip().upper(),))
            row = cursor.fetchone()
            if row and row[0] > 0:
                final_amount = req.amount * (1 - row[0] / 100)

    with sqlite3.connect("vpn_users.db") as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO transactions (tg_id, amount, description, date) VALUES (?, ?, ?, ?)", 
                       (req.tg_id, final_amount, req.description, datetime.now().strftime("%Y-%m-%d %H:%M")))
        new_exp = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("""
            INSERT INTO subscriptions (tg_id, expires_at, status) VALUES (?, ?, 'active')
            ON CONFLICT(tg_id) DO UPDATE SET expires_at=excluded.expires_at, status='active'
        """, (req.tg_id, new_exp))
        conn.commit()
    return {"success": True, "pay_url": "https://t.me/CryptoBot?start=test"}

@app.post("/yookassa-webhook")
async def yookassa_webhook(data: dict):
    event = data.get("event")
    if event == "payment.succeeded":
        payment_object = data.get("object", {})
        metadata = payment_object.get("metadata", {})
        tg_id = metadata.get("tg_id")
        payment_method = payment_object.get("payment_method", {})
        payment_token = payment_method.get("id")
        if tg_id and payment_token:
            with sqlite3.connect("vpn_users.db") as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE subscriptions SET payment_token = ?, card_last4 = '4242' WHERE tg_id = ?
                """, (payment_token, str(tg_id)))
                conn.commit()
    return {"status": "ok"}

def charge_saved_card(payment_token: str, amount: float):
    url = "https://api.yookassa.ru/v3/payments"
    payload = {
        "amount": {"value": f"{amount:.2f}", "currency": "RUB"},
        "capture": True,
        "payment_method_id": payment_token,
        "description": "Автоматическое продление подписки VPN"
    }
    try:
        response = httpx.post(
            url, json=payload, 
            auth=(YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY),
            headers={"Idempotence-Key": str(uuid.uuid4()), "Content-Type": "application/json"}
        )
        result = response.json()
        if response.status_code in [200, 201] and result.get("status") == "succeeded":
            return True
    except Exception as e:
        print(f"Ошибка при автосписании: {e}")
    return False

def process_auto_renewals():
    today = datetime.now().strftime("%Y-%m-%d")
    with sqlite3.connect("vpn_users.db") as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT tg_id, payment_token FROM subscriptions 
            WHERE date(expires_at) = ? AND auto_renewal = 1 AND status = 'active' AND payment_token IS NOT NULL
        """, (today,))
        users_to_renew = cursor.fetchall()
        for tg_id, payment_token in users_to_renew:
            success = charge_saved_card(payment_token, 199.0)
            if success:
                new_exp = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
                cursor.execute("UPDATE subscriptions SET expires_at = ? WHERE tg_id = ?", (new_exp, tg_id))
                cursor.execute("INSERT INTO transactions (tg_id, amount, description, date) VALUES (?, 199.0, ?, ?)",
                               (tg_id, "Автопродление подписки", datetime.now().strftime("%Y-%m-%d %H:%M")))
                conn.commit()

scheduler = BackgroundScheduler()
scheduler.add_job(process_auto_renewals, 'cron', hour=0, minute=0)
scheduler.start()

class AutoRenewalToggle(BaseModel):
    tg_id: str
    auto_renewal: bool

@app.post("/toggle-auto-renewal")
def toggle_auto_renewal(req: AutoRenewalToggle):
    with sqlite3.connect("vpn_users.db") as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE subscriptions SET auto_renewal = ? WHERE tg_id = ?", (int(req.auto_renewal), req.tg_id))
        conn.commit()
    return {"success": True, "auto_renewal": req.auto_renewal}

@app.get("/admin/stats")
def get_admin_stats():
    with sqlite3.connect("vpn_users.db") as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(DISTINCT tg_id) FROM subscriptions")
        total_users = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM subscriptions WHERE status = 'active'")
        active_subs = cursor.fetchone()[0]
        cursor.execute("SELECT SUM(amount) FROM transactions")
        revenue_row = cursor.fetchone()[0]
        total_revenue = revenue_row if revenue_row else 0.0
    return {"success": True, "total_users": total_users, "active_subs": active_subs, "total_revenue": total_revenue}

@app.get("/admin/withdrawals")
def get_admin_withdrawals():
    with sqlite3.connect("vpn_users.db") as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, tg_id, amount, date FROM withdrawals WHERE status = 'pending'")
        rows = cursor.fetchall()
    withdrawals = [{"id": r[0], "tg_id": r[1], "amount": r[2], "date": r[3]} for r in rows]
    return {"success": True, "withdrawals": withdrawals}

class WithdrawalAction(BaseModel):
    withdrawal_id: int
    action: str

@app.post("/admin/withdrawal-action")
def admin_withdrawal_action(req: WithdrawalAction):
    with sqlite3.connect("vpn_users.db") as conn:
        cursor = conn.cursor()
        new_status = 'approved' if req.action == 'approve' else 'rejected'
        cursor.execute("UPDATE withdrawals SET status = ? WHERE id = ?", (new_status, req.withdrawal_id))
        conn.commit()
    return {"success": True, "message": f"Заявка переведена в статус {new_status}"}

class AdminPromoCreate(BaseModel):
    code: str
    discount_percent: int = 0
    bonus_days: int = 0

@app.post("/admin/create-promo")
def admin_create_promo(req: AdminPromoCreate):
    with sqlite3.connect("vpn_users.db") as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO promocodes (code, discount_percent, bonus_days) VALUES (?, ?, ?)", 
                       (req.code.strip().upper(), req.discount_percent, req.bonus_days))
        conn.commit()
    return {"success": True, "message": "Промокод успешно создан"}