import sys
import re
import json
import requests
import datetime
import os
import hmac
import hashlib
import base64
import urllib.parse
import time
from jinja2 import Template
import csv
import io

# ==================== 配置区域 ====================
DINGTALK_WEBHOOK_URL = os.environ.get("DINGTALK_WEBHOOK_URL", "https://oapi.dingtalk.com/robot/send?access_token=你的token")
DINGTALK_SECRET = os.environ.get("DINGTALK_SECRET", "")
FOOTBALL_DATA_API_KEY = os.environ.get("FOOTBALL_DATA_API_KEY", "")  # 注册 football-data.org 获取

# 是否启用实时获取（可全部开启）
ENABLE_WEATHER = True
ENABLE_ELO = True
ENABLE_STANDINGS = True       # 积分榜
ENABLE_SCHEDULE = True        # 未来赛程
ENABLE_RECENT = True          # 近期战绩
ENABLE_XG = True              # xG（可能失败）
ENABLE_INJURY = True          # 伤停（可能失败）
ENABLE_ODDS = True            # 竞彩赔率（可能失败）
# ==================================================

# ==================== 第一部分：球队名称翻译 ====================
TEAM_NAME_MAP = {
    "利雅得新月": "Al Hilal",
    "利雅得胜利": "Al Nassr",
    "吉达国民": "Al Ahli",
    "吉达联合": "Al Ittihad",
    "利雅得青年人": "Al Shabab",
    "达曼协作": "Al Ettifaq",
    "哈萨征服": "Al Fateh",
    "费哈": "Al Feiha",
    "布赖代合作": "Al Taawon",
    "布赖代先锋": "Al Raed",
    "麦加统一": "Al Wehda",
    "艾卜哈": "Abha",
    "达马克": "Damac",
    "塔伊": "Al Tai",
    "卡利杰": "Al Khaleej",
    "阿科多": "Al Akhdoud",
}

def translate_to_english(text):
    """使用 MyMemory 免费 API 翻译中文为英文"""
    try:
        url = "https://api.mymemory.translated.net/get"
        params = {"q": text, "langpair": "zh-CN|en"}
        r = requests.get(url, params=params, timeout=8)
        data = r.json()
        if data.get("responseStatus") == 200:
            return data["responseData"]["translatedText"].strip()
        else:
            return None
    except:
        return None

def get_english_name(team_name):
    """优先手动映射，否则自动翻译"""
    en = TEAM_NAME_MAP.get(team_name)
    if en:
        return en
    print(f"  [翻译] 手动映射未找到 {team_name}，尝试自动翻译...")
    en = translate_to_english(team_name)
    if en:
        print(f"  [翻译] 翻译结果：{en}")
    return en

# ==================== 第二部分：简单数据获取 ====================
def fetch_weather(city):
    """获取真实天气（wttr.in）"""
    if not ENABLE_WEATHER:
        return None
    url = f"https://wttr.in/{urllib.parse.quote(city)}?format=j1"
    data = get_json(url)
    if data:
        try:
            current = data["current_condition"][0]
            desc = current["weatherDesc"][0]["value"]
            temp_c = current["temp_C"]
            humidity = current["humidity"]
            wind_speed = current["windspeedKmph"]
            return f"{desc}，{temp_c}°C，湿度{humidity}%，风速{wind_speed}km/h"
        except:
            pass
    print(f"  [天气] 获取失败（城市：{city}）")
    return None

def fetch_elo(team_name):
    """获取真实 Elo（尝试 ClubElo 和 eloratings.net）"""
    if not ENABLE_ELO:
        return None
    english_name = get_english_name(team_name)
    if not english_name:
        print(f"  [Elo] 无法获取英文名")
        return None

    # 源1: ClubElo API
    api_url = f"https://api.clubelo.com/{english_name.replace(' ', '')}"
    data = get_json(api_url)
    if data and isinstance(data, list) and len(data) > 0:
        elo = safe_float(data[0].get("Elo"))
        if elo:
            print(f"  [Elo] {team_name} -> {english_name}，Elo={elo}（ClubElo）")
            return elo

    # 源2: eloratings.net CSV
    csv_url = "https://www.eloratings.net/en_clubs.csv"
    text = get_text(csv_url)
    if text:
        try:
            reader = csv.DictReader(io.StringIO(text))
            for row in reader:
                if row.get("Club") and english_name.lower() in row["Club"].lower():
                    elo = safe_float(row.get("Elo"))
                    if elo:
                        print(f"  [Elo] {team_name} -> {english_name}，Elo={elo}（eloratings.net）")
                        return elo
        except:
            pass

    print(f"  [Elo] {team_name} 获取失败")
    return None

