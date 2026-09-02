import os
import sys
import asyncio
from datetime import datetime
from pathlib import Path

from input_parser import parse_match_input
from team_mapper import get_english_team_name
from collectors.season_info import collect_season_info
from collectors.fundamentals import (
    collect_elo,
    collect_xg,
    collect_recent_form,
    collect_injuries,
    collect_coach_info,
    collect_head_to_head
)
from collectors.motivation import collect_motivation
from collectors.rhythm import collect_rhythm
from collectors.odds_500 import collect_500_odds
from collectors.odds_okooo import collect_okooo_odds
from collectors.odds_intl import collect_international_odds
from collectors.environment import collect_environment
from collectors.integrity import self_check
from utils import save_json, send_dingtalk, now_str


async def main():
    # 获取输入
    input_text = os.getenv("INPUT_MATCHES", "")
    target_date = os.getenv("INPUT_DATE", None)
    if not input_text:
        print("未提供比赛输入，退出")
        sys.exit(1)

    matches = parse_match_input(input_text, target_date)
    if not matches:
        print("无有效比赛")
        sys.exit(1)

    result_array = []
    for match in matches:
        print(f"开始采集: {match['match_no']} {match['home_team']} VS {match['away_team']}")

        # 翻译队名（中文→英文）
        home_en = get_english_team_name(match['home_team'])
        away_en = get_english_team_name(match['away_team'])
        match['home_team_en'] = home_en
        match['away_team_en'] = away_en

        # 初始化本场比赛数据结构
        match_data = {
            "基本标识": {
                "赛事编号": match['match_no'],
                "联赛": match.get('league'),
                "主队": match['home_team'],
                "客队": match['away_team'],
                "数据覆盖等级": None,      # 阶段8填写
                "竞彩赔率状态": False,     # 阶段6判断后更新
                "数据获取时间": now_str()
            },
            "赛季阶段信息": {},
            "基本面": {
                "主队": {},
                "客队": {},
                "历史交锋": None
            },
            "战意指数": {},
            "节奏数据": {},
            "竞彩盘口": {},
            "国际赔率": {},
            "环境变量": {},
            "自检": {}
        }

        # ----- 阶段2：赛季阶段信息 -----
        print("  阶段2: 赛季信息")
        match_data['赛季阶段信息'] = collect_season_info(match, home_en, away_en)

        # ----- 阶段3：基本面 -----
        print("  阶段3: 基本面")
        for side, team_en in [('主队', home_en), ('客队', away_en)]:
            if team_en:
                match_data['基本面'][side]['Elo'] = collect_elo(team_en)
                match_data['基本面'][side]['xG'] = collect_xg(team_en)
                match_data['基本面'][side]['近期战绩'] = collect_recent_form(team_en)
                match_data['基本面'][side]['伤停'] = collect_injuries(team_en)
                match_data['基本面'][side]['主教练'] = collect_coach_info(team_en)
            else:
                # 如果无法获取英文队名，则将整个子模块设为 None
                match_data['基本面'][side] = None
        if home_en and away_en:
            match_data['基本面']['历史交锋'] = collect_head_to_head(home_en, away_en)
        else:
            match_data['基本面']['历史交锋'] = None

        # ----- 阶段4：战意指数 -----
        print("  阶段4: 战意指数")
        match_data['战意指数'] = collect_motivation(match, home_en, away_en)

        # ----- 阶段5：节奏数据 -----
        print("  阶段5: 节奏数据")
        if home_en:
            match_data['节奏数据']['主队'] = collect_rhythm(home_en)
        else:
            match_data['节奏数据']['主队'] = None
        if away_en:
            match_data['节奏数据']['客队'] = collect_rhythm(away_en)
        else:
            match_data['节奏数据']['客队'] = None

        # ----- 阶段6：竞彩盘口（优先500彩票网，失败则澳客网） -----
        print("  阶段6: 竞彩盘口")
        odds_data = None
        try:
            odds_data = await collect_500_odds(match)
            # 检查500彩票网是否抓到了核心赔率（即赔的主胜）
            if not odds_data.get("胜平负", {}).get("即赔", {}).get("主胜"):
                print("  500彩票网未采集到完整赔率，尝试澳客网")
                odds_data = await collect_okooo_odds(match)
        except Exception as e:
            print(f"  500彩票网采集异常: {e}，尝试澳客网")
            odds_data = await collect_okooo_odds(match)

        match_data['竞彩盘口'] = odds_data
        # 更新竞彩赔率状态
        if odds_data and odds_data.get("胜平负", {}).get("即赔", {}).get("主胜"):
            match_data['基本标识']['竞彩赔率状态'] = True

        # ----- 阶段6（续）：国际赔率、凯利、资金流向 -----
        print("  阶段6: 国际赔率")
        match_data['国际赔率'] = collect_international_odds(match)

        # ----- 阶段7：环境变量 -----
        print("  阶段7: 环境变量")
        match_data['环境变量'] = collect_environment(match)

        # ----- 阶段8：自检与覆盖等级 -----
        print("  阶段8: 自检")
        match_data['自检'] = self_check(match_data)
        match_data['基本标识']['数据覆盖等级'] = match_data['自检']['数据覆盖等级']

        result_array.append(match_data)
        print(f"完成: {match['match_no']}\n")

    # 保存 JSON
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"jc_football_{timestamp}.json"
    filepath = save_json(result_array, filename)
    print(f"JSON 已保存: {filepath}")

    # 生成摘要并发送钉钉
    summary_lines = []
    summary_lines.append("### 竞彩数据采集完成")
    summary_lines.append(f"- 采集时间：{now_str()}")
    summary_lines.append(f"- 比赛数量：{len(result_array)}")
    high = sum(1 for m in result_array if m['自检'].get('数据覆盖等级') == '高')
    mid = sum(1 for m in result_array if m['自检'].get('数据覆盖等级') == '中')
    low = sum(1 for m in result_array if m['自检'].get('数据覆盖等级') == '低')
    summary_lines.append(f"- 覆盖等级：高 {high} 场，中 {mid} 场，低 {low} 场")
    # 列出主要缺失
    missing_summary = []
    for m in result_array:
        if m['自检'].get('缺失项'):
            missing_summary.append(f"{m['基本标识']['赛事编号']}: {', '.join(m['自检']['缺失项'][:3])}")
    if missing_summary:
        summary_lines.append("- 主要缺失：")
        summary_lines.extend([f"  - {x}" for x in missing_summary[:5]])
    # 附下载链接（GitHub Actions 运行时有效）
    if os.getenv("GITHUB_REPOSITORY") and os.getenv("GITHUB_RUN_ID"):
        artifact_url = f"https://github.com/{os.getenv('GITHUB_REPOSITORY')}/actions/runs/{os.getenv('GITHUB_RUN_ID')}"
        summary_lines.append(f"- [查看构建与下载]({artifact_url})")
    dingtalk_text = "\n".join(summary_lines)
    send_dingtalk("竞彩数据采集结果", dingtalk_text)


if __name__ == "__main__":
    asyncio.run(main())
