# =====================================================================
# 📄 文件说明：grandMining 三核混合特征提取模块 (extractor_module.py)
# =====================================================================
# 【功能概述】
#   本文件是 grandMining 系统的核心"特征提取引擎"，
#   采用三核混合架构从 PDF 文献中自动提取 40+ 维爆破参数：
#   - 核 1：PyMuPDF 原生文本层极速提取（0.1s/页）
#   - 核 2：PaddleOCR 视觉兜底扫描（处理乱码/扫描件页面）
#   - 核 3：Qwen-VL 视觉大模型解析炮眼布置平面图
#
# 【核心特性】
#   1. 异步并发模式：利用 asyncio 并发请求大模型，大幅提升处理速度
#   2. 双轨交叉验证：原生文本 + OCR 文本同时提取，裁判机制合并最优结果
#   3. 证据链溯源：每个提取值均附带原文截句证据
#   4. 集成数据修复引擎：提取完成后自动调用五重递进式修复
#
# 【运行方式】
#   python extractor_module.py                    # 独立测试模式
#   # 或在其他模块中调用：
#   from extractor_module import run_extraction_and_imputation
#   run_extraction_and_imputation(deepseek_key="sk-xxx")
#
# 【适用场景】
#   从 PDF 文献中批量提取爆破参数（推荐通过 main_pipelinepdf.py 调用）
#
# 【前置条件】
#   1. 已将 PDF 文件放入 pdfs/ 目录
#   2. 已配置 config.yaml 中的 API 密钥
#
# 【输出产物】
#   outputs/blasting_CBR_dataset_YYYYMMDD_HHMMSS.xlsx              — 原始特征库
#   outputs/blasting_CBR_dataset_YYYYMMDD_HHMMSS_Imputed_Bounded.xlsx — 修复后特征库
#   outputs/*.txt — 每篇文献的文本提取日志
#
# 【依赖模块】
#   - pypdfium2：PDF 高清页面渲染引擎
#   - fitz (PyMuPDF)：PDF 原生文本提取与图片检测
#   - PIL (Pillow)：图像处理与格式转换
#   - pandas：数据处理与 Excel 导出
#   - openai (AsyncOpenAI)：异步大模型 API 调用客户端
#   - paddleocr：PaddleOCR 文字识别引擎
#   - config：统一配置加载器
#   - imputation_engine：数据修复引擎（在 run_extraction_and_imputation 中调用）
# =====================================================================

import pypdfium2 as pdfium
import fitz  # PyMuPDF，用于提取纯文本层和探测图纸
from PIL import Image
import pandas as pd
from openai import AsyncOpenAI  # 异步 OpenAI 客户端，支持并发 API 调用
import json
import os
import datetime
import base64
import re
import uuid
import asyncio
import concurrent.futures
from paddleocr import PaddleOCR

# 从统一配置中导入所有必要的 API 密钥、路径等参数
from config import TEXT_API_KEY, TEXT_BASE_URL, TEXT_MODEL, VISION_API_KEY, VISION_BASE_URL, VISION_MODEL, PDF_DIR, OUTPUT_DIR


# =====================================================================
# ⚙️ 1. 核心引擎与 API 配置区
# =====================================================================

# 创建异步文本大模型 API 客户端（用于参数提取，推荐 DeepSeek Chat）
# 【说明】使用 AsyncOpenAI 而非 OpenAI，支持 asyncio 并发请求，大幅提升处理速度
text_client = AsyncOpenAI(api_key=TEXT_API_KEY, base_url=TEXT_BASE_URL)

# 创建异步视觉大模型 API 客户端（用于图纸解析，推荐通义千问 Qwen-VL）
vision_client = AsyncOpenAI(api_key=VISION_API_KEY, base_url=VISION_BASE_URL)

print("🚀 正在点火：三核混合特征提取系统 (PyMuPDF + PaddleOCR + VLM)...")

# 初始化 PaddleOCR 引擎（用于兜底扫描乱码/扫描件页面）
# 【参数说明】
#   use_textline_orientation=True：启用文本行方向检测
#   lang="ch"：中文语言模型
#   enable_mkldnn=False：关闭 MKLDNN 加速（防崩溃）
#   ocr_version='PP-OCRv4'：使用轻量级 PP-OCRv4 模型
ocr = PaddleOCR(use_textline_orientation=True, lang="ch", enable_mkldnn=False, ocr_version='PP-OCRv4')


# =====================================================================
# 🛡️ 2. 防御与清洗工具箱
# =====================================================================

def robust_parse_json(raw_str):
    """
    暴力撕裂大模型返回的 Markdown 外壳，绝对防范空白 JSON。
    
    【说明】大模型返回的内容可能包含 Markdown 代码块标记（```json...```）、
    多余空白字符、注释等干扰内容。本函数通过查找第一个 '{' 和最后一个 '}'
    来精准提取 JSON 主体部分，确保即使返回格式不规范也能正确解析。
    
    【参数】
      raw_str (str): 大模型返回的原始字符串
      
    【返回值】
      dict：解析后的字典对象，解析失败则返回空字典 {}
    """
    try:
        raw_str = raw_str.strip()
        start_idx = raw_str.find('{')
        end_idx = raw_str.rfind('}')
        if start_idx != -1 and end_idx != -1:
            return json.loads(raw_str[start_idx:end_idx+1])
        return {}
    except Exception:
        return {}


