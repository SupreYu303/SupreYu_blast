import os
import yaml

# 自动定位到当前目录下的 config.yaml
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.yaml")

def load_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    return {}

_config = load_config()

# 1. API 配置注入 (优先读取环境变量，其次读取 yaml 兜底)
TEXT_API_KEY = os.getenv("TEXT_API_KEY", _config.get("api", {}).get("text", {}).get("key", ""))
TEXT_BASE_URL = os.getenv("TEXT_BASE_URL", _config.get("api", {}).get("text", {}).get("base_url", "https://api.deepseek.com"))
TEXT_MODEL = os.getenv("TEXT_MODEL", _config.get("api", {}).get("text", {}).get("model", "deepseek-chat"))

VISION_API_KEY = os.getenv("VISION_API_KEY", _config.get("api", {}).get("vision", {}).get("key", ""))
VISION_BASE_URL = os.getenv("VISION_BASE_URL", _config.get("api", {}).get("vision", {}).get("base_url", ""))
VISION_MODEL = os.getenv("VISION_MODEL", _config.get("api", {}).get("vision", {}).get("model", ""))

# 兼容旧代码里使用 QWEN 的别名
QWEN_API_KEY, QWEN_BASE_URL, QWEN_MODEL = VISION_API_KEY, VISION_BASE_URL, VISION_MODEL

# 2. 核心路径配置注入
PDF_DIR = _config.get("paths", {}).get("pdf_dir", "pdfs")
OUTPUT_DIR = _config.get("paths", {}).get("output_dir", "outputs")
MODEL_DIR = _config.get("paths", {}).get("model_dir", "models")
TXT_DIR = _config.get("paths", {}).get("txt_dir", "txt_inputs")