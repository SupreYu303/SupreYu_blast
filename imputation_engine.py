# =====================================================================
# 📄 文件说明：grandMining 五重递进式数据修复引擎 (imputation_engine.py)
# =====================================================================
# 【功能概述】
#   本文件是 grandMining 系统的核心"数据修复引擎"，
#   采用五重递进式架构对提取到的残缺爆破参数进行智能补全：
#   第一重：RBR 硬规则引擎（对接 domain_rules.json 声明式规则）
#   第二重：物理推导 + 岩石力学专家字典（公式推导 + 经验值匹配）
#   第三重：LLM CoT 思维链深度逻辑重构（大模型 Few-Shot 推演）
#   第四重：XGBoost MICE 多重插补（机器学习梯度提升）
#   第五重：终极物理闭环校验（几何公式 + 拓扑锁 + 体积密度锁）
#
# 【核心特性】
#   1. 声明式规则引擎：所有物理规则和安规边界均来自 domain_rules.json，可在线编辑
#   2. 岩石力学专家字典：内置 8 种常见岩石的基准单耗和 R 系数
#   3. LLM CoT 推演：对重度残缺行使用大模型思维链进行工程逻辑重构
#   4. 增量学习模式：支持 train（训练新模型）和 predict（使用已有模型）双模式
#   5. 全链路溯源：每个数值均标注 📄原始文献 / 🤖AI推导 溯源标签
#
# 【运行方式】
#   python imputation_engine.py                  # 独立运行（修改底部配置后运行）
#   # 或在其他模块中调用：
#   from imputation_engine import BlastingDataImputer
#   imputer = BlastingDataImputer(api_key="sk-xxx")
#   imputer.process_excel("outputs/xxx.xlsx", mode="train")
#
# 【适用场景】
#   1. 配合 extractor_module 自动调用（提取完成后自动修复）
#   2. 通过 flet_app.py GUI 界面调用（独立修复页面）
#   3. 直接独立运行（修改底部的 input_file 后运行）
#
# 【前置条件】
#   1. 已配置 config.yaml 中的 API 密钥
#   2. 存在 domain_rules.json 领域知识配置文件
#   3. 对于 predict 模式，需要先通过 train 模式训练过模型
#
# 【输出产物】
#   *_Imputed_Bounded.xlsx — 修复后特征库（带溯源标签）
#
# 【依赖模块】
#   - pandas：数据处理与 Excel 读写
#   - numpy：数值计算
#   - sklearn (IterativeImputer)：多重插补框架
#   - xgboost (XGBRegressor)：梯度提升回归器（MICE 估计器）
#   - openai：大模型 API 调用客户端（用于 LLM CoT 推演）
#   - joblib：ML 模型序列化存储（增量学习模型持久化）
#   - config：统一配置加载器
# =====================================================================

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
import joblib  # 用于保存和加载 XGBoost MICE 插补模型（增量学习）
import sys
import io
import shutil
import datetime

# 强制将标准输出和标准错误的编码设置为 UTF-8，彻底解决 Windows 打印中文报错
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# 忽略 sklearn 的 UserWarning（如特征名称警告等），保持控制台输出整洁
warnings.filterwarnings("ignore", category=UserWarning)

# 从统一配置中导入文本大模型的模型名称和 Base URL
from config import TEXT_MODEL, TEXT_BASE_URL


