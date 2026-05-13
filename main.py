# =====================================================================
# 📄 文件说明：grandMining 极速轻量版主程序 (main.py)
# =====================================================================
# 【功能概述】
#   本文件是 grandMining 系统的"极速轻量版"PDF 处理程序（旧版），
#   采用单线程同步模式，功能较 extractor_module.py 简化。
#   主要用于快速验证和测试，不包含数据修复引擎。
#
# 【核心特性】
#   1. 三核混合文本提取：PyMuPDF 原生文本 + PaddleOCR 视觉兜底 + Qwen-VL 图纸解析
#   2. 智能分流：文本健康的页面秒速读取，乱码页面才启动 OCR（大幅提速）
#   3. 只有含图的页面才调用视觉大模型（节省 API 调用耗时）
#
# 【运行方式】
#   python main.py
#
# 【适用场景】
#   快速测试单线程 PDF 处理流程，验证提取效果
#
# 【与 extractor_module.py 的区别】
#   main.py：单线程同步模式，功能简化，不包含数据修复引擎
#   extractor_module.py：异步并发模式，功能完整，集成数据修复引擎
#
# 【前置条件】
#   1. 已将 PDF 文件放入 pdfs/ 目录
#   2. 已配置 config.yaml 中的 API 密钥
#
# 【输出产物】
#   outputs/blasting_params_fast_YYYYMMDD_HHMMSS.xlsx — 极速版提取结果
#
# 【依赖模块】
#   - pypdfium2：PDF 高清页面渲染引擎
#   - fitz (PyMuPDF)：PDF 原生文本提取与图片检测
#   - PIL (Pillow)：图像处理与格式转换
#   - pandas：数据处理与 Excel 导出
#   - openai：大模型 API 调用客户端（兼容 DeepSeek/Qwen）
#   - paddleocr：PaddleOCR 文字识别引擎
#   - config：统一配置加载器
# =====================================================================

import pypdfium2 as pdfium
import fitz  # PyMuPDF，用于极速文本提取和图片检测
from PIL import Image
import pandas as pd
from openai import OpenAI
import json
import os
import datetime
import base64
import re
from paddleocr import PaddleOCR

# 从统一配置中导入所有必要的 API 密钥、路径等参数
from config import TEXT_API_KEY, TEXT_BASE_URL, TEXT_MODEL, QWEN_API_KEY, QWEN_BASE_URL, QWEN_MODEL, PDF_DIR, OUTPUT_DIR


# =====================================================================
# ⚙️ 1. API 客户端与 OCR 引擎初始化
# =====================================================================

# 创建文本大模型 API 客户端（同步模式，用于参数提取）
# 推荐使用 DeepSeek Chat 模型
text_client = OpenAI(api_key=TEXT_API_KEY, base_url=TEXT_BASE_URL)

# 创建视觉大模型 API 客户端（同步模式，用于图纸解析）
# 推荐使用通义千问 Qwen-VL 模型
vision_client = OpenAI(api_key=QWEN_API_KEY, base_url=QWEN_BASE_URL)

print("⚡ 正在启动【极速轻量版】视觉与 OCR 引擎...")

# 初始化 PaddleOCR 引擎
# 【参数说明】
#   use_textline_orientation=True：启用文本行方向检测，提高旋转文本的识别率
#   lang="ch"：使用中文语言模型
#   enable_mkldnn=False：关闭 MKLDNN 加速（防止某些 CPU 上崩溃）
#   ocr_version='PP-OCRv4'：强制使用轻量级 PP-OCRv4 模型（放弃缓慢的 server 模型）
ocr = PaddleOCR(use_textline_orientation=True, lang="ch", enable_mkldnn=False, ocr_version='PP-OCRv4')


# =====================================================================
# 🛡️ 2. 基础工具函数
# =====================================================================

