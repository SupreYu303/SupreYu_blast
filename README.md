# 📋 grandMining 项目完整技术文档

> **项目全称**: grandMining — 采矿爆破工程智能数据中枢  
> **核心定位**: 面向立井/巷道爆破领域的工业级自动化数据挖掘、特征提取与智能修复流水线  
> **技术栈**: Python 3.8+ / DeepSeek / Qwen-VL / XGBoost / PaddleOCR / PyMuPDF

---

## 📑 目录

1. [项目概述](#1-项目概述)
2. [解决的核心问题](#2-解决的核心问题)
3. [系统架构总览](#3-系统架构总览)
4. [文件清单与功能说明](#4-文件清单与功能说明)
5. [核心模块深度解析](#5-核心模块深度解析)
6. [数据流水线运行模式](#6-数据流水线运行模式)
7. [配置说明](#7-配置说明)
8. [领域知识引擎 (domain_rules.json)](#8-领域知识引擎)
9. [依赖与环境搭建](#9-依赖与环境搭建)
10. [快速启动指南](#10-快速启动指南)
11. [输出产物说明](#11-输出产物说明)
12. [安全与隐私](#12-安全与隐私)
13. [常见问题](#13-常见问题)

---

## 1. 项目概述

**grandMining** 是一个专为采矿工程（特别是立井爆破领域）打造的端到端数据工程系统。它能够：

- 从**中文学术 PDF 文献**中自动提取 40+ 维爆破参数
- 通过**视觉大模型**解析"炮眼布置平面图"中的空间几何尺寸
- 利用**岩石力学物理规则 + XGBoost 机器学习 + 大语言模型**三重引擎修复残缺数据
- 最终输出可直接用于 **CBR（案例推理）** 系统的高置信度特征矩阵

### 技术亮点

| 维度 | 技术方案 |
|------|----------|
| 文本提取 | PyMuPDF 原生文本层 + PaddleOCR 视觉兜底 |
| 图纸解析 | Qwen-VL 视觉大模型多模态识别 |
| 参数提取 | DeepSeek 文本大模型 + 证据链溯源 |
| 数据修复 | RBR 物理规则 → LLM CoT 推演 → XGBoost MICE 插补 |
| 增量学习 | joblib 模型持久化，支持 train/predict 双模式 |

---

## 2. 解决的核心问题

在采矿爆破工程领域，历史文献数据存在以下致命痛点：

| 痛点 | grandMining 的解决方案 |
|------|----------------------|
| 文献格式极度非标（PDF/Word/扫描件混合） | 三核混合解析引擎：原生文本 + OCR + 视觉大模型 |
| 参数严重残缺（缺失率常 >50%） | 三重递进式插补：物理推导 → ML 预测 → LLM 重构 |
| 大模型输出存在"数值幻觉" | 物理拓扑锁 + 体积密度锁 + 安规红线钳制 |
| 数据来源不可追溯 | 每个提取值均附带"原文截句证据"溯源标签 |
| 图纸信息无法结构化 | 视觉大模型直接解析炮眼布置平面图 |

---

## 3. 系统架构总览

```
┌─────────────────────────────────────────────────────────────────┐
│                    grandMining 系统架构                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐      │
│  │  数据获取层   │    │  数据获取层   │    │  数据获取层   │      │
│  │  知网爬虫     │    │  本地 PDF    │    │  纯文本 TXT  │      │
│  │scraper_module │    │ pdfs/ 目录   │    │txt_inputs/   │      │
│  └──────┬───────┘    └──────┬───────┘    └──────┬───────┘      │
│         │                   │                   │               │
│         ▼                   ▼                   ▼               │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              特征提取层 (extractor_module.py)             │   │
│  │  ┌───────────┐  ┌───────────┐  ┌───────────┐            │   │
│  │  │ PyMuPDF   │  │ PaddleOCR │  │ Qwen-VL   │            │   │
│  │  │ 原生文本  │  │ 视觉OCR   │  │ 图纸解析   │            │   │
│  │  └─────┬─────┘  └─────┬─────┘  └─────┬─────┘            │   │
│  │        └───────────┬───┘              │                   │   │
│  │                    ▼                  │                   │   │
│  │        ┌───────────────────┐          │                   │   │
│  │        │  DeepSeek 文本模型 │◄─────────┘                   │   │
│  │        │  40+参数提取       │                              │   │
│  │        └────────┬──────────┘                              │   │
│  │                 ▼                                          │   │
│  │        ┌───────────────────┐                              │   │
│  │        │  交叉验证裁判     │                              │   │
│  │        │  双轨数据合并     │                              │   │
│  │        └────────┬──────────┘                              │   │
│  └─────────────────┼─────────────────────────────────────────┘   │
│                    ▼                                             │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │           数据修复层 (imputation_engine.py)               │   │
│  │                                                          │   │
│  │  第一重: RBR 物理规则引擎 (domain_rules.json)            │   │
│  │    → 倒挂修正 / 利用率换算 / 致命数据剔除                │   │
│  │           ▼                                              │   │
│  │  第二重: 物理推导 + 岩性专家字典                         │   │
│  │    → 断面积公式 / 孔深耦合 / 装药守恒 / 单耗推导        │   │
│  │           ▼                                              │   │
│  │  第三重: LLM CoT 深度逻辑重构                            │   │
│  │    → Few-Shot 思维链推演重度残缺行                       │   │
│  │           ▼                                              │   │
│  │  第四重: XGBoost MICE 多重插补                           │   │
│  │    → 增量学习 / 类别特征语义编码 / 安规边界钳制          │   │
│  │           ▼                                              │   │
│  │  第五重: 后置 RBR 终极闭环校验                           │   │
│  │    → 物理闭环 / 拓扑锁 / 体积密度锁                     │   │
│  └─────────────────┬───────────────────────────────────────┘   │
│                    ▼                                             │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    输出层 (outputs/)                      │   │
│  │  • 原始特征库 (.xlsx)                                    │   │
│  │  • 修复后特征库 _Imputed_Bounded.xlsx                     │   │
│  │  • 溯源标签列 (🤖 AI推导 / 📄 原始文献)                  │   │
│  │  • 提取日志 (.txt)                                       │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 4. 文件清单与功能说明

### 项目根目录结构

```
blastlimi1/
├── .env                    # 🔒 环境变量 
├── .gitignore              # Git 忽略规则
├── config.example.yaml     # 📝 配置模板 
├── config.yaml             # ⚠️ 实际配置 
├── config.py               # 🔧 配置加载器 (统一读取yaml/env)
├── domain_rules.json       # 🛡️ 领域知识规则引擎 (物理常量/安规红线)
│
├── main.py                 # 📄 旧版主程序 (单线程快速版)
├── main_pipeline.py        # 🚀 完整流水线 (爬虫+提取+修复)
├── main_pipelinepdf.py     # 📕 PDF批量模式 (跳过爬虫，直接提取)
├── run_txt_pipeline.py     # 📝 纯文本模式 (TXT直接提取+修复)
├── merge_datasets.py       # 🔗 数据集融合工具
│
├── extractor_module.py     # 🧠 核心提取模块 (三核混合引擎)
├── imputation_engine.py    # 🏭 核心修复模块 (三重插补引擎)
├── scraper_module.py       # 🕷️ 知网爬虫模块 (Selenium自动化)
│
├── README.md               # 原始 README
├── README2.md              # 📋 本文档 (完整技术文档)
│
├── pdfs/                   # 📂 PDF文献存放目录
├── txt_inputs/             # 📂 纯文本文件存放目录
├── outputs/                # 📂 输出结果目录
├── models/                 # 📂 ML模型持久化目录
│   ├── blasting_scaler.pkl         # (已废弃) 标准化器
│   ├── blasting_imputer.pkl        # XGBoost 插补模型
│   ├── valid_numeric_cols.json     # 有效数值列列表
│   └── categorical_mappings.json   # 类别特征编码映射
│
└── __pycache__/            # Python 缓存 (不上传Git)
```

### 各文件功能详解

| 文件名 | 类型 | 功能描述 |
|--------|------|----------|
| `config.py` | 配置加载器 | 统一从 `config.yaml` 和环境变量中读取 API 密钥、路径、模型名等配置 |
| `config.yaml` | 核心配置 | 包含文本/视觉模型的 API Key、Base URL、模型名，以及路径和并发数设置 |
| `config.example.yaml` | 配置模板 | 不含真实密钥的配置文件模板，供新用户参考 |
| `.env` | 环境变量 | 存放 DeepSeek、智谱 GLM、通义千问的 API Key |
| `domain_rules.json` | 领域知识 | 定义了物理常量、安全边界、岩石专家字典、RBR 规则等 |
| `extractor_module.py` | 提取引擎 | PDF→文本→OCR→大模型参数提取→交叉验证的完整流程 |
| `imputation_engine.py` | 修复引擎 | RBR规则→物理推导→LLM推演→XGBoost插补→闭环校验 |
| `scraper_module.py` | 爬虫模块 | 基于 Selenium 的知网自动化文献下载（含人工破盾机制） |
| `main.py` | 快速版主程序 | 单线程、同步版的 PDF 处理程序（旧版，功能较简单） |
| `main_pipeline.py` | 完整流水线 | 端到端：爬虫下载 → 特征提取 → 数据修复 |
| `main_pipelinepdf.py` | PDF批量模式 | 跳过爬虫，直接处理 `pdfs/` 目录下的所有 PDF |
| `run_txt_pipeline.py` | 文本模式 | 处理 `txt_inputs/` 目录下的纯文本文件 |
| `merge_datasets.py` | 数据融合 | 将多个 Excel 数据集合并去重，生成 Master 特征库 |

---

## 5. 核心模块深度解析

### 5.1 特征提取模块 (`extractor_module.py`)

#### 三核混合提取架构

```
PDF 文件
    │
    ├──→ [核1] PyMuPDF 原生文本层提取 (极速，0.1s/页)
    │         └──→ DeepSeek 文本模型 → 40+ 参数提取
    │
    ├──→ [核2] PaddleOCR 视觉扫描 (兜底乱码页)
    │         └──→ DeepSeek 文本模型 → 40+ 参数提取
    │
    └──→ [核3] Qwen-VL 视觉大模型 (仅处理含图页面)
              └──→ 炮眼布置平面图 → 空间几何参数
```

#### 关键函数说明

| 函数 | 功能 |
|------|------|
| `process_single_paper(pdf_path)` | 单篇 PDF 全量解析：文本提取 + OCR扫描 + 图纸编码 |
| `extract_text_params(text, source_name)` | 调用 DeepSeek 从文本中提取 40+ 维参数，含证据链溯源 |
| `extract_diagram_params(base64_image)` | 调用 Qwen-VL 从图纸中提取掏槽圈径、孔距等空间尺寸 |
| `cross_validate_and_merge(pdf_dict, ocr_dict)` | 双轨数据交叉验证裁判，冲突时优先底层文本 |
| `run_extraction_and_imputation(deepseek_key)` | 主干流水线：提取 → 验证 → 修复 → 输出 |

#### 提取的目标参数 (40+ 维)

| 分类 | 参数 |
|------|------|
| **基础参数** | 工程地点、作者单位、井筒荒径、井筒净径、井深、断面面积、岩性、f值(普氏硬度) |
| **总体爆破** | 炸药类型、装药方式、炮孔直径、单循环进尺、总炮眼数、总装药量、炮孔利用率、单位炸药消耗量 |
| **掏槽眼** | 掏槽眼总数、一阶/二阶三阶眼数、眼深、单孔装药量 |
| **辅助眼** | 辅助眼总数、内/外圈眼数、孔深、平均单孔装药量 |
| **周边眼** | 周边眼数、孔深、孔距、最小抵抗线、单孔装药量 |
| **图纸参数** | 掏槽眼布置形状、各圈层圈径(mm)、孔距(mm)、最小抵抗线(mm) |

---

### 5.2 数据修复模块 (`imputation_engine.py`)

#### 五重递进式修复架构

```
原始残缺数据
    │
    ▼
[第一重] RBR 硬规则引擎 (_apply_rbr_hard_rules)
    │  • 异常进尺排查 (防盲炮/修边数据污染)
    │  • 荒径≤净径 倒挂修正
    │  • 掏槽眼深 ≤ 辅助眼深 矫正
    │  • 炮孔利用率量纲自动换算
    │  • f值异常检测
    │  • 岩性/炸药类型缺失 → 致命级剔除
    │
    ▼
[第二重] 物理推导引擎 (_fill_by_physics_with_bounds)
    │  • 断面积 = π×(D/2)² 强制推导
    │  • 掏槽/辅助/周边眼圈径按比例推算
    │  • 岩石力学专家字典匹配 (花岗岩/砂岩/灰岩...)
    │  • 孔深与进尺耦合推导 (R系数)
    │  • 装药量与单耗守恒推导
    │  • 总炮眼数拓扑加和
    │
    ▼
[第三重] LLM CoT 逻辑重构 (_fill_by_llm)
    │  • 仅处理缺失值≥5的重度残缺行
    │  • Few-Shot + CoT 思维链工程推理
    │  • 强制输出 reasoning_steps 专家诊断报告
    │  • 温度=0.0，严格禁止幻觉
    │
    ▼
[第四重] XGBoost MICE 多重插补 (_fill_by_advanced_ml)
    │  • IterativeImputer + XGBRegressor
    │  • 类别特征语义编码 (岩性/炸药/装药方式)
    │  • 增量学习模式 (train/predict)
    │  • 后置常识修正: 整数卡控 / 孔深红线 / 药量分级红线
    │
    ▼
[第五重] 终极物理闭环校验
    │  • 几何公式绝对服从
    │  • 掏槽超深卡控 (≥进尺+200mm)
    │  • 进尺与孔深绝对物理挂钩
    │  • 总装药量与单耗数学锁定
    │  • 体积密度锁 (防止核弹级装药量幻觉)
    │  • 拓扑汇总锁
    │
    ▼
带溯源标签的修复后特征矩阵
```

#### 溯源标签系统

每个数值参数列都会自动生成对应的 `_溯源` 标签列：
- `📄 原始文献数据` — 该值直接从文献中提取
- `🤖 AI/算法推导` — 该值由 AI 或算法推导填充

---

### 5.3 知网爬虫模块 (`scraper_module.py`)

#### 工作流程

```
1. 启动 Edge 浏览器 (深度防爬伪装)
2. 访问知网首页 → 【人工破盾】等待用户手动完成安全验证
3. 机器接管：输入检索词 → 点击搜索
4. 遍历检索结果：
   ├── 点击文献标题 → 新窗口打开
   ├── 查找"PDF下载"按钮 → 触发下载
   ├── 关闭子窗口 → 切回主窗口
   └── 随机延时 (模拟人类行为)
5. 自动翻页 → 重复步骤4
6. 下载完成，关闭浏览器
```

#### 防爬特性

- Edge WebDriver 深度伪装 (隐藏自动化标识)
- JS 注入抹除 `navigator.webdriver` 属性
- 随机延时 (0.5s - 6s)
- 人工破盾机制 (安全验证/滑块由人类完成)

---

### 5.4 数据融合工具 (`merge_datasets.py`)

将多个批次的 Excel 数据集进行：
1. **列维度求并集** — 不同批次提取的参数列可能不同，合并时自动对齐
2. **重复文献清理** — 基于"论文来源"列去重
3. **废弃列清理** — 清理历史遗留的错误列名
4. **输出 Master 特征库** — 最终的超级矩阵

---

## 6. 数据流水线运行模式

### 模式 A：完整端到端流水线 (爬虫+提取+修复)

```bash
python main_pipeline.py
```

**流程**: 知网爬虫下载 PDF → 特征提取 → 数据修复 → 输出 Excel

**适用场景**: 首次大规模采集文献数据

---

### 模式 B：本地 PDF 批量处理 (跳过爬虫)

```bash
# 1. 将 PDF 文件放入 pdfs/ 目录
# 2. 运行
python main_pipelinepdf.py
```

**流程**: 读取本地 PDF → 特征提取 → 数据修复 → 输出 Excel

**适用场景**: 已有本地 PDF 文献，无需爬虫

---

### 模式 C：纯文本直接处理

```bash
# 1. 将 .txt 文件放入 txt_inputs/ 目录
# 2. 运行
python run_txt_pipeline.py
```

**流程**: 读取 TXT → 大模型参数提取 → 数据修复 → 输出 Excel

**适用场景**: 文献已转为纯文本格式

---

### 模式 D：数据集融合

```bash
python merge_datasets.py
```

**流程**: 读取多个 Excel → 合并去重 → 输出 Master 特征库

**适用场景**: 多批次数据需要合并

---

### 模式 E：独立数据修复 (使用预训练模型)

```python
# 在 imputation_engine.py 底部修改配置后运行
python imputation_engine.py
```

**流程**: 读取已有 Excel → 使用预训练 XGBoost 模型修复 → 输出修复后 Excel

**适用场景**: 已有提取好的数据，仅需补全修复

---

## 7. 配置说明

### config.yaml 配置项

```yaml
api:
  text:                      # 文本大模型配置 (用于参数提取和数据修复)
    key: "sk-xxx"            # DeepSeek API Key
    base_url: "https://api.deepseek.com"
    model: "deepseek-chat"
  vision:                    # 视觉大模型配置 (用于图纸解析)
    key: "sk-xxx"            # 通义千问 API Key
    base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1"
    model: "qwen-vl-plus"

paths:
  pdf_dir: "pdfs"            # PDF 文献目录
  output_dir: "outputs"      # 输出目录
  model_dir: "models"        # ML模型存储目录
  txt_dir: "txt_inputs"      # 纯文本输入目录

settings:
  max_workers: 5             # 线程池并发数
```

### 支持的大模型

| 用途 | 推荐模型 | 备选模型 |
|------|----------|----------|
| 文本参数提取 | DeepSeek Chat | 智谱 GLM-4 |
| 图纸视觉解析 | 通义千问 Qwen-VL-Plus | 智谱 GLM-4V |
| 数据修复推理 | DeepSeek Chat | 智谱 GLM-4 |

---

## 8. 领域知识引擎

`domain_rules.json` 是整个系统的"工程经验大脑"，包含以下核心配置：

### 8.1 物理常量

```json
{
  "physics": {
    "EXPLOSIVE_DENSITY_KG_M3": 1200.0,    // 炸药密度 (kg/m³)
    "MAX_CHARGE_COEF": 0.8,                // 最大装药系数
    "ROCK_HARDNESS_THRESHOLD": 8           // 岩石硬度阈值
  }
}
```

### 8.2 安规边界约束

| 参数 | 最小值 | 最大值 | 单位 |
|------|--------|--------|------|
| 单循环进尺 | 1.0 | 5.0 | m |
| 孔深 | 0.6 | 6.0 | m |
| 最小抵抗线 | 300.0 | - | mm |
| 周边眼装药量 | - | 3.0 | kg |
| 辅助眼装药量 | - | 6.0 | kg |
| 掏槽眼装药量 | - | 8.0 | kg |
| 周边眼孔距 | - | 800.0 | mm |
| 普氏硬度 f 值 | 0.1 | - | - |
| 炮孔利用率 | 80.0 | 100.0 | % |
| 单位炸药消耗量 | 0.8 | 5.5 | kg/m³ |
| 炮孔直径 | 32.0 | 75.0 | mm |

### 8.3 岩石力学专家字典

| 岩性 | 基准单耗 q_base (kg/m³) | R 系数 |
|------|-------------------------|--------|
| 花岗岩 | 2.2 | 0.80 |
| 玄武岩 | 2.0 | 0.82 |
| 石英岩 | 2.1 | 0.80 |
| 砂岩 | 1.8 | 0.85 |
| 灰岩 | 1.6 | 0.88 |
| 页岩 | 1.4 | 0.88 |
| 泥岩 | 1.3 | 0.90 |
| 煤 | 1.1 | 0.95 |

### 8.4 RBR 规则引擎

定义了 11 条声明式规则，按严重级别分为：

- **fatal**: 致命级 — 直接剔除记录 (如岩性/炸药类型缺失)
- **critical**: 严重级 — 强制修正或触发重推 (如荒径≤净径、孔深倒挂)
- **warning**: 警告级 — 自动修正 (如断面积偏差、炮眼数不一致)
- **info**: 信息级 — 自动换算 (如利用率量纲修正)

---

## 9. 依赖与环境搭建

### Python 依赖

```bash
pip install pandas numpy xgboost scikit-learn openai PyMuPDF pypdfium2 pillow joblib pyyaml

# PaddleOCR (OCR引擎)
pip install paddlepaddle paddleocr

# 知网爬虫 (仅模式A需要)
pip install selenium
```

### 完整依赖列表

| 包名 | 用途 |
|------|------|
| `pandas` | 数据处理与 Excel 读写 |
| `numpy` | 数值计算 |
| `xgboost` | 梯度提升回归器 (MICE插补) |
| `scikit-learn` | IterativeImputer 多重插补 |
| `openai` | 大模型 API 调用 (兼容 DeepSeek/Qwen) |
| `PyMuPDF` (fitz) | PDF 原生文本提取与图片检测 |
| `pypdfium2` | PDF 高清页面渲染 |
| `Pillow` | 图像处理与格式转换 |
| `paddlepaddle` + `paddleocr` | OCR 文字识别 |
| `joblib` | ML 模型序列化存储 |
| `pyyaml` | YAML 配置文件解析 |
| `selenium` | 浏览器自动化 (知网爬虫) |

### 系统要求

- Python 3.8+
- Windows 10/11 (已测试) / Linux / macOS
- Edge 浏览器 (爬虫模式需要)
- 建议 8GB+ 内存 (OCR 和 XGBoost 训练需要)

---

## 10. 快速启动指南

### 第一步：克隆项目

```bash
git clone https://github.com/SupreYu303/SupreYu_blast.git
cd blastlimi1
```

### 第二步：安装依赖

```bash
pip install pandas numpy xgboost scikit-learn openai PyMuPDF paddlepaddle paddleocr pypdfium2 pillow joblib pyyaml selenium
```

### 第三步：配置 API 密钥

**方式一**：编辑 `config.yaml` (推荐)

```yaml
api:
  text:
    key: "你的DeepSeek_API_Key"
    base_url: "https://api.deepseek.com"
    model: "deepseek-chat"
  vision:
    key: "你的通义千问_API_Key"
    base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1"
    model: "qwen-vl-plus"
```

**方式二**：编辑 `.env` 文件

```
DEEPSEEK_API_KEY="sk-你的密钥"
VISION_API_KEY="你的密钥"
QWEN_API_KEY="你的密钥"
```

### 第四步：准备数据

```bash
# 将 PDF 文献放入 pdfs/ 目录
# 或将纯文本文件放入 txt_inputs/ 目录
```

### 第五步：运行

```bash
# 模式 A：PDF 批量处理
python main_pipelinepdf.py

# 模式 B：纯文本处理
python run_txt_pipeline.py

# 模式 C：完整流水线 (含爬虫)
python main_pipeline.py
```

### 第六步：查看结果

输出文件保存在 `outputs/` 目录下，文件名格式：
```
blasting_CBR_dataset_YYYYMMDD_HHMMSS.xlsx
blasting_CBR_dataset_YYYYMMDD_HHMMSS_Imputed_Bounded.xlsx
```

---

## 11. 输出产物说明

### Excel 输出列说明

| 列名 | 说明 |
|------|------|
| `论文来源` | 原始 PDF/TXT 文件名 |
| `交叉验证警报` | 双轨提取冲突记录，"完美一致"表示无冲突 |
| `数据质量` | 数据质量等级标识 |
| `*_溯源` | 每个数值参数的溯源标签 (📄原始/🤖AI推导) |
| `*_原文依据` | 大模型摘录的原文证据截句 |
| 其余 40+ 列 | 各类爆破工程参数 |

### 模型输出 (models/ 目录)

| 文件 | 说明 |
|------|------|
| `blasting_imputer.pkl` | XGBoost MICE 插补模型 (可增量更新) |
| `valid_numeric_cols.json` | 参与插补的有效数值列列表 |
| `categorical_mappings.json` | 类别特征编码映射字典 |

---

## 12. 安全与隐私

### Git 安全

`.gitignore` 已配置忽略以下敏感文件：

```gitignore
# 核心机密
.env
config.yaml
domain_rules.json

# 数据与模型
pdfs/
outputs/
txt_inputs/
models/
__pycache__/
```

### API Key 管理

- `config.yaml` 和 `.env` 包含真实 API Key，**绝对不能上传 Git**
- `config.example.yaml` 为安全的配置模板，可放心提交
- 代码中优先读取环境变量，其次读取 `config.yaml` 作为兜底

---

## 13. 常见问题

### Q1: PaddleOCR 首次运行很慢？

PaddleOCR 首次运行需要下载模型文件（约 100MB），后续运行会使用缓存。建议首次运行时保持网络畅通。

### Q2: 出现 `ModuleNotFoundError: No module named 'paddleocr'`？

```bash
pip install paddlepaddle paddleocr
```

如果仍然报错，尝试：
```bash
pip install paddlepaddle==2.5.2 paddleocr==2.7.0.3
```

### Q3: 大模型 API 调用超时？

- 检查网络连接
- 确认 API Key 是否有效
- `imputation_engine.py` 已内置 45 秒超时 + 3 次自动重试

### Q4: XGBoost 插补报错 "样本量过少"？

当 Excel 中数据行数 < 3 时，系统会自动跳过 XGBoost 插补，仅使用物理推导和 LLM 修复。

### Q5: 如何切换大模型？

编辑 `config.yaml`，支持 DeepSeek 和智谱 GLM：

```yaml
# 使用 DeepSeek
api:
  text:
    key: "你的DeepSeek_Key"
    base_url: "https://api.deepseek.com"
    model: "deepseek-chat"

# 切换为智谱 GLM
api:
  text:
    key: "你的智谱_Key"
    base_url: "https://open.bigmodel.cn/api/paas/v4/"
    model: "glm-4"
```

### Q6: 如何对已有数据使用预训练模型修复？

```python
from imputation_engine import BlastingDataImputer
from config import TEXT_API_KEY

imputer = BlastingDataImputer(api_key=TEXT_API_KEY, model_dir="models/")
imputer.process_excel("outputs/你的文件.xlsx", mode="predict")
```

### Q7: 知网爬虫被安全验证拦截？

这是正常现象。`scraper_module.py` 设计了"人工破盾"机制：程序启动后会暂停，等待你在弹出的浏览器中手动完成安全验证，然后按回车让机器接管。

---

## 📊 项目数据流全景图

```
[输入]                          [处理]                              [输出]
                                
PDF 文献 ──┐                    ┌─ PyMuPDF 文本提取 ─────────┐      
           │                    │                             │      
           ├─→ extractor ──────┤─ PaddleOCR 视觉扫描 ───────┤─→ 交叉验证 ─→ 原始特征库.xlsx
           │    _module.py      │                             │      
           │                    └─ Qwen-VL 图纸解析 ─────────┘      
TXT 文稿 ──┤                                                          │
           │                    ┌─ RBR 硬规则清洗 ───────────┐       │
           │                    │                             │       │
           └─→ imputation ──────┤─ 物理推导+专家字典 ─────────┤       │
                _engine.py      │                             │       │
                                ├─ LLM CoT 深度推理 ──────────┤─→ 修复后特征库_Imputed.xlsx
                                │                             │       │
                                ├─ XGBoost MICE 插补 ─────────┤       │
                                │                             │       │
                                └─ 终极物理闭环校验 ──────────┘       │
                                                                      │
知网文献 ──→ scraper_module.py ──→ pdfs/ ──────────────────────────────┘
```

---

## 📜 许可证

本项目仅供学术研究使用。

---

## 🙏 致谢

- [DeepSeek](https://deepseek.com) — 文本大模型 API
- [通义千问](https://dashscope.aliyuncs.com) — 视觉大模型 API
- [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) — OCR 引擎
- [PyMuPDF](https://pymupdf.readthedocs.io/) — PDF 解析库
- [XGBoost](https://xgboost.readthedocs.io/) — 梯度提升框架
- [scikit-learn](https://scikit-learn.org/) — 机器学习工具库
