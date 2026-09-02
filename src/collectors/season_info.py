from utils import random_sleep
import requests
from bs4 import BeautifulSoup

def collect_season_info(match, english_home, english_away):
    """采集阶段2：赛季阶段信息"""
    data = {
        "联赛": match.get("league"),
        "赛季": None,
        "当前轮次": None,
        "近5场数据构成": {
            "主队": None,
            "客队": None
        },
        "查询时间": None
    }
    # 实际实现需访问懂球帝/雷速，解析赛程及近期战绩
    # 此处为占位，返回None表示未采集成功
    return data
