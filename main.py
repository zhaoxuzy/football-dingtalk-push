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

# ==================== 配置区域 ====================
# 从环境变量读取钉钉机器人配置（GitHub Actions 中通过 Secrets 提供）
DINGTALK_WEBHOOK_URL = os.environ.get("DINGTALK_WEBHOOK_URL", "https://oapi.dingtalk.com/robot/send?access_token=你的token")
DINGTALK_SECRET = os.environ.get("DINGTALK_SECRET", "")

# 数据获取开关（目前数据获取函数尚未实现，开关保留用于后续扩展）
ENABLE_WEATHER = True
ENABLE_INJURY = True
ENABLE_XG = True
ENABLE_ELO = True
ENABLE_ODDS = True
# ==================================================

# ==================== 辅助函数 ====================
def get_text(url, headers=None, timeout=5):
    """通用 GET 请求，返回文本，失败返回 None"""
    try:
        r = requests.get(url, headers=headers, timeout=timeout)
        r.raise_for_status()
        return r.text
    except:
        return None

def get_json(url, headers=None, timeout=5):
    """通用 GET JSON 请求，失败返回 None"""
    try:
        r = requests.get(url, headers=headers, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except:
        return None

def safe_float(value):
    """安全转换 float，失败返回 None"""
    try:
        return float(value)
    except:
        return None

# ==================== 数据获取函数（目前为框架，返回 None） ====================
# 后续你可以在这里实现具体的爬虫或 API 调用

def fetch_elo(team_name):
    """获取球队 Elo 评分，尝试多个免费源，失败返回 None"""
    if not ENABLE_ELO:
        return None
    # TODO: 实现 Elo 获取
    # 例如：请求 ClubElo API 或 eloratings.net
    return None

def fetch_xg(team_name):
    """获取近5场 xG 数据，失败返回 None"""
    if not ENABLE_XG:
        return None
    # TODO: 实现 xG 获取
    # 例如：Understat 或 FBref
    return None

def fetch_injury(team_name):
    """获取伤停名单，失败返回 None"""
    if not ENABLE_INJURY:
        return None
    # TODO: 实现伤停获取
    # 例如：SofaScore / WhoScored
    return None

def fetch_odds(league, home, away):
    """获取竞彩赔率，失败返回 None"""
    if not ENABLE_ODDS:
        return None
    # TODO: 实现竞彩赔率获取
    # 例如：500彩票网接口
    return None

def fetch_weather(city):
    """获取天气，使用 wttr.in（免费无key），失败返回 None"""
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
    """获取积分排名，失败返回 None"""
    # TODO: 实现积分排名获取
    return None

# ==================== 战意指数计算（方案A：客观字段自动，主观字段为 None） ====================

def calculate_war_intention(home_standings, away_standings, home_future, away_future):
    """
    根据客观数据计算战意指数，主观字段（教练表态、球迷压力）为 None。
    返回字典或 None。
    """
    # 积分需求：排名越靠前需求越高，1-10分
    def need_score(rank):
        if rank is None:
            return None
        return max(1, 10 - rank)  # 排名1得9，排名10得1

    home_need = need_score(home_standings.get("排名") if home_standings else None)
    away_need = need_score(away_standings.get("排名") if away_standings else None)

    # 未来赛程压力：未来7天内比赛场次（需提供未来赛程列表）
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

    # 休息与体能：简化默认7（实际可计算休息天数）
    home_rest = 7
    away_rest = 7

    # 主观部分设为 None
    home_coach = None
    away_coach = None
    home_fans = None
    away_fans = None

    # 加权总分（主观为 None 时按比例调整权重）
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
        # 归一化到 0-10
        return round(total / weight_sum * 10, 1)

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
    """解析输入字符串，返回 (赛事编号, 联赛, 主队, 客队) 或 None"""
    # 匹配：周X001 联赛 主队 VS 客队
    pattern = r'^(\S+\d{3})\s+(\S+)\s+(.+?)\s+VS\s+(.+)$'
    match = re.match(pattern, input_str.strip(), re.IGNORECASE)
    if not match:
        return None
    return match.group(1), match.group(2), match.group(3).strip(), match.group(4).strip()

def build_markdown(data):
    """渲染 Markdown 模板，None 会显示为 null"""
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

> 数据来源：ClubElo / SofaScore / OddsPortal / 500彩票网  
> 生成时间：{{ 数据获取时间 if 数据获取时间 is not none else 'null' }}  
"""
    template = Template(template_str)
    return template.render(**data)

def send_dingtalk(markdown_text, title):
    """推送钉钉 Markdown 消息，返回是否成功"""
    if DINGTALK_WEBHOOK_URL == "https://oapi.dingtalk.com/robot/send?access_token=你的token":
        print("❌ 错误：请先配置钉钉机器人 Webhook 地址")
        return False

    webhook_url = DINGTALK_WEBHOOK_URL
    if DINGTALK_SECRET:
        # 加签处理
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
    # 优先从环境变量读取输入（GitHub Actions 使用）
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

    # ==================== 初始化数据结构（所有字段默认 None） ====================
    data = {
        "赛事编号": match_id,
        "联赛": league,
        "主队": home,
        "客队": away,
        "数据覆盖等级": "低覆盖",  # 可后续根据实际数据调整
        "竞彩赔率状态": "已发布",  # 可后续根据赔率获取状态调整
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

    # ==================== 获取数据（按模块，失败则保持 None） ====================
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

    print("获取 xG 数据...")
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

    print("获取伤停信息...")
    home_injury = fetch_injury(home)
    away_injury = fetch_injury(away)
    if home_injury is not None:
        data["基本面"]["主队"]["伤停名单"] = home_injury
        data["数据完整度"]["伤停获取"] = True
    if away_injury is not None:
        data["基本面"]["客队"]["伤停名单"] = away_injury
        data["数据完整度"]["伤停获取"] = data["数据完整度"]["伤停获取"] and True

    print("获取竞彩赔率...")
    odds = fetch_odds(league, home, away)
    if odds:
        data["竞彩盘口"] = odds
        data["数据完整度"]["竞彩赔率获取"] = True
        data["竞彩赔率状态"] = "已发布"
    else:
        data["竞彩赔率状态"] = "未获取"

    print("获取天气...")
    weather = fetch_weather(home)  # 使用主队所在城市，实际应使用比赛城市
    if weather:
        data["环境变量"]["天气"] = weather

    print("获取积分排名...")
    standings = fetch_standings(league)
    if standings:
        data["环境变量"]["积分排名"] = standings

    # 战意指数计算（方案A）
    # 未来赛程目前暂未获取，所以传入 None
    war_intention = calculate_war_intention(
        home_standings=standings.get("主队") if standings else None,
        away_standings=standings.get("客队") if standings else None,
        home_future=None,
        away_future=None
    )
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

    # ==================== 渲染与推送 ====================
    markdown_text = build_markdown(data)
    print("\n生成的 Markdown 内容：")
    print(markdown_text)

    title = f"⚽ {match_id} {league} {home} vs {away}"
    send_dingtalk(markdown_text, title)

if __name__ == "__main__":
    main()
