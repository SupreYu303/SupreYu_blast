# 🔬 grandMining — 采矿爆破工程智能数据中枢

<p align="center">
  <strong>从 PDF/TXT 论文中自动提取 40+ 维爆破参数，五重递进式智能修复引擎，多源学术论文自动抓取</strong>
</p>

---

## ✨ 核心特性

### 📄 三核混合特征提取
- **PyMuPDF** 原生文本层极速提取（0.1s/页）
- **PaddleOCR** 视觉兜底扫描（处理乱码/扫描件页面）
- **Qwen-VL 视觉大模型**解析炮眼布置平面图
- 双轨交叉验证 + 证据链溯源

### 🧠 五重递进式数据修复引擎
1. **RBR 硬规则引擎** — 接口 domain_rules.json 声明式规则
2. **物理推导 + 岩石力学专家字典** — 公式推导 + 8 种常见岩石经验值
3. **LLM CoT 深度逻辑重构** — DeepSeek 大模型思维链推演
4. **XGBoost MICE 多重插补** — 增量学习梯度提升
5. **终极物理闭环校验** — 几何公式 + 拓扑锁 + 体积密度锁

### 🌐 多源学术论文自动抓取（6 大源）
| 论文源 | 类型 | 网络要求 | 语言 |
|--------|------|---------|------|
| **CNKI 知网** | Selenium | 国内直连 | 中文 |
| **万方数据** | Selenium | 国内直连 | 中文 |
| **百度学术** | Selenium | 国内直连 | 中文 |
| **Semantic Scholar** | REST API | 国内直连 | 英文 |
| **Google Scholar** | Selenium | 需科学上网 | 英文 |
| **全部源串行** | 综合 | - | 中英文 |

### 🖥️ 图形化操作界面
- 基于 Flet 框架的暗色主题 GUI
- 左侧导航栏 + 仪表盘 + 实时日志
- 一键启动各模块流水线
- 领域规则在线编辑（物理常量/安规边界/岩石专家字典）

---

## 📦 项目结构

```
blastlimi1/
├── flet_app.py                 # 🖥️ GUI 图形界面主入口
├── config.py                   # ⚙️ 配置加载器
├── config.example.yaml         # 📋 配置模板（复制为 config.yaml 后填写）
├── domain_rules.json           # 📐 领域知识规则（物理常量/安规边界/岩石字典）
│
├── extractor_module.py         # 📄 三核混合特征提取引擎
├── imputation_engine.py        # 🧠 五重递进式数据修复引擎
├── merge_datasets.py           # 🔗 多批次数据集融合工具
│
├── main_pipelinepdf.py         # 🚀 PDF 批量处理流水线
├── main_pipeline.py            # 🚀 完整流水线（含爬虫 + 提取 + 修复）
├── run_txt_pipeline.py         # 📝 纯文本直通处理流水线
├── main.py                     # ⚡ 极速轻量版（单线程测试）
│
├── scraper_module.py           # 🕷️ 知网爬虫（原始版本）
├── scraper_manager.py          # 🎯 多源论文爬虫调度器
└── scraper_sources/            # 🌐 多源爬虫模块包
    ├── __init__.py
    ├── base.py                 # 爬虫基类（驱动配置/人工破盾/信号机制）
    ├── cnki.py                 # CNKI 知网爬虫
    ├── wanfang.py              # 万方数据爬虫
    ├── baidu_scholar.py        # 百度学术爬虫
    ├── semantic_scholar.py     # Semantic Scholar API 爬虫
    └── google_scholar.py       # Google Scholar 爬虫（需科学上网）
```

---

## 🚀 快速开始

### 1. 环境准备

```bash
# 克隆项目
git clone https://github.com/SupreYu303/SupreYu_blast.git
cd SupreYu_blast/blastlimi1

# 创建虚拟环境
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Linux/Mac

# 安装依赖
pip install flet pandas numpy scikit-learn xgboost openai pypdfium2 PyMuPDF paddleocr paddlepaddle pyyaml requests selenium
```

