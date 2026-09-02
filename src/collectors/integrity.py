def self_check(match_data):
    """阶段8：数据完整度自检"""
    missing_paths = []
    # 遍历所有字段，找出None值的路径，这里简化处理
    # 实际需递归检查
    risk = []
    if match_data.get("盘口赔率", {}).get("胜平负", {}).get("初赔") is None:
        risk.append("竞彩胜平负初赔未获取")
    # 更多检查...
    return {
        "xG获取": "是" if match_data.get("基本面", {}).get("xG", {}).get("本赛季xG") else "否",
        "Elo获取": "是" if match_data.get("基本面", {}).get("Elo", {}).get("Elo评分") else "否",
        "伤停获取": "是" if match_data.get("基本面", {}).get("伤停", {}).get("伤停球员") else "否",
        "竞彩赔率获取": "是" if match_data.get("盘口赔率", {}).get("胜平负", {}).get("即赔") else "否",
        "伤停信息完整度": "高",  # 需根据实际情况判断
        "数据适用性": "高",  # 需根据实际情况判断
        "数据覆盖等级": "高",  # 同数据适用性
        "缺失项": missing_paths,
        "风险提示": risk
    }
