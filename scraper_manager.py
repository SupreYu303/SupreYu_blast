# =====================================================================
# 📄 文件说明：多源论文爬虫调度器 (scraper_manager.py)
# =====================================================================
# 【功能概述】
#   统一管理所有论文源的爬虫调度，提供：
#   - 按名称选择论文源
#   - 多源串行/并行抓取
#   - 统一的下载统计和日志
#
# 【支持的论文源】
#   cnki         — CNKI 知网
#   wanfang      — 万方数据
#   baidu        — 百度学术
#   semantic     — Semantic Scholar (国际)
#   all          — 全部中文源串行执行
#
# 【运行方式】
#   # 命令行：
#   python scraper_manager.py --source cnki --keyword "立井爆破" --pages 5
#   python scraper_manager.py --source all --keyword "立井爆破" --pages 3
#
#   # 代码调用：
#   from scraper_manager import ScraperManager
#   manager = ScraperManager()
#   count = manager.run("cnki", keyword="立井爆破", max_pages=5)
# =====================================================================

import sys
import os
import argparse

# 项目根目录
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_DIR)

from scraper_sources.cnki import CnkiScraper
from scraper_sources.wanfang import WanfangScraper
from scraper_sources.baidu_scholar import BaiduScholarScraper
from scraper_sources.semantic_scholar import SemanticScholarScraper
from scraper_sources.google_scholar import GoogleScholarScraper


# 论文源注册表
SCRAPER_REGISTRY = {
    "cnki": CnkiScraper,
    "wanfang": WanfangScraper,
    "baidu": BaiduScholarScraper,
    "semantic": SemanticScholarScraper,
    "google": GoogleScholarScraper,
}


class ScraperManager:
    """多源论文爬虫调度器"""
    
    def __init__(self, download_dir=None):
        """
        初始化调度器。
        
        【参数】
          download_dir (str)：PDF 下载目录，默认为 pdfs/
        """
        self.download_dir = download_dir
    
    @staticmethod
    def list_sources():
        """列出所有可用的论文源"""
        return list(SCRAPER_REGISTRY.keys())
    
    def run(self, source_name, keyword, max_pages=1):
        """
        运行指定论文源的爬虫。
        
        【参数】
          source_name (str)：论文源名称（cnki/wanfang/baidu/semantic/all）
          keyword (str)：检索关键词
          max_pages (int)：爬取页数
          
        【返回值】
          int：成功下载的论文总数
        """
        if source_name == "all":
            return self.run_all(keyword, max_pages)
        
        scraper_cls = SCRAPER_REGISTRY.get(source_name)
        if not scraper_cls:
            print(f"❌ 未知的论文源: {source_name}")
            print(f"   可用源: {', '.join(SCRAPER_REGISTRY.keys())}")
            return 0
        
        scraper = scraper_cls(download_dir=self.download_dir)
        return scraper.run(keyword, max_pages)
    
    def run_all(self, keyword, max_pages=1):
        """
        串行运行所有中文论文源（cnki + wanfang + baidu）。
        
        【参数】
          keyword (str)：检索关键词
          max_pages (int)：每个源的爬取页数
          
        【返回值】
          int：成功下载的论文总数
        """
        total = 0
        # 先运行不需要浏览器的 API 源，再运行浏览器源
        for source_name in ["semantic", "baidu", "wanfang", "cnki"]:
            scraper_cls = SCRAPER_REGISTRY.get(source_name)
            if scraper_cls:
                print(f"\n{'='*55}")
                print(f"  🔄 正在启动 {source_name} 爬虫...")
                print(f"{'='*55}")
                try:
                    scraper = scraper_cls(download_dir=self.download_dir)
                    count = scraper.run(keyword, max_pages)
                    total += count
                except Exception as e:
                    print(f"  ❌ {source_name} 爬虫异常: {e}")
        
        print(f"\n{'='*55}")
        print(f"  🎉 全部源抓取完毕！共下载 {total} 篇论文")
        print(f"{'='*55}")
        return total


# ---------------------------------------------------------------------
# 命令行入口
# ---------------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="grandMining 多源论文爬虫调度器")
    parser.add_argument("--source", "-s", type=str, default="cnki",
                        choices=["cnki", "wanfang", "baidu", "semantic", "google", "all"],
                        help="论文源: cnki/wanfang/baidu/semantic/google/all (默认: cnki)")
    parser.add_argument("--keyword", "-k", type=str, default="立井爆破",
                        help="检索关键词 (默认: 立井爆破)")
    parser.add_argument("--pages", "-p", type=int, default=5,
                        help="爬取页数 (默认: 5)")
    
    args = parser.parse_args()
    
    print(f"🚀 启动多源论文爬虫")
    print(f"   源: {args.source} | 关键词: {args.keyword} | 页数: {args.pages}")
    print()
    
    manager = ScraperManager()
    count = manager.run(args.source, args.keyword, args.pages)
    
    print(f"\n📊 最终结果: 共下载 {count} 篇论文")