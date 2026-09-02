import asyncio
import re
import json
from pathlib import Path
from urllib.parse import quote
from playwright.async_api import async_playwright
from utils import now_str

async def collect_okooo_odds(match):
    """
    从澳客网抓取竞彩盘口数据。
    match: dict，包含 match_no, match_date 等字段
    返回标准化 dict
    """
    # ---------- 初始化返回结构 ----------
    data = {
        "胜平负": {
            "初赔": {"主胜": None, "平": None, "客胜": None, "时间": None},
            "即赔": {"主胜": None, "平": None, "客胜": None, "时间": None}
        },
        "让球胜平负": {
            "官方让球数": None,
            "初赔": {"让胜": None, "让平": None, "让负": None, "时间": None},
            "即赔": {"让胜": None, "让平": None, "让负": None, "时间": None}
        },
        "比分赔率": None,       # dict: "1-0" -> 赔率
        "总进球赔率": None,     # dict: "0","1","2","3","4","5","6","7+" -> 赔率
        "半全场赔率": None,     # dict: "胜胜","胜平"等9项 -> 赔率
        "返还率": {
            "胜平负返还率": None,
            "让球胜平负返还率": None
        },
        "是否单关": None,
        "查询时间": now_str()
    }

    # ---------- 构造比赛详情页 URL ----------
    base_url = "https://www.okooo.com/jingcai/"
    match_no = match.get("match_no", "")  # 例如 "周三002"
    # 通常澳客网竞彩赛程页会列出所有比赛，我们通过编号查找链接
    detail_url = None

    # 调试目录
    debug_dir = Path("output/debug")
    debug_dir.mkdir(parents=True, exist_ok=True)

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = await context.new_page()
            page.set_default_timeout(20000)

            # ---------- 第一步：打开赛程页 ----------
            print(f"[澳客网] 打开赛程页: {base_url}")
            await page.goto(base_url, wait_until="domcontentloaded")
            await page.wait_for_timeout(3000)

            # 可选：保存赛程页截图和HTML用于调试
            try:
                await page.screenshot(path=str(debug_dir / "okooo_schedule.png"), full_page=True)
                with open(debug_dir / "okooo_schedule.html", "w", encoding="utf-8") as f:
                    f.write(await page.content())
                print("[澳客网] 已保存赛程页调试文件")
            except Exception as e:
                print(f"[澳客网] 保存赛程页调试文件失败: {e}")

            # ---------- 第二步：查找比赛链接 ----------
            try:
                # 方法1：通过文本定位匹配的编号
                # 可能编号出现在span或a标签中
                locator = page.locator(f"text={match_no}").first
                if await locator.count() > 0:
                    # 向上查找最近的<a>标签
                    link_elem = locator.locator("xpath=ancestor::a[1]")
                    if await link_elem.count() > 0:
                        detail_url = await link_elem.get_attribute("href")
                        if detail_url:
                            if not detail_url.startswith("http"):
                                detail_url = "https://www.okooo.com" + detail_url
                            print(f"[澳客网] 通过文本找到比赛链接: {detail_url}")
                    else:
                        print("[澳客网] 定位到文本，但未找到父级<a>，尝试其他方法")
                else:
                    print("[澳客网] 赛程页未找到比赛编号，尝试直接构造URL")

                # 方法2：如果上面没找到，尝试模糊匹配（可能编号被拆分）
                if not detail_url:
                    # 例如文本可能为 "周三 002"，尝试查找包含数字002的链接
                    # 这里简化：查找所有链接，筛选含match_no最后三位数字的
                    all_links = await page.eval_on_selector_all("a", "els => els.map(e => ({href: e.href, text: e.innerText}))")
                    num = match_no[-3:]
                    for link in all_links:
                        if num in link['text'] or num in link['href']:
                            detail_url = link['href']
                            print(f"[澳客网] 通过模糊匹配找到: {detail_url}")
                            break

            except Exception as e:
                print(f"[澳客网] 查找比赛链接异常: {e}")

            # ---------- 如果仍未找到，尝试直接构造常见URL格式 ----------
            if not detail_url:
                # 尝试几种常见的URL格式
                candidates = [
                    f"https://www.okooo.com/jingcai/soccer/match/{quote(match_no)}",
                    f"https://www.okooo.com/jingcai/soccer/{quote(match_no)}.html",
                    # 有的网站用纯数字编号（例如去掉“周三”），可以尝试拆出数字部分
                    f"https://www.okooo.com/jingcai/soccer/match/{match_no[-3:]}"
                ]
                for url in candidates:
                    try:
                        print(f"[澳客网] 尝试直接访问: {url}")
                        resp = await page.goto(url, wait_until="domcontentloaded", timeout=10000)
                        if resp and resp.status == 200:
                            # 简单判断是否包含赔率关键词
                            content = await page.content()
                            if "胜平负" in content or "欧赔" in content:
                                detail_url = url
                                print("[澳客网] 直接访问成功")
                                break
                    except Exception as e:
                        print(f"[澳客网] 访问 {url} 失败: {e}")
                if not detail_url:
                    print("[澳客网] 未能定位到比赛详情页，跳过该场次赔率采集")
                    return data

            # ---------- 第三步：进入详情页并等待加载 ----------
            print(f"[澳客网] 进入详情页: {detail_url}")
            await page.goto(detail_url, wait_until="networkidle")
            await page.wait_for_timeout(3000)

            # ---------- 第四步：自动点击展开比分赔率按钮 ----------
            expand_texts = ["展开", "全部", "更多", "显示全部", "查看全部", "比分赔率"]
            clicked = False
            for text in expand_texts:
                try:
                    # 寻找按钮或链接，优先用button
                    btn = page.locator(f"button:has-text('{text}'), a:has-text('{text}'), span:has-text('{text}')").first
                    if await btn.count() > 0:
                        print(f"[澳客网] 找到展开按钮（{text}），点击")
                        await btn.click()
                        await page.wait_for_timeout(2000)
                        clicked = True
                        break
                except Exception as e:
                    print(f"[澳客网] 点击 '{text}' 按钮失败: {e}")
                    continue
            if not clicked:
                print("[澳客网] 未找到展开按钮，可能无需展开或按钮文本不同")

            # 保存详情页截图和HTML（点击后）
            try:
                await page.screenshot(path=str(debug_dir / "okooo_detail.png"), full_page=True)
                with open(debug_dir / "okooo_detail.html", "w", encoding="utf-8") as f:
                    f.write(await page.content())
                print("[澳客网] 已保存详情页调试文件")
            except Exception as e:
                print(f"[澳客网] 保存详情页调试文件失败: {e}")

            # ---------- 第五步：解析各赔率模块 ----------
            # 注意：以下选择器为通用猜测，可能需要根据实际页面调整
            html = await page.content()

            # --- 解析胜平负 ---
            try:
                # 假设赔率在表格中，且包含“胜平负”文字的表格行附近
                # 方法：找到包含“胜平负”的元素，然后在其父级表格中查找赔率
                spf_elements = page.locator("text=胜平负")
                count = await spf_elements.count()
                if count > 0:
                    # 取第一个匹配
                    element = spf_elements.first
                    # 向上找到最近的table
                    table = element.locator("xpath=ancestor::table[1]")
                    if await table.count() > 0:
                        # 获取表格中的所有文本，尝试解析
                        table_text = await table.inner_text()
                        print(f"[澳客网] 胜平负表格文本:\n{table_text}")
                        # 简单解析：查找数字模式
                        # 初赔和即赔可能分别在不同行
                        # 这里先粗暴提取所有数字
                        numbers = re.findall(r"\d+\.\d+", table_text)
                        if len(numbers) >= 6:
                            data["胜平负"]["初赔"]["主胜"] = numbers[0]
                            data["胜平负"]["初赔"]["平"] = numbers[1]
                            data["胜平负"]["初赔"]["客胜"] = numbers[2]
                            data["胜平负"]["即赔"]["主胜"] = numbers[3]
                            data["胜平负"]["即赔"]["平"] = numbers[4]
                            data["胜平负"]["即赔"]["客胜"] = numbers[5]
                        # 提取时间（如果存在）
                        times = re.findall(r"\d{2}-\d{2} \d{2}:\d{2}", table_text)
                        if len(times) >= 2:
                            data["胜平负"]["初赔"]["时间"] = times[0]
                            data["胜平负"]["即赔"]["时间"] = times[1]
                else:
                    print("[澳客网] 未找到包含'胜平负'的元素")
            except Exception as e:
                print(f"[澳客网] 解析胜平负失败: {e}")

            # --- 解析让球胜平负 ---
            try:
                # 查找包含“让球”的元素
                rqspf_elements = page.locator("text=让球胜平负")
                if await rqspf_elements.count() > 0:
                    element = rqspf_elements.first
                    table = element.locator("xpath=ancestor::table[1]")
                    if await table.count() > 0:
                        table_text = await table.inner_text()
                        print(f"[澳客网] 让球胜平负表格文本:\n{table_text}")
                        # 提取让球数（可能格式：-1, +1, 1球 等）
                        handicap_match = re.search(r"[-+]?\d球?", table_text)
                        if handicap_match:
                            data["让球胜平负"]["官方让球数"] = handicap_match.group()
                        # 提取数字
                        numbers = re.findall(r"\d+\.\d+", table_text)
                        if len(numbers) >= 6:
                            data["让球胜平负"]["初赔"]["让胜"] = numbers[0]
                            data["让球胜平负"]["初赔"]["让平"] = numbers[1]
                            data["让球胜平负"]["初赔"]["让负"] = numbers[2]
                            data["让球胜平负"]["即赔"]["让胜"] = numbers[3]
                            data["让球胜平负"]["即赔"]["让平"] = numbers[4]
                            data["让球胜平负"]["即赔"]["让负"] = numbers[5]
                        times = re.findall(r"\d{2}-\d{2} \d{2}:\d{2}", table_text)
                        if len(times) >= 2:
                            data["让球胜平负"]["初赔"]["时间"] = times[0]
                            data["让球胜平负"]["即赔"]["时间"] = times[1]
            except Exception as e:
                print(f"[澳客网] 解析让球胜平负失败: {e}")

            # --- 解析比分赔率 ---
            # 比分赔率通常在一个单独的表格中，包含31个比分选项
            try:
                # 找到包含“比分”的标题
                score_section = page.locator("text=比分").first
                if await score_section.count() > 0:
                    # 向上找到容器，例如div或table
                    container = score_section.locator("xpath=ancestor::div[contains(@class,'bd') or contains(@class,'table')][1]")
                    if await container.count() == 0:
                        container = score_section.locator("xpath=ancestor::table[1]")
                    if await container.count() > 0:
                        container_text = await container.inner_text()
                        print(f"[澳客网] 比分区域文本:\n{container_text}")
                        # 提取所有比分和赔率对
                        # 常见格式如 "1:0 6.50" 或 "1-0 6.50"
                        pairs = re.findall(r"(\d+[:：-]\d+|\w+)\s+(\d+\.\d+)", container_text)
                        if pairs:
                            score_dict = {}
                            for score, odds in pairs:
                                # 统一格式为1-0
                                score_clean = score.replace(":", "-").replace("：", "-")
                                score_dict[score_clean] = odds
                            data["比分赔率"] = score_dict
                        else:
                            # 如果正则未匹配，尝试提取表格行
                            rows = container.locator("tr")
                            row_count = await rows.count()
                            for i in range(row_count):
                                row_text = await rows.nth(i).inner_text()
                                # 处理每一行，例如可能一行包含多个比分
                                # 简单调试输出
                                print(f"[澳客网] 比分行 {i}: {row_text}")
            except Exception as e:
                print(f"[澳客网] 解析比分赔率失败: {e}")

            # --- 解析总进球赔率 ---
            try:
                total_section = page.locator("text=总进球").first
                if await total_section.count() > 0:
                    container = total_section.locator("xpath=ancestor::table[1]")
                    if await container.count() > 0:
                        text = await container.inner_text()
                        print(f"[澳客网] 总进球区域文本:\n{text}")
                        # 提取数字对：例如 "0 6.50  1 4.20 ..."
                        pairs = re.findall(r"(\d\+?)\s+(\d+\.\d+)", text)
                        if pairs:
                            total_dict = {k: v for k, v in pairs}
                            data["总进球赔率"] = total_dict
            except Exception as e:
                print(f"[澳客网] 解析总进球失败: {e}")

            # --- 解析半全场赔率 ---
            try:
                hf_section = page.locator("text=半全场").first
                if await hf_section.count() > 0:
                    container = hf_section.locator("xpath=ancestor::table[1]")
                    if await container.count() > 0:
                        text = await container.inner_text()
                        print(f"[澳客网] 半全场区域文本:\n{text}")
                        # 半全场有9项：胜胜、胜平、胜负、平胜、平平、平负、负胜、负平、负负
                        # 格式可能是 "胜胜 3.20  胜平 5.50 ..."
                        # 提取所有类似项
                        options = ["胜胜", "胜平", "胜负", "平胜", "平平", "平负", "负胜", "负平", "负负"]
                        hf_dict = {}
                        for opt in options:
                            # 在文本中查找该词后面的赔率
                            match = re.search(rf"{opt}\s+(\d+\.\d+)", text)
                            if match:
                                hf_dict[opt] = match.group(1)
                        data["半全场赔率"] = hf_dict
            except Exception as e:
                print(f"[澳客网] 解析半全场失败: {e}")

            # --- 解析返还率 ---
            # 页面可能直接显示返还率数值，或需要根据赔率计算
            try:
                # 查找“返还率”文本
                return_section = page.locator("text=返还率").first
                if await return_section.count() > 0:
                    container = return_section.locator("xpath=ancestor::tr[1]")
                    if await container.count() > 0:
                        return_text = await container.inner_text()
                        print(f"[澳客网] 返还率文本: {return_text}")
                        # 提取百分比数字
                        percentages = re.findall(r"(\d+\.\d+%)", return_text)
                        if len(percentages) >= 2:
                            data["返还率"]["胜平负返还率"] = percentages[0]
                            data["返还率"]["让球胜平负返还率"] = percentages[1]
                else:
                    # 若没有显示，则根据赔率计算并标注“计算值”
                    # 计算胜平负返还率 = 1 / (1/主胜 + 1/平 + 1/客胜)
                    try:
                        h, d, a = float(data["胜平负"]["初赔"]["主胜"]), float(data["胜平负"]["初赔"]["平"]), float(data["胜平负"]["初赔"]["客胜"])
                        if h and d and a:
                            calc = 1 / (1/h + 1/d + 1/a)
                            data["返还率"]["胜平负返还率"] = f"{calc*100:.2f}% (计算值)"
                    except:
                        pass
            except Exception as e:
                print(f"[澳客网] 解析返还率失败: {e}")

            # --- 解析是否单关 ---
            try:
                # 查找“单关”字样
                single_section = page.locator("text=单关").first
                if await single_section.count() > 0:
                    text = await single_section.inner_text()
                    if "是" in text or "允许" in text:
                        data["是否单关"] = True
                    elif "否" in text or "禁止" in text:
                        data["是否单关"] = False
                    else:
                        data["是否单关"] = None
            except Exception as e:
                print(f"[澳客网] 解析是否单关失败: {e}")

            await browser.close()
    except Exception as e:
        print(f"[澳客网] 整体采集异常: {e}")

    return data
