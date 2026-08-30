@app.post("/create-yookassa-invoice")
async def create_yookassa_invoice(req: YooKassaRequest):
    final_amount = req.amount
    if req.promo_code:
        with sqlite3.connect("vpn_users.db") as conn:
            cursor = conn.cursor()
            code_upper = req.promo_code.strip().upper()
            cursor.execute("SELECT discount_percent, max_uses, current_uses FROM promocodes WHERE code = ?", (code_upper,))
            row = cursor.fetchone()
            if row and row[0] > 0:
                max_uses, current_uses = row[1], row[2]
                if max_uses > 0 and current_uses >= max_uses:
                    raise HTTPException(status_code=400, detail="Лимит активаций промокода исчерпан")
                # Фронтенд уже передает сумму со скидкой, поэтому здесь повторно не умножаем, а только засчитываем использование
                cursor.execute("UPDATE promocodes SET current_uses = current_uses + 1 WHERE code = ?", (code_upper,))
                conn.commit()

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


@app.post("/create-crypto-invoice")
async def create_crypto_invoice(req: CryptoRequest):
    final_amount = req.amount
    if req.promo_code:
        with sqlite3.connect("vpn_users.db") as conn:
            cursor = conn.cursor()
            code_upper = req.promo_code.strip().upper()
            cursor.execute("SELECT discount_percent, max_uses, current_uses FROM promocodes WHERE code = ?", (code_upper,))
            row = cursor.fetchone()
            if row and row[0] > 0:
                max_uses, current_uses = row[1], row[2]
                if max_uses > 0 and current_uses >= max_uses:
                    raise HTTPException(status_code=400, detail="Лимит активаций промокода исчерпан")
                # Убираем повторное применение скидки для CryptoBot
                cursor.execute("UPDATE promocodes SET current_uses = current_uses + 1 WHERE code = ?", (code_upper,))
                conn.commit()

    url = "https://pay.crypt.bot/api/createInvoice"
    headers = {"Crypto-Pay-API-Token": CRYPTO_BOT_TOKEN, "Content-Type": "application/json"}
    payload = {
        "currency_type": "fiat",
        "fiat": "RUB",
        "amount": f"{final_amount:.2f}",
        "description": req.description,
        "payload": f"tg_id:{req.tg_id}",
        "allow_comments": False,
        "allow_anonymous": False,
        "expires_in": 3600
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, json=payload, headers=headers)
            result = response.json()
            if response.status_code == 200 and result.get("ok"):
                invoice = result["result"]
                pay_url = invoice["bot_invoice_url"]
                
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
                    
                return {"success": True, "pay_url": pay_url}
            else:
                err_msg = result.get("error", {}).get("message", "Ошибка создания счета в CryptoBot")
                raise HTTPException(status_code=400, detail=err_msg)
        except Exception as e:
            if isinstance(e, HTTPException):
                raise e
            raise HTTPException(status_code=500, detail=str(e))