def encode_image_to_base64(image_path):
    """
    将本地图片文件编码为 Base64 字符串，用于发送给视觉大模型 API。
    
    【参数】
      image_path (str): 图片文件的本地路径
      
    【返回值】
      str：Base64 编码的图片字符串（可直接嵌入 data:image/jpeg;base64,... 格式的 URI）
    """
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')


# =====================================================================
# 🔬 2.5 地质条件标准化与布孔圈数推断工具箱
# =====================================================================

# 【地质条件标准标签映射表】
# 将大模型可能输出的各种表述统一映射为标准分类标签
# 用于后续参数优化模型的输入条件标准化
GEOLOGICAL_LABEL_KEYWORDS = {
    "节理发育": ["节理", "裂隙发育", "裂隙密集", "节理密集", "节理较发育", "节理发育",
                  "易片邦", "易片帮", "片邦", "片帮", "节理裂隙", "裂隙较发育"],
    "岩体完整性差": ["岩体破碎", "极破碎", "完整性差", "较破碎", "岩体较破碎",
                      "岩石破碎", "围岩破碎"],
    "岩体较完整": ["较完整", "岩体较完整", "围岩基本处于稳定", "围岩较稳定",
                    "围岩稳定", "岩体基本稳定", "岩石致密"],
    "岩体完整": ["岩体完整", "完整性好", "完整性较好", "岩石坚硬完整",
                  "岩性较硬", "岩性坚硬"],
    "层状岩体": ["层状", "薄层状", "中厚层状", "厚层状", "互层状", "层状结构",
                  "层理发育", "层理面"],
    "断层破碎带": ["断层", "破碎带", "断层泥", "断层发育", "构造破碎",
                    "地质构造复杂"],
    "强风化": ["强风化", "全风化", "风化砂砾岩", "风化严重", "风化带"],
    "中风化": ["中风化", "弱风化"],
    "地下水丰富": ["涌水", "含水层", "地下水丰富", "涌水量大", "渗水",
                    "涌水量", "地下水位", "水文地质"],
    "复杂地质": ["地质条件复杂", "地质构造复杂", "复杂地质", "地质概况",
                  "水文地质条件", "工程地质"],
}


def normalize_geological_conditions(row):
    """
    标准化地质条件字段：将大模型输出的自由文本映射为标准分类标签。
    
    【处理逻辑】
      1. 如果大模型已返回 geologicl_conditions 标签，直接使用
      2. 如果标签为空但描述字段有内容，从描述文本中用关键词匹配推断标签
      3. 如果描述也为空，扫描整行中所有 string 类型字段（特别是岩性），做兜底推断
      4. 最终输出标准化的 geological_conditions（逗号分隔的标准标签）和描述
    
    【参数】
      row (dict)：单行提取结果字典
      
    【返回值】
      dict：更新后的行字典（原地修改 geological_conditions 和 geological_conditions_描述）
    """
    geo_label = row.get("geological_conditions")
    geo_desc = row.get("geological_conditions_描述")
    
    # 如果标签已经是有效值（非 None/空），直接返回
    if geo_label and str(geo_label).lower() not in ["null", "none", ""]:
        return row
    
    # 构造待扫描的文本池：优先用描述字段，其次扫描岩性等文本字段
    scan_text = ""
    if geo_desc and str(geo_desc).lower() not in ["null", "none", ""]:
        scan_text += str(geo_desc) + " "
    # 兜底：扫描岩性、工程地点等 string 字段
    for col_name in ["岩性", "工程地点_或_工作面名称"]:
        val = row.get(col_name)
        if val and str(val).lower() not in ["null", "none", ""]:
            scan_text += str(val) + " "
    
    # 如果扫描文本池为空，无法推断
    if not scan_text.strip():
        return row
    
    # 关键词匹配推断
    matched_labels = []
    for label, keywords in GEOLOGICAL_LABEL_KEYWORDS.items():
        for kw in keywords:
            if kw in scan_text:
                matched_labels.append(label)
                break  # 同一标签只需匹配一次
    
    if matched_labels:
        row["geological_conditions"] = ",".join(matched_labels)
        if not geo_desc or str(geo_desc).lower() in ["null", "none", ""]:
            row["geological_conditions_描述"] = f"从岩性/工程描述中推断: {scan_text.strip()[:100]}"
        print(f"    [地质条件] 自动标注: {row['geological_conditions']}")
    
    return row


