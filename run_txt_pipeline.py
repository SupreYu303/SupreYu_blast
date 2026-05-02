import os
import pandas as pd
from extractor_module import extract_text_params
from imputation_engine import BlastingDataImputer
from config import TEXT_API_KEY as DEEPSEEK_API_KEY, TXT_DIR, OUTPUT_DIR

# ==========================================
# ⚙️ 配置区
# ==========================================

def main():
    if not os.path.exists(TXT_DIR):
        os.makedirs(TXT_DIR)
        print(f"请将你的 txt 文稿放入 '{TXT_DIR}' 文件夹后再运行。")
        return

    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)

    extracted_data = []

    print("=====================================================")
    print("🚀 启动 grandMining [纯文本直通] 自动化流水线")
    print("=====================================================\n")

    # -------------------------------------------------------
    # 阶段 1：遍历读取 txt 并呼叫大模型提取特征
    # -------------------------------------------------------
    for filename in os.listdir(TXT_DIR):
        if filename.lower().endswith(".txt"):
            file_path = os.path.join(TXT_DIR, filename)
            
            with open(file_path, "r", encoding="utf-8") as f:
                raw_text = f.read()
                
            print(f"📖 正在解析文稿: {filename} (字符数: {len(raw_text)})")
            
            # 直接调用提取模块的文本大脑
            params = extract_text_params(raw_text, filename)
            
            if params:
                params["论文来源"] = filename
                extracted_data.append(params)
                print(f"  ✅ 成功提取特征: {len(params)} 项")
            else:
                print(f"  ❌ 提取失败或未找到有效数据。")

    # -------------------------------------------------------
    # 阶段 2：存为中间态 Excel 并启动插补引擎
    # -------------------------------------------------------
    if extracted_data:
        # 1. 保存为 imputation_engine 能看懂的初始 Excel
        df = pd.DataFrame(extracted_data)
        
        # 将论文来源放到第一列
        cols = ['论文来源'] + [c for c in df.columns if c != '论文来源']
        df = df[cols]
        
        temp_excel_path = os.path.join(OUTPUT_DIR, "blasting_CBR_from_txt.xlsx")
        df.to_excel(temp_excel_path, index=False)
        print(f"\n📂 文本解析完毕，已生成初始特征矩阵: {temp_excel_path}")
        
        # 2. 呼叫你的三重修复引擎
        print("\n👉 [阶段 3] 启动三核混合特征提取与数据重构")
        imputer = BlastingDataImputer(api_key=DEEPSEEK_API_KEY)
        
        # 如果是新数据推演，建议 mode="predict"；如果是首批数据重构，用 mode="train"
        final_output_path = imputer.process_excel(temp_excel_path, mode="train")
        
        print("\n=====================================================")
        print(f"🎉 全流程执行完毕！")
        print(f"📂 终极高价值特征库已保存至: {final_output_path}")
        print("=====================================================")
    else:
        print("\n⚠️ 警告：没有从 txt 中提取到任何有效数据，流水线终止。")

if __name__ == "__main__":
    main()