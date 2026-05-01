from DrissionPage import ChromiumPage, ChromiumOptions  # 🔴 注意这里多导入了一个 ChromiumOptions
import time
import os
import random

def auto_download_cnki(keyword, max_pages=1):
    """
    接管真实的 Edge 浏览器，自动搜索并下载知网 PDF
    """
    print("正在尝试接管 Edge 浏览器...")
    
    # 🔴 1. 创建浏览器配置对象
    co = ChromiumOptions()
    
    # 🔴 2. 指定 Edge 浏览器的具体路径 (绝大多数 Windows 电脑都在这个路径下)
    # 记得路径字符串前面加个 r，防止斜杠转义报错
    edge_path = r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'
    co.set_browser_path(edge_path)
    
    # 🔴 3. 用配置好的参数启动页面
    page = ChromiumPage(co)
    
    download_dir = os.path.abspath("pdfs")
    if not os.path.exists(download_dir):
        os.makedirs(download_dir)
        
    # 设置浏览器默认下载路径到我们的 pdfs 文件夹
    page.set.download_path(download_dir)

    print(f"🚀 正在前往知网搜索: {keyword}")
    page.get('https://www.cnki.net/')
    
    # ... 后面的搜索、点击下载、翻页逻辑【完全不用变】，直接粘贴之前的代码即可 ...
    
    time.sleep(2)
    # 输入关键词并搜索
    page.ele('@id=txt_SearchText').input(keyword)
    page.ele('@class=search-btn').click()
    

    
    time.sleep(3) # 等待搜索结果加载

    for current_page in range(max_pages):
        print(f"\n📄 正在解析第 {current_page + 1} 页搜索结果...")
        
        # 2. 获取当前页所有的论文列表
        # 知网的列表通常在 class 为 'result-table-list' 的表格里
        paper_links = page.eles('xpath://table[@class="result-table-list"]//tr/td[@class="name"]/a')
        
        # 收集所有论文的详情页 URL
        detail_urls = [link.attr('href') for link in paper_links if link.attr('href')]
        
        print(f"🔍 本页发现 {len(detail_urls)} 篇论文，开始逐个下载...")
        
        # 3. 逐个进入详情页下载
        for url in detail_urls:
            # 打开新标签页进入论文详情
            tab = page.new_tab(url)
            time.sleep(random.uniform(2, 4)) # 🔴 极其重要的随机停顿，防止被封 IP
            
            try:
                title = tab.ele('.wx-tit').text
                print(f"  > 尝试下载: {title}")
                
                # 🔴 寻找【PDF下载】按钮，避开 CAJ
                # 知网详情页通常有两个按钮：caj下载 和 pdf下载
                pdf_btn = tab.ele('text:PDF下载')
                
                if pdf_btn:
                    pdf_btn.click()
                    print(f"    ✅ 已触发 PDF 下载任务！")
                    # 给一点时间让浏览器把文件下完
                    time.sleep(random.uniform(5, 8)) 
                else:
                    print(f"    ⚠️ 未找到 PDF 下载按钮，可能只有 CAJ 格式或需要额外权限。")
            
            except Exception as e:
                print(f"    ❌ 下载本篇出错: {e}")
            finally:
                # 关闭当前论文标签页，保持浏览器干净
                tab.close()
                time.sleep(random.uniform(1, 2))
                
        # 4. 翻页逻辑
        if current_page < max_pages - 1:
            try:
                next_btn = page.ele('text:下一页')
                if next_btn:
                    next_btn.click()
                    time.sleep(random.uniform(3, 5))
                else:
                    print("到了最后一页。")
                    break
            except:
                break
                
    print(f"\n🎉 批量下载任务结束！PDF 已存入 {download_dir}")

if __name__ == "__main__":
    # 你可以输入你想要的关键词，比如 "爆破参数"、"竖井爆破"
    auto_download_cnki(keyword="立井", max_pages=1)