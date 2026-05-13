# =====================================================================
# 📄 文件说明：Google Scholar 爬虫 (scraper_sources/google_scholar.py)
# =====================================================================
# 【功能概述】
#   从 Google Scholar 自动检索论文并下载免费 PDF。
#   Google Scholar 聚合了全球学术论文，英文文献最全。
#
# 【注意事项】
#   1. 需要科学上网（Google Scholar 在国内被墙）
#   2. Google Scholar 反爬严格，需要人工处理 CAPTCHA
#   3. 建议使用 VPN/代理后再运行
#   4. 下载速度取决于是否有 Open Access 版本
#
# 【运行方式】
#   from scraper_sources.google_scholar import GoogleScholarScraper
#   scraper = GoogleScholarScraper()
#   scraper.run(keyword="shaft blasting", max_pages=3)
# =====================================================================

import os
import time
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from scraper_sources.base import BaseScraper


class GoogleScholarScraper(BaseScraper):
    """Google Scholar 论文爬虫"""

    source_name = "Google Scholar"
    base_url = "https://scholar.google.com/"

    def search_and_download(self, keyword, max_pages=1):
        """
        从 Google Scholar 检索论文并下载免费 PDF。

        【执行流程】
          1. 访问 Google Scholar → 人工处理 CAPTCHA
          2. 搜索关键词
          3. 遍历结果：找免费 PDF 链接并下载
          4. 自动翻页
        """
        driver = self.driver
        wait = self.wait

        # 1. 访问 Google Scholar
        search_url = f"https://scholar.google.com/scholar?q={keyword}&hl=en"
        print(f"  📡 访问: {search_url}")
        driver.get(search_url)

        # 2. 人工破盾（Google 可能有 CAPTCHA）
        self.wait_for_human_verification()

        # 3. 等待结果加载
        print("  ⏳ 等待搜索结果加载...")
        time.sleep(3)

        # 检测是否有搜索结果
        result_found = False
        for selector in [
            "//div[@class='gs_r gs_or gs_scl']//h3[@class='gs_rt']",
            "//div[contains(@class, 'gs_ri')]//h3[@class='gs_rt']/a",
            "//div[@id='gs_res_ccl']//h3/a",
            "//h3[@class='gs_rt']/a",
        ]:
            try:
                elements = driver.find_elements(By.XPATH, selector)
                if elements and len(elements) > 0:
                    print(f"  ✅ 找到 {len(elements)} 条结果")
                    result_found = True
                    self._result_selector = selector
                    break
            except Exception:
                continue

        if not result_found:
            # 可能需要手动搜索
            print("  ℹ️ 未检测到结果，尝试手动搜索...")
            try:
                search_box = None
                for box_xpath in [
                    "//input[@name='q']",
                    "//input[@aria-label='Search']",
                    "//input[@type='text']",
                ]:
                    try:
                        el = driver.find_element(By.XPATH, box_xpath)
                        if el.is_displayed():
                            search_box = el
                            break
                    except Exception:
                        continue

                if search_box:
                    search_box.clear()
                    search_box.send_keys(keyword)
                    search_box.send_keys(Keys.RETURN)
                    print("  🔍 已发送搜索请求")
                    time.sleep(5)

                    # 重新检测
                    for selector in [
                        "//h3[@class='gs_rt']/a",
                        "//div[contains(@class, 'gs_r')]//h3/a",
                    ]:
                        try:
                            elements = driver.find_elements(By.XPATH, selector)
                            if elements and len(elements) > 0:
                                print(f"  ✅ 找到 {len(elements)} 条结果")
                                result_found = True
                                self._result_selector = selector
                                break
                        except Exception:
                            continue
                else:
                    print("  ⚠️ 未找到搜索框，可能需要科学上网")
            except Exception as e:
                print(f"  ⚠️ 手动搜索失败: {e}")

        if not result_found:
            print("  ❌ 未能加载搜索结果")
            print("  💡 提示: Google Scholar 需要科学上网才能访问")
            # 保存调试信息
            try:
                debug_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "outputs")
                if not os.path.exists(debug_dir):
                    os.makedirs(debug_dir)
                driver.save_screenshot(os.path.join(debug_dir, "google_scholar_debug.png"))
                print(f"  📸 已保存调试截图到 outputs/google_scholar_debug.png")
            except Exception:
                pass
            return 0

        print(f"\n🔍 [{self.source_name}] 正在解析 [{keyword}] 检索结果...")

        downloaded = 0

        for page_num in range(1, max_pages + 1):
            print(f"\n📖 [{self.source_name}] 第 {page_num}/{max_pages} 页...")

            # 获取结果列表
            try:
                # Google Scholar 的每条结果在 div.gs_r.gs_or.gs_scl 中
                articles = driver.find_elements(By.XPATH, "//div[@class='gs_r gs_or gs_scl']")
                if not articles:
                    articles = driver.find_elements(By.XPATH, "//div[contains(@class, 'gs_r ')]")
                total = len(articles)
            except Exception:
                print("  ⚠️ 获取结果列表失败")
                break

            if total == 0:
                print("  ⚠️ 本页未找到文献")
                break

            print(f"  📊 本页 {total} 条结果")

            for i, article in enumerate(articles):
                try:
                    # 获取标题
                    try:
                        title_el = article.find_element(By.XPATH, ".//h3[@class='gs_rt']")
                        title = title_el.text.strip()
                    except Exception:
                        title = f"论文_{i+1}"

                    # 清理标题中的 [PDF] [HTML] 等标记
                    title = title.replace("[PDF]", "").replace("[HTML]", "").replace("[B]", "").strip()
                    print(f"  📄 [{i+1}/{total}] {title}")

                    # 尝试找免费 PDF 链接
                    pdf_downloaded = False
                    try:
                        # Google Scholar 的 PDF 链接通常在 gs_or_ggsm 区域
                        pdf_links = article.find_elements(By.XPATH,
                            ".//div[contains(@class, 'gs_or_ggsm')]//a | "
                            ".//a[contains(@href, '.pdf')] | "
                            ".//a[contains(@class, 'gs_ggs gs_fl')]"
                        )

                        for pdf_link in pdf_links:
                            pdf_url = pdf_link.get_attribute("href")
                            if pdf_url and (".pdf" in pdf_url.lower() or "pdf" in pdf_link.text.lower()):
                                # 用 requests 下载 PDF
                                import requests
                                safe_title = "".join(c for c in title if c.isalnum() or c in " _-").strip()[:80]
                                if not safe_title:
                                    safe_title = f"google_scholar_{downloaded+1}"
                                pdf_path = os.path.join(self.download_dir, f"{safe_title}.pdf")

                                print(f"    📥 正在下载 PDF...")
                                try:
                                    resp = requests.get(pdf_url, timeout=60, stream=True, headers={
                                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                                    })
                                    if resp.status_code == 200 and len(resp.content) > 1000:
                                        with open(pdf_path, "wb") as f:
                                            for chunk in resp.iter_content(chunk_size=8192):
                                                f.write(chunk)
                                        file_size = os.path.getsize(pdf_path)
                                        if file_size > 1000:
                                            print(f"    ✅ PDF 已保存 ({file_size/1024:.0f} KB)")
                                            downloaded += 1
                                            pdf_downloaded = True
                                            break
                                        else:
                                            os.remove(pdf_path)
                                except Exception as dl_err:
                                    print(f"    ⚠️ 下载异常: {dl_err}")
                    except Exception:
                        pass

                    if not pdf_downloaded:
                        print(f"    ℹ️ 无免费 PDF")

                    self.random_delay(1.0, 2.0)

                except Exception as e:
                    print(f"    ❌ 错误: {e}")
                    continue

            # 翻页
            if page_num < max_pages:
                try:
                    next_btn = driver.find_element(By.XPATH,
                        "//button[@aria-label='Next'] | //a[contains(@class, 'gs_nma')]"
                    )
                    driver.execute_script("arguments[0].click();", next_btn)
                    self.random_delay(3.0, 5.0)
                except Exception:
                    # 尝试通过 URL 翻页
                    try:
                        next_start = page_num * 10
                        next_url = f"https://scholar.google.com/scholar?q={keyword}&start={next_start}&hl=en"
                        driver.get(next_url)
                        self.random_delay(3.0, 5.0)
                    except Exception:
                        print("  🛑 翻页失败")
                        break

        print(f"\n[{self.source_name}] ✅ 共下载 {downloaded} 篇论文")
        return downloaded