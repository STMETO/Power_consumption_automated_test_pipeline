"""
功耗测试主窗口 - 精简版
基于Tkinter的主界面实现
"""

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import json
import os
import sys
import subprocess
import threading
from pathlib import Path

# 添加项目根目录到sys.path
current_file = Path(__file__).resolve()
project_root = current_file.parent.parent.parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.app.PowerConsumption.PowerConsumption_UI.config_editor import ConfigEditor
from src.app.PowerConsumption.PowerConsumption_jsonManager import PowerConsumptionJsonManager
from src.utils.logger import Logger


class PowerConsumptionMainWindow:
    """功耗测试主窗口类"""
    
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("功耗测试工具 v1.0")
        # 自适应分辨率：兼容 1920x1080 台式 与 3720x1920 笔记本等高分辨率
        try:
            self.root.update_idletasks()
            sw = self.root.winfo_screenwidth()
            sh = self.root.winfo_screenheight()
            if sw >= 100 and sh >= 100:
                # 宽度：1080p 约 1200，3720 屏约 1400；高度：保证底部“开始测试”等露出
                w = max(1000, min(1400, int(sw * 0.65)))
                h = max(900, min(1100, int(sh * 0.88)))
                self.root.geometry(f"{w}x{h}")
            else:
                self.root.geometry("1200x950")
            self.root.minsize(800, 600)
        except Exception:
            self.root.geometry("1200x950")
            self.root.minsize(800, 600)
        
        # 配置编辑器单例引用（仅允许一个配置编辑器窗口）
        self._config_editor = None
        
        # 项目根目录
        self.project_root = project_root
        
        # 设备名称（从环境变量或默认值）
        self.dev_name = os.environ.get('FW_DEV', 'Z03')
        
        # 配置文件路径
        self.config_path = self.project_root / "data" / self.dev_name / "power_consumption.json"
        
        # 日志记录器
        self.logger = Logger()
        
        # JSON管理器
        self.json_manager = PowerConsumptionJsonManager(dev_name=self.dev_name, logger=self.logger)
        
        # 配置数据
        self.config_data = {}
        
        # 测试状态
        self.is_testing = False
        self.test_process = None
        
        # 固件队列
        self.firmware_queue = []  # 存储固件URL或本地路径的队列
        self.current_queue_index = 0  # 当前队列索引
        self.queue_mode = False  # 是否使用队列模式
        
        # 创建界面
        self.create_widgets()
        
        # 加载配置
        self.load_config()
    
    def create_widgets(self):
        """创建界面组件"""
        
        # 创建Notebook（Tab控件）
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # 创建"挡位功耗测试"Tab
        self.create_power_test_tab()
    
    def create_power_test_tab(self):
        """创建挡位功耗测试Tab"""
        power_tab = ttk.Frame(self.notebook)
        self.notebook.add(power_tab, text="挡位功耗测试")
        
        # 顶部工具栏
        toolbar = ttk.Frame(power_tab, padding="5")
        toolbar.pack(fill=tk.X)
        
        # 设备选择
        ttk.Label(toolbar, text="设备类型:", font=("Arial", 9)).pack(side=tk.LEFT, padx=5)
        
        # 创建设备名称文本框
        self.device_var = tk.StringVar(value=self.dev_name)
        device_entry = ttk.Entry(
            toolbar, 
            textvariable=self.device_var,
            width=12
        )
        device_entry.pack(side=tk.LEFT, padx=5)
        
        # 绑定设备变更事件（当文本框失去焦点时）
        device_entry.bind('<FocusOut>', lambda e: self.on_device_changed())
        
        # 分隔符
        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=8)
        
        # 配置编辑器按钮
        ttk.Button(toolbar, text="编辑配置", command=self.open_config_editor, width=12).pack(side=tk.LEFT, padx=5)
        
        # 重新加载配置按钮
        ttk.Button(toolbar, text="重新加载配置", command=self.load_config, width=12).pack(side=tk.LEFT, padx=5)
        
        # 状态信息
        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=8)
        self.status_info_var = tk.StringVar(value="就绪")
        status_info_label = ttk.Label(toolbar, textvariable=self.status_info_var, font=("Arial", 9))
        status_info_label.pack(side=tk.LEFT, padx=5)
        
        # 主内容区域
        main_container = ttk.Frame(power_tab)
        main_container.pack(fill=tk.BOTH, expand=True, padx=8, pady=5)
        
        # 左侧配置面板
        left_panel = ttk.Frame(main_container)
        left_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))
        
        # 创建配置编辑区域
        self.create_config_edit_area(left_panel)
        
        # 右侧测试控制面板
        right_panel = ttk.LabelFrame(main_container, text="测试控制台", padding="8")
        right_panel.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        
        # 创建测试控制区域
        self.create_test_control_area(right_panel)
        
        # 底部按钮和状态栏区域
        bottom_frame = ttk.Frame(power_tab, padding="5")
        bottom_frame.pack(side=tk.BOTTOM, fill=tk.X)
        
        # 操作按钮
        button_container = ttk.Frame(bottom_frame)
        button_container.pack(side=tk.TOP, pady=3)
        
        self.start_button = ttk.Button(button_container, text="开始测试", command=self.start_test, width=12)
        self.start_button.pack(side=tk.LEFT, padx=8)
        
        self.stop_button = ttk.Button(button_container, text="停止测试", command=self.stop_test, state=tk.DISABLED, width=12)
        self.stop_button.pack(side=tk.LEFT, padx=8)
        
        ttk.Button(button_container, text="清空日志", command=self.clear_log, width=12).pack(side=tk.LEFT, padx=8)
        
        # 状态栏
        self.status_var = tk.StringVar(value="就绪")
        status_bar = ttk.Label(bottom_frame, textvariable=self.status_var, relief=tk.SUNKEN, padding="4")
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)
    
    def create_config_edit_area(self, parent):
        """创建配置编辑区域"""
        
        # 1. Record挡位配置
        record_frame = ttk.LabelFrame(parent, text="Record挡位配置", padding="5")
        record_frame.pack(fill=tk.X, pady=2)
        
        # 挡位列表
        list_frame = ttk.Frame(record_frame)
        list_frame.pack(fill=tk.X, pady=2)
        
        columns = ("name", "duration", "width", "height", "record")
        self.record_tree = ttk.Treeview(list_frame, columns=columns, show="headings", height=3)
        
        self.record_tree.heading("name", text="名称")
        self.record_tree.heading("duration", text="时长(秒)")
        self.record_tree.heading("width", text="宽度")
        self.record_tree.heading("height", text="高度")
        self.record_tree.heading("record", text="录制")
        
        self.record_tree.column("name", width=120)
        self.record_tree.column("duration", width=70)
        self.record_tree.column("width", width=70)
        self.record_tree.column("height", width=70)
        self.record_tree.column("record", width=50)
        
        scrollbar1 = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.record_tree.yview)
        self.record_tree.configure(yscrollcommand=scrollbar1.set)
        
        self.record_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar1.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 绑定双击事件
        self.record_tree.bind("<Double-1>", self.on_record_double_click)
        
        # 2. 固件配置（压缩布局）
        firmware_frame = ttk.LabelFrame(parent, text="固件配置", padding="5")
        firmware_frame.pack(fill=tk.X, pady=2)
        
        # 第一行：固件URL和保存按钮
        ttk.Label(firmware_frame, text="固件URL/本地路径:", font=("Arial", 9)).grid(row=0, column=0, sticky=tk.W, pady=1)
        self.firmware_url_var = tk.StringVar()
        firmware_url_entry = ttk.Entry(firmware_frame, textvariable=self.firmware_url_var, width=45)
        firmware_url_entry.grid(row=0, column=1, sticky=tk.W, padx=5, pady=1)
        ttk.Button(firmware_frame, text="保存", command=self.save_firmware_config, width=10).grid(row=0, column=2, sticky=tk.W, padx=5, pady=1)
        
        # 第二行：超时时间和验证版本
        ttk.Label(firmware_frame, text="OTA超时(秒):", font=("Arial", 9)).grid(row=1, column=0, sticky=tk.W, pady=1)
        self.firmware_timeout_var = tk.StringVar(value="900")
        ttk.Entry(firmware_frame, textvariable=self.firmware_timeout_var, width=12).grid(row=1, column=1, sticky=tk.W, padx=5, pady=1)
        self.firmware_verify_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(firmware_frame, text="验证版本", variable=self.firmware_verify_var).grid(row=1, column=2, sticky=tk.W, padx=5, pady=1)
        
        # 3. 环境设置
        env_frame = ttk.LabelFrame(parent, text="环境设置", padding="5")
        env_frame.pack(fill=tk.X, pady=2)
        
        # 使用紧凑的两列布局
        row = 0
        col = 0
        
        self.env_wifi_var = tk.BooleanVar()
        ttk.Checkbutton(env_frame, text="WiFi", variable=self.env_wifi_var).grid(
            row=row, column=col, sticky=tk.W, padx=5, pady=1
        )
        col += 1
        
        self.env_bluetooth_var = tk.BooleanVar()
        ttk.Checkbutton(env_frame, text="蓝牙", variable=self.env_bluetooth_var).grid(
            row=row, column=col, sticky=tk.W, padx=5, pady=1
        )
        col += 1
        
        self.env_usb_power_var = tk.BooleanVar()
        ttk.Checkbutton(env_frame, text="USB供电", variable=self.env_usb_power_var).grid(
            row=row, column=col, sticky=tk.W, padx=5, pady=1
        )
        col += 1
        
        self.env_backlight_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(env_frame, text="背光", variable=self.env_backlight_var).grid(
            row=row, column=col, sticky=tk.W, padx=5, pady=1
        )
        col += 1
        
        self.env_kernel_log_var = tk.BooleanVar()
        ttk.Checkbutton(env_frame, text="Kernel日志", variable=self.env_kernel_log_var).grid(
            row=row, column=col, sticky=tk.W, padx=5, pady=1
        )
        col = 0
        row += 1
        
        self.env_logd_var = tk.BooleanVar()
        ttk.Checkbutton(env_frame, text="Logd", variable=self.env_logd_var).grid(
            row=row, column=col, sticky=tk.W, padx=5, pady=1
        )
        col += 1
        
        self.env_camx_log_var = tk.BooleanVar()
        ttk.Checkbutton(env_frame, text="CamX日志", variable=self.env_camx_log_var).grid(
            row=row, column=col, sticky=tk.W, padx=5, pady=1
        )
        col += 1
        
        self.env_device_sleep_var = tk.BooleanVar()
        ttk.Checkbutton(env_frame, text="设备休眠", variable=self.env_device_sleep_var).grid(
            row=row, column=col, sticky=tk.W, padx=5, pady=1
        )
        col += 1
        
        # 保存环境设置按钮
        ttk.Button(env_frame, text="保存", command=self.save_env_config, width=10).grid(
            row=row, column=col, sticky=tk.W, padx=5, pady=1
        )
        
        # 4. QEPM设置
        qepm_frame = ttk.LabelFrame(parent, text="QEPM设置", padding="5")
        qepm_frame.pack(fill=tk.X, pady=2)
        
        # QEPM URL设置
        ttk.Label(qepm_frame, text="QEPM URL:", font=("Arial", 9)).grid(row=0, column=0, sticky=tk.W, pady=1)
        self.qepm_url_var = tk.StringVar()
        qepm_url_entry = ttk.Entry(qepm_frame, textvariable=self.qepm_url_var, width=45)
        qepm_url_entry.grid(row=0, column=1, sticky=tk.W, padx=5, pady=1)
        
        # QEPM原始数据存储路径设置
        ttk.Label(qepm_frame, text="EPM原始数据存储路径:", font=("Arial", 9)).grid(row=1, column=0, sticky=tk.W, pady=1)
        self.data_path_var = tk.StringVar()
        data_path_entry = ttk.Entry(qepm_frame, textvariable=self.data_path_var, width=45)
        data_path_entry.grid(row=1, column=1, sticky=tk.W, padx=5, pady=1)
        
        # 保存按钮
        ttk.Button(qepm_frame, text="保存", command=self.save_qepm_config, width=10).grid(
            row=0, column=2, rowspan=2, sticky=tk.W+tk.N, padx=5, pady=1
        )
        
        # 5. 飞书配置
        feishu_frame = ttk.LabelFrame(parent, text="飞书配置", padding="5")
        feishu_frame.pack(fill=tk.X, pady=2)
        
        self.feishu_enabled_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(feishu_frame, text="启用飞书通知", variable=self.feishu_enabled_var).grid(
            row=0, column=0, sticky=tk.W, padx=5, pady=1
        )
        
        self.feishu_upload_enabled_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(feishu_frame, text="启用文件上传", variable=self.feishu_upload_enabled_var).grid(
            row=0, column=1, sticky=tk.W, padx=5, pady=1
        )
        
        # 保存飞书配置按钮
        ttk.Button(feishu_frame, text="保存", command=self.save_feishu_config, width=10).grid(
            row=0, column=2, sticky=tk.W, padx=5, pady=1
        )
        
        # 6. 测试配置
        test_config_frame = ttk.LabelFrame(parent, text="测试配置", padding="5")
        test_config_frame.pack(fill=tk.X, pady=2)
        
        # 配置名称选择
        ttk.Label(test_config_frame, text="配置名称:", font=("Arial", 9)).grid(row=0, column=0, sticky=tk.W, pady=1)
        self.config_name_var = tk.StringVar(value=os.environ.get('RECORD_CONFIG_NAME', ''))
        self.config_name_combo = ttk.Combobox(test_config_frame, textvariable=self.config_name_var, width=25)
        self.config_name_combo.grid(row=0, column=1, sticky=tk.W, padx=5, pady=1)
        
        # 全部挡位测试选项
        self.test_all_var = tk.BooleanVar()
        ttk.Checkbutton(test_config_frame, text="全部挡位测试 (testall)", variable=self.test_all_var,
                       command=self.on_test_all_changed).grid(row=1, column=0, columnspan=2, sticky=tk.W, pady=1)
        
        # 7. 固件队列
        queue_frame = ttk.LabelFrame(parent, text="固件队列（按顺序测试，队列中的固件优先）", padding="5")
        queue_frame.pack(fill=tk.X, pady=2)
        
        # 队列输入区域
        input_frame = ttk.Frame(queue_frame)
        input_frame.pack(fill=tk.X, pady=2)
        
        ttk.Label(input_frame, text="固件URL/本地路径:", font=("Arial", 9)).pack(side=tk.LEFT, padx=5)
        self.queue_input_var = tk.StringVar()
        queue_input_entry = ttk.Entry(input_frame, textvariable=self.queue_input_var, width=40)
        queue_input_entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        
        ttk.Button(input_frame, text="添加到队列", command=self.add_to_queue, width=12).pack(side=tk.LEFT, padx=5)
        
        # 队列列表
        list_frame = ttk.Frame(queue_frame)
        list_frame.pack(fill=tk.X, pady=2)
        
        columns = ("index", "firmware_path")
        self.queue_tree = ttk.Treeview(list_frame, columns=columns, show="headings", height=2)
        
        self.queue_tree.heading("index", text="序号")
        self.queue_tree.heading("firmware_path", text="固件URL/本地路径")
        
        self.queue_tree.column("index", width=50, minwidth=50, stretch=tk.NO)
        # firmware_path列设置为可滚动，设置较大的初始宽度以支持长路径
        # 当内容超出显示区域时，会出现水平滚动条
        self.queue_tree.column("firmware_path", width=600, minwidth=200, stretch=tk.NO)
        
        # 垂直滚动条
        scrollbar_queue_v = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.queue_tree.yview)
        self.queue_tree.configure(yscrollcommand=scrollbar_queue_v.set)
        
        # 水平滚动条
        scrollbar_queue_h = ttk.Scrollbar(list_frame, orient=tk.HORIZONTAL, command=self.queue_tree.xview)
        self.queue_tree.configure(xscrollcommand=scrollbar_queue_h.set)
        
        # 使用grid布局以更好地控制滚动条位置
        self.queue_tree.grid(row=0, column=0, sticky="nsew")
        scrollbar_queue_v.grid(row=0, column=1, sticky="ns")
        scrollbar_queue_h.grid(row=1, column=0, sticky="ew")
        
        # 配置grid权重，使Treeview可以扩展
        list_frame.grid_rowconfigure(0, weight=1)
        list_frame.grid_columnconfigure(0, weight=1)
        
        # 绑定双击事件（删除选中项）
        self.queue_tree.bind("<Double-1>", self.on_queue_double_click)
        
        # 队列操作按钮
        queue_button_frame = ttk.Frame(queue_frame)
        queue_button_frame.pack(fill=tk.X, pady=2)
        
        ttk.Button(queue_button_frame, text="删除选中", command=self.remove_from_queue, width=12).pack(side=tk.LEFT, padx=3)
        ttk.Button(queue_button_frame, text="清空队列", command=self.clear_queue, width=12).pack(side=tk.LEFT, padx=3)
        
        # 队列模式选项
        self.queue_mode_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(queue_frame, text="使用队列模式（按顺序测试队列中的固件）", 
                       variable=self.queue_mode_var, command=self.on_queue_mode_changed).pack(side=tk.LEFT, padx=5, pady=1)
    
    def create_test_control_area(self, parent):
        """创建测试控制区域"""
        
        # 测试状态
        self.test_status_var = tk.StringVar(value="就绪")
        status_label = ttk.Label(parent, textvariable=self.test_status_var, font=("Arial", 10, "bold"))
        status_label.pack(pady=3)
        
        # 日志区域
        log_frame = ttk.LabelFrame(parent, text="测试日志", padding="8")
        log_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD, width=55, height=20)
        self.log_text.pack(fill=tk.BOTH, expand=True)
        self.log_text.config(state=tk.DISABLED)
        
        # 日志控制按钮
        button_frame = ttk.Frame(log_frame)
        button_frame.pack(pady=3)
        
        ttk.Button(button_frame, text="导出日志", command=self.export_log, width=10).pack(side=tk.LEFT, padx=5)
    
    def scan_available_devices(self):
        """扫描可用的设备目录"""
        data_dir = self.project_root / "data"
        devices = []
        if data_dir.exists():
            for item in data_dir.iterdir():
                if item.is_dir() and (item / "power_consumption.json").exists():
                    devices.append(item.name)
        return sorted(devices) if devices else ['Z03']
    
    def on_device_changed(self):
        """设备类型改变时"""
        new_dev_name = self.device_var.get()
        if new_dev_name != self.dev_name:
            self.dev_name = new_dev_name
            self.config_path = self.project_root / "data" / self.dev_name / "power_consumption.json"
            
            # 重新初始化JSON管理器
            self.json_manager = PowerConsumptionJsonManager(dev_name=self.dev_name, logger=self.logger)
            
            # 重新加载配置
            self.load_config()
    
    def on_test_all_changed(self):
        """全部挡位测试选项改变时"""
        if self.test_all_var.get():
            self.config_name_var.set("testall")
            self.config_name_combo.config(state='disabled')
        else:
            self.config_name_combo.config(state='normal')
            if self.config_name_var.get() == "testall":
                self.config_name_var.set("")
    
    def on_record_double_click(self, event):
        """双击挡位时，设置为当前配置"""
        selection = self.record_tree.selection()
        if selection:
            item = self.record_tree.item(selection[0])
            record_name = item['values'][0]
            self.test_all_var.set(False)
            self.config_name_combo.config(state='normal')
            self.config_name_var.set(record_name)
    
    def save_firmware_config(self):
        """保存固件配置"""
        try:
            if not self.config_data:
                messagebox.showwarning("警告", "请先加载配置")
                return
            
            firmware = {
                'download_url': self.firmware_url_var.get().strip(),
                'timeout': int(self.firmware_timeout_var.get()) if self.firmware_timeout_var.get().strip() else 900,
                'verify_version': self.firmware_verify_var.get()
            }
            self.config_data['firmware'] = firmware
            self.json_manager.write_json(self.config_data, self.config_path, indent=4, ensure_ascii=False)
            self.status_info_var.set("固件配置已保存")
            messagebox.showinfo("成功", "固件配置已保存")
        except Exception as e:
            messagebox.showerror("错误", f"保存固件配置失败: {e}")
    
    def save_env_config(self):
        """保存环境设置"""
        try:
            if not self.config_data:
                messagebox.showwarning("警告", "请先加载配置")
                return
            
            setenv = {
                'wifi': self.env_wifi_var.get(),
                'bluetooth': self.env_bluetooth_var.get(),
                'usb_power': self.env_usb_power_var.get(),
                'backlight': self.env_backlight_var.get(),
                'kernel_log': self.env_kernel_log_var.get(),
                'logd': self.env_logd_var.get(),
                'camx_log': self.env_camx_log_var.get(),
                'device_sleep': self.env_device_sleep_var.get()
            }
            self.config_data['setEnv'] = setenv
            self.json_manager.write_json(self.config_data, self.config_path, indent=4, ensure_ascii=False)
            self.status_info_var.set("环境设置已保存")
            messagebox.showinfo("成功", "环境设置已保存")
        except Exception as e:
            messagebox.showerror("错误", f"保存环境设置失败: {e}")
    
    def save_qepm_config(self):
        """保存QEPM配置（包括URL和数据路径）"""
        try:
            if not self.config_data:
                messagebox.showwarning("警告", "请先加载配置")
                return
            
            # 获取或创建qepm结构
            if 'qepm' not in self.config_data:
                self.config_data['qepm'] = {}
            
            # 更新QEPM URL
            qepm_url = self.qepm_url_var.get().strip()
            if qepm_url:
                self.config_data['qepm']['url'] = qepm_url
            
            # 获取或创建data_path结构
            if 'data_path' not in self.config_data:
                self.config_data['data_path'] = {}
            
            # 更新原始数据路径
            data_path = self.data_path_var.get().strip()
            if data_path:
                self.config_data['data_path']['raw_data_path'] = data_path
            
            # 保存到文件
            self.json_manager.write_json(self.config_data, self.config_path, indent=4, ensure_ascii=False)
            self.status_info_var.set("QEPM配置已保存")
            messagebox.showinfo("成功", "QEPM配置已保存")
        except Exception as e:
            messagebox.showerror("错误", f"保存QEPM配置失败: {e}")
    
    def save_data_path_config(self):
        """保存数据路径配置（保留此方法以兼容旧代码）"""
        self.save_qepm_config()
    
    def save_feishu_config(self):
        """保存飞书配置"""
        try:
            if not self.config_data:
                messagebox.showwarning("警告", "请先加载配置")
                return
            
            # 获取或创建feishu结构
            if 'feishu' not in self.config_data:
                self.config_data['feishu'] = {}
            
            # 更新飞书配置
            self.config_data['feishu']['enabled'] = self.feishu_enabled_var.get()
            self.config_data['feishu']['upload_enabled'] = self.feishu_upload_enabled_var.get()
            
            # 保存到文件
            self.json_manager.write_json(self.config_data, self.config_path, indent=4, ensure_ascii=False)
            self.status_info_var.set("飞书配置已保存")
            messagebox.showinfo("成功", "飞书配置已保存")
        except Exception as e:
            messagebox.showerror("错误", f"保存飞书配置失败: {e}")
    
    def log_message(self, message):
        """添加日志消息"""
        import time
        self.log_text.config(state=tk.NORMAL)
        timestamp = time.strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)
    
    def clear_log(self):
        """清空日志"""
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete(1.0, tk.END)
        self.log_text.config(state=tk.DISABLED)
    
    def export_log(self):
        """导出日志到文件"""
        from tkinter import filedialog
        import datetime
        
        try:
            # 生成默认文件名
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            default_filename = f"power_test_log_{timestamp}.txt"
            
            # 选择保存位置
            file_path = filedialog.asksaveasfilename(
                defaultextension=".txt",
                filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")],
                initialfile=default_filename
            )
            
            if file_path:
                # 获取日志内容
                self.log_text.config(state=tk.NORMAL)
                log_content = self.log_text.get(1.0, tk.END)
                self.log_text.config(state=tk.DISABLED)
                
                # 写入文件
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(log_content)
                
                self.log_message(f"日志已导出到: {file_path}")
                messagebox.showinfo("成功", f"日志已导出到:\n{file_path}")
                
        except Exception as e:
            messagebox.showerror("错误", f"导出日志失败: {e}")
    
    def _on_config_editor_close(self, editor):
        """配置编辑器关闭时：清理单例引用、刷新主窗口配置、销毁编辑器窗口"""
        self._config_editor = None
        self.load_config()
        try:
            if editor.window.winfo_exists():
                editor.window.destroy()
        except Exception:
            pass

    def open_config_editor(self):
        """打开配置编辑器（单例：已存在则置前聚焦，不重复打开）"""
        try:
            if self._config_editor is not None and self._config_editor.window.winfo_exists():
                self._config_editor.window.lift()
                self._config_editor.window.focus_force()
                return
            editor = ConfigEditor(
                self.root, self.config_path, self.dev_name,
                on_close_callback=lambda: self._on_config_editor_close(editor)
            )
            self._config_editor = editor
            editor.window.protocol("WM_DELETE_WINDOW", lambda: self._on_config_editor_close(editor))
        except Exception as e:
            messagebox.showerror("错误", f"打开配置编辑器失败: {e}")
    
    def load_config(self):
        """加载配置文件"""
        try:
            if not self.config_path.exists():
                self.status_var.set("配置文件不存在")
                self.status_info_var.set("配置文件不存在")
                self.log_message(f"配置文件不存在: {self.config_path}")
                return
            
            # 使用JsonManager加载
            self.config_data = self.json_manager.load_json(self.config_path, use_cache=False)
            
            if not self.config_data:
                self.status_var.set("配置加载失败")
                self.status_info_var.set("配置加载失败")
                return
            
            # 更新UI
            self.update_ui_from_config()
            self.status_var.set("配置加载成功")
            self.status_info_var.set("配置加载成功")
            self.log_message(f"配置加载成功: {self.config_path}")
            
        except Exception as e:
            self.status_var.set("配置加载失败")
            self.status_info_var.set("配置加载失败")
            self.log_message(f"配置加载失败: {e}")
            messagebox.showerror("错误", f"加载配置失败: {e}")
    
    def update_ui_from_config(self):
        """根据配置数据更新UI"""
        
        # 更新Record挡位列表
        records = self.config_data.get('record', [])
        
        # 清空现有项
        for item in self.record_tree.get_children():
            self.record_tree.delete(item)
        
        # 添加新项
        record_names = []
        for record in records:
            record_name = record.get('name', '')
            record_names.append(record_name)
            record_text = "是" if record.get('record', False) else "否"
            self.record_tree.insert("", tk.END, values=(
                record_name,
                record.get('duration', ''),
                record.get('width', ''),
                record.get('height', ''),
                record_text
            ))
        
        # 更新配置名称下拉框
        self.config_name_combo['values'] = record_names
        
        # 如果当前选择的配置名称不在列表中，清空
        current_config = self.config_name_var.get()
        if current_config and current_config != "testall" and current_config not in record_names:
            self.config_name_var.set("")
        
        # 更新固件配置
        firmware = self.config_data.get('firmware', {})
        self.firmware_url_var.set(firmware.get('download_url', ''))
        self.firmware_timeout_var.set(str(firmware.get('timeout', 900)))
        self.firmware_verify_var.set(firmware.get('verify_version', True))
        
        # 更新环境设置（勾选=开，不勾选=关）
        setenv = self.config_data.get('setEnv', {})
        self.env_wifi_var.set(setenv.get('wifi', False))
        self.env_bluetooth_var.set(setenv.get('bluetooth', False))
        self.env_usb_power_var.set(setenv.get('usb_power', False))
        self.env_backlight_var.set(setenv.get('backlight', True))
        self.env_kernel_log_var.set(setenv.get('kernel_log', False))
        self.env_logd_var.set(setenv.get('logd', False))
        self.env_camx_log_var.set(setenv.get('camx_log', False))
        self.env_device_sleep_var.set(setenv.get('device_sleep', False))
        
        # 更新QEPM配置
        qepm = self.config_data.get('qepm', {})
        self.qepm_url_var.set(qepm.get('url', ''))
        
        # 更新数据路径设置
        data_path = self.config_data.get('data_path', {})
        self.data_path_var.set(data_path.get('raw_data_path', ''))
        
        # 更新飞书配置
        feishu = self.config_data.get('feishu', {})
        self.feishu_enabled_var.set(feishu.get('enabled', True))
        self.feishu_upload_enabled_var.set(feishu.get('upload_enabled', True))
    
    def add_to_queue(self):
        """添加固件到队列"""
        firmware_path = self.queue_input_var.get().strip()
        if not firmware_path:
            messagebox.showwarning("警告", "请输入固件URL或本地路径")
            return
        
        # 添加到队列
        self.firmware_queue.append(firmware_path)
        self.update_queue_display()
        self.queue_input_var.set("")  # 清空输入框
        self.status_info_var.set(f"已添加到队列（共 {len(self.firmware_queue)} 项）")
    
    def remove_from_queue(self):
        """从队列中删除选中项"""
        selection = self.queue_tree.selection()
        if not selection:
            messagebox.showwarning("警告", "请先选择要删除的队列项")
            return
        
        # 获取选中项的索引
        item = self.queue_tree.item(selection[0])
        index = int(item['values'][0]) - 1  # 转换为0-based索引
        
        if 0 <= index < len(self.firmware_queue):
            removed = self.firmware_queue.pop(index)
            self.update_queue_display()
            self.status_info_var.set(f"已从队列删除: {removed}")
    
    def clear_queue(self):
        """清空队列"""
        if not self.firmware_queue:
            return
        
        if messagebox.askyesno("确认", f"确定要清空队列吗？\n当前队列有 {len(self.firmware_queue)} 项"):
            self.firmware_queue.clear()
            self.current_queue_index = 0
            self.update_queue_display()
            self.status_info_var.set("队列已清空")
    
    def update_queue_display(self):
        """更新队列显示"""
        # 清空现有项
        for item in self.queue_tree.get_children():
            self.queue_tree.delete(item)
        
        # 添加队列项
        for idx, firmware_path in enumerate(self.firmware_queue, 1):
            self.queue_tree.insert("", tk.END, values=(idx, firmware_path))
    
    def on_queue_double_click(self, event):
        """双击队列项时删除"""
        self.remove_from_queue()
    
    def on_queue_mode_changed(self):
        """队列模式改变时"""
        if self.queue_mode_var.get():
            if not self.firmware_queue:
                messagebox.showwarning("警告", "队列为空，无法启用队列模式")
                self.queue_mode_var.set(False)
                return
            self.queue_mode = True
            self.status_info_var.set(f"队列模式已启用（共 {len(self.firmware_queue)} 项）")
        else:
            self.queue_mode = False
            self.status_info_var.set("队列模式已禁用")
    
    def start_test(self):
        """开始测试"""
        try:
            if self.is_testing:
                messagebox.showwarning("警告", "测试正在进行中")
                return
            
            # 检查配置
            if not self.config_data:
                messagebox.showerror("错误", "请先加载配置文件")
                return
            
            # 获取配置名称
            config_name = self.config_name_var.get().strip()
            if self.test_all_var.get():
                config_name = "testall"
            elif not config_name:
                messagebox.showwarning("警告", "请选择要测试的挡位配置，或选择'全部挡位测试'")
                return
            
            # 检查队列模式
            if self.queue_mode_var.get():
                if not self.firmware_queue:
                    messagebox.showwarning("警告", "队列为空，无法使用队列模式")
                    return
                self.queue_mode = True
                self.current_queue_index = 0
                # 队列模式：使用队列中的固件（优先级高于固件配置）
                queue_info = f"\n队列模式: 共 {len(self.firmware_queue)} 个固件\n⚠️ 将使用队列中的固件，忽略固件配置中的固件"
            else:
                self.queue_mode = False
                # 非队列模式：使用固件配置中的固件
                firmware_url = self.firmware_url_var.get().strip()
                queue_info = f"\n固件: {firmware_url if firmware_url else '使用JSON配置中的固件'}"
            
            # 获取设备名称
            dev_name = self.dev_name
            
            # 确认开始测试
            if self.queue_mode:
                if not messagebox.askyesno("确认", f"开始队列测试？\n设备: {dev_name}\n配置: {config_name}{queue_info}"):
                    return
            else:
                if not messagebox.askyesno("确认", f"开始测试？\n设备: {dev_name}\n配置: {config_name}{queue_info}"):
                    return
            
            # 更新状态
            self.is_testing = True
            self.start_button.config(state=tk.DISABLED)
            self.stop_button.config(state=tk.NORMAL)
            self.status_var.set("测试进行中...")
            self.test_status_var.set("测试进行中...")
            
            if self.queue_mode:
                self.log_message(f"开始队列测试 - 设备: {dev_name}, 配置: {config_name}, 队列共 {len(self.firmware_queue)} 项")
            else:
                self.log_message(f"开始测试 - 设备: {dev_name}, 配置: {config_name}")
            
            # 在新线程中启动测试
            test_thread = threading.Thread(target=self.run_test_queue if self.queue_mode else self.run_test, 
                                         args=(dev_name, config_name), daemon=True)
            test_thread.start()
            
        except Exception as e:
            messagebox.showerror("错误", f"启动测试失败: {e}")
            self.log_message(f"启动测试失败: {e}")
            self.is_testing = False
            self.start_button.config(state=tk.NORMAL)
            self.stop_button.config(state=tk.DISABLED)
    
    def run_test(self, dev_name, config_name, firmware_path=None):
        """运行测试（在后台线程中）
        
        固件优先级说明：
        - 队列模式：队列中的固件 > 固件配置中的固件（队列中的固件会覆盖配置）
        - 非队列模式：UI中配置的固件 > JSON配置中的固件
        
        Args:
            dev_name: 设备名称
            config_name: 配置名称
            firmware_path: 固件URL或本地路径（可选，队列模式时由队列提供）
        """
        try:
            # 优先级1：队列模式 - 使用队列中的固件（最高优先级）
            if firmware_path:
                try:
                    if not self.config_data:
                        self.config_data = self.json_manager.load_json(self.config_path, use_cache=False)
                    
                    if 'firmware' not in self.config_data:
                        self.config_data['firmware'] = {}
                    
                    # 队列模式：使用队列中的固件，覆盖JSON配置
                    self.config_data['firmware']['download_url'] = firmware_path
                    self.json_manager.write_json(self.config_data, self.config_path, indent=4, ensure_ascii=False)
                    self.root.after(0, lambda: self.log_message(f"[队列模式] 已更新固件配置: {firmware_path}"))
                except Exception as e:
                    self.root.after(0, lambda: self.log_message(f"更新固件配置失败: {e}"))
            else:
                # 优先级2：非队列模式 - 使用UI中配置的固件（如果已修改）
                ui_firmware_url = self.firmware_url_var.get().strip()
                if ui_firmware_url:
                    try:
                        if not self.config_data:
                            self.config_data = self.json_manager.load_json(self.config_path, use_cache=False)
                        
                        if 'firmware' not in self.config_data:
                            self.config_data['firmware'] = {}
                        
                        # 非队列模式：使用UI中配置的固件
                        self.config_data['firmware']['download_url'] = ui_firmware_url
                        self.json_manager.write_json(self.config_data, self.config_path, indent=4, ensure_ascii=False)
                        self.root.after(0, lambda: self.log_message(f"[单次测试] 使用UI配置的固件: {ui_firmware_url}"))
                    except Exception as e:
                        self.root.after(0, lambda: self.log_message(f"更新固件配置失败: {e}"))
                else:
                    # 优先级3：使用JSON配置中的固件（默认）
                    self.root.after(0, lambda: self.log_message("[单次测试] 使用JSON配置中的固件"))
            
            # 构建测试命令
            test_script = self.project_root / "tests" / "test_PowerConsumption" / "test_PowerConsumption.py"
            
            if not test_script.exists():
                error_msg = f"测试脚本不存在: {test_script}"
                self.root.after(0, lambda: self.log_message(error_msg))
                self.root.after(0, lambda: messagebox.showerror("错误", error_msg))
                return False
            
            # 构建命令参数
            cmd = [
                sys.executable,
                str(test_script),
                "--dev", dev_name
            ]
            
            if config_name and config_name != "testall":
                cmd.extend(["--config-name", config_name])
            
            # 设置环境变量
            env = os.environ.copy()
            env['FW_DEV'] = dev_name
            if config_name:
                env['RECORD_CONFIG_NAME'] = config_name
            
            self.root.after(0, lambda: self.log_message(f"执行命令: {' '.join(cmd)}"))
            
            # 启动测试进程
            self.test_process = subprocess.Popen(
                cmd,
                cwd=str(self.project_root),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            
            # 实时读取输出
            for line in iter(self.test_process.stdout.readline, ''):
                if not line:
                    break
                line = line.strip()
                if line:
                    self.root.after(0, lambda l=line: self.log_message(l))
            
            # 等待进程完成
            return_code = self.test_process.wait()
            
            # 更新状态（非队列模式：如果没有提供firmware_path，说明是单次测试）
            if firmware_path is None:
                if return_code == 0:
                    self.root.after(0, lambda: self.status_var.set("测试完成"))
                    self.root.after(0, lambda: self.test_status_var.set("测试完成"))
                    self.root.after(0, lambda: self.log_message("测试完成！"))
                    self.root.after(0, lambda: messagebox.showinfo("完成", "测试完成！"))
                else:
                    self.root.after(0, lambda: self.status_var.set("测试失败"))
                    self.root.after(0, lambda: self.test_status_var.set("测试失败"))
                    self.root.after(0, lambda: self.log_message(f"测试失败，返回码: {return_code}"))
                    self.root.after(0, lambda: messagebox.showerror("失败", f"测试失败，返回码: {return_code}"))
                
                # 恢复按钮状态（非队列模式）
                self.root.after(0, lambda: self.start_button.config(state=tk.NORMAL))
                self.root.after(0, lambda: self.stop_button.config(state=tk.DISABLED))
                self.is_testing = False
                self.test_process = None
            
            # 返回测试结果
            return return_code == 0
            
        except Exception as e:
            error_msg = f"测试执行失败: {e}"
            self.root.after(0, lambda: self.log_message(error_msg))
            return False
    
    def run_test_queue(self, dev_name, config_name):
        """运行队列测试（按顺序测试队列中的固件）"""
        try:
            total = len(self.firmware_queue)
            success_count = 0
            fail_count = 0
            
            self.root.after(0, lambda: self.log_message(f"=" * 60))
            self.root.after(0, lambda: self.log_message(f"开始队列测试，共 {total} 个固件"))
            self.root.after(0, lambda: self.log_message(f"=" * 60))
            
            for idx, firmware_path in enumerate(self.firmware_queue, 1):
                # 检查是否被停止
                if not self.is_testing:
                    self.root.after(0, lambda: self.log_message("队列测试已停止"))
                    break
                
                self.current_queue_index = idx - 1
                
                # 更新状态
                self.root.after(0, lambda i=idx, t=total, f=firmware_path: 
                               self.status_var.set(f"队列测试进行中 ({i}/{t})"))
                self.root.after(0, lambda i=idx, t=total, f=firmware_path: 
                               self.test_status_var.set(f"队列测试 ({i}/{t}): {f[:50]}..."))
                self.root.after(0, lambda i=idx, t=total, f=firmware_path: 
                               self.log_message(f"\n[{i}/{t}] 开始测试固件: {f}"))
                
                # 高亮当前队列项
                self.root.after(0, lambda: self.highlight_queue_item(idx - 1))
                
                # 运行测试
                success = self.run_test(dev_name, config_name, firmware_path)
                
                if success:
                    success_count += 1
                    self.root.after(0, lambda i=idx, t=total, f=firmware_path: 
                                   self.log_message(f"[{i}/{t}] 固件测试完成: {f}"))
                else:
                    fail_count += 1
                    self.root.after(0, lambda i=idx, t=total, f=firmware_path: 
                                   self.log_message(f"[{i}/{t}] 固件测试失败: {f}"))
                
                # 如果不是最后一个，等待一下再继续
                if idx < total:
                    self.root.after(0, lambda: self.log_message("等待3秒后继续下一个固件..."))
                    import time
                    time.sleep(3)
            
            # 队列测试完成
            self.root.after(0, lambda: self.log_message(f"\n{'=' * 60}"))
            self.root.after(0, lambda: self.log_message(f"队列测试完成！"))
            self.root.after(0, lambda: self.log_message(f"成功: {success_count}, 失败: {fail_count}, 总计: {total}"))
            self.root.after(0, lambda: self.log_message(f"{'=' * 60}"))
            
            # 更新状态
            if fail_count == 0:
                self.root.after(0, lambda: self.status_var.set(f"队列测试完成（全部成功）"))
                self.root.after(0, lambda: self.test_status_var.set(f"队列测试完成（{success_count}/{total} 成功）"))
                self.root.after(0, lambda: messagebox.showinfo("完成", f"队列测试完成！\n成功: {success_count}/{total}"))
            else:
                self.root.after(0, lambda: self.status_var.set(f"队列测试完成（{fail_count} 个失败）"))
                self.root.after(0, lambda: self.test_status_var.set(f"队列测试完成（成功: {success_count}, 失败: {fail_count}）"))
                self.root.after(0, lambda: messagebox.showwarning("完成", f"队列测试完成\n成功: {success_count}, 失败: {fail_count}"))
            
        except Exception as e:
            error_msg = f"队列测试执行失败: {e}"
            self.root.after(0, lambda: self.log_message(error_msg))
            self.root.after(0, lambda: self.status_var.set("队列测试失败"))
            self.root.after(0, lambda: self.test_status_var.set("队列测试失败"))
            self.root.after(0, lambda: messagebox.showerror("错误", error_msg))
        finally:
            # 恢复按钮状态
            self.root.after(0, lambda: self.start_button.config(state=tk.NORMAL))
            self.root.after(0, lambda: self.stop_button.config(state=tk.DISABLED))
            self.is_testing = False
            self.test_process = None
            self.current_queue_index = 0
            # 清除队列高亮
            self.root.after(0, lambda: self.clear_queue_highlight())
    
    def highlight_queue_item(self, index):
        """高亮显示当前测试的队列项"""
        # 清除所有高亮
        self.clear_queue_highlight()
        
        # 高亮当前项
        items = self.queue_tree.get_children()
        if 0 <= index < len(items):
            item_id = items[index]
            self.queue_tree.selection_set(item_id)
            self.queue_tree.focus(item_id)
            self.queue_tree.see(item_id)
    
    def clear_queue_highlight(self):
        """清除队列高亮"""
        self.queue_tree.selection_remove(self.queue_tree.selection())
    
    def stop_test(self):
        """停止测试"""
        try:
            if not self.is_testing:
                return
            
            if self.test_process:
                self.log_message("正在停止测试...")
                self.test_process.terminate()
                # 等待进程结束
                try:
                    self.test_process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.test_process.kill()
                    self.test_process.wait()
                
                self.log_message("测试已停止")
            
            self.is_testing = False
            self.start_button.config(state=tk.NORMAL)
            self.stop_button.config(state=tk.DISABLED)
            self.status_var.set("测试已停止")
            self.test_status_var.set("测试已停止")
            
            # 如果是队列模式，重置队列索引并清除高亮
            if self.queue_mode:
                self.current_queue_index = 0
                self.clear_queue_highlight()
                self.log_message("队列测试已停止")
            
        except Exception as e:
            messagebox.showerror("错误", f"停止测试失败: {e}")
            self.log_message(f"停止测试失败: {e}")

    def run(self):
        """运行主窗口"""
        self.root.mainloop()


def main():
    """主函数"""
    app = PowerConsumptionMainWindow()
    app.run()


if __name__ == "__main__":
    main()
