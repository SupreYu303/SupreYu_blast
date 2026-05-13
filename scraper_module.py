# =====================================================================
# 📄 文件说明：grandMining 知网爬虫模块 (scraper_module.py)
# =====================================================================
# 【功能概述】
#   本文件是 grandMining 系统的"知网自动化爬虫模块"，
#   基于 Selenium 浏览器自动化框架，实现从中国知网（CNKI）自动检索并下载 PDF 文献。
#
# 【核心功能】
#   1. 自动启动 Edge 浏览器，访问知网搜索页面
#   2. "人工破盾"机制：程序暂停等待用户手动完成安全验证（滑块/验证码）
#   3. 机器接管：自动输入检索关键词、点击搜索
#   4. 遍历搜索结果：逐篇点击文献标题、查找 PDF 下载按钮、触发下载
#   5. 自动翻页：支持多页爬取
#   6. 深度防爬伪装：隐藏 Selenium 自动化标识，模拟真实人类行为
#
# 【运行方式】
#   python scraper_module.py                          # 使用默认参数
#   # 或在其他模块中调用：
#   from scraper_module import auto_download_cnki
#   auto_download_cnki(keyword="立井爆破", max_pages=5)
#
# 【适用场景】
#   需要从知网批量下载采矿爆破领域的 PDF 文献
#
# 【前置条件】
#   1. 已安装 Microsoft Edge 浏览器
#   2. 已安装 Selenium 及 Edge WebDriver（msedgedriver）
#   3. 网络可访问知网（cnki.net），建议使用校园网或有知网下载权限的网络
#
# 【输出产物】
#   pdfs/ 目录下自动保存下载的 PDF 文件
#
# 【防爬策略说明】
#   - Edge WebDriver 深度伪装：隐藏自动化标识，模拟真实浏览器指纹
#   - JS 注入抹除 navigator.webdriver 属性
#   - 随机延时（0.5s - 6s）：模拟人类操作节奏
#   - 人工破盾机制：安全验证/滑块由人类完成，机器只负责后续自动操作
#
# 【依赖模块】
#   - selenium：浏览器自动化框架
#   - os、time、random：文件系统操作、延时控制、随机数生成
# =====================================================================

import os
import time
import random
import sys

# Selenium 核心组件
from selenium import webdriver                                    # 浏览器驱动
from selenium.webdriver.common.by import By                       # 元素定位方式
from selenium.webdriver.support.ui import WebDriverWait           # 显式等待
from selenium.webdriver.support import expected_conditions as EC  # 等待条件
from selenium.common.exceptions import TimeoutException, NoSuchElementException  # 异常类型


