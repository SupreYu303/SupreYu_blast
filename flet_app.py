import flet as ft
import subprocess
import threading
import os
import sys
import json
import re
import time
from datetime import datetime

# =====================================================================
# 项目根目录
# =====================================================================
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))

def get_config_status():
    config_path = os.path.join(PROJECT_DIR, "config.yaml")
    status = {"text_key": False, "vision_key": False, "config_exists": False}
    if os.path.exists(config_path):
        status["config_exists"] = True
        try:
            import yaml
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f)
            text_key = cfg.get("api", {}).get("text", {}).get("key", "")
            vision_key = cfg.get("api", {}).get("vision", {}).get("key", "")
            status["text_key"] = bool(text_key and len(text_key) > 5)
            status["vision_key"] = bool(vision_key and len(vision_key) > 5)
        except Exception:
            pass
    return status

def count_files(directory, ext):
    dir_path = os.path.join(PROJECT_DIR, directory)
    if not os.path.exists(dir_path):
        return 0
    return len([f for f in os.listdir(dir_path) if f.lower().endswith(ext)])

def list_output_files():
    out_dir = os.path.join(PROJECT_DIR, "outputs")
    if not os.path.exists(out_dir):
        return []
    files = []
    for f in sorted(os.listdir(out_dir), reverse=True):
        fpath = os.path.join(out_dir, f)
        if os.path.isfile(fpath):
            size_kb = os.path.getsize(fpath) / 1024
            mtime = datetime.fromtimestamp(os.path.getmtime(fpath)).strftime("%Y-%m-%d %H:%M")
            files.append({"name": f, "size": f"{size_kb:.1f} KB", "time": mtime})
    return files

def list_model_files():
    model_dir = os.path.join(PROJECT_DIR, "models")
    if not os.path.exists(model_dir):
        return []
    return [f for f in os.listdir(model_dir) if os.path.isfile(os.path.join(model_dir, f))]

# ANSI 转义序列清除
ANSI_RE = re.compile(r'\x1b\[[0-9;]*[a-zA-Z]')

def clean_line(text):
    cleaned = ANSI_RE.sub('', str(text)).rstrip()
    return cleaned if cleaned.strip() else None

