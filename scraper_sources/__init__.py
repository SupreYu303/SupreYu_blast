# =====================================================================
# 📄 文件说明：多源论文爬虫模块包 (scraper_sources/)
# =====================================================================
# 【功能概述】
#   本包提供多个学术论文源的自动抓取能力，每个源独立维护。
#
# 【支持的论文源】
#   1. CNKI 知网 (cnki.py) — 中文学术期刊/学位论文
#   2. 万方数据 (wanfang.py) — 中文学术期刊/会议论文
#   3. 百度学术 (baidu_scholar.py) — 聚合多源，免费 PDF 链接
#   4. Semantic Scholar (semantic_scholar.py) — 国际论文 API
#
# 【使用方式】
#   from scraper_sources.cnki import download_from_cnki
#   from scraper_sources.wanfang import download_from_wanfang
#   from scraper_sources.baidu_scholar import download_from_baidu_scholar
#   from scraper_sources.semantic_scholar import download_from_semantic_scholar
#
#   # 或通过调度器统一管理：
#   from scraper_manager import ScraperManager
#   manager = ScraperManager()
#   manager.run("cnki", keyword="立井爆破", max_pages=5)
# =====================================================================