def setup_driver(download_dir):
    """
    配置并初始化 Edge 浏览器驱动，开启深度拟人化伪装，并设置默认下载路径。
    
    【参数说明】
      download_dir (str): PDF 文件的下载保存目录路径
      
    【返回值】
      selenium.webdriver.Edge: 配置完成的 Edge 浏览器驱动实例
      
    【配置细节】
      1. 禁用自动化开关标志（excludeSwitches），隐藏 Selenium 自动化特征
      2. 关闭自动化扩展（useAutomationExtension）
      3. 禁用 Blink 自动化检测特征（AutomationControlled）
      4. 设置真实的 User-Agent（模拟 Edge 浏览器的正常请求头）
      5. 配置下载偏好：自动下载 PDF、不弹出下载确认框、外部打开 PDF
      6. 注入 JS 脚本，抹除 navigator.webdriver 属性（终极底层伪装）
    """
    
    # 确保下载目录存在
    if not os.path.exists(download_dir):
        os.makedirs(download_dir)
        
    # 创建 Edge 浏览器选项对象
    options = webdriver.EdgeOptions()
    
    # ---------------------------------------------------------------
    # 顶级防爬伪装配置（模拟真实人类浏览器环境）
    # ---------------------------------------------------------------
    # 禁用 Chrome/Edge 的"自动化控制"开关，防止被网站检测到 Selenium
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    # 关闭自动化扩展插件
    options.add_experimental_option('useAutomationExtension', False)
    # 禁用 Blink 引擎的自动化检测特征
    options.add_argument("--disable-blink-features=AutomationControlled")
    # 设置真实的 User-Agent，模拟 Edge 浏览器的正常 HTTP 请求头
    options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0')

    # ---------------------------------------------------------------
    # 下载偏好设置（强制自动下载 PDF，不弹出确认框）
    # ---------------------------------------------------------------
    prefs = {
        "download.default_directory": os.path.abspath(download_dir),  # 设置默认下载目录
        "download.prompt_for_download": False,                        # 禁用下载确认弹窗
        "download.directory_upgrade": True,                           # 允许升级下载目录
        "plugins.always_open_pdf_externally": True                    # 强制在外部打开 PDF（而非浏览器内置阅读器）
    }
    options.add_experimental_option("prefs", prefs)
    
    # 启动 Edge 浏览器
    driver = webdriver.Edge(options=options)
    
    # ---------------------------------------------------------------
    # 终极底层伪装：注入 JS 抹除 navigator.webdriver 属性
    # ---------------------------------------------------------------
    # 【说明】即使前面的配置已经隐藏了大部分自动化特征，
    # 某些高级反爬系统仍会检测 navigator.webdriver 属性
    # 通过 CDP（Chrome DevTools Protocol）注入脚本，在每个新页面加载前
    # 自动将 navigator.webdriver 的值改为 undefined
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    })
    
    return driver


