# =====================================================================
# 📄 文件说明：知网爬虫 (scraper_sources/cnki.py)
# =====================================================================
# 【功能概述】
#   从中国知网（CNKI）自动检索并下载 PDF 文献。
#   迁移自原有 scraper_module.py，适配新的多源架构。
#
# 【运行方式】
#   from scraper_sources.cnki import CnkiScraper
#   scraper = CnkiScraper()
#   scraper.run(keyword="立井爆破", max_pages=5)
# =====================================================================

import time
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from scraper_sources.base import BaseScraper


class CnkiScraper(BaseScraper):
    """知网论文爬虫"""
    
    source_name = "CNKI 知网"
    base_url = "https://kns.cnki.net/kns8s/"
    
    def search_and_download(self, keyword, max_pages=1):
        """
        从知网检索并下载 PDF 论文。
        
        【执行流程】
          1. 访问知网首页 → 人工破盾
          2. 输入关键词 → 点击搜索
          3. 遍历结果页：逐篇点击 → 找 PDF 下载按钮 → 下载
          4. 自动翻页
        """
        driver = self.driver
        wait = self.wait
        
        # 1. 访问知网主页
        driver.get(self.base_url)
        
        # 2. 人工破盾
        self.wait_for_human_verification()
        
        # 3. 输入关键词搜索
        search_box = wait.until(EC.element_to_be_clickable(
            (By.XPATH, "//input[@id='txt_SearchText' or contains(@class, 'search-input')][not(@type='hidden')]")
        ))
        driver.execute_script("arguments[0].value = '';", search_box)
        time.sleep(0.5)
        search_box.send_keys(keyword)
        self.random_delay(0.5, 1.2)
        
        search_btn = driver.find_element(By.XPATH, "//input[@value='检索' or @class='search-btn']")
        search_btn.click()
        self.random_delay(3.0, 5.0)
        
        print(f"🔍 [{self.source_name}] 正在解析 [{keyword}] 检索结果...")
        
        downloaded = 0
        
        # 4. 多页循环
        for page_num in range(1, max_pages + 1):
            print(f"\n📖 [{self.source_name}] 第 {page_num}/{max_pages} 页...")
            
            try:
                article_links = wait.until(EC.presence_of_all_elements_located(
                    (By.XPATH, "//table[@class='result-table-list']//tr/td[@class='name']/a")
                ))
                total = len(article_links)
            except TimeoutException:
                print("⚠️ 本页未找到文献，可能已到底。")
                break
            
            for i in range(total):
                try:
                    current_links = wait.until(EC.presence_of_all_elements_located(
                        (By.XPATH, "//table[@class='result-table-list']//tr/td[@class='name']/a")
                    ))
                    if i >= len(current_links):
                        break
                    
                    link = current_links[i]
                    title = link.text
                    print(f"  📄 [{i+1}/{total}] {title}")
                    
                    original_window = driver.current_window_handle
                    old_windows = driver.window_handles
                    
                    driver.execute_script("arguments[0].click();", link)
                    wait.until(lambda d: len(d.window_handles) > len(old_windows))
                    new_windows = [w for w in driver.window_handles if w not in old_windows]
                    
                    if new_windows:
                        driver.switch_to.window(new_windows[0])
                        try:
                            pdf_btn = wait.until(EC.element_to_be_clickable(
                                (By.XPATH, "//a[contains(text(), 'PDF下载') or contains(@id, 'pdfDown')]")
                            ))
                            self.random_delay(0.5, 1.5)
                            driver.execute_script("arguments[0].click();", pdf_btn)
                            print(f"    ✅ 触发 PDF 下载")
                            downloaded += 1
                            self.random_delay(4.0, 6.0)
                        except TimeoutException:
                            print(f"    ⚠️ 无 PDF 下载按钮，跳过")
                        driver.close()
                    
                    driver.switch_to.window(original_window)
                    self.random_delay(1.0, 2.0)
                    
                except Exception as e:
                    print(f"    ❌ 错误: {e}")
                    self.safe_close_extra_windows(original_window)
                    continue
            
            # 翻页
            if page_num < max_pages:
                try:
                    next_btn = wait.until(EC.element_to_be_clickable(
                        (By.XPATH, "//a[@id='PageNext' or contains(text(), '下一页')]")
                    ))
                    driver.execute_script("arguments[0].click();", next_btn)
                    self.random_delay(4.0, 6.0)
                except TimeoutException:
                    print("🛑 已到最后一页")
                    break
        
        print(f"\n[{self.source_name}] ✅ 共下载 {downloaded} 篇论文")
        return downloaded