import pandas as pd
import os

print("🔄 开始融合多模态特征库 (Excel 引擎)...")

# 精确指向 outputs 文件夹里的 xlsx 文件
files = [
    "outputs/blasting_CBR_from_txt.xlsx",
    "outputs/blasting_CBR.xlsx",
    "outputs/blasting_CBR_dataset_20260502_165739.xlsx",
    "outputs/blasting_CBR_dataset_20260502_121008.xlsx",
    "outputs/blasting_CBR_dataset_20260503_115552.xlsx"
]

df_list = []
for f in files:
    if os.path.exists(f):
        # 🔴 关键修改：从 read_csv 改成了 read_excel
        df = pd.read_excel(f)
        df_list.append(df)
        print(f"  ✅ 成功读取: {f} (包含 {len(df)} 行数据)")
    else:
        print(f"  ❌ 找不到文件: {f} (请检查名字是否完全一致)")

if not df_list:
    print("\n🚨 错误：没有读到任何文件，合并终止！")
else:
    # 1. 强行在列维度求并集，缺失的格子自动填入 NaN
    master_df = pd.concat(df_list, axis=0, ignore_index=True)

    # 2. 清理废弃列（清理掉之前老数据里提取错误的列名，防止干扰大模型）
    if '岩性_m_原文依据' in master_df.columns:
        master_df.drop(columns=['岩性_m_原文依据'], inplace=True)

    # 3. 删除完全重复的行（防止同一篇文献被多次爬取）
    before_drop = len(master_df)
    if '论文来源' in master_df.columns:
        master_df.drop_duplicates(subset=['论文来源'], keep='last', inplace=True)
        print(f"\n🗑️ 已清理 {before_drop - len(master_df)} 条重复文献。")

    # 4. 输出最终的 Master 特征库到 outputs 文件夹
    output_name = "outputs/blasting_CBR_Master_438.xlsx"
    master_df.to_excel(output_name, index=False)

    print(f"🎉 融合大业完成！最终的超级矩阵包含 {len(master_df)} 行, {len(master_df.columns)} 列。")
    print(f"💾 文件已保存为: {output_name}")