def robust_parse_json(raw_str):
    """
    暴力解析大模型返回的 JSON 字符串，防范各种格式异常。
    
    【说明】大模型返回的内容可能包含 Markdown 代码块标记、多余空白字符等，
    本函数通过查找第一个 '{' 和最后一个 '}' 来提取 JSON 主体，
    确保即使返回格式不规范也能正确解析。
    
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
    将图片文件编码为 Base64 字符串，用于发送给视觉大模型 API。
    
    【参数】
      image_path (str): 图片文件的本地路径
      
    【返回值】
      str：Base64 编码的图片字符串
    """
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')


def extract_diagram_params(image_path):
    """
    【视觉大模型】从炮眼布置平面图中提取空间几何参数。
    
    【说明】将图片编码为 Base64 后发送给 Qwen-VL 视觉大模型，
    要求模型识别图中是否有"井筒/巷道炮眼布置平面图"，
    如果有则提取掏槽眼布置形状、各圈层圈径、孔距等空间尺寸参数。
    
    【参数】
      image_path (str): 图纸图片的本地文件路径
      
    【返回值】
      dict：提取到的图纸参数字典，如果没有图纸或提取失败则返回空字典 {}
    """
    base64_image = encode_image_to_base64(image_path)
    
    # 构造视觉大模型的 Prompt（提示词）
    prompt = """
    你是采矿工程师。检查图中是否有"井筒/巷道炮眼布置平面图"。
    没有图纸返回：{}
    有图纸则提取（没有填 null）：
    {
      "图纸_掏槽眼布置形状": "string",
      "图纸_一阶掏槽眼圈径_mm": "string或float",
      "图纸_二阶掏槽眼圈径_mm": "string或float",
      "图纸_辅助眼孔距_mm": "string或float",
      "图纸_周边眼孔距_mm": "string或float",
      "图纸_周边眼圈径_mm": "string或float"
    }
    """
    try:
        # 调用视觉大模型 API，发送图片和提示词
        response = vision_client.chat.completions.create(
            model=QWEN_MODEL,
            messages=[
                {"role": "user", "content": [
                    {"type": "text", "text": prompt},
                    # 将图片以 Base64 编码的 data URI 格式嵌入消息
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                ]}
            ],
            temperature=0.1  # 低温度，确保输出稳定
        )
        return robust_parse_json(response.choices[0].message.content)
    except Exception:
        return {}


def extract_text_params(text):
    """
    【文本大模型】从杂乱文本中提取核心爆破参数。
    
    【说明】将 PDF 提取的文本内容发送给 DeepSeek 文本大模型，
    要求模型按照预定义的参数模式提取基础参数、总体爆破、掏槽眼、辅助眼、周边眼等参数。
    
    【参数】
      text (str): 从 PDF 中提取的文本内容
      
    【返回值】
      dict：提取到的参数字典（嵌套结构），提取失败则返回空字典 {}
    """
    # 定义目标参数模式（Schema），告诉大模型需要提取哪些参数
    target_schema = {
        "一_基础参数": {"井筒荒径_m": "float/null", "井深_m": "float/null", "岩性": "string/null"},
        "二_总体爆破": {"炮孔直径_mm": "float/null", "总装药量_kg": "float/null"},
        "三_掏槽眼": {"掏槽眼数": "int/null", "掏槽眼孔深_mm": "float/null", "掏槽眼平均孔距_mm": "float/null"},
        "四_辅助眼": {"辅助眼数": "int/null", "辅助眼平均孔深_m": "float/null", "辅助眼单孔装药量_kg": "float/null"},
        "五_周边眼": {"周边眼数": "int/null", "周边眼孔深_m": "float/null", "周边眼圈径_mm": "float/null"}
    }
    
    # 构造文本大模型的 Prompt（提示词）
    prompt = f"提取爆破参数。找不到填 null。格式：{json.dumps(target_schema, ensure_ascii=False)}\n文本：{text}"
    try:
        # 调用文本大模型 API
        response = text_client.chat.completions.create(
            model=TEXT_MODEL, messages=[{"role": "user", "content": prompt}], temperature=0.0
        )
        return robust_parse_json(response.choices[0].message.content)
    except Exception:
        return {}


# =====================================================================
# 🧠 3. 智能分流处理引擎
# =====================================================================

