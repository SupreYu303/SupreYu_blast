# 🚀 grandMining: 采矿爆破工程智能数据中枢

![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)
![Machine Learning](https://img.shields.io/badge/Machine%20Learning-XGBoost-orange)
![LLM](https://img.shields.io/badge/LLM-DeepSeek%20%7C%20Qwen--VL-green)
![Status](https://img.shields.io/badge/Status-Industrial%20Grade-success)

## 📖 项目简介

**grandMining** 是一个专为采矿工程（特别是立井爆破领域）打造的工业级数据挖掘与特征工程流水线。
面对格式极度非标、参数严重残缺的中文学术文献与工程报告，本系统融合了**多模态大模型提取**、**岩石力学物理边界钳制**与 **XGBoost 增量学习插补**，最终输出可直接用于 CBR（案例推理）的高置信度、零幻觉特征矩阵。

## ✨ 核心工业级特性

1. **👁️ 视觉-文本双轨解析引擎**: 
   - 使用 `PyMuPDF` 高速剥离原生文本，结合 `PaddleOCR` 兜底。
   - 挂载 `Qwen-VL` 视觉大模型，精准狙击并解析“炮眼布置平面图”中的多维空间尺寸。
2. **🛡️ 物理拓扑锁与安规钳制**: 
   - 植入《煤矿安全规程》底线红线（如孔深、最小抵抗线验证）。
   - 引入**炮孔体积密度锁**，基于圆柱体积与炸药密度公式，强行熔断大模型产生的“核弹级装药量”幻觉。
3. **🧠 语义化 XGBoost 插补 (MICE)**: 
   - 内置“稀疏度熔断机制”，自动抛弃无效特征列防污染。
   - 深度识别“语义化零值”（如：无一阶掏槽则二阶参数绝对锁死为0），彻底分离 `0` 与 `null`。
4. **🔗 全链路证据溯源**: 
   - 数据湖中的每一个提取数值，均强制附带大模型摘录的“原文截句证据”，建立100%可信的数据追踪链。

## 📂 核心代码架构

- `Supre_main.py` : 主控节点。负责 PDF 遍历、图文双轨识别调度与交叉验证裁判。
- `imputation_engine.py` : 清洗中枢。负责物理安规约束、加载/训练 XGBoost 经验库、以及大模型零温高压修正。
- `cnki_downloader.py` : 数据获取端。

- ##  环境变量
需在脚本中配置大模型密钥：

TEXT_API_KEY: DeepSeek API (文本重构与证据链)

VISION_API_KEY: Qwen-VL API (工程图纸解析)

# 模式 A: 全量解析新文献 (将 PDF 放入 pdfs/ 目录)
python Supre_main.py

# 模式 B: 独立调用预训练老经验库，对残缺 Excel 进行特征推演
python imputation_engine.py



2026.5.2
## 🏆 核心项目成果

- **自动化构建高价值工程数据湖**：彻底打破工程经验壁垒，将海量非结构化的文献与报告自动转化为结构化的 **40+ 维高精特征矩阵**，为 CBR（案例推理）智能推荐系统提供高质量“燃料”。
- **小样本“数据黑洞”完美修复**：通过独创的“三重插补引擎”，将严重残缺（缺失率>50%）的原始工程记录还原为具备严密物理闭环逻辑的完整参数表，彻底解决矿建领域“数据少、数据脏”的痛点。
- **多模态图纸零代码解析**：摆脱了人工审图与 CAD 尺规量测的繁琐，实现大模型对《炮眼布置平面图》中掏槽圈径、孔距等几何参数的“秒级”视觉抽取。
- **构建 100% 可信审计追踪链**：产出的每一条关键工程参数均锚定“原文依据截句”，满足工业应用对数据透明度和安全审计的严苛要求。

## ⚙️ 极速启动

** 依赖安装**
```bash
pip install pandas numpy xgboost scikit-learn openai PyMuPDF paddlepaddle paddleocr pypdfium2 pillow


