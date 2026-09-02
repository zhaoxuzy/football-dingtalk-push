import os
from datetime import datetime, timezone, timedelta

# 时区
TZ = timezone(timedelta(hours=8))  # 北京时间

# 澳客网
OKOOO_BASE = "https://www.okooo.com"
OKOOO_JC_SCHEDULE = f"{OKOOO_BASE}/jingcai/"

# 钉钉
DINGTALK_WEBHOOK = os.getenv("DINGTALK_WEBHOOK", "")
DINGTALK_SECRET = os.getenv("DINGTALK_SECRET", "")

# GitHub Actions 环境变量
GITHUB_RUN_ID = os.getenv("GITHUB_RUN_ID", "")
GITHUB_REPO = os.getenv("GITHUB_REPOSITORY", "")
ARTIFACT_BASE_URL = f"https://github.com/{GITHUB_REPO}/actions/runs/{GITHUB_RUN_ID}"
