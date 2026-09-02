def collect_elo(team_name_en):
    """阶段3(1): Elo评分"""
    return {"Elo评分": None, "来源": None, "来源URL": None, "更新时间": None}

def collect_xg(team_name_en):
    """阶段3(2): xG/xGA"""
    return {"本赛季xG": None, "本赛季xGA": None, "近5场xG": None, "近5场xGA": None,
            "xG来源": None, "xG是否替代指标": None}

def collect_recent_form(team_name_en):
    """阶段3(3): 近期战绩与进攻防守数据"""
    return {"近5场战绩": None, "近5场进球": None, "近5场失球": None, "近5场对手及赛事类型": None,
            "主场场均进球": None, "主场场均失球": None, "主场战绩": None, "客场场均进球": None,
            "客场场均失球": None, "客场战绩": None, "胜率": None}

def collect_injuries(team_name_en):
    """阶段3(4): 伤停名单"""
    return {"伤停球员": [], "预计首发完整性": None}

def collect_coach_info(team_name_en):
    """阶段3(5): 主教练信息"""
    return {"姓名": None, "上任时间": None, "执教风格": None}

def collect_head_to_head(home_en, away_en):
    """阶段3(6): 历史交锋"""
    return {"近5次交锋": []}
