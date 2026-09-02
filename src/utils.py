import json
import random
import time
import requests
from datetime import datetime
from pathlib import Path
import hashlib
import base64
import urllib.parse
import hmac

from config import TZ, DINGTALK_WEBHOOK, DINGTALK_SECRET

def now_str():
    return datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")

def save_json(data, filename):
    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)
    filepath = output_dir / filename
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return filepath

def send_dingtalk(title, text):
    if not DINGTALK_WEBHOOK:
        print("未配置钉钉机器人，跳过通知")
        return
    timestamp = str(round(time.time() * 1000))
    secret_enc = DINGTALK_SECRET.encode("utf-8")
    string_to_sign = f"{timestamp}\n{DINGTALK_SECRET}"
    string_to_sign_enc = string_to_sign.encode("utf-8")
    hmac_code = hmac.new(secret_enc, string_to_sign_enc, digestmod=hashlib.sha256).digest()
    sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
    url = f"{DINGTALK_WEBHOOK}&timestamp={timestamp}&sign={sign}"
    headers = {"Content-Type": "application/json"}
    payload = {
        "msgtype": "markdown",
        "markdown": {
            "title": title,
            "text": text
        }
    }
    try:
        r = requests.post(url, json=payload, headers=headers, timeout=10)
        print(f"钉钉通知状态: {r.status_code} {r.text}")
    except Exception as e:
        print(f"钉钉通知失败: {e}")

def random_sleep(min_sec=2, max_sec=5):
    time.sleep(random.uniform(min_sec, max_sec))
