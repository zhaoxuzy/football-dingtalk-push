import os
from datetime import timezone, timedelta

TZ = timezone(timedelta(hours=8))  # 北京时间

# 钉钉
DINGTALK_WEBHOOK = os.getenv("DINGTALK_WEBHOOK", "")
DINGTALK_SECRET = os.getenv("DINGTALK_SECRET", "")

# GitHub Actions 环境变量
GITHUB_RUN_ID = os.getenv("GITHUB_RUN_ID", "")
GITHUB_REPO = os.getenv("GITHUB_REPOSITORY", "")
ARTIFACT_BASE_URL = f"https://github.com/{GITHUB_REPO}/actions/runs/{GITHUB_RUN_ID}"

# 维基百科 API
WIKI_API = "https://zh.wikipedia.org/w/api.php"
WIKI_API_EN = "https://en.wikipedia.org/w/api.php"
USER_AGENT = "JCDataCollector/1.0 (contact: your-email@example.com)"
