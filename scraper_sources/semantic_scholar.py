# =====================================================================
# 📄 文件说明：Semantic Scholar 爬虫 (scraper_sources/semantic_scholar.py)
# =====================================================================
# 【功能概述】
#   通过 Semantic Scholar API 搜索国际学术论文并下载免费 PDF。
#   Semantic Scholar 由 Allen AI 提供，免费开放 API。
#   适合补充英文采矿爆破文献（如 blasting, shaft sinking, rock fragmentation 等）。
#
# 【API Key 说明】
#   - 基础使用无需 API Key（当前代码默认方式）
#   - 如需更高请求频率，可免费申请：
#     1. 访问 https://www.semanticscholar.org/product/api#api-key
#     2. 注册账号并申请 API Key
#     3. 在 config.yaml 中配置 api.semantic_scholar.key
#     4. 或设置环境变量 SEMANTIC_SCHOLAR_API_KEY
#
# 【网络要求】
#   - api.semanticscholar.org 在国内通常可直接访问，无需科学上网
#   - 如遇网络问题，可配置代理：在 config.yaml 中设置 proxy.http
#
# 【运行方式】
#   from scraper_sources.semantic_scholar import SemanticScholarScraper
#   scraper = SemanticScholarScraper()
#   scraper.run(keyword="shaft blasting", max_pages=3)
#
# 【特点】
#   - 使用 REST API，无需浏览器驱动
#   - 免费开放，无需登录
#   - 自动下载 Open Access PDF
#   - 返回论文元数据（标题、作者、年份、摘要）
# =====================================================================

import os
import time
import requests
from scraper_sources.base import BaseScraper

# 尝试从 config 读取 API Key（可选）
try:
    import sys
    _config_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, _config_dir)
    from config import _config
    _ss_key = os.getenv("SEMANTIC_SCHOLAR_API_KEY",
                        _config.get("semantic_scholar", {}).get("key", ""))
except Exception:
    _ss_key = os.getenv("SEMANTIC_SCHOLAR_API_KEY", "")