### 2. 配置 API 密钥

```bash
# 复制配置模板
cp config.example.yaml config.yaml

# 编辑 config.yaml，填入你的 API 密钥
# - DeepSeek API Key（文本大模型，用于参数提取与修复）
# - Qwen-VL API Key（视觉大模型，用于图纸解析）
# - Semantic Scholar API Key（可选，用于英文论文抓取）
```

### 3. 启动 GUI

```bash
python flet_app.py
```

### 4. 命令行使用

```bash
# PDF 批量处理
python main_pipelinepdf.py

# 多源论文抓取
python scraper_manager.py --source cnki --keyword "立井爆破" --pages 5
python scraper_manager.py --source semantic --keyword "shaft blasting" --pages 3
python scraper_manager.py --source all --keyword "立井爆破" --pages 2

# 数据集融合
python merge_datasets.py

# 独立数据修复
python -c "from imputation_engine import BlastingDataImputer; imputer = BlastingDataImputer(api_key='your-key'); imputer.process_excel('outputs/xxx.xlsx', mode='predict')"
```

---

## 📊 提取参数维度（40+ 维）

| 类别 | 参数 |
|------|------|
| **基础参数** | 工程地点、作者单位、井筒荒径/净径、井深、断面面积、岩性、f值 |
| **地质条件** | 节理发育、岩体完整性、层状岩体、断层破碎带、风化程度等 |
| **总体爆破** | 炸药类型、装药方式、炮孔直径、单循环进尺、总炮眼数、总装药量等 |
| **掏槽眼** | 总数、一阶/二阶眼数、眼深、单孔装药量 |
| **辅助眼** | 总数、内/外圈眼数、孔深、平均单孔装药量 |
| **周边眼** | 眼数、孔深、孔距、最小抵抗线、单孔装药量 |
| **图纸参数** | 掏槽眼布置形状、各圈层圈径、孔距、最小抵抗线 |

---

## 🔧 配置说明

### config.yaml 结构

```yaml
api:
  text:
    key: "your-DeepSeek-API-Key"
    base_url: "https://api.deepseek.com"
    model: "deepseek-chat"
  vision:
    key: "your-Qwen-VL-API-Key"
    base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1"
    model: "qwen-vl-plus"

paths:
  pdf_dir: "pdfs"
  output_dir: "outputs"
  model_dir: "models"
  txt_dir: "txt_inputs"

settings:
  max_workers: 5

semantic_scholar:
  key: ""  # 可选，免费申请: https://www.semanticscholar.org/product/api#api-key
```

### domain_rules.json

可在线编辑的领域知识配置，包含：
- **physics** — 物理常量（炸药密度、最大装药系数等）
- **bounds** — 安规边界约束（孔深范围、利用率上限、f值阈值等）
- **relationships** — 参数间关系规则（掏槽眼深余量等）
- **rock_expert_dict** — 岩石力学专家字典（8 种常见岩石的基准单耗和 R 系数）

---

## 📋 API Key 申请指南

| API | 用途 | 申请地址 | 费用 |
|-----|------|---------|------|
| **DeepSeek** | 文本参数提取 + 数据修复 | https://platform.deepseek.com | 注册赠送额度 |
| **Qwen-VL** | 图纸视觉解析 | https://dashscope.console.aliyun.com | 注册赠送额度 |
| **Semantic Scholar** | 英文论文抓取 | https://www.semanticscholar.org/product/api#api-key | 完全免费 |

---

## 📜 许可证

MIT License

## 🙏 致谢

- [DeepSeek](https://deepseek.com) — 文本大模型 API
- [通义千问 Qwen-VL](https://qwen.ai) — 视觉大模型 API
- [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) — 文字识别引擎
- [Semantic Scholar](https://www.semanticscholar.org) — 学术论文搜索 API
- [Flet](https://flet.dev) — 跨平台 GUI 框架