def auto_download_cnki(keyword="立井爆破", max_pages=1):
    """
    自动化抓取知网文献（专攻 PDF 格式，含人工破盾与自动翻页）。
    
    【参数说明】
      keyword (str): 知网检索关键词，默认为"立井爆破"
      max_pages (int): 爬取的搜索结果页数，默认为 1 页
      
    【执行流程】
      1. 启动 Edge 浏览器并访问知网首页
      2. 暂停等待用户手动完成安全验证（人工破盾）
      3. 用户按回车后，机器接管控制权
      4. 输入检索关键词并点击搜索
      5. 遍历当前页所有文献：
         - 点击文献标题 → 新窗口打开详情页
         - 查找"PDF下载"按钮 → 触发下载
         - 关闭子窗口 → 切回主窗口
         - 随机延时（模拟人类操作节奏）
      6. 自动翻页 → 重复步骤 5
      7. 所有页面处理完毕后关闭浏览器
      
    【异常处理】
      - 如果某篇文献下载失败，会打印错误信息并继续处理下一篇
      - 如果某个子窗口未正常关闭，会清理所有多余的窗口
      - 如果没有找到"PDF下载"按钮（仅支持 CAJ），会跳过该文献
    """
    
    # 设置 PDF 下载目录为项目根目录下的 pdfs/
    download_dir = "pdfs"
    
    # 初始化浏览器驱动
    driver = setup_driver(download_dir)
    
    # 创建 WebDriverWait 显式等待对象，超时时间为 15 秒
    wait = WebDriverWait(driver, 15) 
    
    try:
        # -------------------------------------------------------
        # 1. 访问知网主页
        # -------------------------------------------------------
        driver.get("https://kns.cnki.net/kns8s/")
        
        # -------------------------------------------------------
        # 2. 人工破盾阶段：暂停程序，等待用户手动完成安全验证
        # -------------------------------------------------------
        # 【说明】知网等学术网站通常有反爬机制（滑块验证、验证码等）
        # 这些无法由机器自动完成，因此设计了"人工破盾"机制：
        # 程序启动后会暂停，等待用户在弹出的浏览器中手动完成安全验证，
        # 然后按回车键将控制权交还给机器
        print("\n=========================================================")
        print("🛡️ 【人工破盾阶段】浏览器已启动！")
        print("👉 请在弹出的浏览器中手动执行以下操作：")
        print("   1. 如果有安全验证或滑块，请手动拖动完成 (你有校园网权限，无需登录)")
        print("   2. 确保页面目前停留在知网主页")
        print("=========================================================\n")
        
        # 🔴 核心机制：挂起程序，等待人类破盾
        # 检查是否有环境变量自动确认（GUI 模式下使用）
        auto_confirm = os.environ.get("GRANDMINING_AUTO_CONFIRM", "").lower() in ("1", "true", "yes")
        
        if auto_confirm:
            # GUI 模式：通过文件信号机制等待用户确认
            signal_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_scraper_ready.signal")
            # 清理旧信号
            if os.path.exists(signal_file):
                os.remove(signal_file)
            print("📌 [GUI模式] 等待信号文件确认...")
            print(f"   请完成验证后，系统将自动继续（超时: 300秒）")
            # 等待信号文件出现，每秒检查一次
            for _wait_i in range(300):
                time.sleep(1)
                if os.path.exists(signal_file):
                    try:
                        os.remove(signal_file)
                    except Exception:
                        pass
                    break
            else:
                print("⏰ 等待超时（300秒），自动继续...")
        else:
            # 终端模式：使用 input() 阻塞等待
            input("✅ 手动验证完成后，请在此处按【回车键】将控制权交还给机器...")
        
        print("\n🚀 机器已接管控制权，开始全速检索与下载...")
        
        # -------------------------------------------------------
        # 3. 机器接管：输入检索关键词并搜索
        # -------------------------------------------------------
        # 定位知网搜索输入框（通过 XPath 匹配 id 或 class）
        # 确保搜索框不仅存在，还要绝对可见可交互
        search_box = wait.until(EC.element_to_be_clickable(
            (By.XPATH, "//input[@id='txt_SearchText' or contains(@class, 'search-input')][not(@type='hidden')]")
        ))
        
        # 使用 JavaScript 暴力清空搜索框内容（比 send_keys 更可靠，防崩溃）
        driver.execute_script("arguments[0].value = '';", search_box)
        time.sleep(0.5)  # 短暂等待清空操作完成
        
        # 输入检索关键词
        search_box.send_keys(keyword)
        time.sleep(random.uniform(0.5, 1.2))  # 随机延时，模拟人类打字节奏
        
        # 点击搜索按钮
        search_btn = driver.find_element(By.XPATH, "//input[@value='检索' or @class='search-btn']")
        search_btn.click()
        time.sleep(random.uniform(3.0, 5.0))  # 等待搜索结果加载
        
        print(f"🔍 正在解析 [{keyword}] 检索结果...")
        
        # -------------------------------------------------------
        # 4. 多页循环抓取文献
        # -------------------------------------------------------
        for current_page in range(1, max_pages + 1):
            print(f"\n=====================================")
            print(f"📖 正在扫荡第 {current_page}/{max_pages} 页...")
            print(f"=====================================\n")

            try:
                # 动态获取当前页共有多少篇文献（通过 XPath 匹配结果表格中的文献链接）
                article_links = wait.until(EC.presence_of_all_elements_located(
                    (By.XPATH, "//table[@class='result-table-list']//tr/td[@class='name']/a")
                ))
                total_links = len(article_links)
            except TimeoutException:
                # 如果当前页没有找到任何文献，可能已到底或加载失败
                print("⚠️ 警告: 本页没有找到任何文献，可能加载失败或已到底。")
                break

            # ---------------------------------------------------
            # 遍历当前页的所有文献，逐篇下载 PDF
            # ---------------------------------------------------
            for i in range(total_links): 
                try:
                    # 【重要】每次循环重新获取一次当前元素引用
                    # 因为页面可能因前一次操作而微动，导致旧的元素引用失效（StaleElement 异常）
                    current_links = wait.until(EC.presence_of_all_elements_located(
                        (By.XPATH, "//table[@class='result-table-list']//tr/td[@class='name']/a")
                    ))
                    if i >= len(current_links): 
                        break
                    
                    link = current_links[i]
                    title = link.text  # 获取文献标题
                    print(f"📄 准备下载: {title}")
                    
                    # 记录当前窗口句柄（用于后续切回主窗口）
                    original_window = driver.current_window_handle
                    old_windows = driver.window_handles  # 记录当前所有窗口
                    
                    # 强行穿透前端遮挡点击（使用 JS 直接触发点击事件，绕过可能的遮挡层）
                    driver.execute_script("arguments[0].click();", link)
                    
                    # 差集法等待新窗口出现（比较点击前后窗口列表的差异）
                    # 这种方法比直接等待新窗口更可靠，不会误杀已有窗口
                    wait.until(lambda d: len(d.window_handles) > len(old_windows))
                    new_windows = [w for w in driver.window_handles if w not in old_windows]
                    
                    if new_windows:
                        # 切换到新打开的文献详情页窗口
                        driver.switch_to.window(new_windows[0])
                        try:
                            # 在详情页中查找"PDF下载"按钮
                            pdf_btn = wait.until(EC.element_to_be_clickable(
                                (By.XPATH, "//a[contains(text(), 'PDF下载') or contains(@id, 'pdfDown')]")
                            ))
                            time.sleep(random.uniform(0.5, 1.5))  # 随机延时
                            # 点击 PDF 下载按钮
                            driver.execute_script("arguments[0].click();", pdf_btn)
                            print(f"✅ 成功触发 [{title}] 的 PDF 下载通道！")
                            time.sleep(random.uniform(4.0, 6.0))  # 等待下载启动完成
                        except TimeoutException:
                            # 如果没有找到 PDF 下载按钮，说明该文献可能仅支持 CAJ 格式
                            print(f"⚠️ 警告: 未找到该文献的 PDF 下载按钮，可能仅支持 CAJ，跳过...")
                            
                        # 关闭文献详情页子窗口
                        driver.close()
                    
                    # 安全切回主搜索结果页面
                    driver.switch_to.window(original_window)
                    time.sleep(random.uniform(1.0, 2.0))  # 随机延时，模拟人类操作节奏
                    
                except Exception as e:
                    # ---------------------------------------------------
                    # 异常处理：下载某篇文献时发生错误
                    # ---------------------------------------------------
                    print(f"❌ 下载第 {i+1} 篇文献时发生错误: {e}")
                    # 终极异常清理：关掉除了主窗口外的所有乱弹窗口
                    for w in driver.window_handles:
                        if w != original_window:
                            driver.switch_to.window(w)
                            driver.close()
                    # 确保切回主窗口
                    driver.switch_to.window(original_window)
                    continue

            # ==========================================
            # 翻页触发模块
            # ==========================================
            # 【说明】如果不是最后一页，点击"下一页"按钮继续爬取
            if current_page < max_pages:
                try:
                    # 定位"下一页"按钮（通过 id 或文本内容匹配）
                    next_page_btn = wait.until(EC.element_to_be_clickable(
                        (By.XPATH, "//a[@id='PageNext' or contains(text(), '下一页')]")
                    ))
                    print(f"➡️ 第 {current_page} 页扫荡完毕，正在启动引擎前往下一页...")
                    # 点击下一页
                    driver.execute_script("arguments[0].click();", next_page_btn)
                    
                    # 留足时间给服务器渲染新表格数据
                    time.sleep(random.uniform(4.0, 6.0))
                except TimeoutException:
                    # 如果没有找到"下一页"按钮，说明已经到达最后一页
                    print("🛑 没有找到【下一页】按钮，可能已经抓取完所有结果！")
                    break

    finally:
        # ---------------------------------------------------
        # 清理工作：无论成功与否，最后都关闭浏览器
        # ---------------------------------------------------
        print("\n🛑 爬虫模块运行完毕，关闭浏览器。")
        driver.quit()


# ---------------------------------------------------------------------
# 程序入口
# ---------------------------------------------------------------------
# 当直接运行本文件时，使用默认参数启动爬虫
# 默认关键词为"立井爆破"，爬取 7 页
if __name__ == "__main__":
    auto_download_cnki(keyword="立井爆破", max_pages=7)