def infer_ring_count(row):
    """
    布孔圈数兜底推断：当大模型未直接提取圈数时，从已有圈层参数推断。
    
    【推断逻辑】
      统计各圈层是否有有效数据（非 None/非0），推断总圈数：
      - 掏槽眼圈层：检查"一阶掏槽眼数" > 0 → 至少1圈；检查"二阶/三阶掏槽眼数" > 0 → +1圈
      - 辅助眼圈层：检查"内圈辅助眼数" > 0 → +1圈；检查"外圈辅助眼数" > 0 → +1圈
      - 周边眼圈层：检查"周边眼数" > 0 → +1圈
    
    【参数】
      row (dict)：单行提取结果字典
      
    【返回值】
      dict：更新后的行字典（原地修改 布孔圈数 字段）
    """
    existing_count = row.get("布孔圈数")
    
    # 如果已有有效值（且为 >= 1 的整数），直接返回
    if existing_count is not None:
        try:
            count_int = int(float(existing_count))
            if count_int >= 1:
                row["布孔圈数"] = count_int
                return row
        except (ValueError, TypeError):
            pass
    
    # 从圈层参数推断
    ring_count = 0
    
    # 掏槽眼：一阶掏槽
    cut1 = row.get("一阶掏槽眼数")
    if cut1 is not None:
        try:
            if float(cut1) > 0:
                ring_count += 1
        except (ValueError, TypeError):
            pass
    
    # 掏槽眼：二阶/三阶掏槽
    cut2 = row.get("二阶/三阶掏槽眼数")
    if cut2 is not None:
        try:
            if float(cut2) > 0:
                ring_count += 1
        except (ValueError, TypeError):
            pass
    
    # 辅助眼：内圈
    aux_inner = row.get("内圈辅助眼数")
    if aux_inner is not None:
        try:
            if float(aux_inner) > 0:
                ring_count += 1
        except (ValueError, TypeError):
            pass
    
    # 辅助眼：外圈
    aux_outer = row.get("外圈辅助眼数")
    if aux_outer is not None:
        try:
            if float(aux_outer) > 0:
                ring_count += 1
        except (ValueError, TypeError):
            pass
    
    # 周边眼
    perim = row.get("周边眼数")
    if perim is not None:
        try:
            if float(perim) > 0:
                ring_count += 1
        except (ValueError, TypeError):
            pass
    
    # 只有推断出至少 2 圈时才写入（避免仅凭单个数据点误判）
    if ring_count >= 2:
        row["布孔圈数"] = ring_count
        print(f"    [布孔圈数] 从圈层参数推断: {ring_count} 圈")
    
    return row


def postprocess_extracted_data(final_dataset):
    """
    提取后处理管线：对所有提取结果执行地质条件标准化 + 布孔圈数推断。
    
    【处理步骤】
      1. 遍历每条记录，标准化 geological_conditions 标签
      2. 遍历每条记录，兜底推断布孔圈数
      3. 打印统计摘要
    
    【参数】
      final_dataset (list[dict])：所有文献的提取结果列表
      
    【返回值】
      list[dict]：后处理后的结果列表
    """
    print("\n=====================================")
    print("🔬 正在执行后处理：地质条件标准化 + 布孔圈数推断...")
    
    geo_count = 0
    ring_count = 0
    
    for row in final_dataset:
        # 地质条件标准化
        old_geo = row.get("geological_conditions")
        normalize_geological_conditions(row)
        if row.get("geological_conditions") and row.get("geological_conditions") != old_geo:
            geo_count += 1
        
        # 布孔圈数推断
        old_ring = row.get("布孔圈数")
        infer_ring_count(row)
        if row.get("布孔圈数") and row.get("布孔圈数") != old_ring:
            ring_count += 1
    
    print(f"  ✅ 后处理完成: 地质条件新标注 {geo_count} 条, 布孔圈数新推断 {ring_count} 条")
    return final_dataset


def filter_complex_blasting_cases(df, min_ring_count=6):
    """
    复杂爆破案例筛选：筛选并汇总所有布孔圈数 >= min_ring_count 的案例。
    
    【说明】高圈数（>=6圈）的爆破案例代表更复杂的布孔方案（如大断面立井），
    是参数优化模型的重点研究对象。本函数提供独立的筛选和统计功能。
    
    【参数】
      df (pd.DataFrame)：完整特征库 DataFrame
      min_ring_count (int)：最小圈数阈值，默认为 6
      
    【返回值】
      pd.DataFrame：筛选后的 DataFrame（仅包含 圈数 >= min_ring_count 的行）
      
    【副作用】
      在 outputs/ 目录下保存筛选结果的 Excel 文件
    """
    print(f"\n=====================================")
    print(f"🔍 正在筛选复杂爆破案例 (布孔圈数 >= {min_ring_count})...")
    
    if '布孔圈数' not in df.columns:
        print("  ⚠️ 警告: 数据中没有 '布孔圈数' 列，无法执行筛选。")
        return pd.DataFrame()
    
    # 确保布孔圈数列为数值类型
    df['布孔圈数'] = pd.to_numeric(df['布孔圈数'], errors='coerce')
    
    # 筛选圈数 >= 阈值的行
    complex_df = df[df['布孔圈数'] >= min_ring_count].copy()
    
    total = len(df)
    filtered = len(complex_df)
    print(f"  📊 筛选结果: 共 {total} 条记录中, {filtered} 条为复杂爆破案例 (圈数 >= {min_ring_count})")
    print(f"  📊 占比: {filtered/total*100:.1f}%" if total > 0 else "  📊 占比: 0%")
    
    # 打印圈数分布统计
    if not complex_df.empty:
        ring_dist = complex_df['布孔圈数'].value_counts().sort_index()
        print(f"  📊 复杂案例圈数分布:")
        for ring, cnt in ring_dist.items():
            print(f"      {int(ring)} 圈: {cnt} 条")
    
    # 保存筛选结果
    if not complex_df.empty:
        out_dir = OUTPUT_DIR
        if not os.path.exists(out_dir):
            os.makedirs(out_dir)
        out_file = os.path.join(out_dir, f"complex_blasting_ring{min_ring_count}plus_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx")
        complex_df.to_excel(out_file, index=False)
        print(f"  💾 复杂案例筛选结果已保存: {out_file}")
    
    return complex_df


