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
FOOTBALL_DATA_API_KEY = os.environ.get("FOOTBALL_DATA_API_KEY", "")

ENABLE_WEATHER = True
ENABLE_INJURY = True
ENABLE_XG = True
ENABLE_ELO = True
ENABLE_ODDS = True
ENABLE_STANDINGS = True
# ==================================================

# ==================== 球队名称映射（中文 → 英文，用于国际数据源） ====================
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
    # 可继续添加
}

# football-data.org 联赛 ID 映射（沙特职业联赛 ID）
LEAGUE_ID_MAP = {
    "沙职": "SA1",  # 沙特职业联赛在 football-data.org 的代码是 SA1
    "沙特联": "SA1",
    "沙地联": "SA1",
    # 其他联赛可自行添加
}

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

# ==================== 数据获取函数 ====================

def fetch_elo(team_name):
    """获取球队 Elo 评分，依次尝试 ClubElo API 和 eloratings.net CSV"""
    if not ENABLE_ELO:
        return None

    english_name = TEAM_NAME_MAP.get(team_name)
    if not english_name:
        print(f"  [Elo] 未找到 {team_name} 的英文映射，跳过")
        return None

    # 源1: ClubElo API
    api_url = f"https://api.clubelo.com/{english_name.replace(' ', '')}"
    data = get_json(api_url)
    if data:
        try:
            if isinstance(data, list) and len(data) > 0:
                elo = safe_float(data[0].get("Elo"))
                if elo:
                    print(f"  [Elo] {team_name} ({english_name}) Elo={elo} (ClubElo)")
                    return elo
        except:
            pass

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
                        print(f"  [Elo] {team_name} ({english_name}) Elo={elo} (eloratings.net)")
                        return elo
        except:
            pass

    print(f"  [Elo] {team_name} 获取失败")
    return None

def fetch_xg(team_name):
    """获取近5场 xG 数据（尝试 Understat，可能需要球队 ID）"""
    if not ENABLE_XG:
        return None
    # Understat 不覆盖沙特联赛，返回 None 是合理的
    return None

def fetch_injury(team_name):
    """获取伤停名单（尝试 SofaScore，成功概率低）"""
    if not ENABLE_INJURY:
        return None
    # TODO: 实现 SofaScore API 获取伤停，需要伪造请求头和球队 ID
    return None

def fetch_odds(league, home, away):
    """获取竞彩赔率（尝试中国竞彩官网或500彩票网）"""
    if not ENABLE_ODDS:
        return None
    # 中国竞彩官网接口通常需要特定的参数，且国外服务器访问可能被限制
    # 这里保留占位，返回 None
    return None

def fetch_weather(city):
    """获取天气，使用 wttr.in"""
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
            return None
    return None

def fetch_standings(league):
    """从 football-data.org 获取积分排名"""
    if not ENABLE_STANDINGS or not FOOTBALL_DATA_API_KEY:
        return None
    league_code = LEAGUE_ID_MAP.get(league)
    if not league_code:
        print(f"  [Standings] 未找到 {league} 的联赛代码")
        return None

    headers = {"X-Auth-Token": FOOTBALL_DATA_API_KEY}
    url = f"https://api.football-data.org/v4/competitions/{league_code}/standings"
    data = get_json(url, headers=headers)
    if data and "standings" in data:
        # 返回第一个赛季的积分表（一般是当前赛季）
        try:
            table = data["standings"][0]["table"]
            standings = {}
            for row in table:
                team_name = row["team"]["name"]
                # 尝试匹配中文名
                for cn, en in TEAM_NAME_MAP.items():
                    if en.lower() == team_name.lower() or cn in team_name:
                        standings[cn] = {
                            "排名": row["position"],
                            "积分": row["points"],
                            "胜": row["won"],
                            "平": row["draw"],
                            "负": row["lost"]
                        }
                        break
            if standings:
                return standings
        except:
            pass
    return None