# ==================== 第三部分：较难数据获取 ====================
def fetch_standings(league):
    """从 football-data.org 获取积分排名（需 API key）"""
    if not ENABLE_STANDINGS or not FOOTBALL_DATA_API_KEY:
        return None
    league_code = {"沙职": "SA1", "沙特联": "SA1", "沙地联": "SA1"}.get(league)
    if not league_code:
        print(f"  [积分] 未找到联赛代码：{league}")
        return None

    headers = {"X-Auth-Token": FOOTBALL_DATA_API_KEY}
    url = f"https://api.football-data.org/v4/competitions/{league_code}/standings"
    data = get_json(url, headers=headers)
    if data and "standings" in data:
        try:
            table = data["standings"][0]["table"]
            standings = {}
            for row in table:
                team_name = row["team"]["name"]
                for cn, en in TEAM_NAME_MAP.items():
                    if en.lower() == team_name.lower():
                        standings[cn] = {
                            "排名": row["position"],
                            "积分": row["points"],
                            "胜": row["won"],
                            "平": row["draw"],
                            "负": row["lost"]
                        }
                        break
            if standings:
                print(f"  [积分] 成功获取 {len(standings)} 支球队积分")
                return standings
        except:
            pass
    print("  [积分] 获取失败")
    return None

def _get_team_id(league_code, english_name):
    """辅助：从 football-data.org 获取球队 ID"""
    if not FOOTBALL_DATA_API_KEY:
        return None
    headers = {"X-Auth-Token": FOOTBALL_DATA_API_KEY}
    url = f"https://api.football-data.org/v4/competitions/{league_code}/teams"
    data = get_json(url, headers=headers)
    if data and "teams" in data:
        for team in data["teams"]:
            if team["name"].lower() == english_name.lower():
                return team["id"]
    return None

def fetch_future_schedule(league, team_name):
    """获取未来赛程（需 API key）"""
    if not ENABLE_SCHEDULE or not FOOTBALL_DATA_API_KEY:
        return None
    league_code = {"沙职": "SA1", "沙特联": "SA1", "沙地联": "SA1"}.get(league)
    if not league_code:
        return None
    english_name = get_english_name(team_name)
    if not english_name:
        return None

    team_id = _get_team_id(league_code, english_name)
    if not team_id:
        print(f"  [赛程] 未找到球队 ID：{team_name}")
        return None

    headers = {"X-Auth-Token": FOOTBALL_DATA_API_KEY}
    url = f"https://api.football-data.org/v4/teams/{team_id}/matches?status=SCHEDULED"
    data = get_json(url, headers=headers)
    if data and "matches" in data:
        future = []
        for match in data["matches"][:5]:
            try:
                date = match["utcDate"][:10]
                if match["homeTeam"]["name"].lower() == english_name.lower():
                    opponent = match["awayTeam"]["name"]
                    home_away = "主"
                else:
                    opponent = match["homeTeam"]["name"]
                    home_away = "客"
                future.append({"对手": opponent, "主客": home_away, "日期": date})
            except:
                continue
        if future:
            print(f"  [赛程] {team_name} 获取到 {len(future)} 场未来比赛")
            return future
    print(f"  [赛程] {team_name} 获取失败")
    return None