# =====================================================================
# 🧠 3. AI 识别与交叉验证逻辑
# =====================================================================

async def extract_diagram_params(base64_image):
    """
    【视觉模型】审视炮眼布置平面图，提取空间几何尺寸参数。
    
    【说明】将 Base64 编码的图片发送给 Qwen-VL 视觉大模型，
    要求模型以采矿工程师的视角识别图中的"井筒/巷道炮眼布置平面图"，
    并顺着标注线提取掏槽眼布置形状、各圈层圈径、孔距、最小抵抗线等空间尺寸参数。
    
    【参数】
      base64_image (str): Base64 编码的图片字符串
      
    【返回值】
      dict：提取到的图纸参数字典（10 个维度），没有图纸或提取失败则返回空字典 {}
      
    【提取的参数列表】
      - 图纸_掏槽眼布置形状（如：桶形、角柱形）
      - 图纸_一阶/二阶掏槽圈径_mm
      - 图纸_内圈/外圈辅助眼孔距_mm、圈径_mm
      - 图纸_周边眼孔距_mm、圈径_mm、最小抵抗线_mm
    """
    prompt = """
    你是采矿工程师。检查图中是否有"井筒/巷道炮眼布置平面图"。
    如果没有图纸直接返回：{}
    如果有图纸，请顺着标注线提取参数（没有填 null）：
    {
      "图纸_掏槽眼布置形状": "string(如:桶形,角柱形)",
      "图纸_一阶掏槽圈径_mm": "string或float",
      "图纸_二阶掏槽圈径_mm": "string或float",
      "图纸_内圈辅助眼孔距_mm": "string或float",
      "图纸_内圈辅助眼圈径_mm": "string或float",
      "图纸_外圈辅助眼孔距_mm": "string或float",
      "图纸_外圈辅助眼圈径_mm": "string或float",
      "图纸_周边眼孔距_mm": "string或float",
      "图纸_周边眼圈径_mm": "string或float",
      "图纸_周边眼最小抵抗线_mm": "string或float"
    }
    """
    try:
        # 调用视觉大模型 API（异步），发送图片和提示词
        response = await vision_client.chat.completions.create(
            model=VISION_MODEL,
            messages=[{"role": "user", "content": [
                {"type": "text", "text": prompt},
                # 将图片以 Base64 编码的 data URI 格式嵌入消息
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
            ]}],
            temperature=0.1  # 低温度，确保输出稳定
        )
        return robust_parse_json(response.choices[0].message.content)
    except Exception:
        return {}