class SemanticScholarScraper(BaseScraper):
    """Semantic Scholar API 论文爬虫（纯 API，无需浏览器）"""

    source_name = "Semantic Scholar"
    API_BASE = "https://api.semanticscholar.org/graph/v1"

    def setup_driver(self):
        """Semantic Scholar 使用 API，不需要浏览器"""
        self.driver = None
        self.wait = None
        return None

    def cleanup(self):
        """无需关闭浏览器"""
        pass

    def _get_headers(self):
        """构建请求头（如果有 API Key 则携带）"""
        headers = {
            "User-Agent": "grandMining/1.0 (academic research tool)"
        }
        if _ss_key:
            headers["x-api-key"] = _ss_key
        return headers

    def search_and_download(self, keyword, max_pages=1):
        """
        通过 Semantic Scholar API 搜索并下载论文 PDF。

        【执行流程】
          1. 调用 /paper/search API 搜索论文
          2. 筛选有 Open Access PDF 的论文
          3. 下载 PDF 到 pdfs/ 目录
          4. 翻页继续搜索
        """
        has_key = bool(_ss_key)
        # 检测是否为中文关键词，提示使用英文效果更好
        has_chinese = any('\u4e00' <= c <= '\u9fff' for c in keyword)
        print(f"🔍 [{self.source_name}] 通过 API 搜索: {keyword}")
        print(f"   API Key: {'已配置 ✅' if has_key else '未配置（使用免费额度，每100秒100次请求）'}")
        if has_chinese:
            print(f"   💡 提示: Semantic Scholar 以英文文献为主，中文关键词结果有限")
            print(f"   💡 建议: 试试 'shaft blasting'、'blasting excavation'、'rock fragmentation' 等英文关键词")

        downloaded = 0
        offset = 0
        limit = 20  # 每页 20 篇
        headers = self._get_headers()

        for page_num in range(1, max_pages + 1):
            print(f"\n📖 [{self.source_name}] 第 {page_num}/{max_pages} 页...")

            try:
                # 调用 Semantic Scholar 搜索 API
                url = f"{self.API_BASE}/paper/search"
                params = {
                    "query": keyword,
                    "offset": offset,
                    "limit": limit,
                    "fields": "title,authors,year,abstract,openAccessPdf,externalIds,venue",
                }

                resp = requests.get(url, params=params, headers=headers, timeout=30)

                # 处理限流：多次重试，逐步增加等待时间
                retry_count = 0
                max_retries = 3
                while resp.status_code == 429 and retry_count < max_retries:
                    wait_time = 30 if not has_key else 10
                    print(f"  ⏳ API 限流 (第{retry_count+1}次重试)，等待 {wait_time} 秒...")
                    time.sleep(wait_time)
                    resp = requests.get(url, params=params, headers=headers, timeout=30)
                    retry_count += 1

                if resp.status_code != 200:
                    print(f"  ❌ API 请求失败: HTTP {resp.status_code}")
                    if resp.status_code == 429:
                        print(f"  💡 提示: 无 API Key 免费额度为每100秒100次请求，请稍后再试")
                        print(f"  💡 提示: 或申请免费 API Key: https://www.semanticscholar.org/product/api#api-key")
                    elif resp.status_code == 403:
                        print("  💡 提示: 可能需要配置 API Key 或检查网络连接")
                    break

                data = resp.json()
                papers = data.get("data", [])
                total_available = data.get("total", 0)

                if not papers:
                    print("  ⚠️ 无更多结果")
                    break

                print(f"  📊 共 {total_available} 篇，本页 {len(papers)} 篇")

                for paper in papers:
                    title = paper.get("title", "Unknown")
                    year = paper.get("year", "N/A")
                    authors = ", ".join([a.get("name", "") for a in (paper.get("authors") or [])[:3]])
                    if authors and len(paper.get("authors", [])) > 3:
                        authors += " et al."

                    print(f"  📄 [{year}] {title}")
                    if authors:
                        print(f"       作者: {authors}")

                    # 检查是否有 Open Access PDF
                    open_pdf = paper.get("openAccessPdf")
                    if open_pdf and open_pdf.get("url"):
                        pdf_url = open_pdf["url"]

                        # 生成安全文件名
                        safe_title = "".join(c for c in title if c.isalnum() or c in " _-").strip()[:80]
                        if not safe_title:
                            safe_title = f"semantic_scholar_{downloaded+1}"
                        pdf_path = os.path.join(self.download_dir, f"{safe_title}.pdf")

                        print(f"    📥 正在下载 Open Access PDF...")
                        try:
                            dl_headers = {
                                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                            }
                            try:
                                pdf_resp = requests.get(pdf_url, timeout=60, stream=True, headers=dl_headers)
                            except requests.exceptions.SSLError:
                                # SSL 错误时禁用证书验证重试（常见于国内网络环境）
                                import urllib3
                                urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
                                print(f"    ⚠️ SSL 错误，尝试禁用证书验证重试...")
                                pdf_resp = requests.get(pdf_url, timeout=60, stream=True, headers=dl_headers, verify=False)
                            
                            if pdf_resp.status_code == 200:
                                with open(pdf_path, "wb") as f:
                                    for chunk in pdf_resp.iter_content(chunk_size=8192):
                                        f.write(chunk)
                                
                                # 验证下载的文件确实是 PDF
                                file_size = os.path.getsize(pdf_path)
                                if file_size > 1000:
                                    print(f"    ✅ PDF 已保存 ({file_size/1024:.0f} KB)")
                                    downloaded += 1
                                else:
                                    os.remove(pdf_path)
                                    print(f"    ⚠️ 文件太小，已删除")
                            else:
                                print(f"    ⚠️ 下载失败 (HTTP {pdf_resp.status_code})")
                        except Exception as dl_err:
                            print(f"    ⚠️ 下载异常: {dl_err}")
                    else:
                        print(f"    ℹ️ 无 Open Access PDF")

                    time.sleep(0.3)  # API 友好延时

                # 检查是否还有更多
                next_offset = data.get("next", 0)
                if next_offset <= offset or next_offset >= total_available:
                    print("  📊 已获取所有结果")
                    break

                offset = next_offset
                time.sleep(1.0)  # API 礼貌延时

            except requests.exceptions.ConnectionError:
                print("  ❌ 网络连接失败")
                print("  💡 提示: 如果 api.semanticscholar.org 无法访问，请检查网络或配置代理")
                break
            except Exception as e:
                print(f"  ❌ 异常: {e}")
                break

        print(f"\n[{self.source_name}] ✅ 共下载 {downloaded} 篇论文 (Open Access)")
        return downloaded

    def run(self, keyword, max_pages=1):
        """
        运行 Semantic Scholar 爬虫（重写基类方法，跳过浏览器初始化）。
        """
        try:
            count = self.search_and_download(keyword, max_pages)
            return count
        except Exception as e:
            print(f"[{self.source_name}] ❌ 异常: {e}")
            return 0
        finally:
            print(f"\n🛑 {self.source_name} 搜索完毕。")