def fetch_recent_matches(league, team_name):
    """获取近期战绩（需 API key）"""
    if not ENABLE_RECENT or not FOOTBALL_DATA_API_KEY:
        return None
    league_code = {"沙职": "SA1", "沙特联": "SA1", "沙地联": "SA1"}.get(league)
    if not league_code:
        return None
    english_name = get_english_name(team_name)
    if not english_name:
        return None

    team_id = _get_team_id(league_code, english_name)
    if not team_id:
        print(f"  [战绩] 未找到球队 ID：{team_name}")
        return None

    headers = {"X-Auth-Token": FOOTBALL_DATA_API_KEY}
    url = f"https://api.football-data.org/v4/teams/{team_id}/matches?status=FINISHED"
    data = get_json(url, headers=headers)
    if data and "matches" in data:
        recent = []
        for match in data["matches"][-5:]:
            try:
                if match["score"]["winner"] is None:
                    continue
                if match["homeTeam"]["name"].lower() == english_name.lower():
                    gf = match["score"]["fullTime"]["home"]
                    ga = match["score"]["fullTime"]["away"]
                    result = "W" if gf > ga else ("L" if gf < ga else "D")
                    opponent = match["awayTeam"]["name"]
                else:
                    gf = match["score"]["fullTime"]["away"]
                    ga = match["score"]["fullTime"]["home"]
                    result = "W" if gf > ga else ("L" if gf < ga else "D")
                    opponent = match["homeTeam"]["name"]
                recent.append({
                    "对手": opponent,
                    "比分": f"{gf}-{ga}",
                    "结果": result,
                    "日期": match["utcDate"][:10]
                })
            except:
                continue
        if recent:
            print(f"  [战绩] {team_name} 获取到 {len(recent)} 场近期比赛")
            return recent
    print(f"  [战绩] {team_name} 获取失败")
    return None

def fetch_xg(team_name):
    """获取 xG（Understat 等不支持沙特联赛，此函数暂不实现）"""
    if not ENABLE_XG:
        return None
    # 真实获取非常困难，返回 None
    return None

def fetch_injury(team_name):
    """获取伤停名单（无免费稳定源，尝试 SofaScore API，大概率失败）"""
    if not ENABLE_INJURY:
        return None
    # SofaScore API 需要特定请求头，且可能有反爬，成功率低
    # 此处省略实现，可后续自行研究
    return None

def fetch_odds(league, home, away):
    """获取竞彩赔率（中国竞彩官网/500彩票网反爬，无法稳定获取）"""
    if not ENABLE_ODDS:
        return None
    # 真实获取难度大，返回 None
    return None

# ==================== 辅助函数 ====================
def get_text(url, headers=None, timeout=8):
    try:
        r = requests.get(url, headers=headers, timeout=timeout)
        r.raise_for_status()
        return r.text
    except:
        return None