async def extract_text_params(text, source_name):
    """
    【文本模型】从杂乱文本中提取 40+ 维核心爆破参数。
    
    【说明】将文本内容发送给 DeepSeek 文本大模型，要求模型：
    1. 按照预定义的 5 大类 40+ 维参数模式提取数据
    2. 对每个成功提取的参数，摘录能证明该数据的"原文半句话"作为证据链
    3. 找不到的参数填 null
    
    【参数】
      text (str): 待解析的文本内容（来自 PyMuPDF 原生提取或 PaddleOCR 识别）
      source_name (str): 文本来源标识（用于日志输出，如 "xxx.pdf-底层文本"）
      
    【返回值】
      dict：展平后的一维参数字典（包含原始参数和 _原文依据 后缀的证据字段）
      
    【提取的参数分类】
      - 基础参数：工程地点、作者单位、井筒荒径/净径、井深、断面面积、岩性、f值
      - 总体爆破：炸药类型、装药方式、炮孔直径、单循环进尺、总炮眼数、总装药量等
      - 掏槽眼参数：总数、一阶/二阶眼数、眼深、单孔装药量
      - 辅助眼参数：总数、内/外圈眼数、孔深、平均单孔装药量
      - 周边眼参数：眼数、孔深、孔距、最小抵抗线、单孔装药量
    """
    # 定义目标参数模式（Schema），告诉大模型需要提取哪些参数及其数据类型
    # 【2024升级】新增"地质条件"和"布孔圈数"两个维度
    target_schema = {
        "基础参数": {
            "工程地点_或_工作面名称": "string/null",
            "作者工作单位": "string/null",
            "井筒荒径_m": "float/null", 
            "井筒净径_m": "float/null", 
            "井深_m": "float/null", 
            "断面面积_m2": "float/null",
            "岩性": "string/null", 
            "f值_普氏硬度": "float/null"
        },
        "地质条件": {
            "geological_conditions": "string/null",
            "geological_conditions_描述": "string/null"
        },
        "总体爆破": {
            "炸药类型": "string/null", 
            "装药方式": "string/null", 
            "炮孔直径_mm": "float/null", 
            "单循环进尺_m": "float/null", 
            "总炮眼数": "int/null", 
            "总装药量_kg": "float/null",
            "炮孔利用率_%": "float/null",
            "单位炸药消耗量_kg/m3": "float/null",
            "布孔圈数": "int/null"
        },
        "掏槽眼参数": {
            "掏槽眼总数": "int/null", 
            "一阶掏槽眼数": "int/null", 
            "一阶掏槽眼深_mm": "float/null", 
            "一阶掏槽单孔装药_kg": "float/null",
            "二阶/三阶掏槽眼数": "int/null",
            "二阶/三阶掏槽眼深_mm": "float/null",
            "二阶/三阶掏槽单孔装药_kg": "float/null"
        },
        "辅助眼参数": {
            "辅助眼总数": "int/null", 
            "内圈辅助眼数": "int/null", 
            "内圈辅助眼孔深_m": "float/null",
            "外圈辅助眼数": "int/null",
            "外圈辅助眼孔深_m": "float/null",
            "辅助眼平均单孔装药_kg": "float/null"
        },
        "周边眼参数": {
            "周边眼数": "int/null", 
            "周边眼孔深_m": "float/null", 
            "周边眼孔距_mm": "float/null", 
            "周边眼最小抵抗线_mm": "float/null",
            "周边眼单孔装药量_kg": "float/null"
        }
    }
    
    # 构造文本大模型的 Prompt（提示词）
    # 【第四维度：证据链溯源指令】
    # 为了保证工程数据的绝对可靠，要求大模型对每个成功提取的参数
    # 摘录能证明该数据的"原文半句话"，作为溯源证据
    prompt = f"""你是资深采矿数据清洗专家。请提取爆破参数，找不到填 null。

【第四维度：证据链溯源指令】
为了保证工程数据的绝对可靠，对于每一个成功提取到的参数，你必须摘录出能证明该数据的"原文半句话"。
请在输出的 JSON 中，为每一个有数据的参数额外新增一个带有 `_原文依据` 后缀的字段。

【新增维度A：地质条件提取指令（CRITICAL）】
请重点扫描文献全文（特别是"工程地质概况"、"地质条件"、"围岩条件"等段落），查找以下岩体结构和地质特征的描述：
1. 岩体节理发育（如：节理发育、节理密集、节理较发育、节理不发育等）
2. 岩体完整性（如：岩体完整、较完整、较破碎、破碎、极破碎等）
3. 层状岩体（如：层状结构、薄层状、中厚层状、厚层状、互层状等）
4. 断层/破碎带（如：断层发育、穿越破碎带、断层泥等）
5. 风化程度（如：强风化、中风化、微风化、未风化等）
6. 地下水情况（如：涌水量大、含水层、干燥等）

一旦发现上述任何关键词或相关语境，必须：
- 将 `geological_conditions` 设为一个分类标签（从以下选项中选一个最匹配的）：
  "节理发育"、"岩体完整性差"、"层状岩体"、"断层破碎带"、"强风化"、"地下水丰富"、"岩体较完整"、"岩体完整"、"复杂地质"
  如果同时存在多个特征，用逗号分隔（如："节理发育,层状岩体"）
- 将 `geological_conditions_描述` 设为从原文摘录的核心描述语句（不超过100字）

示例：
{{
  "geological_conditions": "节理发育,层状岩体",
  "geological_conditions_描述": "井筒穿越的岩体节理较发育，以薄层状灰岩为主，层间结合力差"
}}

【新增维度B：布孔圈数提取指令】
请在文献中查找关于爆破布孔"圈数"的描述，例如：
- "采用X圈布孔"、"分X圈布置"、"炮孔布置共X圈"、"掏槽圈+辅助圈X层+周边圈"
- 从炮眼布置平面图或表格中识别圈数
- 从辅助眼的圈层描述推断（如"内圈辅助眼"+"外圈辅助眼"=辅助眼2圈+掏槽1圈+周边1圈=至少4圈）

将圈数值设为整数（int），如无法确定填 null。

示例格式：
{{
  "单循环进尺_m": 2.5,
  "单循环进尺_m_原文依据": "本月单循环进尺为2.5m",
  "geological_conditions": "节理发育",
  "geological_conditions_描述": "岩体节理发育，完整性较差",
  "geological_conditions_原文依据": "该段岩体节理较发育，完整性较差",
  "布孔圈数": 6,
  "布孔圈数_原文依据": "炮孔布置共分6圈，由内向外依次为..."
}}

目标核心参数清单：{json.dumps(target_schema, ensure_ascii=False)}

待解析文本内容：
{text}"""
    
    try:
        # 调用文本大模型 API（异步），温度设为 0.0 确保输出稳定
        response = await text_client.chat.completions.create(
            model=TEXT_MODEL, messages=[{"role": "user", "content": prompt}], temperature=0.0
        )
        
        # 将大模型返回的嵌套 JSON 展平为一维字典
        # 例如：{"基础参数": {"井筒荒径_m": 6.0}, "总体爆破": {"炮孔直径_mm": 42}}
        # 展平后：{"井筒荒径_m": 6.0, "炮孔直径_mm": 42}
        raw_dict = robust_parse_json(response.choices[0].message.content)
        flat_dict = {}
        for k, v in raw_dict.items():
            if isinstance(v, dict): 
                flat_dict.update(v)
            else: 
                flat_dict[k] = v
        return flat_dict
    except Exception as e:
        print(f"      [!] {source_name} 提取失败: {e}")
        return {}


