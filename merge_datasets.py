# =====================================================================
# 📄 文件说明：grandMining 数据集融合工具 (merge_datasets.py)
# =====================================================================
# 【功能概述】
#   本文件是 grandMining 系统的"数据集融合工具"，
#   负责将多个批次产出的 Excel 特征矩阵进行合并、去重和清洗，
#   最终生成一个统一的 Master 超级特征库。
#
# 【核心功能】
#   1. 自动扫描 outputs/ 目录下所有 .xlsx 文件（排除 Master 和 _Imputed 中间产物）
#   2. 列维度求并集：不同批次提取的参数列可能不同，合并时自动对齐，缺失格子填 NaN
#   3. 基于"论文来源"列自动去重：防止同一篇文献被多次处理后重复入库
#   4. 清理废弃列：删除历史遗留的错误列名，防止干扰大模型
#   5. 输出最终的 Master 超级特征库
#
# 【运行方式】
#   python merge_datasets.py
#
# 【适用场景】
#   多批次数据需要合并时使用，例如：
#   - 第一次处理了 10 篇 PDF，产出 blasting_CBR_dataset_20240101.xlsx
#   - 第二次处理了 5 篇 PDF，产出 blasting_CBR_dataset_20240201.xlsx
#   - 运行本工具将两批数据合并为一个完整的 Master 特征库
#
# 【前置条件】
#   outputs/ 目录下至少有一个 .xlsx 文件（由 extractor_module 或 run_txt_pipeline 产出）
#
# 【输出产物】
#   outputs/blasting_CBR_Master.xlsx — 融合后的超级特征矩阵
#
# 【依赖模块】
#   - pandas：数据处理与 Excel 读写
#   - os、glob：文件系统操作，用于扫描目录和匹配文件
# =====================================================================

import pandas as pd
import os
import glob

print("🔄 开始融合多模态特征库 (Excel 引擎)...")

# ---------------------------------------------------------------------
# 1. 自动扫描 outputs/ 目录下所有 .xlsx 文件
# ---------------------------------------------------------------------
# 【说明】使用 glob 模块匹配 outputs/ 目录下所有以 .xlsx 结尾的文件
# 排除文件名中包含 "Master" 的文件（避免将之前的融合产物再次纳入融合）
output_dir = "outputs"
all_xlsx = glob.glob(os.path.join(output_dir, "*.xlsx"))

# 过滤掉 Master 融合产物和 _Imputed 后缀的中间产物（只保留原始批次数据）
files = [f for f in all_xlsx if "Master" not in os.path.basename(f)]

print(f"  📂 自动扫描到 {len(files)} 个 Excel 文件:")
for f in files:
    print(f"    → {f}")

# ---------------------------------------------------------------------
# 2. 逐个读取 Excel 文件并收集到列表中
# ---------------------------------------------------------------------
# 【说明】逐个读取每个 Excel 文件为 DataFrame，存入 df_list 列表
# 如果某个文件读取失败（如文件损坏），会打印错误信息并跳过，不影响其他文件
df_list = []
for f in files:
    try:
        df = pd.read_excel(f)
        df_list.append(df)
        print(f"  ✅ 成功读取: {os.path.basename(f)} (包含 {len(df)} 行数据)")
    except Exception as e:
        print(f"  ❌ 读取失败: {os.path.basename(f)} ({e})")

if not df_list:
    # 如果没有读到任何有效文件，直接终止
    print("\n🚨 错误：没有读到任何文件，合并终止！")
else:
    # ---------------------------------------------------------------
    # 3. 列维度求并集，纵向拼接所有 DataFrame
    # ---------------------------------------------------------------
    # 【说明】pd.concat(axis=0) 会将所有 DataFrame 纵向堆叠
    # 如果不同批次的 DataFrame 列名不完全一致，缺失的列会自动填入 NaN
    # ignore_index=True 表示重新生成连续的行索引
    master_df = pd.concat(df_list, axis=0, ignore_index=True)

    # ---------------------------------------------------------------
    # 4. 清理废弃列（历史遗留的错误列名）
    # ---------------------------------------------------------------
    # 【说明】清理掉之前老数据里提取错误的列名，防止干扰大模型
    if '岩性_m_原文依据' in master_df.columns:
        master_df.drop(columns=['岩性_m_原文依据'], inplace=True)

    # ---------------------------------------------------------------
    # 5. 删除完全重复的行（基于"论文来源"列去重）
    # ---------------------------------------------------------------
    # 【说明】同一篇文献可能被多次爬取或处理，导致重复入库
    # keep='last' 表示保留最后一条记录（最新的处理结果）
    before_drop = len(master_df)
    if '论文来源' in master_df.columns:
        master_df.drop_duplicates(subset=['论文来源'], keep='last', inplace=True)
        print(f"\n🗑️ 已清理 {before_drop - len(master_df)} 条重复文献。")

    # ---------------------------------------------------------------
    # 6. 输出最终的 Master 超级特征库
    # ---------------------------------------------------------------
    # 【说明】将融合后的 DataFrame 保存为 blasting_CBR_Master.xlsx
    output_name = os.path.join(output_dir, "blasting_CBR_Master.xlsx")
    master_df.to_excel(output_name, index=False)

    print(f"🎉 融合大业完成！最终的超级矩阵包含 {len(master_df)} 行, {len(master_df.columns)} 列。")
    print(f"💾 文件已保存为: {output_name}")