def get_json(url, headers=None, timeout=8):
    try:
        r = requests.get(url, headers=headers, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except:
        return None

def safe_float(value):
    try:
        return float(value)
    except:
        return None

def extract_city_from_team(team_name):
    city_prefixes = ["利雅得", "吉达", "麦加", "达曼", "哈萨", "布赖代", "艾卜哈", "塔伊", "卡利杰", "阿科多"]
    for prefix in city_prefixes:
        if team_name.startswith(prefix):
            return prefix
    return team_name

# ==================== 战意指数计算 ====================
def calculate_war_intention(home_standings, away_standings, home_future, away_future):
    def need_score(rank):
        if rank is None:
            return None
        return max(1, 10 - rank)

    home_need = need_score(home_standings.get("排名") if home_standings else None)
    away_need = need_score(away_standings.get("排名") if away_standings else None)

    def future_pressure(future_schedule):
        if not future_schedule:
            return None
        today = datetime.date.today()
        week_later = today + datetime.timedelta(days=7)
        count = 0
        for match in future_schedule:
            try:
                d = datetime.datetime.strptime(match["日期"], "%Y-%m-%d").date()
                if today <= d <= week_later:
                    count += 1
            except:
                pass
        if count >= 2:
            return 8
        elif count == 1:
            return 5
        else:
            return 3

    home_pressure = future_pressure(home_future)
    away_pressure = future_pressure(away_future)

    home_rest = 7
    away_rest = 7

    home_coach = None
    away_coach = None
    home_fans = None
    away_fans = None

    def weighted_total(need, pressure, rest, coach, fans):
        scores = [need, pressure, rest, coach, fans]
        weights = [0.3, 0.2, 0.2, 0.15, 0.15]
        total = 0
        weight_sum = 0
        for s, w in zip(scores, weights):
            if s is not None:
                total += s * w
                weight_sum += w
        if weight_sum == 0:
            return None
        return round(total / weight_sum, 1)

    home_total = weighted_total(home_need, home_pressure, home_rest, home_coach, home_fans)
    away_total = weighted_total(away_need, away_pressure, away_rest, away_coach, away_fans)

    return {
        "主队加权总分": home_total,
        "客队加权总分": away_total,
        "计算依据": {
            "积分需求": {"主队": home_need, "客队": away_need, "依据": None},
            "未来赛程压力": {"主队": home_pressure, "客队": away_pressure, "依据": None},
            "俱乐部目标与教练表态": {"主队": home_coach, "客队": away_coach, "依据": None},
            "休息与体能": {"主队": home_rest, "客队": away_rest, "依据": None},
            "球迷媒体压力": {"主队": home_fans, "客队": away_fans, "依据": None}
        }
    }

# ==================== 第四部分：合并输出 ====================
def parse_input(input_str):
    pattern = r'^(\S+\d{3})\s+(\S+)\s+(.+?)\s+VS\s+(.+)$'
    match = re.match(pattern, input_str.strip(), re.IGNORECASE)
    if not match:
        return None
    return match.group(1), match.group(2), match.group(3).strip(), match.group(4).strip()

def build_markdown(data):
    template_str = """
## ⚽ {{ 赛事编号 }} {{ 联赛 }} {{ 主队 }} vs {{ 客队 }}

**数据覆盖等级**：{{ 数据覆盖等级 if 数据覆盖等级 is not none else 'null' }}  
**竞彩赔率状态**：{{ 竞彩赔率状态 if 竞彩赔率状态 is not none else 'null' }}  
**数据获取时间**：{{ 数据获取时间 if 数据获取时间 is not none else 'null' }}  

### 📊 基本面对比

**{{ 主队 }}**  
- Elo评分：{{ 基本面.主队.Elo评分 if 基本面.主队.Elo评分 is not none else 'null' }}  
- 近5场战绩：{{ 基本面.主队.近5场战绩 | join('、') if 基本面.主队.近5场战绩 is not none else 'null' }}  
- 近5场进/失球：{{ 基本面.主队.近5场进球 if 基本面.主队.近5场进球 is not none else 'null' }} / {{ 基本面.主队.近5场失球 if 基本面.主队.近5场失球 is not none else 'null' }}  
- 伤停：{% if 基本面.主队.伤停名单 %}{{ 基本面.主队.伤停名单 | map(attribute='球员') | join('、') }}{% else %}null{% endif %}  
- 预计首发完整性：{{ 基本面.主队.预计首发完整性 if 基本面.主队.预计首发完整性 is not none else 'null' }}  

**{{ 客队 }}**  
- Elo评分：{{ 基本面.客队.Elo评分 if 基本面.客队.Elo评分 is not none else 'null' }}  
- 近5场战绩：{{ 基本面.客队.近5场战绩 | join('、') if 基本面.客队.近5场战绩 is not none else 'null' }}  
- 近5场进/失球：{{ 基本面.客队.近5场进球 if 基本面.客队.近5场进球 is not none else 'null' }} / {{ 基本面.客队.近5场失球 if 基本面.客队.近5场失球 is not none else 'null' }}  
- 伤停：{% if 基本面.客队.伤停名单 %}{{ 基本面.客队.伤停名单 | map(attribute='球员') | join('、') }}{% else %}null{% endif %}  
- 预计首发完整性：{{ 基本面.客队.预计首发完整性 if 基本面.客队.预计首发完整性 is not none else 'null' }}  

### 🔥 战意指数
- 主队加权总分：{{ 战意指数.主队加权总分 if 战意指数.主队加权总分 is not none else 'null' }}  
- 客队加权总分：{{ 战意指数.客队加权总分 if 战意指数.客队加权总分 is not none else 'null' }}  

### 💰 竞彩盘口（胜平负）
- 初赔：主胜 {{ 竞彩盘口.胜平负.初赔.主胜 if 竞彩盘口.胜平负.初赔.主胜 is not none else 'null' }} / 平 {{ 竞彩盘口.胜平负.初赔.平 if 竞彩盘口.胜平负.初赔.平 is not none else 'null' }} / 客胜 {{ 竞彩盘口.胜平负.初赔.客胜 if 竞彩盘口.胜平负.初赔.客胜 is not none else 'null' }}  
- 即赔：主胜 {{ 竞彩盘口.胜平负.即赔.主胜 if 竞彩盘口.胜平负.即赔.主胜 is not none else 'null' }} / 平 {{ 竞彩盘口.胜平负.即赔.平 if 竞彩盘口.胜平负.即赔.平 is not none else 'null' }} / 客胜 {{ 竞彩盘口.胜平负.即赔.客胜 if 竞彩盘口.胜平负.即赔.客胜 is not none else 'null' }}  

### 🌦 环境变量
- 天气：{{ 环境变量.天气 if 环境变量.天气 is not none else 'null' }}  
- 比赛场地：{{ 环境变量.比赛场地 if 环境变量.比赛场地 is not none else 'null' }}  
- 主裁判：{{ 环境变量.主裁判.姓名 if 环境变量.主裁判.姓名 is not none else 'null' }}  

### ⚠️ 数据完整度
- xG获取：{{ 数据完整度.xG获取 if 数据完整度.xG获取 is not none else 'null' }}  
- Elo获取：{{ 数据完整度.Elo获取 if 数据完整度.Elo获取 is not none else 'null' }}  
- 伤停获取：{{ 数据完整度.伤停获取 if 数据完整度.伤停获取 is not none else 'null' }}  
- 风险提示：{{ 数据完整度.风险提示 if 数据完整度.风险提示 is not none else 'null' }}  

> 数据来源：ClubElo / SofaScore / OddsPortal / 500彩票网 / football-data.org  
> 生成时间：{{ 数据获取时间 if 数据获取时间 is not none else 'null' }}  
"""
    template = Template(template_str)
    return template.render(**data)

def send_dingtalk(markdown_text, title):
    if DINGTALK_WEBHOOK_URL == "https://oapi.dingtalk.com/robot/send?access_token=你的token":
        print("❌ 错误：请先配置钉钉机器人 Webhook 地址")
        return False

    webhook_url = DINGTALK_WEBHOOK_URL
    if DINGTALK_SECRET:
        timestamp = str(round(time.time() * 1000))
        secret_enc = DINGTALK_SECRET.encode("utf-8")
        string_to_sign = f"{timestamp}\n{DINGTALK_SECRET}"
        string_to_sign_enc = string_to_sign.encode("utf-8")
        hmac_code = hmac.new(secret_enc, string_to_sign_enc, digestmod=hashlib.sha256).digest()
        sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
        webhook_url = f"{webhook_url}&timestamp={timestamp}&sign={sign}"

    payload = {
        "msgtype": "markdown",
        "markdown": {
            "title": title,
            "text": markdown_text
        }
    }
    try:
        resp = requests.post(webhook_url, json=payload, timeout=10)
        result = resp.json()
        if result.get("errcode") == 0:
            print("✅ 钉钉推送成功")
            return True
        else:
            print(f"❌ 钉钉推送失败：{result}")
            return False
    except Exception as e:
        print(f"❌ 钉钉推送异常：{e}")
        return False

def main():
    input_str = os.environ.get("MATCH_INFO")
    if not input_str and len(sys.argv) > 1:
        input_str = " ".join(sys.argv[1:])

    if not input_str:
        print("请提供比赛信息，例如：周二001 沙职 利雅得新月 VS 吉达国民")
        sys.exit(1)

    parsed = parse_input(input_str)
    if not parsed:
        print("输入格式错误，请使用：周X001 联赛 主队 VS 客队")
        sys.exit(1)

    match_id, league, home, away = parsed
    print(f"正在获取 {match_id} {league} {home} vs {away} 的数据...")

    # ==================== 初始化数据结构 ====================
    data = {
        "赛事编号": match_id,
        "联赛": league,
        "主队": home,
        "客队": away,
        "数据覆盖等级": "低覆盖",
        "竞彩赔率状态": "已发布",
        "数据获取时间": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "赛季阶段信息": {
            "联赛": league,
            "赛季": None,
            "当前轮次": None,
            "近5场数据构成": None
        },
        "基本面": {
            "主队": {
                "Elo评分": None,
                "Elo来源": "ClubElo",
                "Elo来源URL": "https://clubelo.com/",
                "Elo更新时间": None,
                "本赛季xG": None,
                "本赛季xGA": None,
                "xG来源": None,
                "xG是否替代指标": None,
                "近5场xG": None,
                "近5场xGA": None,
                "近5场战绩": None,
                "近5场进球": None,
                "近5场失球": None,
                "近5场对手及赛事类型": None,
                "主场场均进球": None,
                "主场场均失球": None,
                "主场战绩": None,
                "主场胜率": None,
                "伤停名单": None,
                "预计首发完整性": None,
                "主教练": None
            },
            "客队": {
                "Elo评分": None,
                "Elo来源": "ClubElo",
                "Elo来源URL": "https://clubelo.com/",
                "Elo更新时间": None,
                "本赛季xG": None,
                "本赛季xGA": None,
                "xG来源": None,
                "xG是否替代指标": None,
                "近5场xG": None,
                "近5场xGA": None,
                "近5场战绩": None,
                "近5场进球": None,
                "近5场失球": None,
                "近5场对手及赛事类型": None,
                "客场场均进球": None,
                "客场场均失球": None,
                "客场战绩": None,
                "客场胜率": None,
                "伤停名单": None,
                "预计首发完整性": None,
                "主教练": None
            },
            "历史交锋": None
        },
        "战意指数": None,
        "节奏数据": None,
        "竞彩盘口": {
            "胜平负": {
                "初赔": {"主胜": None, "平": None, "客胜": None, "时间": None},
                "即赔": {"主胜": None, "平": None, "客胜": None, "时间": None}
            },
            "让球胜平负": None,
            "比分赔率": None,
            "总进球赔率": None,
            "半全场赔率": None,
            "返还率": None,
            "是否单关": None,
            "国际赔率": None,
            "凯利指数": None,
            "资金流向": None
        },
        "环境变量": {
            "天气": None,
            "比赛城市": None,
            "比赛场地": None,
            "场地类型": None,
            "主裁判": None,
            "未来赛程": None,
            "积分排名": None,
            "德比属性": None
        },
        "数据完整度": {
            "xG获取": False,
            "Elo获取": False,
            "伤停获取": False,
            "竞彩赔率获取": False,
            "伤停信息完整度": None,
            "数据适用性": None,
            "缺失项": [],
            "风险提示": None
        }
    }

    # ==================== 获取数据 ====================
    # 天气
    city_for_weather = extract_city_from_team(home)
    weather = fetch_weather(city_for_weather)
    if weather:
        data["环境变量"]["天气"] = weather

    # Elo
    home_elo = fetch_elo(home)
    away_elo = fetch_elo(away)
    if home_elo:
        data["基本面"]["主队"]["Elo评分"] = home_elo
        data["基本面"]["主队"]["Elo更新时间"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        data["数据完整度"]["Elo获取"] = True
    if away_elo:
        data["基本面"]["客队"]["Elo评分"] = away_elo
        data["基本面"]["客队"]["Elo更新时间"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        data["数据完整度"]["Elo获取"] = data["数据完整度"]["Elo获取"] and True

    # 积分排名
    standings = fetch_standings(league)
    if standings:
        data["环境变量"]["积分排名"] = standings
        home_stand = standings.get(home)
        away_stand = standings.get(away)
    else:
        home_stand = None
        away_stand = None

    # 未来赛程
    home_future = fetch_future_schedule(league, home)
    away_future = fetch_future_schedule(league, away)
    if home_future or away_future:
        data["环境变量"]["未来赛程"] = {
            "主队": home_future,
            "客队": away_future
        }

    # 近期战绩
    home_recent = fetch_recent_matches(league, home)
    away_recent = fetch_recent_matches(league, away)
    if home_recent:
        data["基本面"]["主队"]["近5场战绩"] = [m["结果"] for m in home_recent]
        data["基本面"]["主队"]["近5场进球"] = sum(int(m["比分"].split("-")[0]) for m in home_recent)
        data["基本面"]["主队"]["近5场失球"] = sum(int(m["比分"].split("-")[1]) for m in home_recent)
        data["基本面"]["主队"]["近5场对手及赛事类型"] = [{"对手": m["对手"], "赛事": league} for m in home_recent]
    if away_recent:
        data["基本面"]["客队"]["近5场战绩"] = [m["结果"] for m in away_recent]
        data["基本面"]["客队"]["近5场进球"] = sum(int(m["比分"].split("-")[0]) for m in away_recent)
        data["基本面"]["客队"]["近5场失球"] = sum(int(m["比分"].split("-")[1]) for m in away_recent)
        data["基本面"]["客队"]["近5场对手及赛事类型"] = [{"对手": m["对手"], "赛事": league} for m in away_recent]

    # xG、伤停、赔率（尝试真实获取，失败则保持 null）
    home_xg = fetch_xg(home)
    away_xg = fetch_xg(away)
    if home_xg:
        data["基本面"]["主队"]["近5场xG"] = home_xg.get("xG")
        data["基本面"]["主队"]["近5场xGA"] = home_xg.get("xGA")
        data["数据完整度"]["xG获取"] = True
    if away_xg:
        data["基本面"]["客队"]["近5场xG"] = away_xg.get("xG")
        data["基本面"]["客队"]["近5场xGA"] = away_xg.get("xGA")
        data["数据完整度"]["xG获取"] = data["数据完整度"]["xG获取"] and True

    home_injury = fetch_injury(home)
    away_injury = fetch_injury(away)
    if home_injury is not None:
        data["基本面"]["主队"]["伤停名单"] = home_injury
        data["数据完整度"]["伤停获取"] = True
    if away_injury is not None:
        data["基本面"]["客队"]["伤停名单"] = away_injury
        data["数据完整度"]["伤停获取"] = data["数据完整度"]["伤停获取"] and True

    odds = fetch_odds(league, home, away)
    if odds:
        data["竞彩盘口"] = odds
        data["数据完整度"]["竞彩赔率获取"] = True
        data["竞彩赔率状态"] = "已发布"
    else:
        data["竞彩赔率状态"] = "未获取"

    # 战意指数
    war_intention = calculate_war_intention(home_stand, away_stand, home_future, away_future)
    data["战意指数"] = war_intention

    # 数据完整度风险提示
    missing_fields = []
    if not data["数据完整度"]["Elo获取"]:
        missing_fields.append("Elo")
    if not data["数据完整度"]["xG获取"]:
        missing_fields.append("xG")
    if not data["数据完整度"]["伤停获取"]:
        missing_fields.append("伤停")
    if not data["数据完整度"]["竞彩赔率获取"]:
        missing_fields.append("竞彩赔率")
    data["数据完整度"]["缺失项"] = missing_fields
    if missing_fields:
        data["数据完整度"]["风险提示"] = "部分数据缺失：" + "、".join(missing_fields)
    else:
        data["数据完整度"]["风险提示"] = "数据完整"

    # 渲染推送
    markdown_text = build_markdown(data)
    print("\n生成的 Markdown 内容：")
    print(markdown_text)

    title = f"⚽ {match_id} {league} {home} vs {away}"
    send_dingtalk(markdown_text, title)

if __name__ == "__main__":
    main()