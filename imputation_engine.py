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
import sys
import io

# 强制将标准输出和标准错误的编码设置为 UTF-8，彻底解决 Windows 打印中文报错
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
warnings.filterwarnings("ignore", category=UserWarning)
from config import TEXT_MODEL, TEXT_BASE_URL

class BlastingDataImputer:
    def __init__(self, api_key, base_url=TEXT_BASE_URL, model_dir="models/"):
        print("🔧 初始化 grandMining 智能数据补全引擎 (增量学习模式)...")
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.impute_log = []
        
        # 👇 加载外部物理常量与安规红线配置
        config_path = "domain_rules.json"
        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                self.config = json.load(f)
        else:
            raise FileNotFoundError(f"缺失领域知识配置文件: {config_path}")

        self.model_dir = model_dir
        if not os.path.exists(self.model_dir):
            os.makedirs(self.model_dir)
        self.scaler_path = os.path.join(self.model_dir, "blasting_scaler.pkl")
        self.imputer_path = os.path.join(self.model_dir, "blasting_imputer.pkl")
        self.valid_cols_path = os.path.join(self.model_dir, "valid_numeric_cols.json")

    def _fill_by_physics_with_bounds(self, df):
        """【第一重】全参数推导 + 岩石力学专家字典 + 安规边界约束"""
        print("  > 正在执行 [第一重: 物理推导与安全边界锁定 (挂载岩性专家字典)]...")
        
        # 从外部配置加载岩石力学经验字典
        rock_expert_dict = self.config.get("rock_expert_dict", {})

        for index, row in df.iterrows():
            D = row.get('井筒荒径_m')
            f_val = row.get('f值_普氏硬度')
            rock_str = str(row.get('岩性', ''))
            advance = row.get('单循环进尺_m')              
            cut_depth = row.get('一阶掏槽眼深_mm')         
            perim_depth = row.get('周边眼孔深_m')          
            hole_dia = row.get('炮孔直径_mm')              
            
            if pd.notna(D):
                # 强制推算并覆盖掘进断面积
                df.at[index, '掘进断面积_m2'] = round(3.14159 * (D / 2)**2, 2)
                
                # 强制推算内圈/外圈/周边眼圈径 (根据标准立井爆破圈径比例)
                if '图纸_内圈辅助眼圈径_mm' in df.columns and pd.isna(row.get('图纸_内圈辅助眼圈径_mm')):
                    df.at[index, '图纸_内圈辅助眼圈径_mm'] = round(D * 1000 * 0.45, 1) # 内圈占荒径 45%
                if '图纸_外圈辅助眼圈径_mm' in df.columns and pd.isna(row.get('图纸_外圈辅助眼圈径_mm')):
                    df.at[index, '图纸_外圈辅助眼圈径_mm'] = round(D * 1000 * 0.70, 1) # 外圈占荒径 70%
                if '图纸_周边眼圈径_mm' in df.columns and pd.isna(row.get('图纸_周边眼圈径_mm')):
                    df.at[index, '图纸_周边眼圈径_mm'] = round(D * 1000 * 0.90, 1) # 周边眼圈占荒径 90%
            # 👇👇👇 智能识别与物理锚点注入 👇👇👇
            # 尝试从文字中匹配岩石类型，优先使用字典专家经验，兜底使用 f 值
            matched_rock = next((k for k in rock_expert_dict.keys() if k in rock_str), None)
            
            if matched_rock:
                R = rock_expert_dict[matched_rock]['R_coef']
                expert_q = rock_expert_dict[matched_rock]['q_base']
            else:
                # 兜底逻辑
                R = 0.85 if pd.notna(f_val) and f_val > 8 else 0.90 
                expert_q = None

            # 1. 孔深与进尺的耦合推导 (利用更精准的 R 值)
            if pd.isna(perim_depth) and pd.notna(advance):
                inferred_depth = advance / R
                clamped_depth = max(0.6, min(6.0, inferred_depth))
                df.at[index, '周边眼孔深_m'] = round(clamped_depth, 2)
                perim_depth = clamped_depth
                
            if pd.isna(advance) and pd.notna(perim_depth):
                df.at[index, '单循环进尺_m'] = round(perim_depth * R, 2)
                advance = df.at[index, '单循环进尺_m']

            # 2. 掏槽孔深度几何推导
            if pd.notna(perim_depth):
                if pd.isna(cut_depth):
                    df.at[index, '一阶掏槽眼深_mm'] = (perim_depth + 0.7) * 1000
                else:
                    actual_W = cut_depth - (perim_depth * 1000)
                    if actual_W < 500:
                        df.at[index, '一阶掏槽眼深_mm'] = (perim_depth * 1000) + 500
                    elif actual_W > 900:
                        df.at[index, '一阶掏槽眼深_mm'] = (perim_depth * 1000) + 900

            # 3. 周边眼参数推导
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

            # 4. 物质守恒：装药量与单耗的终极推导
            q = row.get('单位炸药消耗量_kg/m3')
            Q = row.get('总装药量_kg')
            
            if pd.notna(D) and pd.notna(advance):
                volume = 3.14159 * (D / 2)**2 * advance
                if pd.isna(Q) and pd.notna(q):
                    df.at[index, '总装药量_kg'] = round(q * volume, 2)
                elif pd.isna(q) and pd.notna(Q):
                    df.at[index, '单位炸药消耗量_kg/m3'] = round(Q / volume, 2)
                # 👇 字典发威：如果总药量和单耗都没提取到，直接用字典经验基准强行推导！
                elif pd.isna(Q) and pd.isna(q) and expert_q is not None:
                    df.at[index, '单位炸药消耗量_kg/m3'] = expert_q
                    df.at[index, '总装药量_kg'] = round(expert_q * volume, 2)

            # 5. 总炮眼数拓扑
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
        【第二重】工业级机器学习插补 (增量学习 + 类别特征语义觉醒)
        """
        print(f"  > 正在执行 [第二重: MICE XGBoost 梯度提升多重插补] (模式: {mode})...")
        
        # 👇👇👇 核心进化 1：文字维度语义觉醒 (Categorical Encoding) 👇👇👇
        # 绝不丢弃文字信息！让 XGBoost 知道在爆什么岩石，用什么炸药
        text_cols = ['岩性', '炸药类型', '装药方式']
        cat_mapping_path = os.path.join(self.model_dir, "categorical_mappings.json")
        mapping_dicts = {}
        
        if mode == "train":
            for col in text_cols:
                if col in df.columns:
                    # 获取该列所有非空的独立类别
                    unique_vals = df[col].dropna().astype(str).unique()
                    # 分配数字 ID (从 1 开始，0 留给未知类别)
                    mapping_dicts[col] = {val: i + 1 for i, val in enumerate(unique_vals)}
            # 存入老经验库
            with open(cat_mapping_path, "w", encoding="utf-8") as f:
                json.dump(mapping_dicts, f, ensure_ascii=False)
        elif mode == "predict":
            if os.path.exists(cat_mapping_path):
                with open(cat_mapping_path, "r", encoding="utf-8") as f:
                    mapping_dicts = json.load(f)

        # 挂载编码列：原列保留给最终输出，新建 `_编码` 列喂给算法
        encoded_cols = []
        for col, mapping in mapping_dicts.items():
            if col in df.columns:
                new_col = f"{col}_特征编码"
                df[new_col] = df[col].apply(lambda x: mapping.get(str(x), 0) if pd.notna(x) else np.nan)
                encoded_cols.append(new_col)
        # 👆👆👆 ======================================================== 👆👆👆

        # 强制数值类型清洗 (防止脏数据导致算法崩溃)
        target_keywords = ['_m', '_mm', '_kg', '数', '率', '面积', '硬度', '特征编码']
        for col in df.columns:
            if any(kw in col for kw in target_keywords):
                df[col] = pd.to_numeric(df[col], errors='coerce')

        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        if not numeric_cols: return df
        
        if len(df) < 3 and mode == "train":
            print("      [!] 样本量过少，跳过 XGBoost 插补。")
            return df

        if mode == "train":
            # 只有真实数据率>=25%的列才参与，防止劣质列污染模型
            valid_numeric_cols = [col for col in numeric_cols if df[col].notna().mean() >= 0.25]
            if not valid_numeric_cols: return df
            
            with open(self.valid_cols_path, "w", encoding="utf-8") as f:
                json.dump(valid_numeric_cols, f, ensure_ascii=False)

            scaler = StandardScaler()
            scaled_data = scaler.fit_transform(df[valid_numeric_cols])
            joblib.dump(scaler, self.scaler_path)

            # 👇👇👇 核心进化 2：专为小样本采矿工程微调的树模型参数 👇👇👇
            xgb_estimator = XGBRegressor(
                n_estimators=150,      # 树的数量适当增加，增强拟合能力
                max_depth=5,           # 允许更深的逻辑分支 (关联孔距、药量、编码)
                learning_rate=0.03,    # 降低学习率，步子迈小一点，防止小样本过拟合
                subsample=0.75,        # 随机抽取 75% 的样本，增加抗噪能力
                colsample_bytree=0.8,  # 随机抽取 80% 的特征，打破强特征垄断
                random_state=42,
                n_jobs=-1
            )
            
            imputer = IterativeImputer(
                estimator=xgb_estimator, max_iter=20, # 增加多重插补的迭代轮数
                random_state=42, min_value=0            
            )
            imputed_scaled_data = imputer.fit_transform(scaled_data)
            joblib.dump(imputer, self.imputer_path)

        elif mode == "predict":
            if not (os.path.exists(self.scaler_path) and os.path.exists(self.imputer_path) and os.path.exists(self.valid_cols_path)):
                print("      [!] 找不到预训练模型，请先跑 'train' 模式。")
                return df
                
            with open(self.valid_cols_path, "r", encoding="utf-8") as f:
                valid_numeric_cols = json.load(f)
                
            scaler = joblib.load(self.scaler_path)
            imputer = joblib.load(self.imputer_path)
            
            # 对齐列维度
            missing_cols = set(valid_numeric_cols) - set(df.columns)
            for col in missing_cols: df[col] = np.nan
                
            scaled_data = scaler.transform(df[valid_numeric_cols]) 
            imputed_scaled_data = imputer.transform(scaled_data)   
        
        else:
            raise ValueError("Unknown mode")

        # 还原量纲并写回 df
        final_imputed_data = scaler.inverse_transform(imputed_scaled_data)
        df[valid_numeric_cols] = np.round(final_imputed_data, 2)

        # 清理掉临时的编码列，保持表格干净
        for col in encoded_cols:
            if col in df.columns:
                df.drop(columns=[col], inplace=True)

        # ==========================================
        # ML 后置常识修正层与拓扑锁 (保留原逻辑)
        # ==========================================


        print("      > 正在执行 ML 后置常识修正 (实施最严苛工程绞杀)...")
        for col in valid_numeric_cols:
            if col not in df.columns: continue
            
            # 1. 炮眼数必须是整数
            if '数' in col:
                df[col] = df[col].apply(lambda x: np.round(x) if pd.notna(x) else x)
            
            # 2. 孔深红线 (👇 修复 Bug 1：使用 endswith 精准匹配后缀，避免 _m 拦截 _mm)
            if '孔深' in col or '眼深' in col:
                if col.endswith('_mm'):
                    df[col] = df[col].apply(lambda x: min(max(x, self.config["bounds"]["MIN_HOLE_DEPTH_M"]*1000), self.config["bounds"]["MAX_HOLE_DEPTH_M"]*1000) if pd.notna(x) else x)
                elif col.endswith('_m'):
                    df[col] = df[col].apply(lambda x: min(max(x, self.config["bounds"]["MIN_HOLE_DEPTH_M"]), self.config["bounds"]["MAX_HOLE_DEPTH_M"]) if pd.notna(x) else x)
            
            # 3. 孔距与抵抗线红线
            if '周边眼孔距' in col:
                df[col] = df[col].apply(lambda x: min(max(x, 300.0), self.config["bounds"]["MAX_PERIMETER_SPACING_MM"]) if pd.notna(x) else x)
            if '抵抗线' in col:
                df[col] = df[col].apply(lambda x: max(x, self.config["bounds"]["MIN_RESISTANCE_LINE_MM"]) if pd.notna(x) else x)

            # 4. 进尺极值防倒挂
            if '进尺' in col:
                df[col] = df[col].apply(lambda x: min(x, self.config["bounds"]["MAX_ADVANCE_M"]) if pd.notna(x) else x)
                
            # 5. 分级药量红线
            if '周边眼单孔装药' in col:
                df[col] = df[col].apply(lambda x: min(max(x, 0.1), self.config["bounds"]["MAX_PERIMETER_CHARGE_KG"]) if pd.notna(x) else x)
            elif '辅助眼' in col and '装药' in col:
                df[col] = df[col].apply(lambda x: min(max(x, 0.1), self.config["bounds"]["MAX_AUXILIARY_CHARGE_KG"]) if pd.notna(x) else x)
            elif '掏槽' in col and '装药' in col:
                df[col] = df[col].apply(lambda x: min(max(x, 0.1), self.config["bounds"]["MAX_CUT_CHARGE_KG"]) if pd.notna(x) else x)

        # 👇👇👇 修复 Bug 3: 强制物理体积闭环校准 👇👇👇
        print("      > 正在执行 [终极物理闭环校验]...")
        EXPLOSIVE_DENSITY = self.config["physics"]["EXPLOSIVE_DENSITY_KG_M3"]  
        MAX_CHARGE_COEF = self.config["physics"]["MAX_CHARGE_COEF"]   
        
        for idx, row in df.iterrows():
            # 获取推算体积所需的核心参数
            D = df.at[idx, '井筒荒径_m'] if '井筒荒径_m' in df.columns else np.nan
            advance = df.at[idx, '单循环进尺_m'] if '单循环进尺_m' in df.columns else np.nan
            q = df.at[idx, '单位炸药消耗量_kg/m3'] if '单位炸药消耗量_kg/m3' in df.columns else np.nan
            Q = df.at[idx, '总装药量_kg'] if '总装药量_kg' in df.columns else np.nan
            
            # --- 闭环 A：进尺与孔深的绝对物理挂钩 ---
            perim_depth = df.at[idx, '周边眼孔深_m'] if '周边眼孔深_m' in df.columns else np.nan
            if pd.notna(advance) and pd.notna(perim_depth):
                if advance >= perim_depth:
                    df.at[idx, '单循环进尺_m'] = round(perim_depth * 0.90, 2)
                    advance = df.at[idx, '单循环进尺_m'] # 更新 advance 用于后续计算
            
            # --- 闭环 B：总装药量强行服从理论体积模型 ---
            if pd.notna(D) and pd.notna(advance):
                # 理论体积 S * L
                volume = 3.14159 * (D / 2)**2 * advance
                
                # 若已有单耗 q，强制覆盖总装药量 Q (击碎 XGBoost 猜出的离谱总药量)
                if pd.notna(q):
                    theoretical_Q = volume * q
                    # 容差检查：如果原始 Q 和理论 Q 偏差超过 15%，强制修正为理论 Q
                    if pd.isna(Q) or abs(Q - theoretical_Q) / theoretical_Q > 0.15:
                        if '总装药量_kg' in df.columns:
                            df.at[idx, '总装药量_kg'] = round(theoretical_Q, 2)
            
            # --- 闭环 C：体积密度锁 (压制周边单孔药量) ---
            hole_dia_mm = df.at[idx, '炮孔直径_mm'] if '炮孔直径_mm' in df.columns else np.nan
            if pd.notna(hole_dia_mm) and hole_dia_mm > 0 and pd.notna(perim_depth) and perim_depth > 0:
                r_m = (hole_dia_mm / 2) / 1000.0
                hole_area = 3.14159 * (r_m ** 2)
                max_perim_charge = hole_area * perim_depth * EXPLOSIVE_DENSITY * MAX_CHARGE_COEF
                
                if '周边眼单孔装药量_kg' in df.columns:
                    current_perim_charge = df.at[idx, '周边眼单孔装药量_kg']
                    if pd.notna(current_perim_charge) and current_perim_charge > max_perim_charge:
                        df.at[idx, '周边眼单孔装药量_kg'] = round(max_perim_charge, 2)

        print("      > 正在执行 [拓扑锁] 修正语义化零值...")
        for idx, row in df.iterrows():
            cut1_holes = df.at[idx, '一阶掏槽眼数'] if '一阶掏槽眼数' in df.columns else np.nan
            cut2_holes = df.at[idx, '二阶/三阶掏槽眼数'] if '二阶/三阶掏槽眼数' in df.columns else np.nan
            
            if pd.notna(cut1_holes) and cut1_holes > 0:
                if pd.isna(cut2_holes) or cut2_holes <= 0:
                    if '二阶/三阶掏槽眼数' in df.columns: df.at[idx, '二阶/三阶掏槽眼数'] = 0.0
                    if '二阶/三阶掏槽眼深_mm' in df.columns: df.at[idx, '二阶/三阶掏槽眼深_mm'] = 0.0
                    if '二阶/三阶掏槽单孔装药_kg' in df.columns: df.at[idx, '二阶/三阶掏槽单孔装药_kg'] = 0.0
        
        print(f"      ✅ 已成功运用 XGBoost ({mode}模式) 重构了 {len(valid_numeric_cols)} 维特征矩阵。")
        return df
    
    def _fill_by_llm(self, df):
        """【第三重】大模型工业级逻辑重构 (CoT 思维链 + Few-Shot 小样本增强版)"""
        print("  > 正在执行 [第三重: 大模型思维链 (CoT) 深度逻辑重构]...")
        for index, row in df.iterrows():
            null_count = row.isna().sum()
            # 只有缺失值较多的行才需要大模型出手兜底
            if null_count >= 5:
                row_dict = row.replace({np.nan: None}).to_dict()
                
                # 👇👇👇 极致优化的 CoT + Few-Shot 工业级 Prompt 👇👇👇
                prompt = f"""[System Directive: High-Precision Engineering Data Reconstruction]
