import asyncio
import sys
from stripe_core import StripeSession, parse_card, log, C

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