def fetch_future_schedule(league, team_name):
    """从 football-data.org 获取未来赛程"""
    if not FOOTBALL_DATA_API_KEY:
        return None
    league_code = LEAGUE_ID_MAP.get(league)
    if not league_code:
        return None
    english_name = TEAM_NAME_MAP.get(team_name)
    if not english_name:
        return None

    headers = {"X-Auth-Token": FOOTBALL_DATA_API_KEY}
    # 获取球队 ID
    teams_url = f"https://api.football-data.org/v4/competitions/{league_code}/teams"
    teams_data = get_json(teams_url, headers=headers)
    team_id = None
    if teams_data and "teams" in teams_data:
        for team in teams_data["teams"]:
            if team["name"].lower() == english_name.lower():
                team_id = team["id"]
                break
    if not team_id:
        return None

    # 获取未来比赛
    matches_url = f"https://api.football-data.org/v4/teams/{team_id}/matches?status=SCHEDULED"
    matches_data = get_json(matches_url, headers=headers)
    if matches_data and "matches" in matches_data:
        future = []
        for match in matches_data["matches"][:5]:  # 最多取5场
            try:
                date = match["utcDate"][:10]
                opponent = match["homeTeam"]["name"] if match["awayTeam"]["name"].lower() == english_name.lower() else match["awayTeam"]["name"]
                home_away = "主" if match["homeTeam"]["name"].lower() == english_name.lower() else "客"
                future.append({"对手": opponent, "主客": home_away, "日期": date})
            except:
                continue
        return future
    return None

def fetch_recent_matches(league, team_name):
    """从 football-data.org 获取近期战绩（近5场）"""
    if not FOOTBALL_DATA_API_KEY:
        return None
    league_code = LEAGUE_ID_MAP.get(league)
    if not league_code:
        return None
    english_name = TEAM_NAME_MAP.get(team_name)
    if not english_name:
        return None

    headers = {"X-Auth-Token": FOOTBALL_DATA_API_KEY}
    # 获取球队 ID
    teams_url = f"https://api.football-data.org/v4/competitions/{league_code}/teams"
    teams_data = get_json(teams_url, headers=headers)
    team_id = None
    if teams_data and "teams" in teams_data:
        for team in teams_data["teams"]:
            if team["name"].lower() == english_name.lower():
                team_id = team["id"]
                break
    if not team_id:
        return None

    # 获取已结束比赛
    matches_url = f"https://api.football-data.org/v4/teams/{team_id}/matches?status=FINISHED"
    matches_data = get_json(matches_url, headers=headers)
    if matches_data and "matches" in matches_data:
        recent = []
        for match in matches_data["matches"][-5:]:  # 最近5场
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
        return recent
    return None

# ==================== 战意指数计算（修正） ====================
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

# ==================== 主程序 ====================
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

    # 初始化 data 结构（同上，略去完整字典，保持原样）

    # 获取 Elo
    print("获取 Elo 评分...")
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

    # 获取积分排名
    print("获取积分排名...")
    standings = fetch_standings(league)
    if standings:
        data["环境变量"]["积分排名"] = standings
        home_stand = standings.get(home)
        away_stand = standings.get(away)
    else:
        home_stand = None
        away_stand = None

    # 获取未来赛程
    print("获取未来赛程...")
    home_future = fetch_future_schedule(league, home)
    away_future = fetch_future_schedule(league, away)
    if home_future:
        data["环境变量"]["未来赛程"] = {"主队": home_future, "客队": away_future} if away_future else {"主队": home_future}

    # 获取近期战绩
    print("获取近期战绩...")
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

    # 战意指数计算
    war_intention = calculate_war_intention(home_stand, away_stand, home_future, away_future)
    data["战意指数"] = war_intention

    # 获取天气
    print("获取天气...")
    weather = fetch_weather(home)  # 主队名可能不是城市名，但暂时如此
    if weather:
        data["环境变量"]["天气"] = weather

    # 数据完整度（更新）
    # ...

    # 渲染与推送
    markdown_text = build_markdown(data)
    print("\n生成的 Markdown 内容：")
    print(markdown_text)

    title = f"⚽ {match_id} {league} {home} vs {away}"
    send_dingtalk(markdown_text, title)

if __name__ == "__main__":
    main()
