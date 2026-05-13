# =====================================================================
# 📄 文件说明：grandMining PDF 批量模式流水线 (main_pipelinepdf.py)
# =====================================================================
# 【功能概述】
#   本文件是 grandMining 系统的"本地 PDF 批量处理流水线"，
#   与 main_pipeline.py 的区别在于：跳过了知网爬虫阶段，直接处理本地已有的 PDF 文件。
#   串联两个核心阶段：
#   阶段 2：三核混合特征提取（PyMuPDF + PaddleOCR + Qwen-VL）
#   阶段 3：五重递进式数据修复（RBR + 物理推导 + LLM + XGBoost + 终极闭环）
#
# 【运行方式】
#   python main_pipelinepdf.py
#
# 【适用场景】
#   已有本地 PDF 文献，无需爬虫，直接进行批量提取与修复
#
# 【前置条件】
#   1. 已将 PDF 文件放入 pdfs/ 目录
#   2. 已配置 config.yaml 中的 API 密钥
#
# 【输出产物】
#   outputs/blasting_CBR_dataset_YYYYMMDD_HHMMSS.xlsx         — 原始特征库
#   outputs/blasting_CBR_dataset_YYYYMMDD_HHMMSS_Imputed_Bounded.xlsx — 修复后特征库
#
# 【与 main_pipeline.py 的区别】
#   main_pipeline.py = 爬虫下载 + 特征提取 + 数据修复（完整流程）
#   main_pipelinepdf.py = 特征提取 + 数据修复（跳过爬虫，本地 PDF 直接处理）
#
# 【依赖模块】
#   - extractor_module：特征提取模块，负责从 PDF 中提取爆破参数并调用修复引擎
#   - config：统一配置加载器，负责读取 API 密钥等配置
# =====================================================================

import os
import time

# 🔴 注意：scraper_module 已被注释掉，因为本模式不需要爬虫功能
# from scraper_module import auto_download_cnki

# 导入特征提取与数据修复一体化流水线函数
from extractor_module import run_extraction_and_imputation

# 从统一配置中导入 DeepSeek 文本大模型的 API 密钥（作为修复引擎的入参）
from config import TEXT_API_KEY as DEEPSEEK_API_KEY


def main():
    """
    PDF 批量处理流水线主函数。
    
    【执行流程】
      1. 校验 API 密钥是否已配置
      2. 跳过爬虫阶段，提示用户已采用本地文献模式
      3. 检查 pdfs/ 目录下是否有 PDF 文件
      4. 启动特征提取与数据修复流水线
      5. 输出最终的高价值特征库 Excel 文件路径
      
    【支持环境变量】
      GRANDMINING_MODE：修复模式（"train" 或 "predict"，默认 "predict"）
    """
    
    # 从环境变量读取修复模式（支持 GUI 传入），默认为 predict
    mode = os.environ.get("GRANDMINING_MODE", "predict")
    
    # -----------------------------------------------------------------
    # 前置校验：检查 API 密钥是否已正确配置
    # -----------------------------------------------------------------
    if not DEEPSEEK_API_KEY:
        raise ValueError("❌ 启动失败：未在环境变量或 .env 中找到 DEEPSEEK_API_KEY")

    print("=====================================================")
    print("🚀 启动 grandMining 端到端自动化流水线 (本地批量文献模式)")
    print(f"📋 修复模式: {mode}")
    print("=====================================================\n")

    # -------------------------------------------------------
    # 阶段 1：自动获取工程文献（已关闭，采用本地 PDF 模式）
    # -------------------------------------------------------
    print("👉 [阶段 1] 检测到采用本地文献提取模式，已跳过知网爬虫下载阶段！")

    # -------------------------------------------------------
    # 阶段 2 & 3：多模态特征提取 + 数据黑洞修复
    # -------------------------------------------------------
    if not os.path.exists("pdfs") or len(os.listdir("pdfs")) == 0:
        print("❌ 警告：pdfs 目录下没有发现文献，流水线终止。请确认你的PDF都放在了pdfs文件夹中！")
        return

    print(f"\n👉 [阶段 2 & 3] 启动三核混合特征提取与数据重构 (模式: {mode})")
    
    final_output_path = run_extraction_and_imputation(deepseek_key=DEEPSEEK_API_KEY, mode=mode)
    
    # -------------------------------------------------------
    # 流水线执行完毕，输出最终结果
    # -------------------------------------------------------
    print("\n=====================================================")
    print(f"🎉 全流程执行完毕！")
    print(f"📂 终极高价值特征库已保存至: {final_output_path}")
    print("=====================================================")


# ---------------------------------------------------------------------
# 程序入口
# ---------------------------------------------------------------------
# 当直接运行本文件时（python main_pipelinepdf.py），调用 main() 函数启动流水线
# 如果被其他模块 import，则不会自动执行，避免副作用
if __name__ == "__main__":
    main()