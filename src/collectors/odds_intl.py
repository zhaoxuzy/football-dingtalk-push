def collect_international_odds(match):
    """阶段6(8-10): 国际赔率、凯利指数、资金流向"""
    return {
        "亚盘": {"初盘": None, "即盘": None},
        "国际欧赔": {"初赔": None, "即赔": None},
        "大小球": {"初盘": None, "即盘": None},
        "凯利指数": {"主胜": None, "平": None, "客胜": None, "来源": None, "算法版本": None},
        "资金流向": {"主胜占比": None, "平占比": None, "客胜占比": None, "来源": None, "是否真实交易量": None},
        "查询时间": None
    }