Role: Senior Industrial Mining Engineering & Blasting Expert.
Task: Based on limited field survey data, perform rigorous logical deduction for incomplete shaft blasting parameters.

[Few-Shot Examples (Learn from these expert patterns)]
Example 1 (Hard Rock, Large Shaft):
Input: {{"井筒荒径_m": 8.0, "岩性": "坚硬细砂岩", "f值_普氏硬度": 10}}
Output: {{
  "reasoning_steps": "荒径8.0m的大断面立井，岩石为坚硬细砂岩(f=10)。因岩石坚硬，周边眼间距应较密，取500mm。大断面通常单循环进尺在3.5m左右，对应周边眼孔深约4.0m。坚硬岩石必须采用二阶甚至三阶直眼掏槽以保证爆破块度。",
  "单循环进尺_m": 3.5,
  "周边眼孔深_m": 4.0,
  "周边眼孔距_mm": 500,
  "一阶掏槽眼深_mm": 4500,
  "二阶/三阶掏槽眼数": 8
}}

Example 2 (Soft Rock, Medium Shaft):
Input: {{"井筒荒径_m": 5.5, "岩性": "泥岩", "f值_普氏硬度": 4}}
Output: {{
  "reasoning_steps": "荒径5.5m中等断面，岩性为泥岩偏软(f=4)。岩石易碎，周边眼间距可适当放宽至600mm。软岩单循环进尺一般在2.0-2.5m，孔深取2.5m。由于岩石较软，一阶掏槽即可，不需要二阶掏槽孔。",
  "单循环进尺_m": 2.0,
  "周边眼孔深_m": 2.5,
  "周边眼孔距_mm": 600,
  "一阶掏槽眼深_mm": 2800,
  "二阶/三阶掏槽眼数": 0
}}