def process_pdf_smart(pdf_path):
    """
    智能分流处理单篇 PDF 文件。
    
    【核心策略】
      - 文本健康的页面（汉字数 >= 50）：直接秒速读取原生文本层，跳过 OCR（耗时 0.1s）
      - 乱码/纯图片页面（汉字数 < 50）：启动 PaddleOCR 视觉扫描（耗时较长）
      - 含图纸的页面：额外调用 Qwen-VL 视觉大模型解析图纸
    
    【参数】
      pdf_path (str): PDF 文件的本地路径
      
    【返回值】
      tuple: (full_text, merged_diagram_data)
        - full_text (str)：提取到的全部文本内容
        - merged_diagram_data (dict)：从图纸中提取的合并参数字典
    """
    full_text = ""
    merged_diagram_data = {}
    
    # 使用 PyMuPDF (fitz) 做极速文本提取和图片检测
    doc_fitz = fitz.open(pdf_path)
    # 使用 pypdfium2 做高清页面渲染（用于 OCR 和图纸截图）
    pdf_pdfium = pdfium.PdfDocument(pdf_path)
    
    for page_num in range(len(doc_fitz)):
        page_fitz = doc_fitz.load_page(page_num)
        
        # ---------------------------------------------------------------
        # 提速核心 2：极速探测文本质量，决定是否需要 OCR
        # ---------------------------------------------------------------
        # 先尝试极速读取原生文本层
        fast_text = page_fitz.get_text()
        # 统计中文字符数量，判断文本质量
        chinese_char_count = len(re.findall(r'[\u4e00-\u9fa5]', fast_text))
        
        # 检测本页是否包含内嵌图片（图纸）
        has_images = len(page_fitz.get_images(full=True)) > 0
        
        # 如果中文字符少于 50 个，说明大概率是乱码或纯图片页，需要 OCR
        needs_ocr = chinese_char_count < 50
        
        if not needs_ocr:
            # -------------------------------------------------------
            # 路线 A：文本健康，直接秒速读取（耗时约 0.1s）
            # -------------------------------------------------------
            print(f"  > 第 {page_num + 1} 页文本健康，秒速读取完成 (耗时 0.1s)")
            full_text += fast_text + "  "
        else:
            # -------------------------------------------------------
            # 路线 B：乱码或纯图片页，启动 OCR 强行扫描
            # -------------------------------------------------------
            print(f"  > 第 {page_num + 1} 页发现乱码或图像，启动视觉 OCR 强行扫描...")
            
            # 使用 pypdfium2 渲染当前页面为图片（分辨率 scale=1.5，兼顾速度与清晰度）
            page_pdfium = pdf_pdfium[page_num]
            bitmap = page_pdfium.render(scale=1.5)
            pil_image = bitmap.to_pil()
            
            # 创建白色背景图层，将渲染图片粘贴上去（消除可能的透明/黑色背景）
            white_bg = Image.new("RGB", pil_image.size, (255, 255, 255))
            if pil_image.mode in ('RGBA', 'LA'):
                white_bg.paste(pil_image, mask=pil_image.split()[-1])
            else:
                white_bg.paste(pil_image)
                
            # 保存为临时 JPEG 文件（PaddleOCR 需要文件路径作为输入）
            temp_img_path = f"temp_page_ocr_{page_num}.jpg"
            white_bg.save(temp_img_path, "JPEG")
            
            # 调用 PaddleOCR 进行文字识别
            try:
                result = ocr.ocr(temp_img_path)
                if result and result[0]:
                    for line in result[0]:
                        full_text += line[1][0] + "  "  # line[1][0] 是识别到的文字内容
            except Exception:
                pass
            
            # 清理临时图片文件
            if os.path.exists(temp_img_path):
                os.remove(temp_img_path)

        # ---------------------------------------------------------------
        # 提速核心 3：只有含图页面才调用视觉大模型（节省 API 耗时）
        # ---------------------------------------------------------------
        if has_images:
            print(f"  > 第 {page_num + 1} 页检测到图纸，正在呼叫视觉大模型审图...")
            
            # 使用更高分辨率 (scale=2.0) 渲染图纸页面，确保细节清晰
            page_pdfium = pdf_pdfium[page_num]
            bitmap = page_pdfium.render(scale=2.0)
            pil_image = bitmap.to_pil()
            
            # 创建白色背景并粘贴
            white_bg = Image.new("RGB", pil_image.size, (255, 255, 255))
            if pil_image.mode in ('RGBA', 'LA'):
                white_bg.paste(pil_image, mask=pil_image.split()[-1])
            else:
                white_bg.paste(pil_image)
                
            # 保存为临时图片文件
            temp_img_path = f"temp_page_vlm_{page_num}.jpg"
            white_bg.save(temp_img_path, "JPEG")
            
            # 调用视觉大模型提取图纸参数
            try:
                diag_data = extract_diagram_params(temp_img_path)
                if diag_data:
                    # 将提取到的有效参数合并到总字典中（过滤掉 null 值）
                    for k, v in diag_data.items():
                        if v is not None and str(v).lower() != "null":
                            merged_diagram_data[k] = v
            except Exception:
                pass
            
            # 清理临时图片文件
            if os.path.exists(temp_img_path):
                os.remove(temp_img_path)
        else:
            # 纯文字页，跳过视觉大模型调用，节省 API 耗时
            print(f"  > 第 {page_num + 1} 页无图纸，跳过视觉大模型 (节省 10s API 耗时)")

    # 关闭 PDF 文档对象，释放内存
    doc_fitz.close()
    pdf_pdfium.close()
    
    return full_text, merged_diagram_data


