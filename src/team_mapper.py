import requests
import re
import json
from pathlib import Path
from config import USER_AGENT, WIKI_API

# 小型兜底映射（常用队名）
FALLBACK_MAP = {
    "曼城": "Manchester City", "曼彻斯特城": "Manchester City",
    "曼联": "Manchester United", "曼彻斯特联": "Manchester United",
    "利物浦": "Liverpool", "阿森纳": "Arsenal", "切尔西": "Chelsea",
    "热刺": "Tottenham Hotspur", "托特纳姆热刺": "Tottenham Hotspur",
    "纽卡斯尔": "Newcastle United", "纽卡斯尔联": "Newcastle United",
    "皇家马德里": "Real Madrid", "皇马": "Real Madrid",
    "巴塞罗那": "Barcelona", "巴萨": "Barcelona",
    "马德里竞技": "Atletico Madrid", "马竞": "Atletico Madrid",
    "拜仁慕尼黑": "Bayern Munich", "拜仁": "Bayern Munich",
    "多特蒙德": "Borussia Dortmund", "莱比锡红牛": "RB Leipzig",
    "巴黎圣日耳曼": "Paris Saint-Germain", "巴黎": "Paris Saint-Germain",
    "尤文图斯": "Juventus", "尤文": "Juventus",
    "国际米兰": "Inter Milan", "国米": "Inter Milan",
    "AC米兰": "AC Milan", "米兰": "AC Milan",
    "利雅得新月": "Al Hilal", "利雅得胜利": "Al Nassr",
    "吉达国民": "Al Ahli", "吉达联合": "Al Ittihad"
}

_cache_file = Path("team_name_cache.json")
_cache = {}
if _cache_file.exists():
    try:
        _cache = json.loads(_cache_file.read_text(encoding="utf-8"))
    except:
        _cache = {}

def _save_cache():
    _cache_file.write_text(json.dumps(_cache, ensure_ascii=False, indent=2), encoding="utf-8")

def _clean_team_name(name):
    # 移除常见后缀
    name = re.sub(r'\s*(足球俱乐部|俱乐部|队|足球队)$', '', name)
    name = re.sub(r'\s*(FC|F\.C\.|Football Club|S\.C\.|CF|AFC|SC)$', '', name, flags=re.IGNORECASE)
    return name.strip()

def get_english_team_name(chinese_name):
    if chinese_name in _cache:
        return _cache[chinese_name]
    if chinese_name in FALLBACK_MAP:
        return FALLBACK_MAP[chinese_name]

    # 步骤1：查找中文维基条目
    params = {
        "action": "query",
        "list": "search",
        "srsearch": chinese_name,
        "format": "json",
        "srlimit": 1,
        "srprop": "size"
    }
    headers = {"User-Agent": USER_AGENT}
    try:
        resp = requests.get(WIKI_API, params=params, headers=headers, timeout=10)
        data = resp.json()
        search_results = data.get("query", {}).get("search", [])
        if not search_results:
            return None
        title_zh = search_results[0]["title"]
    except Exception as e:
        print(f"维基搜索失败: {e}")
        return None

    # 步骤2：获取英文链接
    params = {
        "action": "query",
        "titles": title_zh,
        "prop": "langlinks",
        "lllang": "en",
        "format": "json",
        "redirects": 1
    }
    try:
        resp = requests.get(WIKI_API, params=params, headers=headers, timeout=10)
        data = resp.json()
        pages = data.get("query", {}).get("pages", {})
        for page_id, page in pages.items():
            langlinks = page.get("langlinks", [])
            if langlinks:
                en_title = langlinks[0]["*"]
                en_name = _clean_team_name(en_title)
                _cache[chinese_name] = en_name
                _save_cache()
                return en_name
    except Exception as e:
        print(f"获取英文链接失败: {e}")

    return None
