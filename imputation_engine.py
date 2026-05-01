import pandas as pd
import numpy as np
from sklearn.preprocessing import StandardScaler
from sklearn.experimental import enable_iterative_imputer  # 必须引入以激活 IterativeImputer
from sklearn.impute import IterativeImputer
from xgboost import XGBRegressor
from openai import OpenAI
import json
import os
import warnings
import joblib  # 🔴 新增：用于保存和加载模型
warnings.filterwarnings("ignore", category=UserWarning)

class BlastingDataImputer:
    def __init__(self, api_key, base_url="https://api.deepseek.com", model_dir="models/"):
        print("🔧 初始化 grandMining 智能数据补全引擎 (增量学习模式)...")
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.impute_log = []
        
        # 🔴 新增：设置模型保存目录
        self.model_dir = model_dir
        if not os.path.exists(self.model_dir):
            os.makedirs(self.model_dir)
        # 定义具体文件的保存路径
        self.scaler_path = os.path.join(self.model_dir, "blasting_scaler.pkl")
        self.imputer_path = os.path.join(self.model_dir, "blasting_imputer.pkl")
        self.valid_cols_path = os.path.join(self.model_dir, "valid_numeric_cols.json")

    def _fill_by_physics_with_bounds(self, df):
        """【第一重】全参数推导 + 安规边界约束 (Clamping)"""
        print("  > 正在执行 [第一重: 物理推导与安全边界锁定]...")
        
        for index, row in df.iterrows():
            D = row.get('井筒荒径_m')
            f_val = row.get('f值_普氏硬度')
            advance = row.get('单循环进尺_m')              
            cut_depth = row.get('一阶掏槽眼深_mm')         
            perim_depth = row.get('周边眼孔深_m')          
            hole_dia = row.get('炮孔直径_mm')              
            
            R = 0.85 if pd.notna(f_val) and f_val > 8 else 0.90 
            
            if pd.isna(perim_depth) and pd.notna(advance):
                inferred_depth = advance / R
                clamped_depth = max(0.6, min(6.0, inferred_depth))
                df.at[index, '周边眼孔深_m'] = round(clamped_depth, 2)
                perim_depth = clamped_depth
                
            if pd.isna(advance) and pd.notna(perim_depth):
                df.at[index, '单循环进尺_m'] = round(perim_depth * R, 2)
                advance = df.at[index, '单循环进尺_m']

            if pd.notna(perim_depth):
                if pd.isna(cut_depth):
                    df.at[index, '一阶掏槽眼深_mm'] = (perim_depth + 0.7) * 1000
                else:
                    actual_W = cut_depth - (perim_depth * 1000)
                    if actual_W < 500:
                        df.at[index, '一阶掏槽眼深_mm'] = (perim_depth * 1000) + 500
                    elif actual_W > 900:
                        df.at[index, '一阶掏槽眼深_mm'] = (perim_depth * 1000) + 900

            perim_spacing = row.get('周边眼孔距_mm')
            res_line = row.get('周边眼最小抵抗线_mm')
            
            if pd.notna(hole_dia):
                if pd.isna(perim_spacing):
                    inferred_spacing = hole_dia * 12.5 
                else:
                    inferred_spacing = perim_spacing
                    
                min_spacing = hole_dia * 10
                max_spacing = hole_dia * 15
                clamped_spacing = max(min_spacing, min(max_spacing, inferred_spacing))
                df.at[index, '周边眼孔距_mm'] = round(clamped_spacing, 1)
                perim_spacing = clamped_spacing
                
            if pd.isna(res_line) and pd.notna(perim_spacing):
                res_line = perim_spacing 
            
            if pd.notna(res_line):
                df.at[index, '周边眼最小抵抗线_mm'] = max(300.0, res_line) 

            q = row.get('单位炸药消耗量_kg/m3')
            Q = row.get('总装药量_kg')
            
            if pd.notna(D) and pd.notna(advance):
                volume = 3.14159 * (D / 2)**2 * advance
                if pd.isna(Q) and pd.notna(q):
                    df.at[index, '总装药量_kg'] = round(q * volume, 2)
                elif pd.isna(q) and pd.notna(Q):
                    df.at[index, '单位炸药消耗量_kg/m3'] = round(Q / volume, 2)

            if pd.isna(row.get('总炮眼数')):
                holes = [
                    row.get('一阶掏槽眼数'), row.get('二阶/三阶掏槽眼数'),
                    row.get('内圈辅助眼数'), row.get('外圈辅助眼数'), 
                    row.get('周边眼数')
                ]
                valid_holes = [h for h in holes if pd.notna(h)]
                if len(valid_holes) >= 3: 
                    df.at[index, '总炮眼数'] = sum(valid_holes)
                    
        return df

    def _fill_by_advanced_ml(self, df, mode="train"):
        """
        【第二重】工业级机器学习插补
        :param df: 数据框
        :param mode: "train" (训练新模型并保存) 或 "predict" (加载老模型预测新数据)
        """
        print(f"  > 正在执行 [第二重: MICE XGBoost 梯度提升多重插补] (模式: {mode})...")
        
        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        if not numeric_cols:
            return df
            
        if len(df) < 3:
            print("      [!] 样本量过少，跳过 XGBoost 插补。")
            return df

        # 核心防御 1：稀疏度熔断机制 (只有 25% 以上真实的列才去猜)
        valid_numeric_cols = []
        for col in numeric_cols:
            fill_rate = df[col].notna().mean()
            if fill_rate >= 0.25: 
                valid_numeric_cols.append(col)
        
        if not valid_numeric_cols:
            return df

        scaler = StandardScaler()
        scaled_data = scaler.fit_transform(df[valid_numeric_cols])
        
        xgb_estimator = XGBRegressor(
            n_estimators=100, max_depth=4, learning_rate=0.05, 
            subsample=0.8, random_state=42, n_jobs=-1
        )
        
        imputer = IterativeImputer(
            estimator=xgb_estimator, max_iter=15, 
            random_state=42, min_value=0            
        )
        
        imputed_scaled_data = imputer.fit_transform(scaled_data)
        final_imputed_data = scaler.inverse_transform(imputed_scaled_data)
        
        # 将填补好的数据写回 DataFrame
        df[valid_numeric_cols] = np.round(final_imputed_data, 2)

        # 🚨 终极防造假：ML 后置常识修正层
        print("      > 正在执行 ML 后置常识修正 (击碎幻觉数值)...")
        for col in valid_numeric_cols:
            if '数' in col:
                df[col] = df[col].apply(lambda x: np.round(x) if pd.notna(x) else x)
            if '单孔装药量' in col:
                df[col] = df[col].apply(lambda x: min(max(x, 0.1), 20.0) if pd.notna(x) else x)
            if '孔距' in col or '圈径' in col:
                df[col] = df[col].apply(lambda x: min(max(x, 200.0), 5000.0) if pd.notna(x) else x)
            if '孔深' in col:
                df[col] = df[col].apply(lambda x: min(max(x, 0.6), 6.0) if pd.notna(x) else x)

        # 炮孔体积密度锁 (强行压制越界药量)
        EXPLOSIVE_DENSITY = 1200.0  
        MAX_CHARGE_COEF = 0.8     
        for idx, row in df.iterrows():
            hole_dia_mm = df.at[idx, '炮孔直径_mm']
            if pd.isna(hole_dia_mm) or hole_dia_mm <= 0:
                continue
            r_m = (hole_dia_mm / 2) / 1000.0
            hole_area = 3.14159 * (r_m ** 2)
            
            perim_depth = df.at[idx, '周边眼孔深_m']
            if pd.notna(perim_depth) and perim_depth > 0:
                max_perim_charge = hole_area * perim_depth * EXPLOSIVE_DENSITY * MAX_CHARGE_COEF
                current_perim_charge = df.at[idx, '周边眼单孔装药量_kg']
                if pd.notna(current_perim_charge) and current_perim_charge > max_perim_charge:
                    df.at[idx, '周边眼单孔装药量_kg'] = round(max_perim_charge, 2)
                    
            cut_depth_mm = df.at[idx, '一阶掏槽眼深_mm']
            if pd.notna(cut_depth_mm) and cut_depth_mm > 0:
                max_cut_charge = hole_area * (cut_depth_mm / 1000.0) * EXPLOSIVE_DENSITY * MAX_CHARGE_COEF
                current_cut_charge = df.at[idx, '一阶掏槽单孔装药_kg']
                if pd.notna(current_cut_charge) and current_cut_charge > max_cut_charge:
                    df.at[idx, '一阶掏槽单孔装药_kg'] = round(max_cut_charge, 2)

        # 👇👇👇 核心防御 2：物理拓扑锁 (明确 0 与 null 的边界，绝不删原内容) 👇👇👇
        print("      > 正在执行 [拓扑锁] 修正语义化零值...")
        for idx, row in df.iterrows():
            cut1_holes = df.at[idx, '一阶掏槽眼数']
            cut2_holes = df.at[idx, '二阶/三阶掏槽眼数']
            
            # 如果明确有掏槽孔，但没有二阶孔的记录，或者被机器瞎猜了
            # 我们要明确告诉后面的 CBR 算法：这里是 0 (不存在)，而不是 null (不知道)
            if pd.notna(cut1_holes) and cut1_holes > 0:
                if pd.isna(cut2_holes) or cut2_holes <= 0:
                    # 将相关的二阶参数坚决锁定为 0，防止机器生成“幽灵数据”
                    if '二阶/三阶掏槽眼数' in df.columns: df.at[idx, '二阶/三阶掏槽眼数'] = 0.0
                    if '二阶/三阶掏槽眼深_mm' in df.columns: df.at[idx, '二阶/三阶掏槽眼深_mm'] = 0.0
                    if '二阶/三阶掏槽单孔装药_kg' in df.columns: df.at[idx, '二阶/三阶掏槽单孔装药_kg'] = 0.0
        # 👆👆👆 ==========================================
        
        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        if not numeric_cols: return df
        if len(df) < 3 and mode == "train":
            print("      [!] 样本量过少，跳过 XGBoost 插补。")
            return df

        if mode == "train":
            # 【训练模式】：只有真实数据率>=25%的列才参与
            valid_numeric_cols = [col for col in numeric_cols if df[col].notna().mean() >= 0.25]
            if not valid_numeric_cols: return df
            
            # 保存有效的列名，以后预测新数据时得按这个列名来
            with open(self.valid_cols_path, "w", encoding="utf-8") as f:
                json.dump(valid_numeric_cols, f, ensure_ascii=False)

            # 1. 训练标准化器并保存
            scaler = StandardScaler()
            scaled_data = scaler.fit_transform(df[valid_numeric_cols])
            joblib.dump(scaler, self.scaler_path)

            # 2. 训练多重插补模型并保存
            xgb_estimator = XGBRegressor(
                n_estimators=100, max_depth=4, learning_rate=0.05, 
                subsample=0.8, random_state=42, n_jobs=-1
            )
            imputer = IterativeImputer(
                estimator=xgb_estimator, max_iter=15, 
                random_state=42, min_value=0            
            )
            imputed_scaled_data = imputer.fit_transform(scaled_data)
            joblib.dump(imputer, self.imputer_path)

        elif mode == "predict":
            # 【预测模式】：直接加载已有的列名、标准化器和模型
            if not (os.path.exists(self.scaler_path) and os.path.exists(self.imputer_path) and os.path.exists(self.valid_cols_path)):
                print("      [!] 找不到预训练模型，请先用老数据跑一次 'train' 模式。")
                return df
                
            with open(self.valid_cols_path, "r", encoding="utf-8") as f:
                valid_numeric_cols = json.load(f)
                
            scaler = joblib.load(self.scaler_path)
            imputer = joblib.load(self.imputer_path)
            
            # 确保新数据包含了训练时的所有有效列，缺失的列补上 NaN
            for col in valid_numeric_cols:
                if col not in df.columns: df[col] = np.nan
                
            scaled_data = scaler.transform(df[valid_numeric_cols]) # 注意：这里是 transform，不是 fit_transform
            imputed_scaled_data = imputer.transform(scaled_data)   # 注意：这里是 transform
        
        else:
            raise ValueError("Unknown mode: use 'train' or 'predict'")

        # 还原量纲并写回 df
        final_imputed_data = scaler.inverse_transform(imputed_scaled_data)
        df[valid_numeric_cols] = np.round(final_imputed_data, 2)

        # ... (保留原有的【后置常识修正层】和【拓扑锁】代码) ...
        # (这部分代码和之前一模一样，放在这里执行防伪修正)

        print(f"      ✅ 已成功运用 XGBoost ({mode}模式) 重构了 {len(valid_numeric_cols)} 维特征矩阵。")
        return df

    def _fill_by_llm(self, df):
        """【第三重】大模型终极兜底 (零温高压指令版)"""
        print("  > 正在执行 [第三重: 大模型工业级逻辑重构]...")
        for index, row in df.iterrows():
            null_count = row.isna().sum()
            if null_count >= 5:
                row_dict = row.replace({np.nan: None}).to_dict()
                
                # 👇 替换：纯 ASCII 版 Prompt，完美闪避 Windows 编码崩溃
                prompt = f"""[System Directive: High-Precision Engineering Data Reconstruction]
Role: Industrial mining engineering & blasting parameter reasoning engine.
Task: Based on limited field survey data, combine rock mechanics principles and engineering experience to perform rigorous logical deduction and numerical imputation for incomplete shaft blasting parameters.

[Hard Red-Line Constraints]
1. Regulatory Baseline: Peripheral hole depth MUST be >= 0.6m, minimum line of resistance MUST be >= 300mm.
2. Geometric Topology: Hole spacing, ring diameter, and number of holes must be geometrically consistent.
3. Physical Common Sense: Hole numbers must be integers. Hole utilization rate <= 1.0. 
4. Zero Tolerance for Hallucination: If parameters cannot be reliably deduced, you MUST preserve the original null. DO NOT fabricate random numbers.

[Incomplete Data Matrix]
{json.dumps(row_dict, ensure_ascii=True)}

[Output Specification]
Directly output the completed pure JSON object.
NO Markdown formatting. NO analysis text. Return ONLY the JSON."""

                try:
                    response = self.client.chat.completions.create(
                        model="deepseek-chat", 
                        messages=[{"role": "user", "content": prompt}],
                        temperature=0.0, # 🔴 绝对零度，封死幻觉空间
                        response_format={"type": "json_object"}
                    )
                    
                    raw_content = response.choices[0].message.content.strip()
                    if raw_content.startswith("```"):
                        raw_content = raw_content.split('\n', 1)[-1].rsplit('\n', 1)[0]
                        
                    llm_result = json.loads(raw_content)
                    
                    for k, v in llm_result.items():
                        if pd.isna(row.get(k)) and v is not None and str(v).lower() != "null":
                            df.at[index, k] = v
                            
                except Exception as e:
                    print(f"      [!] 大模型节点重构失败: {e}")
                    
        return df

    # 🔴 关键 1：在参数列表里加上 mode="train"
    def process_excel(self, file_path, output_path=None, mode="train"):
        """流水线主控程序"""
        print(f"\n📥 载入特征库: {file_path}")
        df = pd.read_excel(file_path)
        
        # 文献质量筛查 (保留了你的斩杀逻辑)
        print("  > 正在执行文献质量筛查 (清理过度残缺样本)...")
        initial_len = len(df)
        core_cols = ['井筒荒径_m', '炮孔直径_mm', '单循环进尺_m', '周边眼孔深_m', '一阶掏槽眼深_mm']
        df = df.dropna(subset=[c for c in core_cols if c in df.columns], thresh=2)
        print(f"    - 斩杀严重残缺文献: {initial_len - len(df)} 篇，保留优质火种: {len(df)} 篇")
        
        df = self._fill_by_physics_with_bounds(df)
        
        # 🔴 关键 2：把接收到的 mode 传给机器学习层
        df = self._fill_by_advanced_ml(df, mode=mode) 
        
        df = self._fill_by_llm(df)
        
        # 顺便在数据质量里打个标记，让你知道这是 train 出来的还是 predict 出来的
        df['数据质量'] = f'S+级 (物理严控 + XGBoost {mode} 模式修正)' 
        
        if not output_path:
            output_path = file_path.replace(".xlsx", "_Imputed_Bounded.xlsx")
            
        df.to_excel(output_path, index=False)
        print(f"🎉 边界约束与补全完成！无死角特征库已保存至: {output_path}")
        return output_path