def cross_validate_and_merge(pdf_dict, ocr_dict):
    """
    【工业级裁判】双轨数据交叉验证，输出最终结果和警告日志。
    
    【说明】同时从原生文本层和 OCR 文本层提取的参数进行交叉验证：
    - 如果两个来源的值完全一致 → 最可靠，直接采用
    - 如果两个来源的值不一致 → 优先采用底层文本值，并记录冲突日志
    - 如果只有一个来源有值 → 采用该值
    - 如果两个来源都没有值 → 标记为 None（缺失）
    
    【参数】
      pdf_dict (dict)：从原生文本层提取的参数字典
      ocr_dict (dict)：从 OCR 文本层提取的参数字典
      
    【返回值】
      dict：合并后的参数字典，包含一个"交叉验证警报"字段记录冲突信息
    """
    merged_data = {}
    conflict_log = []
    
    # 获取两个来源中所有参数名的并集
    all_keys = set(pdf_dict.keys()).union(set(ocr_dict.keys()))
    
    for key in all_keys:
        val_pdf = pdf_dict.get(key)
        val_ocr = ocr_dict.get(key)
        
        # 判断两个来源的值是否为空/无效
        is_pdf_empty = val_pdf is None or str(val_pdf).lower() in ["null", "none", "", "未提及"]
        is_ocr_empty = val_ocr is None or str(val_ocr).lower() in ["null", "none", "", "未提及"]
        
        if not is_pdf_empty and not is_ocr_empty:
            # 两个来源都有值
            if str(val_pdf).strip() == str(val_ocr).strip():
                # 完全一致，最可靠
                merged_data[key] = val_pdf
            else:
                # 冲突：优先信底层文本，并记录冲突日志
                merged_data[key] = val_pdf
                conflict_log.append(f"[{key}] 底层:{val_pdf} 视觉:{val_ocr}")
        elif not is_pdf_empty: 
            # 只有底层文本有值
            merged_data[key] = val_pdf
        elif not is_ocr_empty: 
            # 只有 OCR 有值
            merged_data[key] = val_ocr
        else: 
            # 两个来源都没有值
            merged_data[key] = None
            
    # 记录交叉验证结果
    merged_data["交叉验证警报"] = " | ".join(conflict_log) if conflict_log else "完美一致"
    return merged_data


# =====================================================================
# 🏭 4. 主干流水线 (双轨扫描提取)
# =====================================================================

