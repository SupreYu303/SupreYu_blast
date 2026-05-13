# =====================================================================
# 📄 文件说明：爬虫基类 (scraper_sources/base.py)
# =====================================================================
# 【功能概述】
#   定义所有论文爬虫的公共基类，提供统一的：
#   - Edge 浏览器驱动配置（深度防爬伪装）
#   - 下载目录管理
#   - 临时文件清理
#   - 信号文件机制（GUI 模式下的人工破盾）
#   - 统一的运行入口
# =====================================================================

import os
import time
import random
import sys
import json
from abc import ABC, abstractmethod

# Selenium 核心组件
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

# 项目根目录
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class BaseScraper(ABC):
    """
    论文爬虫基类。
    
    【子类需实现】
      source_name (str)：数据源名称（如 "CNKI"、"万方"）
      base_url (str)：数据源首页 URL
      search_and_download(keyword, max_pages)：核心搜索下载逻辑
    """
    
    source_name = "base"
    base_url = ""
    
    def __init__(self, download_dir=None):
        """
        初始化爬虫。
        
        【参数】
          download_dir (str)：PDF 下载目录，默认为项目根目录下的 pdfs/
        """
        self.download_dir = download_dir or os.path.join(PROJECT_DIR, "pdfs")
        if not os.path.exists(self.download_dir):
            os.makedirs(self.download_dir)
        self.driver = None
        self.wait = None
    
    def setup_driver(self):
        """
        配置并初始化 Edge 浏览器驱动，开启深度拟人化伪装。
        
        【返回值】
          selenium.webdriver.Edge: 配置完成的浏览器驱动实例
        """
        options = webdriver.EdgeOptions()
        
        # 顶级防爬伪装
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument(
            'user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0'
        )
        
        # 下载偏好
        prefs = {
            "download.default_directory": os.path.abspath(self.download_dir),
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "plugins.always_open_pdf_externally": True,
        }
        options.add_experimental_option("prefs", prefs)
        
        # 启动浏览器
        self.driver = webdriver.Edge(options=options)
        self.wait = WebDriverWait(self.driver, 15)
        
        # 终极底层伪装
        self.driver.execute_cdp_cmd(
            "Page.addScriptToEvaluateOnNewDocument",
            {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"}
        )
        
        return self.driver
    
    def wait_for_human_verification(self, timeout=300):
        """
        人工破盾机制：等待用户手动完成安全验证。
        
        【说明】
          - 终端模式：使用 input() 阻塞
          - GUI 模式：通过信号文件 _scraper_ready.signal 等待确认
          
        【参数】
          timeout (int)：GUI 模式下的超时秒数，默认 300 秒
        """
        print(f"\n{'='*55}")
        print(f"🛡️  【{self.source_name} - 人工破盾阶段】浏览器已启动！")
        print(f"👉  请在弹出的浏览器中手动完成安全验证")
        print(f"{'='*55}\n")
        
        auto_confirm = os.environ.get("GRANDMINING_AUTO_CONFIRM", "").lower() in ("1", "true", "yes")
        
        if auto_confirm:
            signal_file = os.path.join(PROJECT_DIR, "_scraper_ready.signal")
            if os.path.exists(signal_file):
                os.remove(signal_file)
            print(f"📌 [GUI模式] 等待信号文件确认... (超时: {timeout}秒)")
            for _ in range(timeout):
                time.sleep(1)
                if os.path.exists(signal_file):
                    try:
                        os.remove(signal_file)
                    except Exception:
                        pass
                    break
            else:
                print("⏰ 等待超时，自动继续...")
        else:
            input("✅ 手动验证完成后，请按【回车键】将控制权交还给机器...")
        
        print(f"\n🚀 机器已接管控制权，开始 {self.source_name} 检索与下载...\n")
    
    def random_delay(self, min_sec=0.5, max_sec=2.0):
        """随机延时，模拟人类操作节奏"""
        time.sleep(random.uniform(min_sec, max_sec))
    
    def safe_close_extra_windows(self, original_window):
        """安全关闭除主窗口外的所有多余窗口"""
        try:
            for w in self.driver.window_handles:
                if w != original_window:
                    self.driver.switch_to.window(w)
                    self.driver.close()
            self.driver.switch_to.window(original_window)
        except Exception:
            pass
    
    def cleanup(self):
        """清理工作：关闭浏览器"""
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
            self.driver = None
    
    @abstractmethod
    def search_and_download(self, keyword, max_pages=1):
        """
        核心搜索下载逻辑（子类必须实现）。
        
        【参数】
          keyword (str)：检索关键词
          max_pages (int)：爬取页数
          
        【返回值】
          int：成功下载的论文数量
        """
        pass
    
    def run(self, keyword, max_pages=1):
        """
        运行爬虫（统一入口）。
        
        【参数】
          keyword (str)：检索关键词
          max_pages (int)：爬取页数
          
        【返回值】
          int：成功下载的论文数量
        """
        try:
            self.setup_driver()
            count = self.search_and_download(keyword, max_pages)
            return count
        except Exception as e:
            print(f"[{self.source_name}] ❌ 爬虫异常: {e}")
            return 0
        finally:
            self.cleanup()
            print(f"\n🛑 {self.source_name} 爬虫模块运行完毕，浏览器已关闭。")