[Hard Red-Line Constraints]
1. Regulatory Baseline: Peripheral hole depth MUST be >= 0.6m.
2. Geometric Topology: Hole spacing and ring diameter must match hole numbers.
3. CoT Requirement (CRITICAL): You MUST output a `reasoning_steps` field FIRST, detailing your step-by-step mining engineering logic, BEFORE outputting the numerical parameters.
4. Zero Tolerance for Hallucination: If a parameter cannot be logically deduced, keep its value as null.

[Incomplete Data Matrix]
{json.dumps(row_dict, ensure_ascii=False)}

[Output Specification]
Return ONLY a valid JSON object containing `reasoning_steps` and the filled numeric parameters. NO Markdown.
"""
                # 👆👆👆 ================================================= 👆👆👆

                try:
                    response = self.client.chat.completions.create(
                        model=TEXT_MODEL, 
                        messages=[{"role": "user", "content": prompt}],
                        temperature=0.0, # 依然保持绝对零度，封死随机性幻觉
                        response_format={"type": "json_object"}
                    )
                    
                    raw_content = response.choices[0].message.content.strip()
                    if raw_content.startswith("```"):
                        raw_content = raw_content.split('\n', 1)[-1].rsplit('\n', 1)[0]
                        
                    llm_result = json.loads(raw_content)
                    
                    # 💡 帅气加分项：在控制台打印出大模型的“专家诊断报告”
                    if "reasoning_steps" in llm_result:
                        print(f"      [专家诊断 {index+2}行] 🧠: {llm_result['reasoning_steps']}")
                    
                    # 将大模型算出的数字写回表格（跳过 reasoning_steps 文本）
                    for k, v in llm_result.items():
                        if k == "reasoning_steps": 
                            continue # 这是解题过程，不写入最终的数字矩阵
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
        
        # 👇👇👇 终极防线：在所有运算开始前，把能转数字的全转数字 👇👇👇
        print("  > 正在执行全局数据类型强转与脏字符清洗...")
        target_keywords = ['_m', '_mm', '_kg', '数', '率', '面积', '硬度', 'f值']
        for col in df.columns:
            if any(kw in col for kw in target_keywords):
                # errors='coerce' 极其强大：
                # 如果遇到 "8" 会转成数字 8.0；
                # 如果遇到 "8-10" 或 "见原图" 这种乱码，会强行变成 NaN (缺失值)
                # 这样物理引擎不仅不会崩溃，还会触发兜底逻辑去自动补全它！
                df[col] = pd.to_numeric(df[col], errors='coerce')
        # 👆👆👆 ==========================================

        # 文献质量筛查
        print("  > 正在执行文献质量筛查 (清理过度残缺样本)...")
        initial_len = len(df)
        core_cols = ['井筒荒径_m', '炮孔直径_mm', '单循环进尺_m', '周边眼孔深_m', '一阶掏槽眼深_mm']
        df = df.dropna(subset=[c for c in core_cols if c in df.columns], thresh=2)
        print(f"    - 斩杀严重残缺文献: {initial_len - len(df)} 篇，保留优质火种: {len(df)} 篇")
        
        # 三重引擎依次点火
        df = self._fill_by_physics_with_bounds(df)
        df = self._fill_by_advanced_ml(df, mode=mode) 
        df = self._fill_by_llm(df)
        
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
#     API_KEY = "：sk-5269491b0b5747a49491267ead088065"  # 记得改这里！
    
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
    from config import TEXT_API_KEY
    API_KEY = TEXT_API_KEY
    
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
        final_file = imputer.process_excel(input_file, mode="train")
        
        print("=====================================")
        print(f"✨ 新数据独立修复结束！请前往查看: {final_file}")