def process_single_paper(pdf_path):
    """
    处理单篇 PDF 文件，执行三核混合提取。
    
    【处理流程】
      1. 使用 PyMuPDF 极速提取每页的原生文本层
      2. 使用 pypdfium2 渲染每页为高清图片
      3. 对渲染图片进行 PaddleOCR 识别（兜底乱码页）
      4. 对含图页面进行 Base64 编码，留给后续视觉大模型处理
      5. 将所有提取结果写入日志文件
    
    【参数】
      pdf_path (str): PDF 文件的本地路径
      
    【返回值】
      tuple: (native_text_full, ocr_text_full, base64_diagrams)
        - native_text_full (str)：PyMuPDF 原生提取的全部文本
        - ocr_text_full (str)：PaddleOCR 识别的全部文本
        - base64_diagrams (list)：所有含图页面的 Base64 编码列表
    """
    print(f"\n=====================================\n📜 正在解构文献: {os.path.basename(pdf_path)}")
    
    # 打开 PDF 文件（同时使用两个库：fitz 用于文本提取，pdfium 用于渲染）
    doc_fitz = fitz.open(pdf_path)
    pdf_pdfium = pdfium.PdfDocument(pdf_path)
    
    native_text_full = ""   # 存储原生文本层提取的全部文本
    ocr_text_full = ""      # 存储 OCR 识别的全部文本
    base64_diagrams = []    # 缓存所有图纸页面的 Base64 编码，留给大模型后续并发处理
    
    for page_num in range(len(doc_fitz)):
        print(f"  > 扫描第 {page_num + 1}/{len(doc_fitz)} 页...")
        page_fitz = doc_fitz.load_page(page_num)
        
        # ---------------------------------------------------------------
        # 路线 A：极速提取原生文本层（PyMuPDF，耗时约 0.1s/页）
        # ---------------------------------------------------------------
        native_text_full += page_fitz.get_text() + "\n"
        
        # 判断本页是否有内嵌图片（图纸），用于后续决定是否调用视觉大模型
        has_images = len(page_fitz.get_images(full=True)) > 0
        
        # ---------------------------------------------------------------
        # 路线 B：工业级图片渲染 + OCR 扫描（pypdfium2 + PaddleOCR）
        # ---------------------------------------------------------------
        # 使用 pypdfium2 渲染当前页面为高清图片（scale=1.5 兼顾速度与内存）
        page_pdfium = pdf_pdfium[page_num]
        bitmap = page_pdfium.render(scale=1.5)
        pil_image = bitmap.to_pil()
        
        # 创建白色背景图层，将渲染图片粘贴上去（防止黑底/透明底影响 OCR）
        white_bg = Image.new("RGB", pil_image.size, (255, 255, 255))
        if pil_image.mode in ('RGBA', 'LA'): 
            white_bg.paste(pil_image, mask=pil_image.split()[-1])
        else: 
            white_bg.paste(pil_image)
            
        # 使用 UUID 生成唯一的临时文件名，彻底避免多线程文件名冲突
        temp_img_path = f"temp_{uuid.uuid4().hex[:8]}_page_{page_num}.jpg"
        white_bg.save(temp_img_path, "JPEG")
        
        # 强制对每一页进行 OCR 扫描（用于验证和兜底原生文本提取）
        try:
            result = ocr.ocr(temp_img_path)
            if result and result[0]:
                for line in result[0]: 
                    ocr_text_full += line[1][0] + "  "  # line[1][0] 是识别到的文字内容
        except Exception: 
            pass

        # ---------------------------------------------------------------
        # 路线 C：多模态图纸狙击（仅对含图页面进行编码）
        # ---------------------------------------------------------------
        if has_images:
            print("    [发现内嵌图形] 正在将其编码入队，准备进行视觉提取...")
            # 将含图页面编码为 Base64，存入队列，后续由视觉大模型并发处理
            base64_diagrams.append(encode_image_to_base64(temp_img_path))
                    
        # 清理临时图片文件
        if os.path.exists(temp_img_path): 
            os.remove(temp_img_path)

    # 关闭 PDF 文档对象，释放内存
    doc_fitz.close()
    pdf_pdfium.close()
    
    # 将提取的文本写入日志文件，便于人工复查
    with open(f"outputs/{os.path.basename(pdf_path)}_提取日志.txt", "w", encoding="utf-8") as f:
        f.write(f"【PyMuPDF 原生文本】\n{native_text_full}\n\n【OCR 视觉文本】\n{ocr_text_full}")
    
    return native_text_full, ocr_text_full, base64_diagrams


