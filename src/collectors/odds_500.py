import asyncio
import re
from pathlib import Path
from urllib.parse import quote
from playwright.async_api import async_playwright
from utils import now_str

async def collect_500_odds(match):
    """
    从500彩票网抓取竞彩盘口数据（备用方案）。
    match: dict, 包含 match_no, match_date 等字段
    返回标准化 dict
    """
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
        "比分赔率": None,
        "总进球赔率": None,
        "半全场赔率": None,
        "返还率": {
            "胜平负返还率": None,
            "让球胜平负返还率": None
        },
        "是否单关": None,
        "查询时间": now_str()
    }

    base_url = "https://trade.500.com/jczq/"
    match_no = match.get("match_no", "")  # 例如 "周三003"
    detail_url = None

    # 调试目录
    debug_dir = Path("output/debug_500")
    debug_dir.mkdir(parents=True, exist_ok=True)

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = await context.new_page()
            page.set_default_timeout(20000)

            # 第一步：打开赛程页
            print(f"[500彩票网] 打开赛程页: {base_url}")
            await page.goto(base_url, wait_until="domcontentloaded")
            await page.wait_for_timeout(3000)

            # 保存调试文件
            try:
                await page.screenshot(path=str(debug_dir / "500_schedule.png"), full_page=True)
                with open(debug_dir / "500_schedule.html", "w", encoding="utf-8") as f:
                    f.write(await page.content())
                print("[500彩票网] 已保存赛程页调试文件")
            except Exception as e:
                print(f"[500彩票网] 保存调试文件失败: {e}")

            # 第二步：查找比赛链接
            # 500彩票网赛程页通常有比赛编号，格式如“周三003”
            try:
                # 先尝试文本匹配
                locator = page.locator(f"text={match_no}").first
                if await locator.count() > 0:
                    link_elem = locator.locator("xpath=ancestor::a[1]")
                    if await link_elem.count() > 0:
                        detail_url = await link_elem.get_attribute("href")
                        if detail_url:
                            if not detail_url.startswith("http"):
                                detail_url = "https://trade.500.com" + detail_url
                            print(f"[500彩票网] 通过文本找到比赛链接: {detail_url}")
                else:
                    print("[500彩票网] 赛程页未找到比赛编号，尝试模糊匹配")
                    # 模糊匹配：查找包含编号数字的链接
                    all_links = await page.eval_on_selector_all("a", "els => els.map(e => ({href: e.href, text: e.innerText}))")
                    num = match_no[-3:]
                    for link in all_links:
                        if num in link['text'] or num in link['href']:
                            detail_url = link['href']
                            print(f"[500彩票网] 通过模糊匹配找到: {detail_url}")
                            break
            except Exception as e:
                print(f"[500彩票网] 查找链接异常: {e}")

            # 如果未找到，尝试直接构造常见URL格式（需根据实际调整）
            if not detail_url:
                candidates = [
                    f"https://trade.500.com/jczq/{quote(match_no)}.shtml",
                    f"https://trade.500.com/jczq/{match_no[-3:]}.shtml",
                    # 实际格式请观察浏览器地址栏后修改
                ]
                for url in candidates:
                    try:
                        print(f"[500彩票网] 尝试直接访问: {url}")
                        resp = await page.goto(url, wait_until="domcontentloaded", timeout=10000)
                        if resp and resp.status == 200:
                            content = await page.content()
                            if "胜平负" in content or "欧赔" in content:
                                detail_url = url
                                print("[500彩票网] 直接访问成功")
                                break
                    except:
                        pass
                if not detail_url:
                    print("[500彩票网] 未能定位到比赛详情页，跳过")
                    return data

            # 第三步：进入详情页
            print(f"[500彩票网] 进入详情页: {detail_url}")
            await page.goto(detail_url, wait_until="networkidle")
            await page.wait_for_timeout(3000)

            # 保存详情页调试文件
            try:
                await page.screenshot(path=str(debug_dir / "500_detail.png"), full_page=True)
                with open(debug_dir / "500_detail.html", "w", encoding="utf-8") as f:
                    f.write(await page.content())
                print("[500彩票网] 已保存详情页调试文件")
            except Exception as e:
                print(f"[500彩票网] 保存详情页调试文件失败: {e}")

            # 第四步：解析赔率
            # 以下解析逻辑为通用猜测，需根据实际页面调整
            html = await page.content()

            # 尝试解析胜平负（简单正则提取）
            # 500彩票网可能将初赔和即赔放在表格中，数字格式如 "2.35 3.20 2.80"
            try:
                # 寻找包含“胜平负”的区域
                spf_section = page.locator("text=胜平负").first
                if await spf_section.count() > 0:
                    container = spf_section.locator("xpath=ancestor::div[contains(@class,'bet') or contains(@class,'table')][1]")
                    if await container.count() == 0:
                        container = spf_section.locator("xpath=ancestor::table[1]")
                    if await container.count() > 0:
                        text = await container.inner_text()
                        print(f"[500彩票网] 胜平负区域文本:\n{text}")
                        # 提取所有数字
                        numbers = re.findall(r"\d+\.\d+", text)
                        if len(numbers) >= 6:
                            data["胜平负"]["初赔"]["主胜"] = numbers[0]
                            data["胜平负"]["初赔"]["平"] = numbers[1]
                            data["胜平负"]["初赔"]["客胜"] = numbers[2]
                            data["胜平负"]["即赔"]["主胜"] = numbers[3]
                            data["胜平负"]["即赔"]["平"] = numbers[4]
                            data["胜平负"]["即赔"]["客胜"] = numbers[5]
            except Exception as e:
                print(f"[500彩票网] 解析胜平负失败: {e}")

            # 其他模块（让球、比分、总进球、半全场）类似处理，此处省略具体代码，请根据实际页面结构补充

            await browser.close()
    except Exception as e:
        print(f"[500彩票网] 采集异常: {e}")

    return data
