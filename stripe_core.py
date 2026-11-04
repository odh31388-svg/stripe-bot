    async def charge(self, card_dict: dict) -> dict:
        t0 = time.time()
        cc = card_dict["cc"]
        mm = card_dict["mm"]
        yy = card_dict["yy"]
        cvv = card_dict["cvv"]

        try:
            # 1. جلب تفاصيل جلسة الـ Checkout الحالية لضمان استخراج الـ Payment Intent الصحيح
            r_page = await self.session.get(
                f"https://api.stripe.com/v1/payment_pages/{self.cs}",
                params={"key": self.pk},
                headers={"Origin": "https://js.stripe.com", "Referer": "https://js.stripe.com/", "Accept": "application/json"},
                timeout=12
            )
            page_data = r_page.json() or {}
            pi_obj = page_data.get("payment_intent") or {}
            pi_id = pi_obj.get("id")
            pi_client_secret = pi_obj.get("client_secret")

            # 2. إنشاء Payment Method للبطاقة
            tok_body = {
                "type": "card",
                "card[number]": cc,
                "card[cvc]": cvv,
                "card[exp_month]": mm,
                "card[exp_year]": yy,
                "billing_details[address][country]": "US",
                "billing_details[address][postal_code]": "10001",
                "key": self.pk,
                "payment_user_agent": "stripe.js/c3ec434e35; stripe-js-v3/c3ec434e35; checkout"
            }
            
            r_tok = await self.session.post(
                "https://api.stripe.com/v1/payment_methods",
                data=tok_body,
                headers={"Content-Type": "application/x-www-form-urlencoded", "Origin": "https://js.stripe.com", "Referer": "https://js.stripe.com/"},
                timeout=12
            )
            td = r_tok.json() or {}
            pm_id = td.get("id")
            
            if not pm_id:
                err = td.get("error", {})
                return {
                    "status": "DECLINED",
                    "card": f"{cc[:6]}****{cc[-4:]}|{mm}|{yy}|{cvv}",
                    "amount": f"{self.currency} {self.amount/100:.2f}",
                    "response_time": time.time() - t0,
                    "message": err.get("message", "Card Declined")
                }

            # 3. التأكيد المباشر عبر الـ Payment Intent إذا متوفر لتفادي خطأ الـ Checkout Session الصارم
            if pi_id and pi_client_secret:
                conf_pi_body = {
                    "payment_method": pm_id,
                    "expected_payment_method_type": "card",
                    "use_stripe_sdk": "true",
                    "key": self.pk,
                    "client_secret": pi_client_secret
                }
                r_conf = await self.session.post(
                    f"https://api.stripe.com/v1/payment_intents/{pi_id}/confirm",
                    data=conf_pi_body,
                    headers={"Content-Type": "application/x-www-form-urlencoded", "Origin": "https://js.stripe.com", "Referer": "https://js.stripe.com/"},
                    timeout=20
                )
            else:
                # الطريقة البديلة عبر الـ Checkout Session
                confirm_body = {
                    "key": self.pk,
                    "payment_method": pm_id,
                    "expected_payment_method_type": "card",
                    "expected_amount": str(self.amount),
                    "return_url": self.url.split("#")[0],
                    "client_attribution_metadata[client_session_id]": self.cs,
                }
                r_conf = await self.session.post(
                    f"https://api.stripe.com/v1/payment_pages/{self.cs}/confirm",
                    data=confirm_body,
                    headers={"Content-Type": "application/x-www-form-urlencoded", "Origin": "https://js.stripe.com", "Referer": "https://js.stripe.com/"},
                    timeout=20
                )

            resp = r_conf.json() or {}
            err = resp.get("error") or {}
            if err:
                return {
                    "status": "DECLINED",
                    "card": f"{cc[:6]}****{cc[-4:]}|{mm}|{yy}|{cvv}",
                    "amount": f"{self.currency} {self.amount/100:.2f}",
                    "response_time": time.time() - t0,
                    "message": err.get("message", "Declined")
                }

            pi = resp.get("payment_intent") or resp.get("setup_intent") or resp or {}
            pi_status = str(pi.get("status") or "")

            if pi_status in ("succeeded", "complete", "requires_capture"):
                return {
                    "status": "CHARGED",
                    "card": f"{cc[:6]}****{cc[-4:]}|{mm}|{yy}|{cvv}",
                    "amount": f"{self.currency} {self.amount/100:.2f}",
                    "response_time": time.time() - t0,
                    "message": "تم خصم المبلغ بنجاح ✅"
                }
            elif pi_status == "requires_action" or pi.get("next_action"):
                return {
                    "status": "REQUIRES_ACTION",
                    "card": f"{cc[:6]}****{cc[-4:]}|{mm}|{yy}|{cvv}",
                    "amount": f"{self.currency} {self.amount/100:.2f}",
                    "response_time": time.time() - t0,
                    "message": "تتطلب مصادقة 3DS / OTP 🔐"
                }
            else:
                return {
                    "status": "DECLINED",
                    "card": f"{cc[:6]}****{cc[-4:]}|{mm}|{yy}|{cvv}",
                    "amount": f"{self.currency} {self.amount/100:.2f}",
                    "response_time": time.time() - t0,
                    "message": f"الرد: {pi_status or 'Declined'}"
                }

        except Exception as e:
            return {
                "status": "ERROR",
                "card": f"{cc[:6]}****{cc[-4:]}|{mm}|{yy}|{cvv}",
                "amount": f"{self.currency} {self.amount/100:.2f}",
                "response_time": time.time() - t0,
                "message": str(e)[:100]
            }