# =====================================================================
# 主应用
# =====================================================================
def main(page: ft.Page):
    page.title = "grandMining - 采矿爆破工程智能数据中枢"
    page.window.width = 1200
    page.window.height = 800
    page.window.min_width = 900
    page.window.min_height = 600
    page.theme_mode = ft.ThemeMode.DARK
    page.padding = 0
    
    is_running = [False]
    current_process = [None]
    current_tab = [0]
    
    # =================================================================
    # 日志
    # =================================================================
    log_text = ft.Text(
        value="[INFO] grandMining 控制台已就绪\n[TIP] 请在左侧选择功能模块后点击运行\n",
        selectable=True, size=12, font_family="Consolas", color=ft.Colors.GREEN_300,
    )
    
    log_container = ft.Column(
        controls=[log_text], scroll=ft.ScrollMode.AUTO, expand=True, spacing=0,
    )
    
    def append_log(msg):
        cleaned = clean_line(msg)
        if cleaned is None:
            return
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_text.value += f"[{timestamp}] {cleaned}\n"
        page.update()
    
    def clear_log(e=None):
        log_text.value = ""
        page.update()
    
    def save_log_to_file():
        """将当前日志保存到 outputs/ 目录"""
        try:
            out_dir = os.path.join(PROJECT_DIR, "outputs")
            if not os.path.exists(out_dir):
                os.makedirs(out_dir)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            log_file = os.path.join(out_dir, f"run_log_{timestamp}.txt")
            with open(log_file, "w", encoding="utf-8") as f:
                f.write(f"grandMining 运行日志\n")
                f.write(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write("=" * 60 + "\n")
                f.write(log_text.value)
            append_log(f"[LOG] 日志已保存: {log_file}")
        except Exception as ex:
            append_log(f"[WARN] 日志保存失败: {ex}")
    
    # =================================================================
    # 子进程运行器 (修复版)
    # =================================================================
    def run_command_async(cmd_list, cwd=None, open_terminal=False):
        """运行子进程
        open_terminal=True: 在新终端窗口中运行 (用于需要 input() 的爬虫)
        open_terminal=False: 在 GUI 内捕获输出 (默认)
        """
        if is_running[0]:
            append_log("[WARN] 已有任务在运行中，请等待完成")
            return
        
        is_running[0] = True
        run_btn.disabled = True
        stop_btn.disabled = False
        progress_ring.visible = True
        page.update()
        
        if open_terminal:
            # 在新终端窗口中运行 (支持 input() 交互)
            def _worker_terminal():
                try:
                    append_log("在新终端窗口中启动任务...")
                    append_log("请在弹出的终端窗口中操作")
                    
                    env = os.environ.copy()
                    env["PYTHONIOENCODING"] = "utf-8"
                    env["PYTHONUTF8"] = "1"
                    
                    # Windows: 用 start cmd /k 在新窗口运行
                    if sys.platform == "win32":
                        script_path = cmd_list[-1] if len(cmd_list) > 1 else cmd_list[0]
                        terminal_cmd = f'start "grandMining" cmd /k "cd /d {cwd or PROJECT_DIR} && {" ".join(cmd_list)}"'
                        proc = subprocess.Popen(
                            terminal_cmd, shell=True, cwd=cwd or PROJECT_DIR, env=env,
                        )
                    else:
                        proc = subprocess.Popen(
                            cmd_list, cwd=cwd or PROJECT_DIR, env=env,
                        )
                    current_process[0] = proc
                    proc.wait()
                    
                    if proc.returncode == 0:
                        append_log("[DONE] 终端任务完成")
                    else:
                        append_log(f"[INFO] 终端已关闭 (退出码: {proc.returncode})")
                except Exception as ex:
                    append_log(f"[ERROR] {ex}")
                finally:
                    current_process[0] = None
                    is_running[0] = False
                    run_btn.disabled = False
                    stop_btn.disabled = True
                    progress_ring.visible = False
                    page.update()
                    refresh_dashboard()
            
            thread = threading.Thread(target=_worker_terminal, daemon=True)
            thread.start()
            return
        
        def _worker():
            proc = None
            try:
                append_log(f"执行: {' '.join(cmd_list)}")
                append_log("=" * 50)
                append_log("[INFO] 任务启动中，请耐心等待...")
                
                env = os.environ.copy()
                env["PYTHONIOENCODING"] = "utf-8"
                env["PYTHONUTF8"] = "1"
                
                # -u 参数强制 Python 无缓冲输出
                final_cmd = [cmd_list[0]] + (["-u"] if cmd_list[0].endswith("python.exe") or cmd_list[0].endswith("python") else []) + cmd_list[1:]
                
                proc = subprocess.Popen(
                    final_cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    cwd=cwd or PROJECT_DIR,
                    bufsize=0,
                    env=env,
                )
                current_process[0] = proc
                
                for raw_line in iter(proc.stdout.readline, b""):
                    if not raw_line:
                        break
                    try:
                        line = raw_line.decode("utf-8", errors="replace").rstrip()
                    except Exception:
                        line = raw_line.decode("gbk", errors="replace").rstrip()
                    cleaned = clean_line(line)
                    if cleaned:
                        timestamp = datetime.now().strftime("%H:%M:%S")
                        log_text.value += f"[{timestamp}] {cleaned}\n"
                        page.update()
                
                proc.wait()
                
                if proc.returncode == 0:
                    append_log("=" * 50)
                    append_log("[DONE] 任务执行完成!")
                else:
                    append_log("=" * 50)
                    append_log(f"[ERROR] 退出码: {proc.returncode}")
                
                # 保存运行日志到 outputs/
                save_log_to_file()
                    
            except Exception as ex:
                append_log(f"[ERROR] {ex}")
                save_log_to_file()
            finally:
                current_process[0] = None
                is_running[0] = False
                run_btn.disabled = False
                stop_btn.disabled = True
                progress_ring.visible = False
                page.update()
                refresh_dashboard()
        
        thread = threading.Thread(target=_worker, daemon=True)
        thread.start()
    
    def stop_task(e):
        proc = current_process[0]
        if proc and proc.poll() is None:
            try:
                proc.terminate()
                append_log("[INFO] 已发送终止信号")
            except Exception as ex:
                append_log(f"[WARN] 终止失败: {ex}")
        else:
            append_log("[INFO] 没有正在运行的任务")
    
    # =================================================================
    # 顶部工具栏
    # =================================================================
    progress_ring = ft.ProgressRing(width=20, height=20, visible=False, stroke_width=2)
    
    run_btn = ft.ElevatedButton(
        "运行", icon=ft.Icons.PLAY_ARROW,
        color=ft.Colors.WHITE, bgcolor=ft.Colors.GREEN_700,
        on_click=lambda e: run_selected_pipeline(),
    )
    stop_btn = ft.ElevatedButton(
        "终止", icon=ft.Icons.STOP,
        color=ft.Colors.WHITE, bgcolor=ft.Colors.RED_700,
        on_click=stop_task, disabled=True,
    )
    clear_btn = ft.IconButton(icon=ft.Icons.DELETE_SWEEP, tooltip="清空日志", on_click=clear_log)
    
    toolbar = ft.Container(
        content=ft.Row(
            [ft.Text("控制台输出", size=14, weight=ft.FontWeight.BOLD),
             ft.Container(expand=True), progress_ring, clear_btn, stop_btn, run_btn],
            alignment=ft.MainAxisAlignment.START,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        padding=ft.Padding(16, 8, 16, 8),
        bgcolor=ft.Colors.with_opacity(0.05, ft.Colors.WHITE),
    )
    
    # =================================================================
    # 全局设置: 全局 train/predict 模式
    # =================================================================
    global_mode = ft.Dropdown(
        label="默认运行模式",
        width=220,
        value="train",
        options=[
            ft.dropdown.Option("train", "train - 训练新模型"),
            ft.dropdown.Option("predict", "predict - 使用已有模型"),
        ],
    )
    
    # =================================================================
    # 仪表盘
    # =================================================================
    def build_dashboard():
        config_status = get_config_status()
        pdf_count = count_files("pdfs", ".pdf")
        txt_count = count_files("txt_inputs", ".txt")
        out_count = count_files("outputs", ".xlsx")
        model_count = len(list_model_files())
        
        def si(ok):
            return ft.Icons.CHECK_CIRCLE if ok else ft.Icons.CANCEL
        def sc(ok):
            return ft.Colors.GREEN_400 if ok else ft.Colors.RED_400
        
        cards = ft.Row(wrap=True, spacing=12, controls=[
            ft.Card(bgcolor=ft.Colors.with_opacity(0.1, ft.Colors.RED), content=ft.Container(padding=20, width=160,
                content=ft.Column(horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=4, controls=[
                    ft.Icon(ft.Icons.PICTURE_AS_PDF, size=32, color=ft.Colors.RED_300),
                    ft.Text(str(pdf_count), size=28, weight=ft.FontWeight.BOLD, text_align=ft.TextAlign.CENTER),
                    ft.Text("PDF 文献", size=12, color=ft.Colors.GREY_400, text_align=ft.TextAlign.CENTER),
                ]))),
            ft.Card(bgcolor=ft.Colors.with_opacity(0.1, ft.Colors.BLUE), content=ft.Container(padding=20, width=160,
                content=ft.Column(horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=4, controls=[
                    ft.Icon(ft.Icons.TEXT_SNIPPET, size=32, color=ft.Colors.BLUE_300),
                    ft.Text(str(txt_count), size=28, weight=ft.FontWeight.BOLD, text_align=ft.TextAlign.CENTER),
                    ft.Text("TXT 文稿", size=12, color=ft.Colors.GREY_400, text_align=ft.TextAlign.CENTER),
                ]))),
            ft.Card(bgcolor=ft.Colors.with_opacity(0.1, ft.Colors.GREEN), content=ft.Container(padding=20, width=160,
                content=ft.Column(horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=4, controls=[
                    ft.Icon(ft.Icons.TABLE_CHART, size=32, color=ft.Colors.GREEN_300),
                    ft.Text(str(out_count), size=28, weight=ft.FontWeight.BOLD, text_align=ft.TextAlign.CENTER),
                    ft.Text("输出数据集", size=12, color=ft.Colors.GREY_400, text_align=ft.TextAlign.CENTER),
                ]))),
            ft.Card(bgcolor=ft.Colors.with_opacity(0.1, ft.Colors.ORANGE), content=ft.Container(padding=20, width=160,
                content=ft.Column(horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=4, controls=[
                    ft.Icon(ft.Icons.MODEL_TRAINING, size=32, color=ft.Colors.ORANGE_300),
                    ft.Text(str(model_count), size=28, weight=ft.FontWeight.BOLD, text_align=ft.TextAlign.CENTER),
                    ft.Text("ML 模型", size=12, color=ft.Colors.GREY_400, text_align=ft.TextAlign.CENTER),
                ]))),
        ])
        
        api_card = ft.Card(content=ft.Container(padding=16, width=360, content=ft.Column(spacing=8, controls=[
            ft.Text("API 连接状态", size=14, weight=ft.FontWeight.BOLD),
            ft.Divider(height=1),
            ft.Row([
                ft.Icon(si(config_status["text_key"]), color=sc(config_status["text_key"]), size=18),
                ft.Text("DeepSeek 文本大模型", size=13), ft.Container(expand=True),
                ft.Text("已连接" if config_status["text_key"] else "未配置", size=12, color=sc(config_status["text_key"])),
            ]),
            ft.Row([
                ft.Icon(si(config_status["vision_key"]), color=sc(config_status["vision_key"]), size=18),
                ft.Text("通义千问视觉大模型", size=13), ft.Container(expand=True),
                ft.Text("已连接" if config_status["vision_key"] else "未配置", size=12, color=sc(config_status["vision_key"])),
            ]),
            ft.Row([
                ft.Icon(si(config_status["config_exists"]), color=sc(config_status["config_exists"]), size=18),
                ft.Text("config.yaml", size=13), ft.Container(expand=True),
                ft.Text("已就绪" if config_status["config_exists"] else "缺失", size=12, color=sc(config_status["config_exists"])),
            ]),
        ])))
        
        output_files = list_output_files()[:5]
        recent = []
        for f in output_files:
            recent.append(ft.Row([
                ft.Icon(ft.Icons.INSERT_DRIVE_FILE, size=16, color=ft.Colors.BLUE_300),
                ft.Text(f["name"], size=12, expand=True, overflow=ft.TextOverflow.ELLIPSIS),
                ft.Text(f["size"], size=11, color=ft.Colors.GREY_500),
                ft.Text(f["time"], size=11, color=ft.Colors.GREY_500),
            ]))
        
        outputs_card = ft.Card(content=ft.Container(padding=16, width=500, content=ft.Column(spacing=6,
            controls=[ft.Text("最近输出", size=14, weight=ft.FontWeight.BOLD), ft.Divider(height=1)]
            + (recent if recent else [ft.Text("暂无输出", size=12, color=ft.Colors.GREY_500)])
        )))
        
        # 全局模式选择器
        settings_card = ft.Card(content=ft.Container(padding=16, content=ft.Column(spacing=8, controls=[
            ft.Text("全局设置", size=14, weight=ft.FontWeight.BOLD),
            ft.Divider(height=1),
            global_mode,
            ft.Text("选择 train 模式会训练新模型, predict 模式使用已有模型修复", size=11, color=ft.Colors.GREY_500),
        ])))
        
        return ft.Column(scroll=ft.ScrollMode.AUTO, expand=True, spacing=8, controls=[
            ft.Text("系统仪表盘", size=20, weight=ft.FontWeight.BOLD),
            ft.Container(height=4),
            cards,
            ft.Container(height=4),
            ft.Row(spacing=12, vertical_alignment=ft.CrossAxisAlignment.START, controls=[
                api_card, outputs_card,
            ]),
            ft.Container(height=4),
            ft.Row(spacing=12, controls=[settings_card]),
        ])
    
    # =================================================================
    # PDF 页面 (带关键词输入)
    # =================================================================
    pdf_keyword_input = ft.TextField(
        label="知网检索关键词", hint_text="立井爆破", width=300, value="立井爆破",
    )
    pdf_pages_input = ft.TextField(
        label="爬取页数", hint_text="5", width=120, value="5",
    )
    pdf_mode_dropdown = ft.Dropdown(
        label="处理模式", width=300, value="pdf_batch",
        options=[
            ft.dropdown.Option("pdf_batch", "本地 PDF 批量处理 (推荐)"),
            ft.dropdown.Option("full_pipeline", "完整流水线 (含知网爬虫)"),
        ],
    )
    
    pdf_page = ft.Column(scroll=ft.ScrollMode.AUTO, expand=True, spacing=4, controls=[
        ft.Text("PDF 文献批量处理", size=20, weight=ft.FontWeight.BOLD),
        ft.Container(height=4),
        ft.Text("将 PDF 放入 pdfs/ 目录后, 系统将自动执行三核混合特征提取 + 数据修复引擎", size=13, color=ft.Colors.GREY_400),
        ft.Container(height=12),
        pdf_mode_dropdown,
        ft.Container(height=8),
        ft.Card(content=ft.Container(padding=16, content=ft.Column(spacing=4, controls=[
            ft.Text("爬虫设置 (仅完整流水线模式生效)", size=13, weight=ft.FontWeight.BOLD),
            pdf_keyword_input,
            pdf_pages_input,
        ]))),
        ft.Container(height=8),
        ft.Card(content=ft.Container(padding=16, content=ft.Column(spacing=4, controls=[
            ft.Text("处理流程", size=13, weight=ft.FontWeight.BOLD),
            ft.Text("1. PyMuPDF 原生文本层极速提取", size=12),
            ft.Text("2. PaddleOCR 视觉兜底扫描", size=12),
            ft.Text("3. Qwen-VL 视觉大模型解析图纸", size=12),
            ft.Text("4. DeepSeek 文本模型提取 40+ 维参数", size=12),
            ft.Text("5. 双轨交叉验证 + 数据冲突检测", size=12),
            ft.Text("6. RBR 物理规则引擎清洗", size=12),
            ft.Text("7. XGBoost MICE 多重插补 + LLM 推演", size=12),
            ft.Text("8. 终极物理闭环校验 -> 输出 Excel", size=12),
        ]))),
        ft.Container(height=8),
        ft.Container(content=ft.Row([
            ft.Icon(ft.Icons.FOLDER_OPEN, color=ft.Colors.AMBER_300),
            ft.Text(f"pdfs/ 目录: {count_files('pdfs', '.pdf')} 个 PDF 文件", size=13, color=ft.Colors.AMBER_300, weight=ft.FontWeight.BOLD),
        ])),
    ])
    
    # =================================================================
    # TXT 页面
    # =================================================================
    txt_mode_dropdown = ft.Dropdown(
        label="处理模式", width=350, value="train",
        options=[
            ft.dropdown.Option("train", "提取 + train训练新模型 (完整流程)"),
            ft.dropdown.Option("predict", "提取 + predict用已有模型修复 (推荐)"),
            ft.dropdown.Option("extract_only", "仅提取原始数据 (不修复)"),
        ],
    )
    
    txt_page = ft.Column(scroll=ft.ScrollMode.AUTO, expand=True, spacing=4, controls=[
        ft.Text("纯文本直通处理", size=20, weight=ft.FontWeight.BOLD),
        ft.Container(height=4),
        ft.Text("将 .txt 文件放入 txt_inputs/ 目录后运行", size=13, color=ft.Colors.GREY_400),
        ft.Container(height=12),
        txt_mode_dropdown,
        ft.Container(height=8),
        ft.Card(content=ft.Container(padding=16, content=ft.Column(spacing=4, controls=[
            ft.Text("处理流程", size=13, weight=ft.FontWeight.BOLD),
            ft.Text("1. 遍历 txt_inputs/ 读取所有 .txt 文件", size=12),
            ft.Text("2. DeepSeek 文本模型提取 40+ 维参数", size=12),
            ft.Text("3. 生成初始特征矩阵 Excel (原始数据集)", size=12),
            ft.Text("4. 修复引擎 (train/predict 模式可选)", size=12),
            ft.Text("5. 输出修复后特征库 + 运行日志", size=12),
        ]))),
        ft.Container(height=8),
        ft.Card(content=ft.Container(padding=16, content=ft.Column(spacing=4, controls=[
            ft.Text("模式说明", size=13, weight=ft.FontWeight.BOLD),
            ft.Text("  train: 提取后用数据训练新 XGBoost 模型再修复", size=12),
            ft.Text("  predict: 提取后直接用 models/ 已有模型修复 (推荐)", size=12),
            ft.Text("  extract_only: 仅提取原始参数, 不运行修复引擎", size=12),
            ft.Text("  运行日志会自动保存到 outputs/ 目录", size=12, color=ft.Colors.GREEN_300),
        ]))),
        ft.Container(height=8),
        ft.Container(content=ft.Row([
            ft.Icon(ft.Icons.FOLDER_OPEN, color=ft.Colors.CYAN_300),
            ft.Text(f"txt_inputs/ 目录: {count_files('txt_inputs', '.txt')} 个 TXT 文件", size=13, color=ft.Colors.CYAN_300, weight=ft.FontWeight.BOLD),
        ])),
    ])
    
    # =================================================================
    # 融合页面
    # =================================================================
    merge_page = ft.Column(scroll=ft.ScrollMode.AUTO, expand=True, spacing=4, controls=[
        ft.Text("数据集融合工具", size=20, weight=ft.FontWeight.BOLD),
        ft.Container(height=4),
        ft.Text("自动扫描 outputs/ 目录下所有 Excel 并合并", size=13, color=ft.Colors.GREY_400),
        ft.Container(height=12),
        ft.Card(content=ft.Container(padding=16, content=ft.Column(spacing=4, controls=[
            ft.Text("功能说明", size=13, weight=ft.FontWeight.BOLD),
            ft.Text("  - 自动扫描 outputs/*.xlsx (排除 Master)", size=12),
            ft.Text("  - 列维度求并集, 不同批次参数列自动对齐", size=12),
            ft.Text("  - 基于论文来源列自动去重", size=12),
            ft.Text("  - 输出 blasting_CBR_Master.xlsx", size=12),
        ]))),
        ft.Container(height=8),
        ft.Container(content=ft.Row([
            ft.Icon(ft.Icons.AUTO_AWESOME, color=ft.Colors.GREEN_300),
            ft.Text("已自动扫描, 无需手动配置文件列表", size=12, color=ft.Colors.GREEN_300),
        ])),
    ])
    
    # =================================================================
    # 独立修复页面
    # =================================================================
    impute_excel_input = ft.TextField(
        label="输入 Excel 路径", hint_text="outputs/blasting_CBR_Master.xlsx",
        width=500, value="outputs/blasting_CBR_Master.xlsx",
    )
    impute_mode_dropdown = ft.Dropdown(
        label="运行模式", width=200, value="train",
        options=[
            ft.dropdown.Option("train", "train - 训练新模型"),
            ft.dropdown.Option("predict", "predict - 使用已有模型"),
        ],
    )
    
    impute_page = ft.Column(scroll=ft.ScrollMode.AUTO, expand=True, spacing=4, controls=[
        ft.Text("独立数据修复引擎", size=20, weight=ft.FontWeight.BOLD),
        ft.Container(height=4),
        ft.Text("对已有的 Excel 运行五重递进式修复", size=13, color=ft.Colors.GREY_400),
        ft.Container(height=12),
        impute_excel_input,
        ft.Container(height=8),
        impute_mode_dropdown,
        ft.Container(height=8),
        ft.Card(content=ft.Container(padding=16, content=ft.Column(spacing=4, controls=[
            ft.Text("五重修复架构", size=13, weight=ft.FontWeight.BOLD),
            ft.Text("第一重: RBR 硬规则引擎", size=12),
            ft.Text("第二重: 物理推导 + 岩性专家字典", size=12),
            ft.Text("第三重: LLM CoT 深度逻辑重构", size=12),
            ft.Text("第四重: XGBoost MICE 多重插补", size=12),
            ft.Text("第五重: 终极物理闭环校验", size=12),
        ]))),
        ft.Container(height=8),
        ft.Container(content=ft.Row([
            ft.Icon(ft.Icons.MODEL_TRAINING, color=ft.Colors.ORANGE_300),
            ft.Text(f"models/: {len(list_model_files())} 个模型文件", size=13, color=ft.Colors.ORANGE_300, weight=ft.FontWeight.BOLD),
        ])),
    ])
    
    # =================================================================
    # 领域规则页面 (可编辑版)
    # =================================================================
    rules_status_text = ft.Text("", size=12, color=ft.Colors.GREEN_300)
    
    def build_rules_page():
        rules_path = os.path.join(PROJECT_DIR, "domain_rules.json")
        if not os.path.exists(rules_path):
            return ft.Text("未找到 domain_rules.json", color=ft.Colors.RED_300)
        with open(rules_path, "r", encoding="utf-8") as f:
            rules = json.load(f)
        
        # --- 物理常量编辑区 (可增删改) ---
        physics = rules.get("physics", {})
        physics_container = ft.Column(spacing=2)
        
        def make_kv_row(key, val, container, label_prefix=""):
            name_f = ft.TextField(value=str(key), width=200, text_size=12, label="参数名")
            val_f = ft.TextField(value=str(val), width=120, text_size=12, label="值")
            row = ft.Row([name_f, val_f], spacing=4, vertical_alignment=ft.CrossAxisAlignment.CENTER)
            def remove_row(e):
                if row in container.controls:
                    container.controls.remove(row)
                    page.update()
            del_btn = ft.IconButton(icon=ft.Icons.DELETE, icon_color=ft.Colors.RED_300, icon_size=18, on_click=remove_row, tooltip="删除")
            row.controls.append(del_btn)
            container.controls.append(row)
            return name_f, val_f
        
        for k, v in physics.items():
            make_kv_row(k, v, physics_container)
        
        def add_physics_row(e):
            make_kv_row("", "", physics_container)
            page.update()
        
        # --- 安规边界编辑区 (可增删改) ---
        bounds = rules.get("bounds", {})
        bounds_container = ft.Column(spacing=2)
        
        for k, v in bounds.items():
            make_kv_row(k, v, bounds_container)
        
        def add_bounds_row(e):
            make_kv_row("", "", bounds_container)
            page.update()
        
        # --- 岩石专家字典编辑区 ---
        rock_dict = rules.get("rock_expert_dict", {})
        rock_rows_controls = []
        
        def make_rock_row(name, q, r, container):
            name_f = ft.TextField(value=name, width=120, text_size=12, label="岩性")
            q_f = ft.TextField(value=str(q), width=100, text_size=12, label="q_base")
            r_f = ft.TextField(value=str(r), width=100, text_size=12, label="R_coef")
            row = ft.Row([name_f, q_f, r_f], spacing=4, vertical_alignment=ft.CrossAxisAlignment.CENTER)
            def remove_row(e):
                if row in container.controls:
                    container.controls.remove(row)
                    page.update()
            del_btn = ft.IconButton(icon=ft.Icons.DELETE, icon_color=ft.Colors.RED_300, icon_size=18, on_click=remove_row, tooltip="删除")
            row.controls.append(del_btn)
            container.controls.append(row)
            return name_f, q_f, r_f
        
        rock_container = ft.Column(spacing=2)
        rock_data_refs = []
        for rock, params in rock_dict.items():
            nf, qf, rf = make_rock_row(rock, params.get("q_base",""), params.get("R_coef",""), rock_container)
            rock_data_refs.append((nf, qf, rf))
        
        def add_rock_row(e):
            nf, qf, rf = make_rock_row("", "", "", rock_container)
            rock_data_refs.append((nf, qf, rf))
            page.update()
        
        # --- 保存逻辑 ---
        def read_kv_container(container):
            """从容器中读取所有 key-value 行"""
            result = {}
            for child in container.controls:
                if isinstance(child, ft.Row) and len(child.controls) >= 2:
                    k = child.controls[0].value.strip()
                    v = child.controls[1].value.strip()
                    if k and v:
                        try:
                            result[k] = float(v)
                        except ValueError:
                            result[k] = v
            return result
        
        def save_rules(e):
            try:
                # 从容器中读取物理常量和安规边界
                new_physics = read_kv_container(physics_container)
                new_bounds = read_kv_container(bounds_container)
                
                # 保留原始结构中的其他字段
                with open(rules_path, "r", encoding="utf-8") as f:
                    old_rules = json.load(f)
                
                # 读取岩石字典
                new_rock = {}
                for child in rock_container.controls:
                    if isinstance(child, ft.Row) and len(child.controls) >= 3:
                        name_val = child.controls[0].value.strip()
                        q_val = child.controls[1].value.strip()
                        r_val = child.controls[2].value.strip()
                        if name_val and q_val and r_val:
                            new_rock[name_val] = {"q_base": float(q_val), "R_coef": float(r_val)}
                
                old_rules["physics"] = new_physics
                old_rules["bounds"] = new_bounds
                old_rules["rock_expert_dict"] = new_rock
                
                with open(rules_path, "w", encoding="utf-8") as f:
                    json.dump(old_rules, f, ensure_ascii=False, indent=2)
                
                rules_status_text.value = f"[OK] 规则已保存! ({datetime.now().strftime('%H:%M:%S')})"
                rules_status_text.color = ft.Colors.GREEN_300
                page.update()
            except Exception as ex:
                rules_status_text.value = f"[ERROR] 保存失败: {ex}"
                rules_status_text.color = ft.Colors.RED_300
                page.update()
        
        def reload_rules(e):
            content_area.content = build_rules_page()
            page.update()
        
        # --- 布局 ---
        return ft.Column(scroll=ft.ScrollMode.AUTO, expand=True, spacing=12, controls=[
            ft.Row([
                ft.Text("领域知识引擎 (可编辑)", size=20, weight=ft.FontWeight.BOLD),
                ft.Container(expand=True),
                rules_status_text,
                ft.ElevatedButton("重新加载", icon=ft.Icons.REFRESH, on_click=reload_rules, color=ft.Colors.CYAN_300),
                ft.ElevatedButton("保存规则", icon=ft.Icons.SAVE, on_click=save_rules, 
                                  color=ft.Colors.WHITE, bgcolor=ft.Colors.GREEN_700),
            ]),
            ft.Text("修改后点击「保存规则」，修复引擎会实时使用新边界", size=11, color=ft.Colors.GREY_500),
            
            ft.Card(content=ft.Container(padding=16, content=ft.Column(spacing=4, controls=[
                ft.Row([
                    ft.Text("物理常量", size=15, weight=ft.FontWeight.BOLD),
                    ft.Container(expand=True),
                    ft.ElevatedButton("添加参数", icon=ft.Icons.ADD, on_click=add_physics_row,
                                      color=ft.Colors.WHITE, bgcolor=ft.Colors.BLUE_700),
                ]),
                ft.Row([ft.Text("参数名", width=200, weight=ft.FontWeight.BOLD, size=12),
                         ft.Text("值", width=120, weight=ft.FontWeight.BOLD, size=12)], spacing=4),
                physics_container,
            ]))),
            
            ft.Card(content=ft.Container(padding=16, content=ft.Column(spacing=4, controls=[
                ft.Row([
                    ft.Text("安规边界约束", size=15, weight=ft.FontWeight.BOLD),
                    ft.Container(expand=True),
                    ft.ElevatedButton("添加参数", icon=ft.Icons.ADD, on_click=add_bounds_row,
                                      color=ft.Colors.WHITE, bgcolor=ft.Colors.BLUE_700),
                ]),
                ft.Text("修改这些值会直接影响修复引擎的边界钳制", size=11, color=ft.Colors.AMBER_300),
                ft.Row([ft.Text("参数名", width=200, weight=ft.FontWeight.BOLD, size=12),
                         ft.Text("值", width=120, weight=ft.FontWeight.BOLD, size=12)], spacing=4),
                bounds_container,
            ]))),
            
            ft.Card(content=ft.Container(padding=16, content=ft.Column(spacing=4, controls=[
                ft.Row([
                    ft.Text("岩石力学专家字典", size=15, weight=ft.FontWeight.BOLD),
                    ft.Container(expand=True),
                    ft.ElevatedButton("添加岩性", icon=ft.Icons.ADD, on_click=add_rock_row, 
                                      color=ft.Colors.WHITE, bgcolor=ft.Colors.BLUE_700),
                ]),
                ft.Text("修改 q_base 和 R_coefficient 会影响物理推导引擎", size=11, color=ft.Colors.AMBER_300),
                ft.Row([ft.Text("岩性", width=120, weight=ft.FontWeight.BOLD, size=12), 
                         ft.Text("q_base", width=100, weight=ft.FontWeight.BOLD, size=12),
                         ft.Text("R_coef", width=100, weight=ft.FontWeight.BOLD, size=12)], spacing=4),
                rock_container,
            ]))),
        ])
    
    rules_page = build_rules_page()
    
    # =================================================================
    # 输出页面
    # =================================================================
    def build_outputs_page():
        output_files = list_output_files()
        if not output_files:
            return ft.Column(controls=[
                ft.Text("输出文件管理", size=20, weight=ft.FontWeight.BOLD),
                ft.Container(height=20),
                ft.Text("outputs/ 目录为空", size=13, color=ft.Colors.GREY_500),
            ])
        rows = []
        for f in output_files:
            rows.append(ft.DataRow(cells=[
                ft.DataCell(ft.Text(f["name"], size=11, selectable=True)),
                ft.DataCell(ft.Text(f["size"], size=11)),
                ft.DataCell(ft.Text(f["time"], size=11)),
            ]))
        return ft.Column(scroll=ft.ScrollMode.AUTO, expand=True, spacing=4, controls=[
            ft.Text("输出文件管理", size=20, weight=ft.FontWeight.BOLD),
            ft.Text(f"共 {len(output_files)} 个文件", size=13, color=ft.Colors.GREY_400),
            ft.Container(height=8),
            ft.DataTable(
                columns=[ft.DataColumn(ft.Text("文件名")), ft.DataColumn(ft.Text("大小")), ft.DataColumn(ft.Text("时间"))],
                rows=rows, border=ft.border.all(1, ft.Colors.WHITE24),
            ),
        ])
    
    # =================================================================
    # 内容区
    # =================================================================
    content_area = ft.Container(content=build_dashboard(), expand=True, padding=ft.Padding(20, 20, 20, 20))
    
    def on_tab_change(e):
        idx = e.control.selected_index
        current_tab[0] = idx
        if idx == 0:
            content_area.content = build_dashboard()
        elif idx == 1:
            content_area.content = pdf_page
        elif idx == 2:
            content_area.content = txt_page
        elif idx == 3:
            content_area.content = merge_page
        elif idx == 4:
            content_area.content = impute_page
        elif idx == 5:
            content_area.content = build_rules_page()
        elif idx == 6:
            content_area.content = build_outputs_page()
        page.update()
    
    def run_selected_pipeline():
        idx = current_tab[0]
        
        if idx == 0:
            append_log("[TIP] 请在左侧选择功能模块")
            return
        
        elif idx == 1:  # PDF
            mode = pdf_mode_dropdown.value
            if mode == "full_pipeline":
                keyword = pdf_keyword_input.value.strip() or "立井爆破"
                pages = pdf_pages_input.value.strip() or "5"
                # 写一个临时脚本来运行带参数的爬虫流水线
                script = f"""
import sys, os
sys.path.insert(0, r"{PROJECT_DIR}")
os.chdir(r"{PROJECT_DIR}")
from scraper_module import auto_download_cnki
from extractor_module import run_extraction_and_imputation
from config import TEXT_API_KEY as DEEPSEEK_API_KEY
import time

print("阶段1: 知网爬虫 | 关键词={keyword} | 页数={pages}")
auto_download_cnki(keyword="{keyword}", max_pages={pages})
time.sleep(3)

if not os.path.exists("pdfs") or len(os.listdir("pdfs")) == 0:
    print("[ERROR] pdfs 目录为空, 流水线终止")
else:
    print("阶段2+3: 特征提取与数据修复")
    final = run_extraction_and_imputation(deepseek_key=DEEPSEEK_API_KEY)
    print(f"[DONE] 输出: {{final}}")
"""
                run_command_async([sys.executable, "-c", script], open_terminal=True)
            else:
                run_command_async([sys.executable, "-u", "main_pipelinepdf.py"])
        
        elif idx == 2:  # TXT
            txt_mode = txt_mode_dropdown.value
            if txt_mode == "extract_only":
                script = f"""
import sys, os, pandas as pd, asyncio
sys.path.insert(0, r"{PROJECT_DIR}")
os.chdir(r"{PROJECT_DIR}")
from extractor_module import extract_text_params
from config import TXT_DIR, OUTPUT_DIR

if not os.path.exists(OUTPUT_DIR): os.makedirs(OUTPUT_DIR)
extracted = []
for fn in sorted(os.listdir(TXT_DIR)):
    if fn.lower().endswith(".txt"):
        with open(os.path.join(TXT_DIR, fn), "r", encoding="utf-8") as f:
            txt = f.read()
        print(f"[提取] {{fn}} ({{len(txt)}} 字符)")
        params = asyncio.run(extract_text_params(txt, fn))
        if params:
            params["论文来源"] = fn
            extracted.append(params)
            print(f"  -> 提取到 {{len(params)}} 项参数")
        else:
            print(f"  -> 未提取到有效数据")

if extracted:
    df = pd.DataFrame(extracted)
    cols = ['论文来源'] + [c for c in df.columns if c != '论文来源']
    df = df[cols]
    out = os.path.join(OUTPUT_DIR, "blasting_CBR_from_txt_raw.xlsx")
    df.to_excel(out, index=False)
    print(f"[DONE] 原始数据集已保存: {{out}}")
    print(f"[INFO] 共 {{len(df)}} 行, {{len(df.columns)}} 列")
else:
    print("[ERROR] 未提取到任何有效数据")
"""
                run_command_async([sys.executable, "-c", script])
            else:
                # train 或 predict 模式，使用对应的 run_txt_pipeline
                # 创建一个临时脚本，支持指定 mode
                script = f"""
import sys, os, pandas as pd, asyncio
sys.path.insert(0, r"{PROJECT_DIR}")
os.chdir(r"{PROJECT_DIR}")
from extractor_module import extract_text_params
from imputation_engine import BlastingDataImputer
from config import TEXT_API_KEY as DEEPSEEK_API_KEY, TXT_DIR, OUTPUT_DIR

if not os.path.exists(OUTPUT_DIR): os.makedirs(OUTPUT_DIR)
if not os.path.exists(TXT_DIR):
    print("[ERROR] txt_inputs/ 目录不存在")
    sys.exit(1)

extracted = []
for fn in sorted(os.listdir(TXT_DIR)):
    if fn.lower().endswith(".txt"):
        with open(os.path.join(TXT_DIR, fn), "r", encoding="utf-8") as f:
            txt = f.read()
        print(f"[提取] {{fn}} ({{len(txt)}} 字符)")
        params = asyncio.run(extract_text_params(txt, fn))
        if params:
            params["论文来源"] = fn
            extracted.append(params)
            print(f"  -> 提取到 {{len(params)}} 项参数")

if not extracted:
    print("[ERROR] 未提取到有效数据")
    sys.exit(1)

df = pd.DataFrame(extracted)
cols = ['论文来源'] + [c for c in df.columns if c != '论文来源']
df = df[cols]
raw_excel = os.path.join(OUTPUT_DIR, "blasting_CBR_from_txt.xlsx")
df.to_excel(raw_excel, index=False)
print(f"[提取完成] 原始数据集: {{raw_excel}} ({{len(df)}} 行)")

print(f"\\n[修复引擎] 启动 {txt_mode} 模式...")
imputer = BlastingDataImputer(api_key=DEEPSEEK_API_KEY, model_dir="models/")
final = imputer.process_excel(raw_excel, mode="{txt_mode}")
print(f"[DONE] 最终输出: {{final}}")
"""
                run_command_async([sys.executable, "-c", script])
        
        elif idx == 3:  # 融合
            run_command_async([sys.executable, "-u", "merge_datasets.py"])
        
        elif idx == 4:  # 独立修复
            excel_path = impute_excel_input.value.strip()
            mode = impute_mode_dropdown.value
            if not excel_path:
                append_log("[ERROR] 请输入 Excel 路径")
                return
            # 自动补全路径：如果只是文件名没有目录前缀，自动加上 outputs/
            script = f"""
import sys, os
sys.path.insert(0, r"{PROJECT_DIR}")
os.chdir(r"{PROJECT_DIR}")
from config import TEXT_API_KEY
from imputation_engine import BlastingDataImputer

excel_path = "{excel_path}"
# 自动补全路径
if not os.path.sep in excel_path and not excel_path.startswith("outputs"):
    excel_path = os.path.join("outputs", excel_path)
if not os.path.exists(excel_path):
    # 再试一次在当前目录找
    if os.path.exists(os.path.join(r"{PROJECT_DIR}", excel_path)):
        excel_path = os.path.join(r"{PROJECT_DIR}", excel_path)
    else:
        print(f"[ERROR] 找不到文件: {{excel_path}}")
        # 列出 outputs 目录的 xlsx 文件供参考
        out_dir = os.path.join(r"{PROJECT_DIR}", "outputs")
        if os.path.exists(out_dir):
            xlsx_files = [f for f in os.listdir(out_dir) if f.endswith('.xlsx')]
            if xlsx_files:
                print("[INFO] outputs/ 目录下的可用文件:")
                for f in xlsx_files:
                    print(f"  - {{f}}")
        sys.exit(1)

print(f"[INFO] 输入文件: {{excel_path}}")
print(f"[INFO] 模式: {mode}")
imputer = BlastingDataImputer(api_key=TEXT_API_KEY, model_dir="models/")
imputer.process_excel(excel_path, mode="{mode}")
"""
            run_command_async([sys.executable, "-c", script])
        
        elif idx == 5:
            append_log("[TIP] 领域规则为只读页面")
        
        elif idx == 6:
            out_dir = os.path.join(PROJECT_DIR, "outputs")
            if os.path.exists(out_dir):
                os.startfile(out_dir)
    
    # =================================================================
    # 导航栏
    # =================================================================
    nav_rail = ft.NavigationRail(
        selected_index=0, label_type=ft.NavigationRailLabelType.ALL,
        min_width=100, min_extended_width=200,
        destinations=[
            ft.NavigationRailDestination(icon=ft.Icons.DASHBOARD_OUTLINED, selected_icon=ft.Icons.DASHBOARD, label="仪表盘"),
            ft.NavigationRailDestination(icon=ft.Icons.PICTURE_AS_PDF_OUTLINED, selected_icon=ft.Icons.PICTURE_AS_PDF, label="PDF 处理"),
            ft.NavigationRailDestination(icon=ft.Icons.TEXT_SNIPPET_OUTLINED, selected_icon=ft.Icons.TEXT_SNIPPET, label="TXT 处理"),
            ft.NavigationRailDestination(icon=ft.Icons.MERGE_OUTLINED, selected_icon=ft.Icons.MERGE, label="数据融合"),
            ft.NavigationRailDestination(icon=ft.Icons.BUILD_OUTLINED, selected_icon=ft.Icons.BUILD, label="独立修复"),
            ft.NavigationRailDestination(icon=ft.Icons.RULE_OUTLINED, selected_icon=ft.Icons.RULE, label="领域规则"),
            ft.NavigationRailDestination(icon=ft.Icons.FOLDER_OPEN_OUTLINED, selected_icon=ft.Icons.FOLDER_OPEN, label="输出文件"),
        ],
        on_change=on_tab_change,
    )
    
    # =================================================================
    # 布局
    # =================================================================
    main_content = ft.Row([
        nav_rail,
        ft.VerticalDivider(width=1),
        ft.Column([
            content_area,
            ft.Divider(height=1),
            toolbar,
            ft.Container(
                content=log_container, height=200,
                padding=ft.Padding(16, 8, 16, 8),
                bgcolor=ft.Colors.with_opacity(0.03, ft.Colors.WHITE),
            ),
        ], expand=True, spacing=0),
    ], expand=True)
    
    page.add(main_content)
    
    def refresh_dashboard():
        if current_tab[0] == 0:
            content_area.content = build_dashboard()
            page.update()


if __name__ == "__main__":
    ft.run(main)