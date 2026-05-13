# =====================================================================
# 📄 文件说明：grandMining 纯文本直通处理流水线 (run_txt_pipeline.py)
# =====================================================================
# 【功能概述】
#   本文件是 grandMining 系统的"纯文本直通处理流水线"，
#   专门处理 .txt 格式的文献文本文件，无需 PDF 解析和 OCR。
#   串联三个核心阶段：
#   阶段 1：遍历 txt_inputs/ 目录读取所有 .txt 文件
#   阶段 2：调用 DeepSeek 文本大模型提取 40+ 维爆破参数
#   阶段 3：启动五重递进式数据修复引擎（train 模式）
#
# 【运行方式】
#   python run_txt_pipeline.py
#
# 【适用场景】
#   文献已转为纯文本格式（.txt），无需 PDF 解析和 OCR，直接提取参数
#
# 【前置条件】
#   1. 已将 .txt 文件放入 txt_inputs/ 目录
#   2. 已配置 config.yaml 中的 API 密钥
#
# 【输出产物】
#   outputs/blasting_CBR_from_txt.xlsx           — 原始特征矩阵
#   outputs/blasting_CBR_from_txt_Imputed_Bounded.xlsx — 修复后特征库
#
# 【依赖模块】
#   - extractor_module：特征提取模块，提供 extract_text_params() 文本参数提取函数
#   - imputation_engine：数据修复模块，提供 BlastingDataImputer 五重修复引擎
#   - config：统一配置加载器，负责读取 API 密钥和路径配置
# =====================================================================

import os
import pandas as pd
import asyncio

# 从特征提取模块中导入异步文本参数提取函数（调用 DeepSeek 大模型）
from extractor_module import extract_text_params

# 从数据修复模块中导入五重递进式修复引擎类
from imputation_engine import BlastingDataImputer

# 从统一配置中导入 API 密钥、纯文本输入目录、输出目录
from config import TEXT_API_KEY as DEEPSEEK_API_KEY, TXT_DIR, OUTPUT_DIR


# ==========================================
# ⚙️ 配置区
# ==========================================


def main():
    """
    纯文本直通处理流水线主函数。
    
    【执行流程】
      1. 创建必要的目录（txt_inputs/ 和 outputs/）
      2. 遍历 txt_inputs/ 目录下的所有 .txt 文件
      3. 逐个调用 DeepSeek 大模型提取 40+ 维爆破参数
      4. 将提取结果汇总为 DataFrame 并保存为初始 Excel
      5. 启动五重递进式数据修复引擎进行修复
      6. 输出最终的高价值特征库
    """
    
    # -----------------------------------------------------------------
    # 前置准备：确保输入和输出目录存在
    # -----------------------------------------------------------------
    # 如果纯文本输入目录不存在，自动创建并提示用户放入文件
    if not os.path.exists(TXT_DIR):
        os.makedirs(TXT_DIR)
        print(f"请将你的 txt 文稿放入 '{TXT_DIR}' 文件夹后再运行。")
        return

    # 如果输出目录不存在，自动创建
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)

    # 用于存储所有 .txt 文件的提取结果
    extracted_data = []

    print("=====================================================")
    print("🚀 启动 grandMining [纯文本直通] 自动化流水线")
    print("=====================================================\n")

    # -------------------------------------------------------
    # 阶段 1：遍历读取 txt 并呼叫大模型提取特征
    # -------------------------------------------------------
    # 【说明】逐个读取 txt_inputs/ 目录下的 .txt 文件，
    # 调用 DeepSeek 大模型的 extract_text_params() 函数提取 40+ 维参数
    for filename in os.listdir(TXT_DIR):
        if filename.lower().endswith(".txt"):
            file_path = os.path.join(TXT_DIR, filename)
            
            # 读取 .txt 文件的全部文本内容（使用 UTF-8 编码）
            with open(file_path, "r", encoding="utf-8") as f:
                raw_text = f.read()
                
            print(f"📖 正在解析文稿: {filename} (字符数: {len(raw_text)})")
            
            # 调用提取模块的异步文本参数提取函数
            # extract_text_params() 是一个 async 函数，需要用 asyncio.run() 包裹执行
            # 该函数会调用 DeepSeek 大模型，从文本中提取 40+ 维爆破参数
            params = asyncio.run(extract_text_params(raw_text, filename))
            
            if params:
                # 提取成功，将"论文来源"字段设为文件名，便于后续溯源
                params["论文来源"] = filename
                extracted_data.append(params)
                print(f"  ✅ 成功提取特征: {len(params)} 项")
            else:
                print(f"  ❌ 提取失败或未找到有效数据。")

    # -------------------------------------------------------
    # 阶段 2：存为中间态 Excel 并启动插补引擎
    # -------------------------------------------------------
    if extracted_data:
        # 1. 将所有提取结果转为 DataFrame（表格形式）
        df = pd.DataFrame(extracted_data)
        
        # 将"论文来源"列放到最前面，方便查阅
        cols = ['论文来源'] + [c for c in df.columns if c != '论文来源']
        df = df[cols]
        
        # 保存为初始特征矩阵 Excel 文件（修复引擎的输入）
        temp_excel_path = os.path.join(OUTPUT_DIR, "blasting_CBR_from_txt.xlsx")
        df.to_excel(temp_excel_path, index=False)
        print(f"\n📂 文本解析完毕，已生成初始特征矩阵: {temp_excel_path}")
        
        # 2. 启动五重递进式数据修复引擎
        print("\n👉 [阶段 3] 启动三核混合特征提取与数据重构")
        
        # 初始化修复引擎实例，传入 DeepSeek API 密钥
        # BlastingDataImputer 会加载 domain_rules.json 中的物理规则和安规边界
        imputer = BlastingDataImputer(api_key=DEEPSEEK_API_KEY)
        
        # 【模式选择说明】
        # mode="train"：首次数据重构，会训练新的 XGBoost 模型并保存到 models/ 目录
        # mode="predict"：已有预训练模型，直接加载 models/ 中的模型进行预测修复
        # 建议：如果是首批数据，使用 mode="train"；后续新数据推演使用 mode="predict"
        final_output_path = imputer.process_excel(temp_excel_path, mode="train")
        
        # -------------------------------------------------------
        # 流水线执行完毕，输出最终结果
        # -------------------------------------------------------
        print("\n=====================================================")
        print(f"🎉 全流程执行完毕！")
        print(f"📂 终极高价值特征库已保存至: {final_output_path}")
        print("=====================================================")
    else:
        print("\n⚠️ 警告：没有从 txt 中提取到任何有效数据，流水线终止。")


# ---------------------------------------------------------------------
# 程序入口
# ---------------------------------------------------------------------
# 当直接运行本文件时（python run_txt_pipeline.py），调用 main() 函数启动流水线
# 如果被其他模块 import，则不会自动执行，避免副作用
if __name__ == "__main__":
    main()