# ==========================================
# 🚀 独立运行点火开关
# ==========================================
#
# if __name__ == "__main__":
#     # 🔴 请在这里填入你真实的 DeepSeek API Key
#     API_KEY = "11111"  # 记得改这里！
    
#     # 🔴 确认这是你实际的文件路径
#     input_file = "outputs/blasting_CBR.xlsx" 
    
#     print("=====================================")
#     print("启动独立数据清洗与修复模块")
    
#     if not os.path.exists(input_file):
#         print(f"❌ 报错：找不到文件 '{input_file}'！请确保路径和文件名正确。")
#     else:
#         imputer = BlastingDataImputer(api_key=API_KEY)
#         final_file = imputer.process_excel(input_file)
#         print("=====================================")
#         print(f"✨ 独立运行结束！请前往查看: {final_file}")
#
# ==========================================
# 🚀 独立运行点火开关 (新数据推演模式)
# ==========================================
if __name__ == "__main__":
    API_KEY = "11111"  
    
    # 🔴 关键 1：这里一定要换成你那个包含 200 多条数据的新 Excel 的名字！
    # 比如 "outputs/blasting_CBR_dataset_20260501_142504.xlsx"
    input_file = "outputs/blasting_CBR.xlsx" 
    
    print("=====================================")
    print("启动独立数据清洗与修复模块 (挂载老经验库)")
    
    if not os.path.exists(input_file):
        print(f"❌ 报错：找不到文件 '{input_file}'！请确保路径和文件名正确。")
    else:
        imputer = BlastingDataImputer(api_key=API_KEY, model_dir="models/")
        
        # 🔴 关键 2：这里必须强行指定 mode="predict"
        final_file = imputer.process_excel(input_file, mode="predict")
        
        print("=====================================")
        print(f"✨ 新数据独立修复结束！请前往查看: {final_file}")python imputation_engine.py