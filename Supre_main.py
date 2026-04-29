import pypdfium2 as pdfium
import fitz  # 用于提取纯文本层和探测图纸
from PIL import Image
import pandas as pd
from openai import OpenAI
import json
import os
import datetime
import base64
import re
from paddleocr import PaddleOCR

# =====================================================================
# ⚙️ 1. 核心引擎与 API 配置区
# =====================================================================
# 🔴 [文本大脑] 负责处理 OCR 和纯文本提取表格参数 (推荐 DeepSeek)
TEXT_API_KEY = "your_deepseek_key_here"  
TEXT_BASE_URL = "https://api.deepseek.com"
text_client = OpenAI(api_key=TEXT_API_KEY, base_url=TEXT_BASE_URL)

# 🔴 [视觉大脑] 负责看炮眼布置平面图提取空间尺寸 (如通义千问 Qwen-VL)
VISION_API_KEY = "your_deepseek_key_here" 
VISION_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1" 
VISION_MODEL = "qwen-vl-max" 
vision_client = OpenAI(api_key=VISION_API_KEY, base_url=VISION_BASE_URL)

print("🚀 正在点火：三核混合特征提取系统 (PyMuPDF + PaddleOCR + VLM)...")
# 强制加载轻量级模型 PP-OCRv4，关闭 MKLDNN 防崩溃
ocr = PaddleOCR(use_textline_orientation=True, lang="ch", enable_mkldnn=False, ocr_version='PP-OCRv4')

# =====================================================================
# 🛡️ 2. 防御与清洗工具箱
# =====================================================================
def robust_parse_json(raw_str):
    """暴力撕裂大模型返回的 markdown 外壳，绝对防范空白 JSON"""
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
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