# =====================================================================
# 🏭 4. 主函数
# =====================================================================

def main():
    """
    极速轻量版主函数：遍历 pdfs/ 目录下的所有 PDF 文件，
    逐个进行智能分流处理并提取参数，最终汇总输出 Excel。
    
    【执行流程】
      1. 遍历 pdfs/ 目录下的所有 .pdf 文件
      2. 对每个 PDF 调用 process_pdf_smart() 进行智能分流处理
      3. 调用 DeepSeek 文本大模型提取核心参数
      4. 合并文本参数和图纸参数
      5. 汇总所有文献的参数，输出为 Excel 文件
    """
    pdf_dir = PDF_DIR
    output_dir = OUTPUT_DIR
    
    # 确保输出目录存在
    if not os.path.exists(output_dir): 
        os.makedirs(output_dir)
    
    all_data = []  # 存储所有文献的提取结果
    
    for filename in os.listdir(pdf_dir):
        if filename.lower().endswith(".pdf"):
            pdf_path = os.path.join(pdf_path, filename)
            print(f"\n======================\n🚀 极速处理: {filename}")
            
            # 步骤 1：智能分流处理 PDF（文本提取 + OCR + 图纸编码）
            full_text, diagram_data = process_pdf_smart(pdf_path)
            
            # 步骤 2：调用 DeepSeek 文本大模型提取核心参数
            print("  > 正在呼叫 DeepSeek 抽取表格数据...")
            text_data = extract_text_params(full_text)
            
            # 步骤 3：合并文本参数和图纸参数
            final_row = {"论文来源": filename}
            if text_data:
                for cat, params in text_data.items():
                    if isinstance(params, dict): 
                        final_row.update(params)
                    else: 
                        final_row[cat] = params
            
            if diagram_data:
                print(f"  > 🎯 成功抓取图纸参数: {diagram_data}")
                final_row.update(diagram_data)
                
            all_data.append(final_row)
            print("✅ 本篇极速处理完毕！")

    # 步骤 4：汇总输出为 Excel 文件
    if all_data:
        df = pd.DataFrame(all_data)
        out_file = os.path.join(output_dir, f"blasting_params_fast_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx")
        df.to_excel(out_file, index=False)
        print(f"\n🎉 极速版大功告成！文件存入: {out_file}")


# ---------------------------------------------------------------------
# 程序入口
# ---------------------------------------------------------------------
# 当直接运行本文件时（python main.py），调用 main() 函数启动处理流程
if __name__ == "__main__":
    main()