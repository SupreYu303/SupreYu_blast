# 🚀 grandMining — 采矿爆破工程智能数据中枢

![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)
![Flet](https://img.shields.io/badge/GUI-Flet%200.84-purple.svg)
![Machine Learning](https://img.shields.io/badge/ML-XGBoost-orange)
![LLM](https://img.shields.io/badge/LLM-DeepSeek%20%7C%20Qwen--VL-green)
![Status](https://img.shields.io/badge/Status-Industrial%20Grade-success)

> 面向立井/巷道爆破领域的工业级自动化数据挖掘、特征提取与智能修复流水线

---

## 📖 项目简介

**grandMining** 是一个专为采矿工程（特别是立井爆破领域）打造的端到端数据工程系统，能够：

- 从中文学术 PDF / TXT 文献中自动提取 **40+ 维**爆破参数
- 通过**视觉大模型**解析"炮眼布置平面图"中的空间几何尺寸
- 利用**岩石力学物理规则 + XGBoost 机器学习 + 大语言模型**三重引擎修复残缺数据
- 提供**图形化操作界面 (Flet GUI)**，一键启动各模块流水线

---

## ✨ 核心特性

| 特性 | 说明 |
|------|------|
| 🧠 三核混合提取 | PyMuPDF 原生文本 + PaddleOCR 视觉兜底 + Qwen-VL 图纸解析 |
| 🛡️ 五重递进修复 | RBR 硬规则 → 物理推导 → LLM CoT → XGBoost MICE → 终极闭环 |
| 📊 全链路溯源 | 每个数值均标注 📄原始文献 / 🤖AI推导 + 原文证据截句 |
| 🖥️ 图形化界面 | Flet GUI 一键操作，支持日志实时输出、规则在线编辑 |
| 🔗 数据集融合 | 自动扫描 outputs/ 目录，合并多批次数据集 |
| 📝 运行日志 | 每次任务自动保存日志到 outputs/ 目录 |

---

## 🏗️ 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                    grandMining GUI (flet_app.py)             │
├──────────┬──────────┬──────────┬──────────┬─────────────────┤
│ PDF处理  │ TXT处理  │ 数据融合 │ 独立修复 │ 领域规则(可编辑)│
├──────────┴──────────┴──────────┴──────────┴─────────────────┤
│                                                             │
│  ┌─────────────── 特征提取层 (extractor_module.py) ───────┐ │
│  │ PyMuPDF 文本 │ PaddleOCR  │ Qwen-VL 图纸 │ DeepSeek   │ │
│  │    原生提取   │  视觉扫描  │   多模态解析  │ 40+维提取  │ │
│  └─────────────────────── 交叉验证 ───────────────────────┘ │
│                          ▼                                  │
│  ┌─────────────── 数据修复层 (imputation_engine.py) ──────┐ │
│  │ RBR规则 → 物理推导 → LLM CoT → XGBoost → 终极闭环    │ │
│  └───────────────────────────────────────────────────────┘ │
│                          ▼                                  │
│  ┌─────────────── 输出层 ────────────────────────────────┐ │
│  │ Excel 特征矩阵 + 溯源标签 + 运行日志                  │ │
│  └───────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

---

## 📂 项目结构

```
blastlimi1/
├── flet_app.py              # 🖥️ Flet GUI 图形界面
├── extractor_module.py      # 🧠 特征提取模块 (三核混合引擎)
├── imputation_engine.py     # 🏭 数据修复模块 (五重递进引擎)
├── scraper_module.py        # 🕷️ 知网爬虫模块
├── main_pipeline.py         # 🚀 完整流水线 (爬虫+提取+修复)
├── main_pipelinepdf.py      # 📕 PDF批量模式 (跳过爬虫)
├── run_txt_pipeline.py      # 📝 纯文本模式
├── merge_datasets.py        # 🔗 数据集融合工具
├── config.py                # 🔧 配置加载器
├── config.yaml              # ⚠️ 实际配置 (含密钥，不上传Git)
├── config.example.yaml      # 📝 配置模板 (安全)
├── domain_rules.json        # 🛡️ 领域知识规则引擎
├── pdfs/                    # PDF文献存放目录
├── txt_inputs/              # 纯文本文件存放目录
├── outputs/                 # 输出结果目录
└── models/                  # ML模型持久化目录
```

---

## ⚡ 快速启动

### 1. 克隆项目

```bash
git clone https://github.com/SupreYu303/SupreYu_blast.git
cd blastlimi1
```

### 2. 安装依赖

```bash
pip install pandas numpy xgboost scikit-learn openai PyMuPDF pypdfium2 pillow joblib pyyaml paddlepaddle paddleocr flet
```

### 3. 配置 API 密钥

复制 `config.example.yaml` 为 `config.yaml`，填入你的真实密钥：

```bash
cp config.example.yaml config.yaml
```

编辑 `config.yaml`，填入 DeepSeek 和通义千问的 API Key。

### 4. 启动 GUI

```bash
python flet_app.py
```

---

## 🖥️ GUI 功能说明

| 页面 | 功能 |
|------|------|
| **仪表盘** | 系统概览：文件统计、API 连接状态、全局 train/predict 模式选择 |
| **PDF 处理** | 本地 PDF 批量处理 / 完整流水线(含知网爬虫)，支持自定义关键词和爬取页数 |
| **TXT 处理** | 三种模式：train训练 / predict修复 / 仅提取原始数据 |
| **数据融合** | 自动扫描 outputs/ 目录，合并多批次数据集 |
| **独立修复** | 对已有 Excel 运行五重修复引擎，支持文件路径自动补全 |
| **领域规则** | **可编辑**：物理常量、安规边界、岩石专家字典均可增删改，保存后实时生效 |
| **输出文件** | 浏览 outputs/ 目录下的所有文件 |

---

## 🔧 领域知识引擎 (domain_rules.json)

可通过 GUI 的"领域规则"页面在线编辑，也可直接修改 JSON 文件：

- **物理常量**：炸药密度、最大装药系数等
- **安规边界**：孔深/进尺/药量/孔距等安全红线
- **岩石专家字典**：花岗岩/砂岩/灰岩等 8 种岩石的基准单耗和 R 系数
- **RBR 规则**：11 条声明式规则，按 fatal/critical/warning/info 分级

---

## 📊 数据流水线

```
输入                    处理                              输出

PDF ────┐        ┌─ PyMuPDF + OCR ──────────┐
        ├───────→┤─ Qwen-VL 图纸解析 ───────┼→ 交叉验证 → 原始特征库.xlsx
TXT ────┘        └─ DeepSeek 40+维提取 ─────┘
                                                     │
                   ┌─ RBR 硬规则清洗 ─────────┐      │
                   ├─ 物理推导 + 专家字典 ────┤      │
                   ├─ LLM CoT 深度推理 ──────┤◄─────┘
                   ├─ XGBoost MICE 插补 ─────┤
                   └─ 终极物理闭环校验 ──────┘
                                                     │
                                                     ▼
                                       修复后特征库_Imputed.xlsx
                                       + 运行日志 run_log_*.txt
```

---

## 📜 许可证

本项目仅供学术研究使用。

## 🙏 致谢

- [DeepSeek](https://deepseek.com) — 文本大模型
- [通义千问](https://dashscope.aliyuncs.com) — 视觉大模型
- [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) — OCR 引擎
- [PyMuPDF](https://pymupdf.readthedocs.io/) — PDF 解析
- [XGBoost](https://xgboost.readthedocs.io/) — 梯度提升框架
- [Flet](https://flet.dev/) — 跨平台 GUI 框架