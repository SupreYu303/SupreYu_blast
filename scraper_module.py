import os
import time
import random
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

def setup_driver(download_dir):
    """配置 Edge 浏览器，开启深度拟人化伪装，并设置默认下载路径"""
    if not os.path.exists(download_dir):
        os.makedirs(download_dir)
        
    options = webdriver.EdgeOptions()
    
    # 顶级防爬伪装 (模拟真实人类)
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0')

    # 下载偏好设置 (强制下载 PDF)
    prefs = {
        "download.default_directory": os.path.abspath(download_dir),
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "plugins.always_open_pdf_externally": True 
    }
    options.add_experimental_option("prefs", prefs)
    
    driver = webdriver.Edge(options=options)
    
    # 终极底层伪装：注入 JS 抹除 navigator.webdriver 属性
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    })
    
    return driver

def auto_download_cnki(keyword="立井爆破", max_pages=1):
    """
    自动化抓取知网文献（专攻 PDF 格式，含人工破盾与自动翻页）
    """
    download_dir = "pdfs"
    driver = setup_driver(download_dir)
    wait = WebDriverWait(driver, 15) 
    
    try:
        # 1. 访问知网主页
        driver.get("https://kns.cnki.net/kns8s/")
        
        print("\n=========================================================")
        print("🛡️ 【人工破盾阶段】浏览器已启动！")
        print("👉 请在弹出的浏览器中手动执行以下操作：")
        print("   1. 如果有安全验证或滑块，请手动拖动完成 (你有校园网权限，无需登录)")
        print("   2. 确保页面目前停留在知网主页")
        print("=========================================================\n")
        
        # 🔴 核心机制：挂起程序，等待人类破盾
        input("✅ 手动验证完成后，请在此处按【回车键】将控制权交还给机器...")
        print("\n🚀 机器已接管控制权，开始全速检索与下载...")
        
        # 2. 机器接管：输入检索词并搜索
        # 确保搜索框不仅存在，还要绝对可见
        search_box = wait.until(EC.element_to_be_clickable(
            (By.XPATH, "//input[@id='txt_SearchText' or contains(@class, 'search-input')][not(@type='hidden')]")
        ))
        
        # 暴力 JS 清空，防崩溃
        driver.execute_script("arguments[0].value = '';", search_box)
        time.sleep(0.5) 
        
        search_box.send_keys(keyword)
        time.sleep(random.uniform(0.5, 1.2)) 
        
        search_btn = driver.find_element(By.XPATH, "//input[@value='检索' or @class='search-btn']")
        search_btn.click()
        time.sleep(random.uniform(3.0, 5.0)) 
        
        print(f"🔍 正在解析 [{keyword}] 检索结果...")
        
        # 3. 机器搬砖：多页循环抓取文献
        for current_page in range(1, max_pages + 1):
            print(f"\n=====================================")
            print(f"📖 正在扫荡第 {current_page}/{max_pages} 页...")
            print(f"=====================================\n")

            try:
                # 动态获取当前页共有多少篇文献
                article_links = wait.until(EC.presence_of_all_elements_located(
                    (By.XPATH, "//table[@class='result-table-list']//tr/td[@class='name']/a")
                ))
                total_links = len(article_links)
            except TimeoutException:
                print("⚠️ 警告: 本页没有找到任何文献，可能加载失败或已到底。")
                break

            # 遍历当前页的所有文献（完全解开封印）
            for i in range(total_links): 
                try:
                    # 每次循环重新获取一次当前元素，防止页面微动导致 StaleElement
                    current_links = wait.until(EC.presence_of_all_elements_located(
                        (By.XPATH, "//table[@class='result-table-list']//tr/td[@class='name']/a")
                    ))
                    if i >= len(current_links): break
                    
                    link = current_links[i]
                    title = link.text
                    print(f"📄 准备下载: {title}")
                    
                    original_window = driver.current_window_handle
                    old_windows = driver.window_handles 
                    
                    # 强行穿透前端遮挡点击
                    driver.execute_script("arguments[0].click();", link)
                    
                    # 差集法等待新窗口，绝不误杀
                    wait.until(lambda d: len(d.window_handles) > len(old_windows))
                    new_windows = [w for w in driver.window_handles if w not in old_windows]
                    
                    if new_windows:
                        driver.switch_to.window(new_windows[0])
                        try:
                            pdf_btn = wait.until(EC.element_to_be_clickable(
                                (By.XPATH, "//a[contains(text(), 'PDF下载') or contains(@id, 'pdfDown')]")
                            ))
                            time.sleep(random.uniform(0.5, 1.5))
                            driver.execute_script("arguments[0].click();", pdf_btn)
                            print(f"✅ 成功触发 [{title}] 的 PDF 下载通道！")
                            time.sleep(random.uniform(4.0, 6.0)) 
                        except TimeoutException:
                            print(f"⚠️ 警告: 未找到该文献的 PDF 下载按钮，可能仅支持 CAJ，跳过...")
                            
                        driver.close()
                    
                    # 安全切回主页面
                    driver.switch_to.window(original_window)
                    time.sleep(random.uniform(1.0, 2.0))
                    
                except Exception as e:
                    print(f"❌ 下载第 {i+1} 篇文献时发生错误: {e}")
                    # 终极异常清理：关掉除了主窗口外的所有乱弹窗口
                    for w in driver.window_handles:
                        if w != original_window:
                            driver.switch_to.window(w)
                            driver.close()
                    driver.switch_to.window(original_window)
                    continue

            # ==========================================
            # 翻页触发模块
            # ==========================================
            if current_page < max_pages:
                try:
                    next_page_btn = wait.until(EC.element_to_be_clickable(
                        (By.XPATH, "//a[@id='PageNext' or contains(text(), '下一页')]")
                    ))
                    print(f"➡️ 第 {current_page} 页扫荡完毕，正在启动引擎前往下一页...")
                    driver.execute_script("arguments[0].click();", next_page_btn)
                    
                    # 留足时间给服务器渲染新表格数据
                    time.sleep(random.uniform(4.0, 6.0))
                except TimeoutException:
                    print("🛑 没有找到【下一页】按钮，可能已经抓取完所有结果！")
                    break

    finally:
        print("\n🛑 爬虫模块运行完毕，关闭浏览器。")
        driver.quit()

if __name__ == "__main__":
    auto_download_cnki(keyword="立井爆破", max_pages=7)