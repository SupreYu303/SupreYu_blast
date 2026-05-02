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
from config import TEXT_API_KEY, TEXT_BASE_URL, TEXT_MODEL, VISION_API_KEY, VISION_BASE_URL, VISION_MODEL, PDF_DIR, OUTPUT_DIR

# =====================================================================
# ⚙️ 1. 核心引擎与 API 配置区
# =====================================================================
# 🔴 [文本大脑] 负责处理 OCR 和纯文本提取表格参数 (推荐 DeepSeek)
text_client = OpenAI(api_key=TEXT_API_KEY, base_url=TEXT_BASE_URL)

# 🔴 [视觉大脑] 负责看炮眼布置平面图提取空间尺寸 (如通义千问 Qwen-VL)
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
        "基础参数": {
            "井筒荒径_m": "float/null", 
            "井筒净径_m": "float/null", 
            "井深_m": "float/null", 
            "断面面积_m2": "float/null",
            "岩性": "string/null", 
            "f值_普氏硬度": "float/null"
        },
        "总体爆破": {
            "炸药类型": "string/null", 
            "装药方式": "string/null", 
            "炮孔直径_mm": "float/null", 
            "单循环进尺_m": "float/null", 
            "总炮眼数": "int/null", 
            "总装药量_kg": "float/null",
            "炮孔利用率_%": "float/null",
            "单位炸药消耗量_kg/m3": "float/null"
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
    # 👇👇👇 替换原有的 prompt，开启第四维度：证据链溯源 👇👇👇
    prompt = f"""你是资深采矿数据清洗专家。请提取爆破参数，找不到填 null。
【第四维度：证据链溯源指令】
为了保证工程数据的绝对可靠，对于每一个成功提取到的参数，你必须摘录出能证明该数据的“原文半句话”。
请在输出的 JSON 中，为每一个有数据的参数额外新增一个带有 `_原文依据` 后缀的字段。
示例格式：
{{
  "单循环进尺_m": 2.5,
  "单循环进尺_m_原文依据": "本月单循环进尺为2.5m",
  "炮孔直径_mm": 42,
  "炮孔直径_mm_原文依据": "选用直径42mm的一字形钎头"
}}
目标核心参数清单：{json.dumps(target_schema, ensure_ascii=False)}

待解析文本内容：
{text}"""
    # 👆👆👆 ================================================= 👆👆👆
    try:
        response = text_client.chat.completions.create(
            model=TEXT_MODEL, messages=[{"role": "user", "content": prompt}], temperature=0.0
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
    with open(f"outputs/{os.path.basename(pdf_path)}_提取日志.txt", "w", encoding="utf-8") as f:
        f.write(f"【PyMuPDF 原生文本】\n{native_text_full}\n\n【OCR 视觉文本】\n{ocr_text_full}")
    return native_text_full, ocr_text_full, diagram_data_full

def run_extraction_and_imputation(deepseek_key):
    pdf_dir = PDF_DIR
    output_dir = OUTPUT_DIR
    if not os.path.exists(output_dir): os.makedirs(output_dir)
    
    final_dataset = []
    pdf_files = [f for f in os.listdir(pdf_dir) if f.lower().endswith(".pdf")]
    
    def process_pdf(filename):
        pdf_path = os.path.join(pdf_dir, filename)
        
        # 1. 物理层解析获取全量素材
        native_txt, ocr_txt, diagram_data = process_single_paper(pdf_path)
        
        # 2. 让大模型理解两路文本
        print(f"  > [逻辑重构 {filename}] 分析底层原生文本...")
        native_params = extract_text_params(native_txt, f"{filename}-底层文本")
        
        print(f"  > [逻辑重构 {filename}] 分析 OCR 视觉文本...")
        ocr_params = extract_text_params(ocr_txt, f"{filename}-OCR文本")
        
        # 3. 裁判进行数据交叉验证
        final_row = cross_validate_and_merge(native_params, ocr_params)
        final_row["论文来源"] = filename
        
        # 4. 缝合图纸空间参数
        if diagram_data:
            print(f"  > 🎯 完美融合图纸参数: {list(diagram_data.keys())}")
            final_row.update(diagram_data)
            
        print(f"✅ {filename} 数据装载完毕，冲突警告: [{final_row.get('交叉验证警报')}]")
        return final_row

    # 采用最大 5 个工作线程并发解析多篇 PDF
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        results = list(executor.map(process_pdf, pdf_files))
        final_dataset.extend([r for r in results if r])

    # 导出至数据湖
    if final_dataset:
        df = pd.DataFrame(final_dataset)
        # 将重要的来源和报警列挪到最前面方便查阅
        cols = ['论文来源', '交叉验证警报'] + [c for c in df.columns if c not in ['论文来源', '交叉验证警报']]
        df = df[cols]
        
        out_file = os.path.join(output_dir, f"blasting_CBR_dataset_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx")
        df.to_excel(out_file, index=False)
        print(f"\n🎉 原始特征库已锚定至: {out_file}")
        
        print("\n=====================================")
        print("启动第二阶段：数据黑洞修复")
        from imputation_engine import BlastingDataImputer
        
        # 🟢 2. 这里不再写死 API Key，而是使用外面传进来的参数
        imputer = BlastingDataImputer(api_key=deepseek_key)
        
        # 🟢 3. 补全引擎处理完后，拿到最终的文件路径
        final_perfect_file = imputer.process_excel(out_file)
        
        print("\n🚀 grandMining 底层数据准备彻底完成！")
        print("💡 建议：打开 Excel 后，优先排查 [交叉验证警报] 列中非“完美一致”的字段。")
        
        # 🟢 4. 最重要的一步：把最终生成的文件路径 return 出去，交给流水线总控
        return final_perfect_file
    
    else:
        print("没有提取到任何有效数据。")
        return None

# 🟢 5. 把原来的 if __name__ == "__main__": main() 删掉或者注释掉
# 因为这个文件现在变成了工具模块，我们要让 main_pipeline.py 来统一指挥它
# 删掉或者注释掉下面这两行！
# if __name__ == "__main__":
#     main()


if __name__ == "__main__":
    print("🧪 [独立测试模式] 启动特征提取模块...")
    
    # 确保有一个测试用的 PDF 在文件夹里
    if not os.path.exists("pdfs"):
        os.makedirs("pdfs")
        print("请在 pdfs/ 放入测试文献后再运行")
    else:
        run_extraction_and_imputation(deepseek_key=TEXT_API_KEY)