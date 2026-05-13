# =====================================================================
# 📄 文件说明：grandMining 项目统一配置加载器 (config.py)
# =====================================================================
# 【功能概述】
#   本文件是整个 grandMining 系统的"神经中枢配置中心"，负责：
#   1. 自动定位并加载项目根目录下的 config.yaml 配置文件
#   2. 从 YAML 配置文件或环境变量中读取所有 API 密钥、模型名称、路径等参数
#   3. 将配置参数导出为全局常量，供其他模块（如 extractor_module、imputation_engine）直接 import 使用
#
# 【配置优先级】
#   环境变量 > config.yaml 文件 > 代码默认值
#   即：如果系统环境变量中已设置了对应变量，则优先使用环境变量的值
#
# 【依赖说明】
#   - os：Python 内置模块，用于文件路径操作
#   - yaml (PyYAML)：第三方库，用于解析 YAML 格式的配置文件
#
# 【使用示例】
#   from config import TEXT_API_KEY, PDF_DIR, OUTPUT_DIR
#   print(TEXT_API_KEY)   # 输出文本大模型的 API 密钥
#   print(PDF_DIR)        # 输出 PDF 文献存放目录路径
# =====================================================================

import os
import yaml

# ---------------------------------------------------------------------
# 1. 配置文件路径定位
# ---------------------------------------------------------------------
# 自动定位到当前脚本文件所在目录下的 config.yaml
# 例如：如果本文件位于 C:\project\blastlimi1\config.py，
#       则 CONFIG_PATH = C:\project\blastlimi1\config.yaml
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.yaml")


def load_config():
    """
    加载 config.yaml 配置文件并返回解析后的字典对象。
    
    【逻辑说明】
      - 如果 config.yaml 文件存在，则使用 yaml.safe_load() 安全解析
      - 如果文件不存在（例如首次部署时只提供了 config.example.yaml），则返回空字典
      
    【返回值】
      dict：包含 API 配置、路径配置、运行时设置的嵌套字典
    """
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    return {}


# 调用加载函数，获取配置字典（模块级别执行，import 时自动触发）
_config = load_config()


# ---------------------------------------------------------------------
# 2. API 配置注入
# ---------------------------------------------------------------------
# 【读取策略】优先读取环境变量，若环境变量不存在则从 config.yaml 中读取作为兜底
# 这种设计使得在 Docker 容器、CI/CD 流水线等场景下可以通过环境变量灵活注入密钥

# 2.1 文本大模型 API 配置 (推荐 DeepSeek Chat，用于参数提取与数据修复)
TEXT_API_KEY = os.getenv("TEXT_API_KEY", _config.get("api", {}).get("text", {}).get("key", ""))
TEXT_BASE_URL = os.getenv("TEXT_BASE_URL", _config.get("api", {}).get("text", {}).get("base_url", "https://api.deepseek.com"))
TEXT_MODEL = os.getenv("TEXT_MODEL", _config.get("api", {}).get("text", {}).get("model", "deepseek-chat"))

# 2.2 视觉大模型 API 配置 (推荐通义千问 Qwen-VL，用于炮眼布置图纸解析)
VISION_API_KEY = os.getenv("VISION_API_KEY", _config.get("api", {}).get("vision", {}).get("key", ""))
VISION_BASE_URL = os.getenv("VISION_BASE_URL", _config.get("api", {}).get("vision", {}).get("base_url", ""))
VISION_MODEL = os.getenv("VISION_MODEL", _config.get("api", {}).get("vision", {}).get("model", ""))

# 2.3 兼容旧代码中的 QWEN 别名
# 部分历史代码（如 main.py）使用 QWEN_* 作为变量名，此处建立别名映射保持兼容
QWEN_API_KEY, QWEN_BASE_URL, QWEN_MODEL = VISION_API_KEY, VISION_BASE_URL, VISION_MODEL


# ---------------------------------------------------------------------
# 3. 核心路径配置注入
# ---------------------------------------------------------------------
# 【说明】定义各工作目录的路径，确保所有模块统一使用同一套路径规范
# 所有路径均为相对于项目根目录的相对路径

# PDF 文献存放目录（爬虫下载的 PDF 或手动放入的 PDF 文件）
PDF_DIR = _config.get("paths", {}).get("pdf_dir", "pdfs")

# 输出结果目录（提取的 Excel、修复后的特征库、运行日志等）
OUTPUT_DIR = _config.get("paths", {}).get("output_dir", "outputs")

# ML 模型持久化目录（XGBoost 插补模型、特征编码映射等）
MODEL_DIR = _config.get("paths", {}).get("model_dir", "models")

# 纯文本输入目录（直接放入 .txt 文件进行提取）
TXT_DIR = _config.get("paths", {}).get("txt_dir", "txt_inputs")