# =====================================================================
# 🧠 3. AI 识别与交叉验证逻辑
# =====================================================================
def extract_diagram_params(image_path):
    """【视觉模型】审视图纸，提取炮孔布置尺寸"""
    base64_image = encode_image_to_base64(image_path)
    prompt = """
    你是采矿工程师。检查图中是否有“井筒/巷道炮眼布置平面图”。
    如果没有图纸直接返回：{}
    如果有图纸，请顺着标注线提取参数（没有填 null）：
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
        response = vision_client.chat.completions.create(
            model=VISION_MODEL,
            messages=[{"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
            ]}],
            temperature=0.1
        )
        return robust_parse_json(response.choices[0].message.content)
    except Exception:
        return {}

def extract_text_params(text, source_name):
    """【文本模型】从杂乱文本中提取 40+ 核心参数"""
    target_schema = {
        "基础参数": {"井筒荒径_m": "float/null", "井筒净径_m": "float/null", "井深_m": "float/null", "岩性": "string/null", "f值_普氏硬度": "float/null"},
        "总体爆破": {"炸药类型": "string/null", "装药方式": "string/null", "炮孔直径_mm": "float/null", "单循环进尺_m": "float/null", "总炮眼数": "int/null", "总装药量_kg": "float/null"},
        "掏槽眼": {"掏槽眼数": "int/null", "掏槽眼孔深_mm": "float/null", "掏槽眼平均孔距_mm": "float/null", "一阶掏槽眼单孔装药量_kg": "float/null"},
        "辅助眼": {"辅助眼数": "int/null", "辅助眼平均孔深_m": "float/null", "辅助眼平均孔距_mm": "float/null", "辅助眼单孔装药量_kg": "float/null"},
        "周边眼": {"周边眼数": "int/null", "周边眼孔深_m": "float/null", "周边眼孔距_mm": "float/null", "周边眼单孔装药量_kg": "float/null", "周边眼圈径_mm": "float/null"}
    }
    prompt = f"你是数据清洗专家。提取爆破参数，找不到填 null。格式：{json.dumps(target_schema, ensure_ascii=False)}\n文本内容：{text}"
    try:
        response = text_client.chat.completions.create(
            model="deepseek-chat", messages=[{"role": "user", "content": prompt}], temperature=0.0
        )
        # 将结果展平为一维字典
        raw_dict = robust_parse_json(response.choices[0].message.content)
        flat_dict = {}
        for k, v in raw_dict.items():
            if isinstance(v, dict): flat_dict.update(v)
            else: flat_dict[k] = v
        return flat_dict
    except Exception as e:
        print(f"      [!] {source_name} 提取失败: {e}")
        return {}

def cross_validate_and_merge(pdf_dict, ocr_dict):
    """【工业级裁判】双轨数据交叉验证，输出最终结果和警告日志"""
    merged_data = {}
    conflict_log = []
    all_keys = set(pdf_dict.keys()).union(set(ocr_dict.keys()))
    
    for key in all_keys:
        val_pdf = pdf_dict.get(key)
        val_ocr = ocr_dict.get(key)
        is_pdf_empty = val_pdf is None or str(val_pdf).lower() in ["null", "none", "", "未提及"]
        is_ocr_empty = val_ocr is None or str(val_ocr).lower() in ["null", "none", "", "未提及"]
        
        if not is_pdf_empty and not is_ocr_empty:
            if str(val_pdf).strip() == str(val_ocr).strip():
                merged_data[key] = val_pdf  # 完全一致，最可靠
            else:
                merged_data[key] = val_pdf  # 冲突时优先信底层文本，并报警
                conflict_log.append(f"[{key}] 底层:{val_pdf} 视觉:{val_ocr}")
        elif not is_pdf_empty: merged_data[key] = val_pdf
        elif not is_ocr_empty: merged_data[key] = val_ocr
        else: merged_data[key] = None
            
    merged_data["交叉验证警报"] = " | ".join(conflict_log) if conflict_log else "完美一致"
    return merged_data

# =====================================================================
# 🏭 4. 主干流水线 (双轨扫描提取)
# =====================================================================
def process_single_paper(pdf_path):
    print(f"\n=====================================\n📜 正在解构文献: {os.path.basename(pdf_path)}")
    
    doc_fitz = fitz.open(pdf_path)
    pdf_pdfium = pdfium.PdfDocument(pdf_path)
    
    native_text_full = ""
    ocr_text_full = ""
    diagram_data_full = {}
    
    for page_num in range(len(doc_fitz)):
        print(f"  > 扫描第 {page_num + 1}/{len(doc_fitz)} 页...")
        page_fitz = doc_fitz.load_page(page_num)
        
        # 路线A：极速提取原生文本层
        native_text_full += page_fitz.get_text() + "\n"
        
        # 判断本页是否有需要视觉干预的情况 (有图，或者文字极少疑似乱码)
        has_images = len(page_fitz.get_images(full=True)) > 0
        
        # 路线B：工业级图片渲染 (防黑底)
        page_pdfium = pdf_pdfium[page_num]
        bitmap = page_pdfium.render(scale=1.5)  # 兼顾速度与内存
        pil_image = bitmap.to_pil()
        
        white_bg = Image.new("RGB", pil_image.size, (255, 255, 255))
        if pil_image.mode in ('RGBA', 'LA'): white_bg.paste(pil_image, mask=pil_image.split()[-1])
        else: white_bg.paste(pil_image)
            
        temp_img_path = f"temp_page_{page_num}.jpg"
        white_bg.save(temp_img_path, "JPEG")
        
        # 强制 OCR 视觉扫字 (用于验证和兜底)
        try:
            result = ocr.ocr(temp_img_path)
            if result and result[0]:
                for line in result[0]: ocr_text_full += line[1][0] + "  "
        except Exception: pass

        # 路线C：多模态图纸狙击
        if has_images:
            print("    [发现内嵌图形] 呼叫视觉大模型检索图纸参数...")
            diag_data = extract_diagram_params(temp_img_path)
            if diag_data:
                for k, v in diag_data.items():
                    if v is not None and str(v).lower() != "null": diagram_data_full[k] = v
                    
        if os.path.exists(temp_img_path): os.remove(temp_img_path)

    doc_fitz.close()
    pdf_pdfium.close()
    return native_text_full, ocr_text_full, diagram_data_full

def main():
    pdf_dir = "pdfs/"
    output_dir = "outputs/"
    if not os.path.exists(output_dir): os.makedirs(output_dir)
    
    final_dataset = []
    
    for filename in os.listdir(pdf_dir):
        if filename.lower().endswith(".pdf"):
            pdf_path = os.path.join(pdf_dir, filename)
            
            # 1. 物理层解析获取全量素材
            native_txt, ocr_txt, diagram_data = process_single_paper(pdf_path)
            
            # 2. 并行让大模型理解两路文本
            print("  > [逻辑重构] 分析底层原生文本...")
            native_params = extract_text_params(native_txt, "底层文本")
            
            print("  > [逻辑重构] 分析 OCR 视觉文本...")
            ocr_params = extract_text_params(ocr_txt, "OCR文本")
            
            # 3. 裁判进行数据交叉验证
            final_row = cross_validate_and_merge(native_params, ocr_params)
            final_row["论文来源"] = filename
            
            # 4. 缝合图纸空间参数
            if diagram_data:
                print(f"  > 🎯 完美融合图纸参数: {list(diagram_data.keys())}")
                final_row.update(diagram_data)
                
            final_dataset.append(final_row)
            print(f"✅ {filename} 数据装载完毕，冲突警告: [{final_row.get('交叉验证警报')}]")

    # 导出至数据湖
    if final_dataset:
        df = pd.DataFrame(final_dataset)
        # 将重要的来源和报警列挪到最前面方便查阅
        cols = ['论文来源', '交叉验证警报'] + [c for c in df.columns if c not in ['论文来源', '交叉验证警报']]
        df = df[cols]
        
        out_file = os.path.join(output_dir, f"blasting_CBR_dataset_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx")
        df.to_excel(out_file, index=False)
        print(f"\n🎉 终极特征库组装完成！共计 {len(final_dataset)} 篇，数据已锚定至: {out_file}")
        print("💡 建议：打开 Excel 后，优先排查 [交叉验证警报] 列中非“完美一致”的字段。")

if __name__ == "__main__":
    main() 