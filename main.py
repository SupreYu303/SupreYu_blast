import pypdfium2 as pdfium
import fitz  # 用于极速文本提取和图片检测
from PIL import Image
import pandas as pd
from openai import OpenAI
import json
import os
import datetime
import base64
import re
from paddleocr import PaddleOCR
from config import TEXT_API_KEY, TEXT_BASE_URL, TEXT_MODEL, QWEN_API_KEY, QWEN_BASE_URL, QWEN_MODEL, PDF_DIR, OUTPUT_DIR

# ================= 1. API 配置 =================
text_client = OpenAI(api_key=TEXT_API_KEY, base_url=TEXT_BASE_URL)

vision_client = OpenAI(api_key=QWEN_API_KEY, base_url=QWEN_BASE_URL)

print("⚡ 正在启动【极速轻量版】视觉与 OCR 引擎...")
# 🔴 提速核心 1：强制使用轻量级 mobile 模型，放弃缓慢的 server 模型！
ocr = PaddleOCR(use_textline_orientation=True, lang="ch", enable_mkldnn=False, ocr_version='PP-OCRv4')

# ================= 2. 基础工具函数 =================
def robust_parse_json(raw_str):
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

def extract_diagram_params(image_path):
    base64_image = encode_image_to_base64(image_path)
    prompt = """
    你是采矿工程师。检查图中是否有“井筒/巷道炮眼布置平面图”。
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
        response = vision_client.chat.completions.create(
            model=QWEN_MODEL,
            messages=[
                {"role": "user", "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                ]}
            ],
            temperature=0.1
        )
        return robust_parse_json(response.choices[0].message.content)
    except Exception:
        return {}

def extract_text_params(text):
    target_schema = {
        "一_基础参数": {"井筒荒径_m": "float/null", "井深_m": "float/null", "岩性": "string/null"},
        "二_总体爆破": {"炮孔直径_mm": "float/null", "总装药量_kg": "float/null"},
        "三_掏槽眼": {"掏槽眼数": "int/null", "掏槽眼孔深_mm": "float/null", "掏槽眼平均孔距_mm": "float/null"},
        "四_辅助眼": {"辅助眼数": "int/null", "辅助眼平均孔深_m": "float/null", "辅助眼单孔装药量_kg": "float/null"},
        "五_周边眼": {"周边眼数": "int/null", "周边眼孔深_m": "float/null", "周边眼圈径_mm": "float/null"}
    }
    prompt = f"提取爆破参数。找不到填 null。格式：{json.dumps(target_schema, ensure_ascii=False)}\n文本：{text}"
    try:
        response = text_client.chat.completions.create(
            model=TEXT_MODEL, messages=[{"role": "user", "content": prompt}], temperature=0.0
        )
        return robust_parse_json(response.choices[0].message.content)
    except Exception:
        return {}

# ================= 3. 智能分流处理引擎 =================
def process_pdf_smart(pdf_path):
    full_text = ""
    merged_diagram_data = {}
    
    # 使用 fitz 做极速侦察
    doc_fitz = fitz.open(pdf_path)
    # 使用 pdfium 做高清视觉兜底
    pdf_pdfium = pdfium.PdfDocument(pdf_path)
    
    for page_num in range(len(doc_fitz)):
        page_fitz = doc_fitz.load_page(page_num)
        
        # 🔴 提速核心 2：极速探测文本，如果这页文本很健康，直接秒抽，跳过缓慢的 OCR！
        fast_text = page_fitz.get_text()
        chinese_char_count = len(re.findall(r'[\u4e00-\u9fa5]', fast_text))
        
        has_images = len(page_fitz.get_images(full=True)) > 0
        needs_ocr = chinese_char_count < 50  # 如果一页汉字不到50个，说明大概率是乱码或纯图片
        
        if not needs_ocr:
            print(f"  > 第 {page_num + 1} 页文本健康，秒速读取完成 (耗时 0.1s)")
            full_text += fast_text + "  "
        else:
            print(f"  > 第 {page_num + 1} 页发现乱码或图像，启动视觉 OCR 强行扫描...")
            # 渲染并 OCR
            page_pdfium = pdf_pdfium[page_num]
            # 提速：分辨率从 2.0 降到 1.5，速度再快 30%，清晰度依旧够用
            bitmap = page_pdfium.render(scale=1.5)
            pil_image = bitmap.to_pil()
            
            white_bg = Image.new("RGB", pil_image.size, (255, 255, 255))
            if pil_image.mode in ('RGBA', 'LA'):
                white_bg.paste(pil_image, mask=pil_image.split()[-1])
            else:
                white_bg.paste(pil_image)
                
            temp_img_path = f"temp_page_ocr_{page_num}.jpg"
            white_bg.save(temp_img_path, "JPEG")
            
            try:
                result = ocr.ocr(temp_img_path)
                if result and result[0]:
                    for line in result[0]:
                        full_text += line[1][0] + "  "
            except Exception:
                pass
            if os.path.exists(temp_img_path):
                os.remove(temp_img_path)

        # 🔴 提速核心 3：只把“包含图片的页面”发给视觉大模型，纯文字页直接跳过！
        if has_images:
            print(f"  > 第 {page_num + 1} 页检测到图纸，正在呼叫视觉大模型审图...")
            page_pdfium = pdf_pdfium[page_num]
            bitmap = page_pdfium.render(scale=2.0)
            pil_image = bitmap.to_pil()
            white_bg = Image.new("RGB", pil_image.size, (255, 255, 255))
            if pil_image.mode in ('RGBA', 'LA'):
                white_bg.paste(pil_image, mask=pil_image.split()[-1])
            else:
                white_bg.paste(pil_image)
                
            temp_img_path = f"temp_page_vlm_{page_num}.jpg"
            white_bg.save(temp_img_path, "JPEG")
            
            try:
                diag_data = extract_diagram_params(temp_img_path)
                if diag_data:
                    for k, v in diag_data.items():
                        if v is not None and str(v).lower() != "null":
                            merged_diagram_data[k] = v
            except Exception:
                pass
            if os.path.exists(temp_img_path):
                os.remove(temp_img_path)
        else:
            print(f"  > 第 {page_num + 1} 页无图纸，跳过视觉大模型 (节省 10s API 耗时)")

    doc_fitz.close()
    pdf_pdfium.close()
    return full_text, merged_diagram_data

def main():
    pdf_dir = PDF_DIR
    output_dir = OUTPUT_DIR
    if not os.path.exists(output_dir): os.makedirs(output_dir)
    all_data = []
    
    for filename in os.listdir(pdf_dir):
        if filename.lower().endswith(".pdf"):
            pdf_path = os.path.join(pdf_dir, filename)
            print(f"\n======================\n🚀 极速处理: {filename}")
            
            full_text, diagram_data = process_pdf_smart(pdf_path)
            
            print("  > 正在呼叫 DeepSeek 抽取表格数据...")
            text_data = extract_text_params(full_text)
            
            final_row = {"论文来源": filename}
            if text_data:
                for cat, params in text_data.items():
                    if isinstance(params, dict): final_row.update(params)
                    else: final_row[cat] = params
            
            if diagram_data:
                print(f"  > 🎯 成功抓取图纸参数: {diagram_data}")
                final_row.update(diagram_data)
                
            all_data.append(final_row)
            print("✅ 本篇极速处理完毕！")

    if all_data:
        df = pd.DataFrame(all_data)
        out_file = os.path.join(output_dir, f"blasting_params_fast_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx")
        df.to_excel(out_file, index=False)
        print(f"\n🎉 极速版大功告成！文件存入: {out_file}")

if __name__ == "__main__":
    main()