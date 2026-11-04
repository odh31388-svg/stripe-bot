import asyncio
from curl_cffi.requests import AsyncSession

async def main():
    print("Testing direct connection to Stripe...")
    try:
        async with AsyncSession(impersonate="chrome") as s:
            r = await s.get("https://api.stripe.com/v1/payment_pages", timeout=15)
            print(f"✅ Stripe is reachable! Status: {r.status_code}")
    except Exception as e:
        print(f"❌ Stripe connection failed: {e}")

    print("\nTesting DNS resolution (Google)...")
    try:
        async with AsyncSession(impersonate="chrome") as s:
            r = await s.get("https://www.google.com", timeout=15)
            print(f"✅ Google is reachable! Status: {r.status_code}")
    except Exception as e:
        print(f"❌ Google connection failed: {e}")

if __name__ == "__main__":
    asyncio.run(main())