# =====================================================================
# 🏭 核心类：BlastingDataImputer（爆破数据智能补全引擎）
# =====================================================================
class BlastingDataImputer:
    """
    爆破数据智能补全引擎类。
    
    【核心职责】
      对提取到的残缺爆破参数矩阵执行五重递进式修复，
      确保输出的特征矩阵在物理、几何、工程逻辑上完全自洽。
    
    【五重修复架构】
      第一重：RBR 硬规则引擎（_apply_rbr_hard_rules）
      第二重：物理推导 + 岩性专家字典（_fill_by_physics_with_bounds）
      第三重：LLM CoT 深度逻辑重构（_fill_by_llm）
      第四重：XGBoost MICE 多重插补（_fill_by_advanced_ml）
      第五重：后置 RBR 终极兜底校验（_apply_rbr_hard_rules 二次调用）
    """

    # ==================================================================
    # 第一重：RBR 硬规则引擎
    # ==================================================================
    def _apply_rbr_hard_rules(self, df):
        """
        【RBR 规则引擎】对接最新的声明式 domain_rules.json，
        执行级别：critical（报错/重置）、warning（修正）、fatal（剔除）。
        
        【说明】RBR（Rule-Based Reasoning）基于规则的推理引擎，
        从 domain_rules.json 中加载动态阈值配置和关系规则，
        逐行逐字段检查数据的物理合理性和工程合规性。
        
        【处理的规则类型】
          - 异常进尺排查（防盲炮/修边爆破数据污染）
          - 荒径 ≤ 净径 倒挂修正
          - 掏槽眼深 ≤ 辅助眼深 矫正
          - 炮孔利用率量纲自动换算（小数 → 百分比）
          - f 值异常检测（低于最小阈值则置空重推）
          - 岩性/炸药类型缺失 → 致命级剔除
        
        【参数】
          df (pd.DataFrame)：待检查的爆破参数 DataFrame
          
        【返回值】
          pd.DataFrame：经过规则清洗后的 DataFrame
        """
        print("  > 正在执行 [RBR 规则引擎: 挂载高级域知识约束]...")
        
        # 从外部配置文件加载动态阈值
        bounds = self.config.get("bounds", {})         # 安规边界约束
        rels = self.config.get("relationships", {})     # 参数间关系规则
        
        drop_indices = []  # 存储需要被 fatal 级别剔除的行索引

        for index, row in df.iterrows():

            # =========================================================
            # 规则 0：异常进尺排查（防盲炮/修边爆破数据污染）
            # =========================================================
            # 【说明】如果单循环进尺小于最小安全阈值（默认 1.0m），
            # 说明该数据可能来自盲炮、修边爆破等非正常掘进场景，
            # 属于"毒数据"，强行置空，交由后续物理闭环重新推算
            advance = row.get('单循环进尺_m')
            min_adv = bounds.get("MIN_ADVANCE_M", 1.0)
            
            if pd.notna(advance) and advance < min_adv:
                print(f"      [Warning] 行 {index}: 发现异常进尺 {advance}m (疑似提取错误或非正常掘进)，强行置空，交由管线重推！")
                df.at[index, '单循环进尺_m'] = np.nan
                advance = np.nan

            # =========================================================
            # 规则 1：diameter_inversion_check & geometry_correction
            # =========================================================
            # 【说明】检查荒径与净径的逻辑关系：
            # - 荒径必须 > 净径（荒径 = 净径 + 支护厚度）
            # - 如果荒径 ≤ 净径，说明提取错误，自动交换两个值
            # - 然后用荒径强制推算掘进断面积：S = π × (D/2)²
            D_gross = row.get('井筒荒径_m')
            D_net = row.get('井筒净径_m')
            
            if pd.notna(D_gross) and pd.notna(D_net):
                if D_gross <= D_net:
                    print(f"      [Critical] 行 {index}: 荒径({D_gross}m) <= 净径({D_net}m), 触发倒挂修正。")
                    # 自动交换荒径和净径
                    df.at[index, '井筒荒径_m'], df.at[index, '井筒净径_m'] = D_net, D_gross
                    D_gross = df.at[index, '井筒荒径_m']

            # 强制用荒径推算掘进断面积（物理公式不可违背）
            if pd.notna(D_gross): 
                calculated_area = np.pi * (D_gross / 2)**2
                df.at[index, '掘进断面积_m2'] = round(calculated_area, 2)

            # =========================================================
            # 规则 2：hole_depth_validation（孔深倒挂检测）
            # =========================================================
            # 【说明】掏槽眼深度必须 > 辅助眼/周边眼深度
            # （掏槽眼是最先起爆的中心孔，必须比其他孔更深才能形成自由面）
            # 如果不满足，自动将掏槽眼深度设为最大辅助眼深度 + 安全余量
            cut_depth = row.get('一阶掏槽眼深_mm')
            aux_depths = [
                row.get('内圈辅助眼孔深_mm', 0), 
                row.get('外圈辅助眼孔深_mm', 0), 
                row.get('周边眼孔深_m', 0) * 1000 if pd.notna(row.get('周边眼孔深_m')) else 0
            ]
            max_aux_depth = max([d for d in aux_depths if pd.notna(d)] or [0])
            
            if max_aux_depth > 0:
                if pd.isna(cut_depth) or cut_depth <= max_aux_depth:
                    # 动态读取安全余量配置（单位：米转毫米）
                    extra_mm = rels.get("hole_depth", {}).get("CUT_HOLE_EXTRA_DEPTH_MIN_M", 0.1) * 1000
                    df.at[index, '一阶掏槽眼深_mm'] = max_aux_depth + extra_mm

            # =========================================================
            # 规则 3：hole_count_correction（炮眼数拓扑修正）
            # =========================================================
            # 【说明】总炮眼数 = 掏槽眼数 + 辅助眼数 + 周边眼数
            # 只要核心的三个圈层中至少有两个有数据，就强制覆盖总炮眼数
            hole_sub_cols = ['一阶掏槽眼数', '二阶/三阶掏槽眼数', '内圈辅助眼数', '外圈辅助眼数', '周边眼数']
            sub_vals = [row.get(c, 0) if pd.notna(row.get(c)) else 0 for c in hole_sub_cols]
            total_calculated = sum(sub_vals)
            
            # 统计有多少个圈层有有效数据
            valid_count = sum(1 for c in hole_sub_cols if pd.notna(row.get(c)))
            if valid_count >= 2: 
                df.at[index, '总炮眼数'] = total_calculated

            # =========================================================
            # 规则 4：utilization_rate_scaling & capping（利用率量纲修正）
            # =========================================================
            # 【说明】炮孔利用率有两种常见表示方式：
            # - 小数形式：0.85（表示 85%）
            # - 百分比形式：85（表示 85%）
            # 本规则自动识别并统一为百分比形式，同时封顶在 100% 以内
            util_rate = row.get('炮孔利用率')
            max_util = bounds.get("MAX_UTILIZATION_RATE_PCT", 100.0)
            if pd.notna(util_rate):
                try:
                    util_rate = float(util_rate)
                    if util_rate <= 2.0:  # 放宽到 2.0，防止个别 1.xx 被漏掉
                        # 小数形式，乘以 100 转为百分比
                        df.at[index, '炮孔利用率'] = util_rate * 100
                    elif util_rate > max_util:
                        # 超过最大阈值，强制封顶
                        df.at[index, '炮孔利用率'] = max_util
                except ValueError:
                    pass

            # =========================================================
            # 规则 5：f_value_validation（普氏硬度 f 值验证）
            # =========================================================
            # 【说明】f 值（普氏硬度系数）不能低于最小安全阈值（默认 0.1）
            # 如果低于阈值，说明数据异常，置空交由后续 XGB/LLM 重新推导
            f_val = row.get('f值_普氏硬度')
            min_f = bounds.get("MIN_F_VALUE", 0.1)
            if pd.notna(f_val) and f_val < min_f:
                df.at[index, 'f值_普氏硬度'] = np.nan

            # =========================================================
            # 规则 6：mandatory_field_check（CBR 致命级约束）
            # =========================================================
            # 【说明】对于 CBR（案例推理）系统，没有"岩性"和"炸药类型"的历史数据
            # 属于不可达的死数据，必须硬删除（fatal 级别）
            rock_type = row.get('岩性')
            exp_type = row.get('炸药类型')
            
            if pd.isna(rock_type) or pd.isna(exp_type):
                drop_indices.append(index)

        # 执行 Fatal 级别的剔除操作
        if drop_indices:
            print(f"      [Fatal] 触发 mandatory_field_check，硬删除 {len(drop_indices)} 条确实核心特征的脏数据。")
            df = df.drop(index=drop_indices).reset_index(drop=True)

        return df
    
    # ==================================================================
    # 构造函数（初始化引擎）
    # ==================================================================
    def __init__(self, api_key, base_url=TEXT_BASE_URL, model_dir="models/"):
        """
        初始化 grandMining 智能数据补全引擎（增量学习模式）。
        
        【参数】
          api_key (str): DeepSeek 文本大模型的 API 密钥
          base_url (str): 大模型 API 的 Base URL（默认从 config 读取）
          model_dir (str): ML 模型持久化目录（默认 "models/"）
          
        【初始化内容】
          1. 创建 OpenAI 客户端（设置 45 秒超时 + 3 次自动重试）
          2. 加载 domain_rules.json 领域知识配置
          3. 确保模型目录存在
          4. 设置模型文件路径（scaler、imputer、valid_cols、categorical_mappings）
        """
        print("🔧 初始化 grandMining 智能数据补全引擎 (增量学习模式)...")
        
        # 创建 OpenAI 客户端，用于 LLM CoT 推演
        self.client = OpenAI(
            api_key=api_key, 
            base_url=base_url,
            timeout=45.0,     # 设置 45 秒超时，如果 API 45秒不回话，直接切断
            max_retries=3     # 遇到网络抖动或超时，底层自动重试 3 次
        )
        self.impute_log = []
        
        # 加载外部物理常量与安规红线配置（domain_rules.json）
        config_path = "domain_rules.json"
        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                self.config = json.load(f)
        else:
            raise FileNotFoundError(f"缺失领域知识配置文件: {config_path}")

        # 设置模型持久化目录和文件路径
        self.model_dir = model_dir
        if not os.path.exists(self.model_dir):
            os.makedirs(self.model_dir)
        self.scaler_path = os.path.join(self.model_dir, "blasting_scaler.pkl")        # 标准化器（已废弃）
        self.imputer_path = os.path.join(self.model_dir, "blasting_imputer.pkl")      # XGBoost 插补模型
        self.valid_cols_path = os.path.join(self.model_dir, "valid_numeric_cols.json") # 有效数值列列表

    # ==================================================================
    # 模型备份工具
    # ==================================================================
    def _backup_models(self):
        """
        在训练模式覆盖模型之前，将已有模型文件备份到 models/backup/ 目录。
        防止误操作导致已训练好的模型丢失。
        """
        backup_dir = os.path.join(self.model_dir, "backup")
        if not os.path.exists(backup_dir):
            os.makedirs(backup_dir)
        
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        
        files_to_backup = [
            self.imputer_path,
            self.valid_cols_path,
            os.path.join(self.model_dir, "categorical_mappings.json"),
        ]
        
        backed_up = 0
        for fpath in files_to_backup:
            if os.path.exists(fpath):
                fname = os.path.basename(fpath)
                backup_path = os.path.join(backup_dir, f"{fname}.{timestamp}.bak")
                shutil.copy2(fpath, backup_path)
                backed_up += 1
        
        if backed_up > 0:
            print(f"      [🛡️ 模型保护] 已将 {backed_up} 个模型文件备份至 models/backup/")
        else:
            print(f"      [ℹ️ 模型保护] 未发现已有模型文件，跳过备份（首次训练）")

    # ==================================================================
    # 第二重：物理推导 + 岩性专家字典
    # ==================================================================
    def _fill_by_physics_with_bounds(self, df):
        """
        【第一重推导】全参数物理推导 + 岩石力学专家字典 + 安规边界约束。
        
        【说明】利用采矿工程的物理公式和经验关系，对缺失参数进行推导补全：
          1. 断面积 = π × (D/2)²（强制推导，不可违背）
          2. 各圈层圈径按荒径比例推算（内圈 45%、外圈 70%、周边 90%）
          3. 岩石力学专家字典匹配（8 种常见岩石的基准单耗和 R 系数）
          4. 孔深与进尺的耦合推导（利用 R 系数）
          5. 掏槽孔深度几何推导（必须比进尺深 200~900mm）
          6. 周边眼参数推导（孔距 = 炮孔直径 × 10~15）
          7. 装药量与单耗的物质守恒推导（q = Q / (S × advance)）
          8. 总炮眼数拓扑加和
        
        【参数】
          df (pd.DataFrame)：待修复的爆破参数 DataFrame
          
        【返回值】
          pd.DataFrame：经过物理推导修复后的 DataFrame
        """
        print("  > 正在执行 [第一重: 物理推导与安全边界锁定 (挂载岩性专家字典)]...")
        
        # 从外部配置加载岩石力学经验字典
        rock_expert_dict = self.config.get("rock_expert_dict", {})

        for index, row in df.iterrows():
            # 读取当前行的关键参数
            D = row.get('井筒荒径_m')                    # 井筒荒径（m）
            f_val = row.get('f值_普氏硬度')              # 普氏硬度系数
            rock_str = str(row.get('岩性', ''))          # 岩性描述文本
            advance = row.get('单循环进尺_m')             # 单循环进尺（m）
            cut_depth = row.get('一阶掏槽眼深_mm')        # 一阶掏槽眼深度（mm）
            perim_depth = row.get('周边眼孔深_m')         # 周边眼深度（m）
            hole_dia = row.get('炮孔直径_mm')             # 炮孔直径（mm）
            
            # ---------------------------------------------------------
            # 1. 断面积强制推导 + 圈径按比例推算
            # ---------------------------------------------------------
            if pd.notna(D):
                # 强制用物理公式推算掘进断面积：S = π × (D/2)²
                df.at[index, '掘进断面积_m2'] = round(3.14159 * (D / 2)**2, 2)
                
                # 按标准立井爆破圈径比例推算各圈层圈径
                if '图纸_内圈辅助眼圈径_mm' in df.columns and pd.isna(row.get('图纸_内圈辅助眼圈径_mm')):
                    df.at[index, '图纸_内圈辅助眼圈径_mm'] = round(D * 1000 * 0.45, 1)  # 内圈占荒径 45%
                if '图纸_外圈辅助眼圈径_mm' in df.columns and pd.isna(row.get('图纸_外圈辅助眼圈径_mm')):
                    df.at[index, '图纸_外圈辅助眼圈径_mm'] = round(D * 1000 * 0.70, 1)  # 外圈占荒径 70%
                if '图纸_周边眼圈径_mm' in df.columns and pd.isna(row.get('图纸_周边眼圈径_mm')):
                    df.at[index, '图纸_周边眼圈径_mm'] = round(D * 1000 * 0.90, 1)     # 周边眼圈占荒径 90%
            
            # ---------------------------------------------------------
            # 2. 智能识别岩性与物理锚点注入
            # ---------------------------------------------------------
            # 【说明】尝试从岩性文字中匹配岩石类型，优先使用字典专家经验
            # 例如：文字中包含"花岗"二字 → 匹配为花岗岩 → q_base=2.2, R_coef=0.8
            # 如果没有匹配到，则使用 f 值兜底推算 R 系数
            matched_rock = next((k for k in rock_expert_dict.keys() if k in rock_str), None)
            
            if matched_rock:
                R = rock_expert_dict[matched_rock]['R_coef']       # 炮孔利用率系数
                expert_q = rock_expert_dict[matched_rock]['q_base'] # 基准单位炸药消耗量
            else:
                # 兜底逻辑：根据 f 值粗略估算 R 系数
                R = 0.85 if pd.notna(f_val) and f_val > 8 else 0.90 
                expert_q = None

            # ---------------------------------------------------------
            # 3. 孔深与进尺的耦合推导（利用 R 系数）
            # ---------------------------------------------------------
            # 【公式】advance = perim_depth × R（进尺 = 周边眼深度 × 利用率系数）
            # 如果缺少周边眼深度，用进尺反推
            if pd.isna(perim_depth) and pd.notna(advance):
                inferred_depth = advance / R
                clamped_depth = max(0.6, min(6.0, inferred_depth))  # 安规边界钳制
                df.at[index, '周边眼孔深_m'] = round(clamped_depth, 2)
                perim_depth = clamped_depth
                
            # 如果缺少进尺，用周边眼深度正推
            if pd.isna(advance) and pd.notna(perim_depth):
                df.at[index, '单循环进尺_m'] = round(perim_depth * R, 2)
                advance = df.at[index, '单循环进尺_m']

            # ---------------------------------------------------------
            # 4. 掏槽孔深度几何推导
            # ---------------------------------------------------------
            # 【说明】掏槽眼必须比周边眼深 500~900mm，以确保形成足够的自由面
            if pd.notna(perim_depth):
                if pd.isna(cut_depth):
                    # 缺失时，设为周边眼深度 + 700mm
                    df.at[index, '一阶掏槽眼深_mm'] = (perim_depth + 0.7) * 1000
                else:
                    # 已有时，检查安全余量是否在合理范围内
                    actual_W = cut_depth - (perim_depth * 1000)
                    if actual_W < 500:
                        df.at[index, '一阶掏槽眼深_mm'] = (perim_depth * 1000) + 500
                    elif actual_W > 900:
                        df.at[index, '一阶掏槽眼深_mm'] = (perim_depth * 1000) + 900

            # ---------------------------------------------------------
            # 5. 周边眼参数推导（孔距与抵抗线）
            # ---------------------------------------------------------
            # 【公式】周边眼孔距 ≈ 炮孔直径 × 10~15（经验值）
            perim_spacing = row.get('周边眼孔距_mm')
            res_line = row.get('周边眼最小抵抗线_mm')
            
            if pd.notna(hole_dia):
                if pd.isna(perim_spacing):
                    inferred_spacing = hole_dia * 12.5  # 默认取中间值
                else:
                    inferred_spacing = perim_spacing
                    
                # 安规边界钳制
                min_spacing = hole_dia * 10
                max_spacing = hole_dia * 15
                clamped_spacing = max(min_spacing, min(max_spacing, inferred_spacing))
                df.at[index, '周边眼孔距_mm'] = round(clamped_spacing, 1)
                perim_spacing = clamped_spacing
                
            # 最小抵抗线 ≈ 周边眼孔距（经验关系）
            if pd.isna(res_line) and pd.notna(perim_spacing):
                res_line = perim_spacing 
            
            # 安规下限钳制（最小抵抗线不得低于 300mm）
            if pd.notna(res_line):
                df.at[index, '周边眼最小抵抗线_mm'] = max(300.0, res_line) 

            # ---------------------------------------------------------
            # 6. 物质守恒：装药量与单耗的终极推导
            # ---------------------------------------------------------
            # 【公式】Q = q × S × advance（总装药量 = 单耗 × 断面积 × 进尺）
            q = row.get('单位炸药消耗量_kg/m3')
            Q = row.get('总装药量_kg')
            
            if pd.notna(D) and pd.notna(advance):
                volume = 3.14159 * (D / 2)**2 * advance  # 掘进体积
                if pd.isna(Q) and pd.notna(q):
                    # 有单耗，推导总药量
                    df.at[index, '总装药量_kg'] = round(q * volume, 2)
                elif pd.isna(q) and pd.notna(Q):
                    # 有总药量，推导单耗
                    df.at[index, '单位炸药消耗量_kg/m3'] = round(Q / volume, 2)
                # 字典发威：如果总药量和单耗都没提取到，直接用字典经验基准强行推导！
                elif pd.isna(Q) and pd.isna(q) and expert_q is not None:
                    df.at[index, '单位炸药消耗量_kg/m3'] = expert_q
                    df.at[index, '总装药量_kg'] = round(expert_q * volume, 2)

            # ---------------------------------------------------------
            # 7. 总炮眼数拓扑加和
            # ---------------------------------------------------------
            # 【公式】总炮眼数 = 掏槽眼数 + 辅助眼数 + 周边眼数
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

    # ==================================================================
    # 第四重：XGBoost MICE 多重插补
    # ==================================================================
    def _fill_by_advanced_ml(self, df, mode="train"):
        """
        【第四重】工业级机器学习插补（增量学习 + 类别特征语义觉醒）。
        
        【说明】使用 XGBoost 作为 MICE（Multiple Imputation by Chained Equations）
        的估计器，对剩余的数值空洞进行梯度提升多重插补。
        
        【核心特性】
          1. 类别特征语义编码：将岩性、炸药类型、装药方式等文字列转为数字编码，
             让 XGBoost 知道在爆什么岩石、用什么炸药
          2. 增量学习模式：
             - train：训练新模型并保存到 models/ 目录
             - predict：加载已有模型进行预测修复
          3. 后置常识修正：ML 插补后进行整数卡控、孔深红线、药量分级红线等工程约束
        
        【参数】
          df (pd.DataFrame)：待修复的爆破参数 DataFrame
          mode (str)：运行模式，"train"（训练新模型）或 "predict"（使用已有模型）
          
        【返回值】
          pd.DataFrame：经过 ML 插补修复后的 DataFrame
        """
        print(f"  > 正在执行 [第二重: MICE XGBoost 梯度提升多重插补] (模式: {mode})...")
        
        # =========================================================
        # 类别特征语义编码（Categorical Encoding）
        # =========================================================
        # 【说明】绝不丢弃文字信息！将岩性、炸药类型、装药方式等文字列
        # 转为数字编码（如：花岗岩 → 1，砂岩 → 2），让 XGBoost 能够理解
        # 【升级】新增 geological_conditions（地质条件）作为类别特征参与编码
        text_cols = ['岩性', '炸药类型', '装药方式', 'geological_conditions']
        cat_mapping_path = os.path.join(self.model_dir, "categorical_mappings.json")
        mapping_dicts = {}
        
        if mode == "train":
            # 训练模式：从当前数据中学习类别映射
            for col in text_cols:
                if col in df.columns:
                    unique_vals = df[col].dropna().astype(str).unique()
                    mapping_dicts[col] = {val: i + 1 for i, val in enumerate(unique_vals)}
            # 保存映射字典到 models/ 目录（增量学习：下次可直接加载）
            with open(cat_mapping_path, "w", encoding="utf-8") as f:
                json.dump(mapping_dicts, f, ensure_ascii=False)
        elif mode == "predict":
            # 预测模式：加载已有的类别映射
            if os.path.exists(cat_mapping_path):
                with open(cat_mapping_path, "r", encoding="utf-8") as f:
                    mapping_dicts = json.load(f)

        # 挂载编码列：原列保留给最终输出，新建 `_特征编码` 列喂给算法
        encoded_cols = []
        for col, mapping in mapping_dicts.items():
            if col in df.columns:
                new_col = f"{col}_特征编码"
                df[new_col] = df[col].apply(lambda x: mapping.get(str(x), 0) if pd.notna(x) else np.nan)
                encoded_cols.append(new_col)

        # 强制数值类型清洗（防止脏数据导致算法崩溃）
        # 【升级】新增 '圈数' 关键词，确保 布孔圈数 字段参与数值插补
        target_keywords = ['_m', '_mm', '_kg', '数', '率', '面积', '硬度', '特征编码', '圈数']
        for col in df.columns:
            if any(kw in col for kw in target_keywords):
                df[col] = pd.to_numeric(df[col], errors='coerce')

        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        if not numeric_cols: 
            return df
        
        # 样本量检查：少于 3 行时跳过 ML 插补（样本太少无法训练）
        if len(df) < 3 and mode == "train":
            print("      [!] 样本量过少，跳过 XGBoost 插补。")
            return df

        if mode == "train":
            # =========================================================
            # 训练模式：拟合新的 XGBoost MICE 插补器
            # =========================================================
            # 先备份已有模型，防止误覆盖
            self._backup_models()
            
            # 只有真实数据率 >= 25% 的列才参与插补（太稀疏的列无法训练）
            valid_numeric_cols = [col for col in numeric_cols if df[col].notna().mean() >= 0.25]
            if not valid_numeric_cols: 
                return df
            
            # 保存有效列列表到 models/ 目录
            with open(self.valid_cols_path, "w", encoding="utf-8") as f:
                json.dump(valid_numeric_cols, f, ensure_ascii=False)

            # 创建 XGBoost 回归器作为 MICE 的估计器
            xgb_estimator = XGBRegressor(
                n_estimators=150,       # 决策树数量
                max_depth=5,            # 最大树深度
                learning_rate=0.03,     # 学习率
                subsample=0.75,         # 行采样比例
                colsample_bytree=0.8,   # 列采样比例
                random_state=42,        # 随机种子（确保可复现）
                n_jobs=-1               # 使用所有 CPU 核心
            )
            
            # 创建 MICE 多重插补器
            imputer = IterativeImputer(
                estimator=xgb_estimator,  # 使用 XGBoost 作为估计器
                max_iter=20,              # 最大迭代次数
                random_state=42,          # 随机种子
                min_value=0               # 最小值约束（爆破参数不能为负）
            )
            
            # 拟合并执行插补
            imputed_data = imputer.fit_transform(df[valid_numeric_cols])
            # 保存训练好的插补器到 models/ 目录（增量学习）
            joblib.dump(imputer, self.imputer_path)
            
            # 将插补结果写回 DataFrame
            df[valid_numeric_cols] = np.round(imputed_data, 2)

        elif mode == "predict":
            # =========================================================
            # 预测模式：加载已有模型进行预测
            # =========================================================
            if not (os.path.exists(self.imputer_path) and os.path.exists(self.valid_cols_path)):
                print("      [!] 找不到预训练模型，请先跑 'train' 模式。")
                return df
                
            # 加载有效列列表
            with open(self.valid_cols_path, "r", encoding="utf-8") as f:
                valid_numeric_cols = json.load(f)
                
            # 加载预训练的插补器
            imputer = joblib.load(self.imputer_path)
            
            # 补齐缺失的列（新数据可能缺少某些列）
            missing_cols = set(valid_numeric_cols) - set(df.columns)
            for col in missing_cols: 
                df[col] = np.nan
                
            # 使用预训练模型执行插补（transform，不重新 fit）
            imputed_data = imputer.transform(df[valid_numeric_cols])   
            df[valid_numeric_cols] = np.round(imputed_data, 2)   
        
        else:
            raise ValueError("Unknown mode")

        # 清理掉临时的编码列，保持表格干净
        for col in encoded_cols:
            if col in df.columns:
                df.drop(columns=[col], inplace=True)

        # =========================================================
        # ML 后置常识修正层与拓扑锁（终极工程绞杀）
        # =========================================================
        # 【说明】ML 模型可能产生违反工程常识的预测值，
        # 此处对所有 ML 插补的结果进行安规红线钳制
        print("      > 正在执行 ML 后置常识修正 (实施最严苛工程绞杀)...")
        for col in valid_numeric_cols:
            if col not in df.columns: 
                continue
            
            # 修正 1：强制整数卡控（炮眼数、f值、硬度等必须为整数）
            if '数' in col or 'f值' in col or '硬度' in col:
                df[col] = df[col].apply(lambda x: np.round(x) if pd.notna(x) else x)
            
            # 修正 2：孔深红线钳制
            if '孔深' in col or '眼深' in col:
                if col.endswith('_mm'):
                    df[col] = df[col].apply(lambda x: min(max(x, self.config["bounds"]["MIN_HOLE_DEPTH_M"]*1000), self.config["bounds"]["MAX_HOLE_DEPTH_M"]*1000) if pd.notna(x) else x)
                elif col.endswith('_m'):
                    df[col] = df[col].apply(lambda x: min(max(x, self.config["bounds"]["MIN_HOLE_DEPTH_M"]), self.config["bounds"]["MAX_HOLE_DEPTH_M"]) if pd.notna(x) else x)
            
            # 修正 3：周边眼孔距红线
            if '周边眼孔距' in col:
                df[col] = df[col].apply(lambda x: min(max(x, 300.0), self.config["bounds"]["MAX_PERIMETER_SPACING_MM"]) if pd.notna(x) else x)
            # 最小抵抗线红线
            if '抵抗线' in col:
                df[col] = df[col].apply(lambda x: max(x, self.config["bounds"]["MIN_RESISTANCE_LINE_MM"]) if pd.notna(x) else x)

            # 修正 4：进尺极值防倒挂
            if '进尺' in col:
                df[col] = df[col].apply(lambda x: min(x, self.config["bounds"]["MAX_ADVANCE_M"]) if pd.notna(x) else x)
                
            # 修正 5：分级药量红线
            if '周边眼单孔装药' in col:
                df[col] = df[col].apply(lambda x: min(max(x, 0.1), self.config["bounds"]["MAX_PERIMETER_CHARGE_KG"]) if pd.notna(x) else x)
            elif '辅助眼' in col and '装药' in col:
                df[col] = df[col].apply(lambda x: min(max(x, 0.1), self.config["bounds"]["MAX_AUXILIARY_CHARGE_KG"]) if pd.notna(x) else x)
            elif '掏槽' in col and '装药' in col:
                df[col] = df[col].apply(lambda x: min(max(x, 0.1), self.config["bounds"]["MAX_CUT_CHARGE_KG"]) if pd.notna(x) else x)

        # =========================================================
        # 终极物理与几何闭环校验
        # =========================================================
        print("      > 正在执行 [终极物理与几何闭环校验]...")
        EXPLOSIVE_DENSITY = self.config["physics"]["EXPLOSIVE_DENSITY_KG_M3"]  # 炸药密度（kg/m³）
        MAX_CHARGE_COEF = self.config["physics"]["MAX_CHARGE_COEF"]            # 最大装药系数
        
        for idx, row in df.iterrows():
            D = df.at[idx, '井筒荒径_m'] if '井筒荒径_m' in df.columns else np.nan
            advance = df.at[idx, '单循环进尺_m'] if '单循环进尺_m' in df.columns else np.nan
            q = df.at[idx, '单位炸药消耗量_kg/m3'] if '单位炸药消耗量_kg/m3' in df.columns else np.nan
            Q = df.at[idx, '总装药量_kg'] if '总装药量_kg' in df.columns else np.nan
            
            # 修复 2：几何公式绝对服从（强行覆盖 ML 瞎猜的断面积）
            if pd.notna(D) and '掘进断面积_m2' in df.columns:
                df.at[idx, '掘进断面积_m2'] = round(3.14159 * (D / 2)**2, 2)

            # 修复 3：掏槽超深卡控（爆破底线：掏槽必须比进尺深至少 200mm）
            if pd.notna(advance) and '一阶掏槽眼深_mm' in df.columns:
                min_cut_mm = (advance + 0.2) * 1000 
                current_cut = df.at[idx, '一阶掏槽眼深_mm']
                if pd.notna(current_cut) and current_cut < min_cut_mm:
                    df.at[idx, '一阶掏槽眼深_mm'] = np.round(min_cut_mm, -1)  # 拉长并取整到十位

            # 闭环 A：进尺与孔深的绝对物理挂钩
            perim_depth = df.at[idx, '周边眼孔深_m'] if '周边眼孔深_m' in df.columns else np.nan
            if pd.notna(advance) and pd.notna(perim_depth):
                if advance >= perim_depth:
                    # 进尺不能超过周边眼深度，否则会导致爆破失控
                    df.at[idx, '单循环进尺_m'] = round(perim_depth * 0.90, 2)
                    advance = df.at[idx, '单循环进尺_m'] 
            
            # 闭环 B：总装药量与单耗的绝对数学锁定
            if pd.notna(D) and pd.notna(advance):
                S = df.at[idx, '掘进断面积_m2'] if pd.notna(df.at[idx, '掘进断面积_m2']) else 3.14159 * (D / 2)**2
                volume = S * advance
                
                if pd.notna(Q) and volume > 0:
                    # 无论 ML 预测了什么 q，只要有总药量和体积，q 必须反算得出！
                    df.at[idx, '单位炸药消耗量_kg/m3'] = round(Q / volume, 2)
                elif pd.notna(q) and pd.isna(Q):
                    # 如果只有单耗，推导总药量
                    df.at[idx, '总装药量_kg'] = round(q * volume, 2)
            
            # 闭环 C：体积密度锁（防止"核弹级"装药量幻觉）
            # 【公式】单孔最大装药量 = 炮孔截面积 × 孔深 × 炸药密度 × 装药系数
            hole_dia_mm = df.at[idx, '炮孔直径_mm'] if '炮孔直径_mm' in df.columns else np.nan
            if pd.notna(hole_dia_mm) and hole_dia_mm > 0 and pd.notna(perim_depth) and perim_depth > 0:
                r_m = (hole_dia_mm / 2) / 1000.0
                hole_area = 3.14159 * (r_m ** 2)
                max_perim_charge = hole_area * perim_depth * EXPLOSIVE_DENSITY * MAX_CHARGE_COEF
                if '周边眼单孔装药量_kg' in df.columns:
                    current_perim_charge = df.at[idx, '周边眼单孔装药量_kg']
                    if pd.notna(current_perim_charge) and current_perim_charge > max_perim_charge:
                        df.at[idx, '周边眼单孔装药量_kg'] = round(max_perim_charge, 2)

            # 修复 4：拓扑汇总锁（用局部眼数之和，强行覆盖总眼数）
            hole_sub_cols = ['一阶掏槽眼数', '二阶/三阶掏槽眼数', '内圈辅助眼数', '外圈辅助眼数', '周边眼数']
            valid_sub_cols = [c for c in hole_sub_cols if c in df.columns]
            if valid_sub_cols and '总炮眼数' in df.columns:
                sub_vals = df.loc[idx, valid_sub_cols]
                # 只要算出了 3 个以上圈层的眼数，总眼数就必须彻底服从加和逻辑
                if sub_vals.notna().sum() >= 3: 
                    df.at[idx, '总炮眼数'] = sub_vals.fillna(0).sum()
                    
        # 拓扑锁：修正语义化零值（如果只有一阶掏槽，则二阶掏槽相关字段设为 0）
        print("      > 正在执行 [拓扑锁] 修正语义化零值...")
        for idx, row in df.iterrows():
            cut1_holes = df.at[idx, '一阶掏槽眼数'] if '一阶掏槽眼数' in df.columns else np.nan
            cut2_holes = df.at[idx, '二阶/三阶掏槽眼数'] if '二阶/三阶掏槽眼数' in df.columns else np.nan
            
            if pd.notna(cut1_holes) and cut1_holes > 0:
                if pd.isna(cut2_holes) or cut2_holes <= 0:
                    if '二阶/三阶掏槽眼数' in df.columns: 
                        df.at[idx, '二阶/三阶掏槽眼数'] = 0.0
                    if '二阶/三阶掏槽眼深_mm' in df.columns: 
                        df.at[idx, '二阶/三阶掏槽眼深_mm'] = 0.0
                    if '二阶/三阶掏槽单孔装药_kg' in df.columns: 
                        df.at[idx, '二阶/三阶掏槽单孔装药_kg'] = 0.0
        
        print(f"      ✅ 已成功运用 XGBoost ({mode}模式) 重构了 {len(valid_numeric_cols)} 维特征矩阵。")
        return df
    
    # ==================================================================
    # 第三重：LLM CoT 深度逻辑重构
    # ==================================================================
    def _fill_by_llm(self, df):
        """
        【第三重】大模型工业级逻辑重构（CoT 思维链 + Few-Shot 小样本增强版）。
        
        【说明】对缺失值较多（>= 5 个）的重度残缺行，使用 DeepSeek 大模型
        进行 Chain-of-Thought（思维链）推理，从有限的已知参数出发，
        结合采矿工程专业知识进行逻辑推演，补全缺失参数。
        
        【核心特性】
          1. Few-Shot 增强：提供两个专家推演示例（硬岩大断面 + 软岩中等断面）
          2. CoT 思维链：强制要求模型先输出 reasoning_steps（推导过程），再输出数值
          3. 硬红线约束：孔深 >= 0.6m、几何拓扑一致性等
          4. 零幻觉容忍：无法逻辑推导的参数保持 null
        
        【参数】
          df (pd.DataFrame)：待修复的爆破参数 DataFrame
          
        【返回值】
          pd.DataFrame：经过 LLM 推演修复后的 DataFrame
        """
        print("  > 正在执行 [第三重: 大模型思维链 (CoT) 深度逻辑重构]...")
        for index, row in df.iterrows():
            null_count = row.isna().sum()
            # 只有缺失值较多的行才需要大模型出手兜底
            if null_count >= 5:
                row_dict = row.replace({np.nan: None}).to_dict()
                
                # 构造 CoT + Few-Shot 工业级 Prompt
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

                try:
                    # 调用 DeepSeek 文本大模型（温度 0.0，严格禁止幻觉）
                    response = self.client.chat.completions.create(
                        model=TEXT_MODEL, 
                        messages=[{"role": "user", "content": prompt}],
                        temperature=0.0,
                        response_format={"type": "json_object"}
                    )
                    
                    raw_content = response.choices[0].message.content.strip()
                    # 清理可能的 Markdown 代码块标记
                    if raw_content.startswith("```"):
                        raw_content = raw_content.split('\n', 1)[-1].rsplit('\n', 1)[0]
                        
                    llm_result = json.loads(raw_content)
                    
                    # 在控制台打印大模型的"专家诊断报告"
                    if "reasoning_steps" in llm_result:
                        print(f"      [专家诊断 {index+2}行] 🧠: {llm_result['reasoning_steps']}")
                    
                    # 将大模型算出的数字写回表格（跳过 reasoning_steps 文本）
                    for k, v in llm_result.items():
                        if k == "reasoning_steps": 
                            continue  # 这是解题过程，不写入最终的数字矩阵
                        if pd.isna(row.get(k)) and v is not None and str(v).lower() != "null":
                            df.at[index, k] = v
                            
                except Exception as e:
                    # 打印警告，但不 raise，继续处理下一行
                    print(f"      [!] 行 {index} 大模型节点重构失败 (网络超时或API异常): {e}")
                    continue
                    
        return df

    # ==================================================================
    # 流水线主控程序
    # ==================================================================
    def process_excel(self, file_path, output_path=None, mode="train"):
        """
        流水线主控程序：对 Excel 特征矩阵执行五重递进式修复。
        
        【完整处理流程】
          1. 全局数据类型强转与脏字符清洗
          2. 文献质量筛查（清理过度残缺样本）
          3. 生成数据溯源快照（记录原始数据状态）
          4. 执行五重递进式修复：
             第一重：RBR 硬规则引擎
             第二重：物理推导 + 岩性专家字典
             第三重：LLM CoT 深度逻辑重构
             第四重：XGBoost MICE 多重插补
             第五重：后置 RBR 终极兜底校验
          5. 固化 AI 插补溯源标签
          6. 输出修复后特征库
        
        【参数】
          file_path (str)：输入 Excel 文件路径
          output_path (str)：输出文件路径（默认在输入文件名后加 _Imputed_Bounded 后缀）
          mode (str)：运行模式，"train" 或 "predict"
          
        【返回值】
          str：修复后的特征库 Excel 文件路径
        """
        print(f"\n📥 载入特征库: {file_path}")
        df = pd.read_excel(file_path)
        
        # =========================================================
        # 步骤 1：全局数据类型强转与脏字符清洗
        # =========================================================
        # 【说明】在所有运算开始前，把能转数字的全转数字
        # errors='coerce' 极其强大：遇到 "8" 会转成 8.0；
        # 遇到 "8-10" 或 "见原图" 这种乱码，会强行变成 NaN（缺失值）
        print("  > 正在执行全局数据类型强转与脏字符清洗...")
        # 【升级】新增 '圈数' 关键词，确保 布孔圈数 字段参与数值转换
        target_keywords = ['_m', '_mm', '_kg', '数', '率', '面积', '硬度', 'f值', '圈数']
        for col in df.columns:
            if any(kw in col for kw in target_keywords):
                df[col] = pd.to_numeric(df[col], errors='coerce')

        # =========================================================
        # 步骤 2：文献质量筛查（清理过度残缺样本）
        # =========================================================
        # 【说明】如果一篇文献的核心参数列中至少有 2 个有效值才保留
        print("  > 正在执行文献质量筛查 (清理过度残缺样本)...")
        initial_len = len(df)
        core_cols = ['井筒荒径_m', '炮孔直径_mm', '单循环进尺_m', '周边眼孔深_m', '一阶掏槽眼深_mm']
        df = df.dropna(subset=[c for c in core_cols if c in df.columns], thresh=2)
        print(f"    - 斩杀严重残缺文献: {initial_len - len(df)} 篇，保留优质火种: {len(df)} 篇")

        # =========================================================
        # 步骤 3：生成数据溯源快照
        # =========================================================
        # 【说明】记录最初始的状态：True 代表这个格子原本就是空的
        # 后续用于区分哪些值是原始数据，哪些是 AI/算法推导填充的
        print("  > 正在生成数据溯源快照 (记录真实文献依据)...")
        original_null_mask = df.isna().copy()
        
        # =========================================================
        # 步骤 4：执行五重递进式修复（引擎点火顺序重组）
        # =========================================================
        
        # 第一重：前置 RBR 规则拦截（清洗倒挂、量纲错误、致命缺失）
        df = self._apply_rbr_hard_rules(df)
        
        # 第二重：基础物理推导打底（利用干净的几何数据进行数学公式推导）
        df = self._fill_by_physics_with_bounds(df) 
        
        # 第三重：LLM 处理重度残缺行（交由大模型进行 CoT 推演）
        df = self._fill_by_llm(df)                 
        
        # 第四重：XGBoost 收尾（对剩余数值空洞进行梯度提升多重插补）
        df = self._fill_by_advanced_ml(df, mode=mode) 
        
        # 第五重：后置 RBR 终极兜底（防止 XGBoost/LLM 产生新的物理幻觉）
        df = self._apply_rbr_hard_rules(df)

        # =========================================================
        # 步骤 5：固化 AI 插补溯源标签
        # =========================================================
        # 【说明】根据快照对比，为每个数值参数列生成对应的 `_溯源` 标签列
        # - 📄 原始文献数据：该值直接从文献中提取
        # - 🤖 AI/算法推导：该值由 AI 或算法推导填充
        print("  > 正在固化 AI 插补溯源标签...")
        target_keywords = ['_m', '_mm', '_kg', '数', '率', '面积', '硬度', 'f值']
        for col in df.columns:
            if any(kw in col for kw in target_keywords):
                mask_col_name = f"{col}_溯源"
                
                # 终极防弹补丁：如果快照里压根没有这一列（说明是算法中途无中生有推导出来的）
                # 那么它在"原始状态"下 100% 属于"缺失(True)"
                if col in original_null_mask.columns:
                    original_was_null = original_null_mask[col]
                else:
                    original_was_null = pd.Series(True, index=df.index)
                
                # 对比原始快照和当前值，判断是否为 AI 推导
                is_imputed = original_was_null & df[col].notna()
                df[mask_col_name] = is_imputed.map({True: '🤖 AI/算法推导', False: '📄 原始文献数据'})
        
        # 标记数据质量等级
        df['数据质量'] = f'S+级 (物理严控 + XGBoost {mode} 模式修正)' 
        
        # =========================================================
        # 步骤 6：输出修复后的特征库
        # =========================================================
        if not output_path:
            output_path = file_path.replace(".xlsx", "_Imputed_Bounded.xlsx")
            
        df.to_excel(output_path, index=False)
        print(f"🎉 边界约束与补全完成！无死角特征库已保存至: {output_path}")
        return output_path


# =====================================================================
# 🚀 独立运行入口
# =====================================================================
# 【说明】当直接运行本文件时（python imputation_engine.py），
# 使用默认配置对指定的 Excel 文件执行五重递进式修复
if __name__ == "__main__":
    from config import TEXT_API_KEY
    API_KEY = TEXT_API_KEY
    
    # 🔴 关键：这里一定要换成你实际的 Excel 文件名！
    input_file = "outputs/blasting_CBR_Master_438.xlsx" 
    
    print("=====================================")
    print("启动独立数据清洗与修复模块 (挂载老经验库)")
    
    if not os.path.exists(input_file):
        print(f"❌ 报错：找不到文件 '{input_file}'！请确保路径和文件名正确。")
    else:
        imputer = BlastingDataImputer(api_key=API_KEY, model_dir="models/")
        
        # 🔴 关键：指定运行模式（"train" 训练新模型 / "predict" 使用已有模型）
        final_file = imputer.process_excel(input_file, mode="train")
        
        print("=====================================")
        print(f"✨ 新数据独立修复结束！请前往查看: {final_file}")