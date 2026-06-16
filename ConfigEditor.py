"""
配置编辑器
用于编辑JSON配置文件的专用窗口
支持：record挡位管理、固件链接编辑、环境设置编辑
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import json
from pathlib import Path
import sys
import os

# 添加项目根目录到sys.path
current_file = Path(__file__).resolve()
project_root = current_file.parent.parent.parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.app.PowerConsumption.PowerConsumption_jsonManager import PowerConsumptionJsonManager
from src.utils.logger import Logger


class ConfigEditor:
    """JSON配置编辑器（单例，置顶；挡位增删改即时写入）"""
    
    def __init__(self, parent, config_path, dev_name=None, on_close_callback=None):
        self.parent = parent
        self.config_path = Path(config_path)
        self.dev_name = dev_name or os.environ.get('FW_DEV', 'Z03')
        self.on_close_callback = on_close_callback  # 关闭时由主窗口回调，用于清理单例并刷新配置
        self.logger = Logger()
        self.json_manager = PowerConsumptionJsonManager(dev_name=self.dev_name, logger=self.logger)
        
        # 配置数据
        self.config_data = {}
        
        # 创建编辑器窗口
        self.window = tk.Toplevel(parent)
        self.window.title(f"配置编辑器 - {self.dev_name}")
        # 自适应分辨率：兼容 1920x1080 台式 与 3720x1920 笔记本等高分辨率
        try:
            self.window.update_idletasks()
            sw = self.window.winfo_screenwidth()
            sh = self.window.winfo_screenheight()
            if sw >= 100 and sh >= 100:
                # 宽度：1080p 约 900，3720 屏约 1100；高度：保证底部按钮与状态栏露出
                w = max(800, min(1100, int(sw * 0.48)))
                h = max(750, min(950, int(sh * 0.75)))
                self.window.geometry(f"{w}x{h}")
            else:
                self.window.geometry("900x700")
            self.window.minsize(700, 500)
        except Exception:
            self.window.geometry("900x700")
            self.window.minsize(700, 500)
        # 配置编辑器始终置顶，避免被主窗口抢占
        self.window.attributes('-topmost', True)
        
        # 创建界面
        self.create_widgets()
        
        # 加载配置
        self.load_config()

    def _msg(self, mb_func, title, message, **kwargs):
        """统一弹窗并确保显示在配置编辑器上层：暂时取消置顶后弹窗，关闭后恢复置顶"""
        self.window.attributes('-topmost', False)
        try:
            return mb_func(title, message, parent=self.window, **kwargs)
        finally:
            self.window.attributes('-topmost', True)
    
    def create_widgets(self):
        """创建编辑器界面"""
        
        # 主框架
        main_frame = ttk.Frame(self.window, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # 创建标签页
        notebook = ttk.Notebook(main_frame)
        notebook.pack(fill=tk.BOTH, expand=True, pady=5)
        
        # 1. Record挡位配置标签页
        record_frame = ttk.Frame(notebook, padding="10")
        notebook.add(record_frame, text="Record挡位配置")
        self.create_record_tab(record_frame)
        
        # 2. 固件配置标签页
        firmware_frame = ttk.Frame(notebook, padding="10")
        notebook.add(firmware_frame, text="固件配置")
        self.create_firmware_tab(firmware_frame)
        
        # 3. 环境设置标签页
        env_frame = ttk.Frame(notebook, padding="10")
        notebook.add(env_frame, text="环境设置")
        self.create_env_tab(env_frame)
        
        # 按钮框架
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(pady=10)
        
        ttk.Button(button_frame, text="保存配置", command=self.save_config).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="重新加载", command=self.load_config).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="关闭", command=self._on_close).pack(side=tk.LEFT, padx=5)
        
        # 状态栏
        self.status_var = tk.StringVar()
        self.status_var.set("就绪")
        status_bar = ttk.Label(main_frame, textvariable=self.status_var, relief=tk.SUNKEN)
        status_bar.pack(fill=tk.X)
    
    def create_record_tab(self, parent):
        """创建Record挡位配置标签页"""
        
        # 挡位列表框架
        list_frame = ttk.LabelFrame(parent, text="挡位列表", padding="5")
        list_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        # 创建表格
        columns = ("name", "mode", "duration", "width", "height", "record")
        self.record_tree = ttk.Treeview(list_frame, columns=columns, show="headings", height=10)
        
        # 设置列标题和宽度
        self.record_tree.heading("name", text="名称")
        self.record_tree.heading("mode", text="模式")
        self.record_tree.heading("duration", text="时长(秒)")
        self.record_tree.heading("width", text="宽度")
        self.record_tree.heading("height", text="高度")
        self.record_tree.heading("record", text="录制")
        
        self.record_tree.column("name", width=150)
        self.record_tree.column("mode", width=200)
        self.record_tree.column("duration", width=80)
        self.record_tree.column("width", width=80)
        self.record_tree.column("height", width=80)
        self.record_tree.column("record", width=60)
        
        # 滚动条
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.record_tree.yview)
        self.record_tree.configure(yscrollcommand=scrollbar.set)
        
        self.record_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 绑定选择事件
        self.record_tree.bind("<<TreeviewSelect>>", self.on_record_select)
        
        # 按钮框架：2x2 矩形排列，避免横向挤在一起导致上移/下移看不见
        btn_frame = ttk.Frame(list_frame)
        btn_frame.pack(fill=tk.X, pady=5)
        ttk.Button(btn_frame, text="添加挡位", command=self.add_record).grid(row=0, column=0, padx=4, pady=2)
        ttk.Button(btn_frame, text="删除挡位", command=self.delete_record).grid(row=0, column=1, padx=4, pady=2)
        ttk.Button(btn_frame, text="上移", command=self.move_record_up).grid(row=1, column=0, padx=4, pady=2)
        ttk.Button(btn_frame, text="下移", command=self.move_record_down).grid(row=1, column=1, padx=4, pady=2)
        
        # 编辑区域（列 1 可拉伸，便于大屏自适应）
        edit_frame = ttk.LabelFrame(parent, text="编辑挡位", padding="5")
        edit_frame.pack(fill=tk.BOTH, expand=False, pady=5)
        edit_frame.columnconfigure(1, weight=1)
        
        # 名称
        ttk.Label(edit_frame, text="名称:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.record_name_var = tk.StringVar()
        ttk.Entry(edit_frame, textvariable=self.record_name_var, width=40).grid(row=0, column=1, sticky=tk.W, padx=5)
        
        # 模式
        ttk.Label(edit_frame, text="模式:").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.record_mode_var = tk.StringVar()
        ttk.Entry(edit_frame, textvariable=self.record_mode_var, width=40).grid(row=1, column=1, sticky=tk.W, padx=5)
        
        # 配置（多行）
        ttk.Label(edit_frame, text="配置:").grid(row=2, column=0, sticky=tk.NW, pady=2)
        self.record_config_text = scrolledtext.ScrolledText(edit_frame, width=40, height=3, wrap=tk.WORD)
        self.record_config_text.grid(row=2, column=1, sticky=tk.W, padx=5)
        
        # 时长、宽度、高度
        ttk.Label(edit_frame, text="时长(秒):").grid(row=3, column=0, sticky=tk.W, pady=2)
        self.record_duration_var = tk.StringVar()
        ttk.Entry(edit_frame, textvariable=self.record_duration_var, width=10).grid(row=3, column=1, sticky=tk.W, padx=5)
        
        ttk.Label(edit_frame, text="宽度:").grid(row=4, column=0, sticky=tk.W, pady=2)
        self.record_width_var = tk.StringVar()
        ttk.Entry(edit_frame, textvariable=self.record_width_var, width=10).grid(row=4, column=1, sticky=tk.W, padx=5)
        
        ttk.Label(edit_frame, text="高度:").grid(row=5, column=0, sticky=tk.W, pady=2)
        self.record_height_var = tk.StringVar()
        ttk.Entry(edit_frame, textvariable=self.record_height_var, width=10).grid(row=5, column=1, sticky=tk.W, padx=5)
        
        # 录制开关
        self.record_enable_var = tk.BooleanVar()
        ttk.Checkbutton(edit_frame, text="启用录制", variable=self.record_enable_var).grid(row=6, column=1, sticky=tk.W, padx=5)
        
        # 应用按钮
        ttk.Button(edit_frame, text="应用修改", command=self.apply_record_changes).grid(row=7, column=1, sticky=tk.W, padx=5, pady=5)
        
        self.selected_record_index = None
    
    def create_firmware_tab(self, parent):
        """创建固件配置标签页"""
        
        # 下载URL
        ttk.Label(parent, text="下载URL:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.firmware_url_var = tk.StringVar()
        firmware_url_entry = ttk.Entry(parent, textvariable=self.firmware_url_var, width=80)
        firmware_url_entry.grid(row=0, column=1, sticky=tk.W, padx=5)
        
        # 超时时间
        ttk.Label(parent, text="超时时间(秒):").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.firmware_timeout_var = tk.StringVar()
        ttk.Entry(parent, textvariable=self.firmware_timeout_var, width=20).grid(row=1, column=1, sticky=tk.W, padx=5)
        
        # 验证版本
        self.firmware_verify_var = tk.BooleanVar()
        ttk.Checkbutton(parent, text="验证版本", variable=self.firmware_verify_var).grid(row=2, column=1, sticky=tk.W, padx=5, pady=5)
    
    def create_env_tab(self, parent):
        """创建环境设置标签页"""
        
        # 使用网格布局
        row = 0
        
        # WiFi
        self.env_wifi_var = tk.BooleanVar()
        ttk.Checkbutton(parent, text="WiFi", variable=self.env_wifi_var).grid(row=row, column=0, sticky=tk.W, padx=5, pady=5)
        row += 1
        
        # 蓝牙（勾选=开，不勾选=关）
        self.env_bluetooth_var = tk.BooleanVar()
        ttk.Checkbutton(parent, text="蓝牙", variable=self.env_bluetooth_var).grid(row=row, column=0, sticky=tk.W, padx=5, pady=5)
        row += 1
        
        # USB供电
        self.env_usb_power_var = tk.BooleanVar()
        ttk.Checkbutton(parent, text="USB供电", variable=self.env_usb_power_var).grid(row=row, column=0, sticky=tk.W, padx=5, pady=5)
        row += 1
        
        # 背光
        self.env_backlight_var = tk.BooleanVar()
        ttk.Checkbutton(parent, text="背光", variable=self.env_backlight_var).grid(row=row, column=0, sticky=tk.W, padx=5, pady=5)
        row += 1
        
        # Kernel日志
        self.env_kernel_log_var = tk.BooleanVar()
        ttk.Checkbutton(parent, text="Kernel日志", variable=self.env_kernel_log_var).grid(row=row, column=0, sticky=tk.W, padx=5, pady=5)
        row += 1
        
        # Logd
        self.env_logd_var = tk.BooleanVar()
        ttk.Checkbutton(parent, text="Logd", variable=self.env_logd_var).grid(row=row, column=0, sticky=tk.W, padx=5, pady=5)
        row += 1
        
        # CamX日志
        self.env_camx_log_var = tk.BooleanVar()
        ttk.Checkbutton(parent, text="CamX日志", variable=self.env_camx_log_var).grid(row=row, column=0, sticky=tk.W, padx=5, pady=5)
        row += 1
        
        # 设备休眠
        self.env_device_sleep_var = tk.BooleanVar()
        ttk.Checkbutton(parent, text="设备休眠", variable=self.env_device_sleep_var).grid(row=row, column=0, sticky=tk.W, padx=5, pady=5)
    
    def load_config(self):
        """加载配置文件"""
        try:
            if not self.config_path.exists():
                self.status_var.set("配置文件不存在")
                self._msg(messagebox.showerror, "错误", f"配置文件不存在: {self.config_path}")
                return
            
            # 使用JsonManager加载
            self.config_data = self.json_manager.load_json(self.config_path, use_cache=False)
            
            if not self.config_data:
                self.status_var.set("配置加载失败")
                self._msg(messagebox.showerror, "错误", "配置加载失败")
                return
            
            # 更新UI
            self.update_ui_from_config()
            self.status_var.set("配置加载成功")
                         
        except Exception as e:
            self.status_var.set("配置加载失败")
            self._msg(messagebox.showerror, "错误", f"加载配置失败: {e}")
    
    def update_ui_from_config(self):
        """根据配置数据更新UI"""
        
        # 更新Record挡位列表
        self.update_record_list()
        
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
    
    def update_record_list(self):
        """更新Record挡位列表"""
        # 清空现有项
        for item in self.record_tree.get_children():
            self.record_tree.delete(item)
        
        # 添加新项
        records = self.config_data.get('record', [])
        for record in records:
            config_text = ', '.join(record.get('config', [])) if isinstance(record.get('config'), list) else str(record.get('config', ''))
            record_text = "是" if record.get('record', False) else "否"
            self.record_tree.insert("", tk.END, values=(
                record.get('name', ''),
                record.get('mode', ''),
                record.get('duration', ''),
                record.get('width', ''),
                record.get('height', ''),
                record_text
            ))
    
    def on_record_select(self, event):
        """当选择Record挡位时"""
        selection = self.record_tree.selection()
        if not selection:
            return
        
        item = self.record_tree.item(selection[0])
        values = item['values']
        record_name = values[0]
        
        # 找到对应的record配置
        records = self.config_data.get('record', [])
        for idx, record in enumerate(records):
            if record.get('name') == record_name:
                self.selected_record_index = idx
                # 填充编辑区域
                self.record_name_var.set(record.get('name', ''))
                self.record_mode_var.set(record.get('mode', ''))
                config_list = record.get('config', [])
                if isinstance(config_list, list):
                    self.record_config_text.delete(1.0, tk.END)
                    self.record_config_text.insert(1.0, '\n'.join(config_list))
                else:
                    self.record_config_text.delete(1.0, tk.END)
                    self.record_config_text.insert(1.0, str(config_list))
                self.record_duration_var.set(str(record.get('duration', '')))
                self.record_width_var.set(str(record.get('width', '')))
                self.record_height_var.set(str(record.get('height', '')))
                self.record_enable_var.set(record.get('record', False))
                break
    
    def _persist_config(self):
        """将当前 config_data 立即写入配置文件（挡位增删改后调用）"""
        try:
            self.json_manager.write_json(self.config_data, self.config_path, indent=4, ensure_ascii=False)
        except Exception as e:
            self.status_var.set("写入失败")
            self._msg(messagebox.showerror, "错误", f"写入配置失败: {e}")

    def _on_close(self):
        """关闭窗口：若有回调则通知主窗口后销毁，否则直接销毁"""
        if self.on_close_callback:
            self.on_close_callback()
        else:
            self.window.destroy()

    def add_record(self):
        """添加新挡位（立即写入配置文件）"""
        # 创建默认配置
        new_record = {
            "name": "新挡位",
            "mode": "mode switch kSATAngle kNormalVideo 1",
            "config": ["config spec InsMediaResRatioFps kRes4K kRatio16x9 k30"],
            "duration": 60,
            "width": 3840,
            "height": 2160,
            "record": True
        }
        
        if 'record' not in self.config_data:
            self.config_data['record'] = []
        
        self.config_data['record'].append(new_record)
        self.update_record_list()
        self._persist_config()
        self.status_var.set("已添加新挡位并已保存")
    
    def delete_record(self):
        """删除选中的挡位（弹窗在配置编辑器上层显示）"""
        selection = self.record_tree.selection()
        if not selection:
            self._msg(messagebox.showwarning, "警告", "请先选择要删除的挡位")
            return
        
        item = self.record_tree.item(selection[0])
        values = item['values']
        record_name = str(values[0]).strip() if values else ""
        if not record_name:
            self._msg(messagebox.showwarning, "警告", "无法获取挡位名称")
            return
        
        # 确认删除（弹窗在配置编辑器上层显示）
        if not self._msg(messagebox.askyesno, "确认", f"确定要删除挡位 '{record_name}' 吗？"):
            return
        
        # 从配置中删除并立即写入
        records = self.config_data.get('record', [])
        self.config_data['record'] = [r for r in records if str(r.get('name', '')).strip() != record_name]
        self.update_record_list()
        self.selected_record_index = None
        self._persist_config()
        self.status_var.set("已删除挡位并已保存")
    
    def move_record_up(self):
        """上移挡位"""
        selection = self.record_tree.selection()
        if not selection:
            self._msg(messagebox.showwarning, "警告", "请先选择要移动的挡位")
            return
        
        item = self.record_tree.item(selection[0])
        values = item['values']
        record_name = values[0]
        
        records = self.config_data.get('record', [])
        for idx, record in enumerate(records):
            if record.get('name') == record_name:
                if idx > 0:
                    records[idx], records[idx - 1] = records[idx - 1], records[idx]
                    self.update_record_list()
                    self._persist_config()
                    # 重新选择
                    for child in self.record_tree.get_children():
                        if self.record_tree.item(child)['values'][0] == record_name:
                            self.record_tree.selection_set(child)
                            break
                    self.status_var.set("已上移挡位并已保存")
                break
    
    def move_record_down(self):
        """下移挡位"""
        selection = self.record_tree.selection()
        if not selection:
            self._msg(messagebox.showwarning, "警告", "请先选择要移动的挡位")
            return
        
        item = self.record_tree.item(selection[0])
        values = item['values']
        record_name = values[0]
        
        records = self.config_data.get('record', [])
        for idx, record in enumerate(records):
            if record.get('name') == record_name:
                if idx < len(records) - 1:
                    records[idx], records[idx + 1] = records[idx + 1], records[idx]
                    self.update_record_list()
                    self._persist_config()
                    # 重新选择
                    for child in self.record_tree.get_children():
                        if self.record_tree.item(child)['values'][0] == record_name:
                            self.record_tree.selection_set(child)
                            break
                    self.status_var.set("已下移挡位并已保存")
                break
    
    def apply_record_changes(self):
        """应用Record挡位的修改"""
        if self.selected_record_index is None:
            self._msg(messagebox.showwarning, "警告", "请先选择要修改的挡位")
            return
        
        records = self.config_data.get('record', [])
        if self.selected_record_index >= len(records):
            return
        
        # 获取编辑区域的值
        name = self.record_name_var.get().strip()
        if not name:
            self._msg(messagebox.showerror, "错误", "名称不能为空")
            return
        
        mode = self.record_mode_var.get().strip()
        config_text = self.record_config_text.get(1.0, tk.END).strip()
        config_list = [line.strip() for line in config_text.split('\n') if line.strip()]
        
        try:
            duration = int(self.record_duration_var.get())
            width = int(self.record_width_var.get())
            height = int(self.record_height_var.get())
        except ValueError:
            self._msg(messagebox.showerror, "错误", "时长、宽度、高度必须是数字")
            return
        
        record = records[self.selected_record_index]
        record['name'] = name
        record['mode'] = mode
        record['config'] = config_list
        record['duration'] = duration
        record['width'] = width
        record['height'] = height
        record['record'] = self.record_enable_var.get()
        
        self.update_record_list()
        self._persist_config()
        self.status_var.set("已应用修改并已保存")
    
    def save_config(self):
        """保存配置"""
        try:
            # 更新配置数据
            self.update_config_from_ui()
            
            # 使用JsonManager保存
            self.json_manager.write_json(self.config_data, self.config_path, indent=4, ensure_ascii=False)
            
            self.status_var.set("配置保存成功")
            self._msg(messagebox.showinfo, "成功", "配置已保存")
            
        except Exception as e:
            self.status_var.set("保存失败")
            self._msg(messagebox.showerror, "错误", f"保存配置失败: {e}")
    
    def update_config_from_ui(self):
        """从UI更新配置数据"""
        
        # 更新固件配置
        firmware = {
            'download_url': self.firmware_url_var.get().strip(),
            'timeout': int(self.firmware_timeout_var.get()) if self.firmware_timeout_var.get().strip() else 900,
            'verify_version': self.firmware_verify_var.get()
        }
        self.config_data['firmware'] = firmware
        
        # 更新环境设置
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
        
        # Record配置已在apply_record_changes中更新，这里不需要再更新
    
    def show(self):
        """显示编辑器窗口"""
        self.window.grab_set()  # 模态窗口
        self.window.wait_window()