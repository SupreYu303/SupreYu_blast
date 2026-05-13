# =====================================================================
# 📄 文件说明：百度学术爬虫 (scraper_sources/baidu_scholar.py)
# =====================================================================
# 【功能概述】
#   从百度学术（Xueshu Baidu）自动检索论文并收集 PDF 下载链接。
#   百度学术聚合了知网/万方/维普等多源，能找到免费 PDF 链接。
#
# 【运行方式】
#   from scraper_sources.baidu_scholar import BaiduScholarScraper
#   scraper = BaiduScholarScraper()
#   scraper.run(keyword="立井爆破", max_pages=5)
# =====================================================================

import time
import os
import requests
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from scraper_sources.base import BaseScraper


class BaiduScholarScraper(BaseScraper):
    """百度学术论文爬虫"""
    
    source_name = "百度学术"
    base_url = "https://xueshu.baidu.com/"
    
    def search_and_download(self, keyword, max_pages=1):
        """
        从百度学术检索论文并下载 PDF。
        
        【执行流程】
          1. 访问百度学术搜索页（无需人工破盾，百度学术反爬较弱）
          2. 遍历搜索结果，查找有 PDF 免费下载链接的论文
          3. 直接用 requests 下载 PDF（比 Selenium 更快更可靠）
          4. 自动翻页
        """
        driver = self.driver
        wait = self.wait
        
        # 1. 访问百度学术搜索页
        search_url = f"https://xueshu.baidu.com/s?wd={keyword}&pn=0"
        driver.get(search_url)
        
        # 百度学术通常不需要人工破盾，但加上保险
        try:
            wait.until(EC.presence_of_element_located(
                (By.XPATH, "//div[contains(@class, 'sc_default_result') or contains(@class, 'result')]")
            ))
        except TimeoutException:
            self.wait_for_human_verification()
        
        print(f"🔍 [{self.source_name}] 正在解析 [{keyword}] 检索结果...")
        
        downloaded = 0
        
        for page_num in range(1, max_pages + 1):
            print(f"\n📖 [{self.source_name}] 第 {page_num}/{max_pages} 页...")
            
            # 等待结果加载
            try:
                articles = wait.until(EC.presence_of_all_elements_located(
                    (By.XPATH, "//div[contains(@class, 'sc_default_result')]//div[contains(@class, 'result')] | "
                               "//div[contains(@class, 'res_item')]")
                ))
                total = len(articles)
            except TimeoutException:
                print("⚠️ 本页未找到文献")
                break
            
            for i in range(total):
                try:
                    # 获取论文标题
                    try:
                        title_el = driver.find_element(
                            By.XPATH,
                            f"(//div[contains(@class, 'sc_default_result')]//h3/a | "
                            f"//div[contains(@class, 'res_item')]//h3/a)[{i+1}]"
                        )
                        title = title_el.text.strip()
                    except Exception:
                        title = f"论文_{i+1}"
                    
                    print(f"  📄 [{i+1}/{total}] {title}")
                    
                    # 尝试找 PDF 下载链接
                    try:
                        pdf_link = driver.find_element(
                            By.XPATH,
                            f"(//div[contains(@class, 'sc_default_result')]//div[contains(@class, 'result')])[{i+1}]"
                            f"//a[contains(text(), '免费下载') or contains(@class, 'dl_item')]"
                        )
                        pdf_url = pdf_link.get_attribute("href")
                        
                        if pdf_url:
                            # 用 requests 直接下载 PDF（比 Selenium 更快）
                            safe_title = "".join(c for c in title if c.isalnum() or c in " _-").strip()[:80]
                            if not safe_title:
                                safe_title = f"baidu_scholar_{downloaded+1}"
                            pdf_path = os.path.join(self.download_dir, f"{safe_title}.pdf")
                            
                            print(f"    📥 正在下载 PDF...")
                            try:
                                resp = requests.get(pdf_url, timeout=30, headers={
                                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                                })
                                if resp.status_code == 200 and len(resp.content) > 1000:
                                    with open(pdf_path, "wb") as f:
                                        f.write(resp.content)
                                    print(f"    ✅ PDF 已保存: {os.path.basename(pdf_path)}")
                                    downloaded += 1
                                else:
                                    print(f"    ⚠️ 下载失败 (HTTP {resp.status_code})")
                            except Exception as dl_err:
                                print(f"    ⚠️ 下载异常: {dl_err}")
                        else:
                            print(f"    ⚠️ 无 PDF 链接")
                    except Exception:
                        print(f"    ⚠️ 无免费 PDF 下载")
                    
                    self.random_delay(0.5, 1.5)
                    
                except Exception as e:
                    print(f"    ❌ 错误: {e}")
                    continue
            
            # 翻页
            if page_num < max_pages:
                try:
                    # 百度学术翻页 URL 格式：pn=0, pn=10, pn=20, ...
                    next_pn = page_num * 10
                    next_url = f"https://xueshu.baidu.com/s?wd={keyword}&pn={next_pn}"
                    driver.get(next_url)
                    self.random_delay(3.0, 5.0)
                except Exception:
                    print("🛑 翻页失败")
                    break
        
        print(f"\n[{self.source_name}] ✅ 共下载 {downloaded} 篇论文")
        return downloaded