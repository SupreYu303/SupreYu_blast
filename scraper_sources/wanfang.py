# =====================================================================
# 📄 文件说明：万方数据爬虫 (scraper_sources/wanfang.py)
# =====================================================================
# 【功能概述】
#   从万方数据（Wanfang Data）自动检索并下载 PDF 文献。
#   万方是中国第二大中文学术数据库，矿业工程文献丰富。
#
# 【运行方式】
#   from scraper_sources.wanfang import WanfangScraper
#   scraper = WanfangScraper()
#   scraper.run(keyword="立井爆破", max_pages=5)
# =====================================================================

import os
import time
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from scraper_sources.base import BaseScraper


class WanfangScraper(BaseScraper):
    """万方数据论文爬虫"""

    source_name = "万方数据"
    base_url = "https://s.wanfangdata.com.cn/paper"

    def search_and_download(self, keyword, max_pages=1):
        """
        从万方数据检索并下载 PDF 论文。

        【执行流程】
          1. 访问万方搜索页 → 人工破盾
          2. 等待结果加载或手动搜索
          3. 遍历结果页：逐篇尝试下载 PDF
          4. 自动翻页
        """
        driver = self.driver
        wait = self.wait

        # 1. 访问万方搜索页（URL 已含关键词）
        from urllib.parse import quote
        search_url = f"https://s.wanfangdata.com.cn/paper?q={quote(keyword)}"
        print(f"  📡 访问: {search_url}")
        driver.get(search_url)

        # 2. 人工破盾
        self.wait_for_human_verification()

        # 3. 等待页面完全加载（给足时间）
        print("  ⏳ 等待页面加载...")
        time.sleep(5)

        # 尝试查找结果列表（基于万方实际DOM结构）
        # 万方搜索结果标题在 span.title 中（不是 a 标签！）
        result_found = False
        for selector in [
            "//span[@class='title' and @tabindex='0']",
            "//div[contains(@class, 'normal-list')]//span[@class='title']",
            "//div[contains(@class, 'periodical-list')]//span[@class='title']",
            "//div[contains(@class, 'thesis-list')]//span[@class='title']",
            "//div[contains(@class, 'detail-list-wrap')]//span[@class='title']",
            "//a[@class='title' or contains(@class, 'title')]",
            "//h3/a",
        ]:
            try:
                elements = driver.find_elements(By.XPATH, selector)
                if elements and len(elements) > 0:
                    print(f"  ✅ 找到 {len(elements)} 条结果 (选择器: {selector[:50]}...)")
                    result_found = True
                    self._result_selector = selector
                    break
            except Exception:
                continue

        if not result_found:
            # 尝试手动搜索
            print("  ℹ️ 未检测到结果，尝试手动搜索...")
            try:
                # 找搜索框
                search_box = None
                for box_xpath in [
                    "//input[@id='search-input']",
                    "//input[contains(@class, 'search-input')]",
                    "//input[@name='q']",
                    "//input[@type='search']",
                    "//input[contains(@placeholder, '检索') or contains(@placeholder, '搜索')]",
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
                    driver.execute_script("arguments[0].value = '';", search_box)
                    time.sleep(0.2)
                    search_box.send_keys(keyword)
                    time.sleep(0.5)
                    # 用回车键触发搜索
                    search_box.send_keys(Keys.RETURN)
                    print("  🔍 已发送搜索请求")
                    time.sleep(5)

                    # 重新检测结果
                    for selector in [
                        "//span[@class='title' and @tabindex='0']",
                        "//div[contains(@class, 'normal-list')]//span[@class='title']",
                        "//div[contains(@class, 'periodical-list')]//span[@class='title']",
                        "//h3/a",
                        "//a[contains(@href, 'detail')]",
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
                    print("  ⚠️ 未找到搜索框")
            except Exception as e:
                print(f"  ⚠️ 手动搜索失败: {e}")

        if not result_found:
            # 保存调试截图和页面源码
            try:
                debug_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "outputs")
                if not os.path.exists(debug_dir):
                    os.makedirs(debug_dir)
                driver.save_screenshot(os.path.join(debug_dir, "wanfang_debug.png"))
                with open(os.path.join(debug_dir, "wanfang_debug.html"), "w", encoding="utf-8") as f:
                    f.write(driver.page_source)
                print(f"  📸 已保存调试截图到 outputs/wanfang_debug.png")
                print(f"  📄 已保存页面源码到 outputs/wanfang_debug.html")
                print(f"  💡 当前URL: {driver.current_url}")
                all_links = driver.find_elements(By.TAG_NAME, "a")
                print(f"  💡 页面中共有 {len(all_links)} 个链接")
            except Exception as dbg_err:
                print(f"  ⚠️ 调试信息保存失败: {dbg_err}")
            return 0

        print(f"\n� [{self.source_name}] 正在解析 [{keyword}] 检索结果...")

        downloaded = 0

        for page_num in range(1, max_pages + 1):
            print(f"\n📖 [{self.source_name}] 第 {page_num}/{max_pages} 页...")

            # 获取结果列表
            try:
                article_items = driver.find_elements(By.XPATH, self._result_selector)
                total = len(article_items)
            except Exception:
                print("  ⚠️ 获取结果列表失败")
                break

            if total == 0:
                print("  ⚠️ 本页未找到文献")
                break

            print(f"  📊 本页 {total} 条结果")

            for i in range(total):
                try:
                    # 重新获取元素引用
                    current_items = driver.find_elements(By.XPATH, self._result_selector)
                    if i >= len(current_items):
                        break

                    link = current_items[i]
                    title = link.text.strip()
                    if not title:
                        continue
                    print(f"  📄 [{i+1}/{total}] {title}")

                    original_window = driver.current_window_handle
                    old_windows = driver.window_handles

                    # 万方的标题是 span.title（不是 a 标签），需要找父级 div 或同级的下载按钮
                    # 先尝试在当前列表项中直接找下载按钮（无需进入详情页）
                    pdf_downloaded = False
                    try:
                        # 找到当前标题所在的列表项容器
                        parent_item = link.find_element(By.XPATH, "./ancestor::div[contains(@class, 'normal-list') or contains(@class, 'periodical-list') or contains(@class, 'thesis-list')]")
                        # 在列表项中找下载按钮
                        download_btns = parent_item.find_elements(By.XPATH, ".//div[contains(@class, 'wf-list-button')]//span[contains(text(), '下载')]")
                        if download_btns:
                            self.random_delay(0.3, 0.8)
                            driver.execute_script("arguments[0].click();", download_btns[0])
                            print(f"    ✅ 触发下载")
                            downloaded += 1
                            pdf_downloaded = True
                            self.random_delay(3.0, 5.0)
                    except Exception:
                        pass

                    if not pdf_downloaded:
                        # 备选：点击标题进入详情页找下载
                        try:
                            driver.execute_script("arguments[0].click();", link)
                            try:
                                WebDriverWait(driver, 8).until(lambda d: len(d.window_handles) > len(old_windows))
                                new_windows = [w for w in driver.window_handles if w not in old_windows]
                                if new_windows:
                                    driver.switch_to.window(new_windows[0])
                                    self.random_delay(1.5, 3.0)
                                    for pdf_xpath in [
                                        "//div[contains(@class, 'wf-list-button')]//span[contains(text(), '下载')]",
                                        "//a[contains(text(), 'PDF')]",
                                        "//a[contains(text(), '下载')]",
                                    ]:
                                        try:
                                            pdf_btn = driver.find_element(By.XPATH, pdf_xpath)
                                            if pdf_btn.is_displayed():
                                                driver.execute_script("arguments[0].click();", pdf_btn)
                                                print(f"    ✅ 触发 PDF 下载")
                                                downloaded += 1
                                                self.random_delay(3.0, 5.0)
                                                break
                                        except Exception:
                                            continue
                                    else:
                                        print(f"    ⚠️ 无下载按钮，跳过")
                                    driver.close()
                            except TimeoutException:
                                self.random_delay(1.0, 2.0)
                        except Exception:
                            pass

                    driver.switch_to.window(original_window)
                    self.random_delay(1.0, 2.0)

                except Exception as e:
                    print(f"    ❌ 错误: {e}")
                    self.safe_close_extra_windows(original_window)
                    continue

            # 翻页
            if page_num < max_pages:
                try:
                    next_btn = driver.find_element(By.XPATH,
                        "//a[contains(text(), '下一页') or contains(@class, 'next')]")
                    driver.execute_script("arguments[0].click();", next_btn)
                    self.random_delay(3.0, 5.0)
                except Exception:
                    print("  🛑 已到最后一页或无翻页按钮")
                    break

        print(f"\n[{self.source_name}] ✅ 共下载 {downloaded} 篇论文")
        return downloaded