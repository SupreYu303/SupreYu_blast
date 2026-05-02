import os
import time
from scraper_module import auto_download_cnki
from extractor_module import run_extraction_and_imputation
from config import TEXT_API_KEY as DEEPSEEK_API_KEY

def main():
    if not DEEPSEEK_API_KEY:
        raise ValueError("❌ 启动失败：未在环境变量或 .env 中找到 DEEPSEEK_API_KEY")
    print("=====================================================")
    print("🚀 启动 grandMining 端到端自动化流水线")
    print("=====================================================\n")

    # -------------------------------------------------------
    # 阶段 1：自动获取工程文献
    # -------------------------------------------------------
    target_keyword = "立井掏槽"
    pages_to_scrape = 5  # 测试阶段建议设为 1
    
    print(f"👉 [阶段 1] 开始执行知网检索与自动下载任务 | 关键词: '{target_keyword}'")
    auto_download_cnki(keyword=target_keyword, max_pages=pages_to_scrape)
    
    print("\n⏳ 阶段 1 完成，稍作休眠等待文件系统刷新...")
    time.sleep(3)

    # -------------------------------------------------------
    # 阶段 2 & 3：多模态特征提取 + 数据黑洞修复
    # -------------------------------------------------------
    # 检查是否有下载到 PDF
    if not os.path.exists("pdfs") or len(os.listdir("pdfs")) == 0:
        print("❌ 警告：pdfs 目录下没有发现文献，流水线终止。")
        return

    print(f"\n👉 [阶段 2 & 3] 启动三核混合特征提取与数据重构")
    final_output_path = run_extraction_and_imputation(deepseek_key=DEEPSEEK_API_KEY)
    
    print("\n=====================================================")
    print(f"🎉 全流程执行完毕！")
    print(f"📂 终极高价值特征库已保存至: {final_output_path}")
    print("=====================================================")

if __name__ == "__main__":
    main()