def run_extraction_and_imputation(deepseek_key, mode="train"):
    """
    主干流水线函数：双轨扫描提取 + 数据修复一体化。
    
    【完整处理流程】
      1. 遍历 pdfs/ 目录下的所有 PDF 文件
      2. 对每个 PDF 执行三核混合提取（文本 + OCR + 图纸）
      3. 并发请求大模型进行参数提取（文本模型 + 视觉模型同时工作）
      4. 交叉验证双轨数据并合并
      5. 融合图纸空间参数
      6. 导出原始特征库 Excel
      7. 自动调用五重递进式数据修复引擎
      8. 输出最终的高价值特征库
    
    【参数】
      deepseek_key (str): DeepSeek API 密钥，传递给数据修复引擎使用
      
    【返回值】
      str 或 None：最终修复后的特征库 Excel 文件路径，如果无有效数据则返回 None
    """
    pdf_dir = PDF_DIR
    output_dir = OUTPUT_DIR
    
    # 确保输出目录存在
    if not os.path.exists(output_dir): 
        os.makedirs(output_dir)
    
    final_dataset = []  # 存储所有文献的最终提取结果
    
    # 获取 pdfs/ 目录下所有 PDF 文件列表
    pdf_files = [f for f in os.listdir(pdf_dir) if f.lower().endswith(".pdf")]
    
    def process_pdf(filename):
        """
        处理单个 PDF 文件的内部函数（供线程池调用）。
        
        【处理流程】
          1. 物理层解析：CPU 计算层提取文本与渲染图纸
          2. 网络层：并发请求大模型进行文本与图纸特征抽取
          3. 裁判：数据交叉验证与合并
          4. 缝合：融合图纸空间参数
        """
        pdf_path = os.path.join(pdf_dir, filename)
        
        # 步骤 1：物理层解析获取全量素材（CPU 计算层：提取文本与渲染图纸）
        native_txt, ocr_txt, base64_diagrams = process_single_paper(pdf_path)
        
        # 步骤 2：并发网络层 —— 让大模型"同时"理解多轨文本与图纸
        async def fetch_all_llm_tasks():
            """
            异步并发请求大模型任务组。
            同时发起：原生文本提取 + OCR 文本提取 + 所有图纸的视觉提取
            """
            print(f"  > [异步网络层 {filename}] ⚡ 正在并发请求大模型进行文本与图纸特征抽取...")
            
            # 构建并发任务列表
            tasks = [
                extract_text_params(native_txt, f"{filename}-底层文本"),  # 原生文本参数提取
                extract_text_params(ocr_txt, f"{filename}-OCR文本")       # OCR 文本参数提取
            ]
            # 为每个图纸页面添加视觉大模型提取任务
            for b64 in base64_diagrams:
                tasks.append(extract_diagram_params(b64))
            
            # 使用 asyncio.gather() 并发执行所有任务
            return await asyncio.gather(*tasks)
        
        # 执行并发任务，解包结果
        results = asyncio.run(fetch_all_llm_tasks())
        native_params = results[0]      # 原生文本提取结果
        ocr_params = results[1]         # OCR 文本提取结果
        diagram_results = results[2:]   # 所有图纸的视觉提取结果
        
        # 步骤 3：裁判进行数据交叉验证（双轨合并）
        final_row = cross_validate_and_merge(native_params, ocr_params)
        final_row["论文来源"] = filename
        
        # 步骤 4：缝合图纸空间参数
        # 将所有图纸提取的有效参数合并到最终结果中
        diagram_data = {}
        for dr in diagram_results:
            for k, v in dr.items():
                if v is not None and str(v).lower() != "null": 
                    diagram_data[k] = v
                
        if diagram_data:
            print(f"  > 🎯 完美融合图纸参数: {list(diagram_data.keys())}")
            final_row.update(diagram_data)
            
        print(f"✅ {filename} 数据装载完毕，冲突警告: [{final_row.get('交叉验证警报')}]")
        return final_row

    # ---------------------------------------------------------------
    # 采用线程池并发解析多篇 PDF（当前 max_workers=1 为串行模式）
    # ---------------------------------------------------------------
    # 【说明】ThreadPoolExecutor 用于并发处理多篇 PDF，
    # 当前设置为 1 个线程（串行），可根据机器性能调整
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        results = list(executor.map(process_pdf, pdf_files))
        final_dataset.extend([r for r in results if r])

    # ---------------------------------------------------------------
    # 导出原始特征库并启动数据修复引擎
    # ---------------------------------------------------------------
    if final_dataset:
        # ---------------------------------------------------------------
        # 新增：后处理管线（地质条件标准化 + 布孔圈数推断）
        # ---------------------------------------------------------------
        final_dataset = postprocess_extracted_data(final_dataset)
        
        df = pd.DataFrame(final_dataset)
        
        # 将重要的来源和报警列挪到最前面方便查阅
        priority_cols = ['论文来源', '交叉验证警报', 'geological_conditions', 'geological_conditions_描述', '布孔圈数']
        cols = [c for c in priority_cols if c in df.columns] + [c for c in df.columns if c not in priority_cols]
        df = df[cols]
        
        # 导出原始特征库 Excel
        out_file = os.path.join(output_dir, f"blasting_CBR_dataset_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx")
        df.to_excel(out_file, index=False)
        print(f"\n🎉 原始特征库已锚定至: {out_file}")
        
        # ---------------------------------------------------------------
        # 新增：复杂爆破案例筛选（圈数 >= 6）
        # ---------------------------------------------------------------
        complex_df = filter_complex_blasting_cases(df, min_ring_count=6)
        if not complex_df.empty:
            print(f"  🔥 共筛出 {len(complex_df)} 条高复杂度爆破案例 (圈数>=6)，已独立导出。")
        
        # ---------------------------------------------------------------
        # 启动第二阶段：五重递进式数据黑洞修复
        # ---------------------------------------------------------------
        print("\n=====================================")
        print("启动第二阶段：数据黑洞修复")
        
        # 导入数据修复引擎（延迟导入，避免循环依赖）
        from imputation_engine import BlastingDataImputer
        
        # 初始化修复引擎，使用传入的 API 密钥
        imputer = BlastingDataImputer(api_key=deepseek_key)
        
        # 调用修复引擎处理原始特征库，获得最终的修复后文件路径
        final_perfect_file = imputer.process_excel(out_file, mode=mode)
        
        print("\n🚀 grandMining 底层数据准备彻底完成！")
        print('💡 建议：打开 Excel 后，优先排查 [交叉验证警报] 列中非"完美一致"的字段。')
        
        # 🔴 最重要的一步：把最终生成的文件路径 return 出去，交给流水线总控
        return final_perfect_file
    
    else:
        print("没有提取到任何有效数据。")
        return None


# =====================================================================
# 🧪 5. 独立测试模式入口
# =====================================================================
# 【说明】当直接运行本文件时（python extractor_module.py），
# 进入独立测试模式，使用默认配置处理 pdfs/ 目录下的 PDF 文件
if __name__ == "__main__":
    print("🧪 [独立测试模式] 启动特征提取模块...")
    
    # 确保 pdfs/ 测试目录存在
    if not os.path.exists("pdfs"):
        os.makedirs("pdfs")
        print("请在 pdfs/ 放入测试文献后再运行")
    else:
        # 使用默认的 DeepSeek API 密钥启动提取与修复流水线
        run_extraction_and_imputation(deepseek_key=TEXT_API_KEY)