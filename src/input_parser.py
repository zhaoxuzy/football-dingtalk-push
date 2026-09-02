import re
from datetime import datetime, timedelta

WEEKDAY_MAP = {
    "周一": 0, "周二": 1, "周三": 2, "周四": 3, "周五": 4, "周六": 5, "周日": 6
}

LEAGUE_MAP = {
    "英超": "英格兰超级联赛", "英冠": "英格兰冠军联赛", "英甲": "英格兰甲级联赛", "英乙": "英格兰乙级联赛",
    "西甲": "西班牙甲级联赛", "西乙": "西班牙乙级联赛", "意甲": "意大利甲级联赛", "意乙": "意大利乙级联赛",
    "德甲": "德国甲级联赛", "德乙": "德国乙级联赛", "法甲": "法国甲级联赛", "法乙": "法国乙级联赛",
    "荷甲": "荷兰甲级联赛", "荷乙": "荷兰乙级联赛", "葡超": "葡萄牙超级联赛", "苏超": "苏格兰超级联赛",
    "比甲": "比利时甲级联赛", "奥甲": "奥地利甲级联赛", "瑞超": "瑞士超级联赛", "瑞典超": "瑞典超级联赛",
    "挪超": "挪威超级联赛", "芬超": "芬兰超级联赛", "丹超": "丹麦超级联赛", "波兰甲": "波兰甲级联赛",
    "捷克甲": "捷克甲级联赛", "希腊超": "希腊超级联赛", "土超": "土耳其超级联赛", "俄超": "俄罗斯超级联赛",
    "乌克超": "乌克兰超级联赛", "沙职": "沙特职业联赛", "卡塔联": "卡塔尔联赛", "阿联酋超": "阿联酋超级联赛",
    "美职": "美国职业足球大联盟", "墨超": "墨西哥超级联赛", "巴甲": "巴西甲级联赛", "巴乙": "巴西乙级联赛",
    "阿甲": "阿根廷甲级联赛", "智甲": "智利甲级联赛", "哥伦甲": "哥伦比亚甲级联赛", "乌拉甲": "乌拉圭甲级联赛",
    "日职": "日本职业联赛", "日乙": "日本乙级联赛", "韩K": "韩国K联赛", "韩K2": "韩国K2联赛",
    "澳超": "澳大利亚超级联赛", "中超": "中国超级联赛", "中甲": "中国甲级联赛",
    "欧冠": "欧洲冠军联赛", "欧联": "欧洲联赛", "欧会杯": "欧洲协会联赛", "亚冠": "亚洲冠军联赛",
    "亚联": "亚洲联赛", "世俱杯": "世界俱乐部杯", "友谊赛": "友谊赛", "世界杯": "世界杯",
    "欧洲杯": "欧洲杯", "美洲杯": "美洲杯", "亚洲杯": "亚洲杯", "非洲杯": "非洲杯",
    "国王杯": "西班牙国王杯", "足总杯": "英格兰足总杯", "联赛杯": "英格兰联赛杯", "德国杯": "德国杯",
    "意大利杯": "意大利杯", "法国杯": "法国杯", "巴西杯": "巴西杯", "亚冠杯": "亚冠杯"
}

def parse_match_input(input_text, target_date=None):
    if target_date is None:
        target_date = datetime.now().date()
    elif isinstance(target_date, str):
        target_date = datetime.strptime(target_date, "%Y-%m-%d").date()

    matches = []
    lines = [l.strip() for l in input_text.strip().splitlines() if l.strip()]
    pattern = re.compile(r"^(周[一二三四五六日])(\d{3})\s+(.+?)\s+VS\s+(.+?)$", re.IGNORECASE)
    for line in lines:
        m = pattern.match(line)
        if not m:
            print(f"无法解析的行：{line}")
            continue
        weekday_cn = m.group(1)
        match_no = f"{weekday_cn}{m.group(2)}"
        middle_part = m.group(3).strip()
        away_team = m.group(4).strip()

        league = None
        home_team = middle_part
        for abbr, full in LEAGUE_MAP.items():
            if middle_part.startswith(abbr):
                league = full
                home_team = middle_part[len(abbr):].strip()
                break
        if league is None:
            tokens = middle_part.split()
            if len(tokens) >= 2 and tokens[0] in LEAGUE_MAP:
                league = LEAGUE_MAP[tokens[0]]
                home_team = " ".join(tokens[1:]).strip()

        weekday_num = WEEKDAY_MAP[weekday_cn]
        days_ahead = (weekday_num - target_date.weekday()) % 7
        match_date = target_date + timedelta(days=days_ahead)

        matches.append({
            "match_no": match_no,
            "weekday": weekday_cn,
            "league": league,
            "home_team": home_team,
            "away_team": away_team,
            "match_date": match_date.strftime("%Y-%m-%d")
        })
    return matches
