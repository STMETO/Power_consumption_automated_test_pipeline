#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
功耗测试 - 飞书报告模块
用于构建功耗测试的飞书消息并发送通知
"""
import os
import sys
import json
import re
from pathlib import Path
from typing import Optional, Dict

# 添加项目根目录到Python路径
current_file = Path(__file__).resolve()
project_root = current_file.parent.parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.utils.config_manager import ConfigManager
from src.utils.logger import Logger
from src.utils.feishu_request import FeishuRequest
from src.app.PowerConsumption.PowerConsumption_jsonManager import PowerConsumptionJsonManager


# ============= 配置常量 =============
# setEnv字段名称映射
SETENV_FIELD_NAMES = {
    'wifi': 'WiFi',
    'usb_power': 'USB供电',
    'backlight': '背光',
    'kernel_log': 'Kernel日志',
    'logd': 'Logd',
    'camx_log': 'CamX日志',
    'device_sleep': '设备休眠'
}


class PowerConsumptionFeishuReport:
    """
    功耗测试飞书报告类
    用于构建和发送功耗测试的飞书通知
    """
    
    def __init__(self, config: ConfigManager, logger: Logger, dev_name: str = None):
        """
        初始化飞书报告类
        
        Args:
            config: 配置管理器
            logger: 日志记录器
            dev_name: 设备名称（如 'Z03'），如果为None则从环境变量FW_DEV获取
        """
        self.config = config
        self.logger = logger
        
        # 确定设备名称
        if not dev_name:
            dev_name = os.environ.get('FW_DEV', 'Z03')
            if dev_name == 'Unknow':
                dev_name = 'Z03'
        self.dev_name = dev_name
        
        # 获取项目根目录
        self.project_root = current_file.parent.parent.parent.parent
        
        # 飞书配置
        self.feishu_config = None
        self.chat_id = None
        self.enabled = False
        
        # JSON配置管理器
        self.json_manager = PowerConsumptionJsonManager(dev_name=self.dev_name, logger=self.logger)
    
    def load_feishu_config(self, json_file: str = None) -> Dict:
        """
        从JSON文件加载飞书配置
        
        Args:
            json_file: JSON文件路径，如果为None则使用默认路径 data/{device}/power_consumption.json
            
        Returns:
            dict: 飞书配置字典，包含 chat_id, enabled 等字段，如果失败则返回None
        """
        # 直接获取 feishu section
        feishu_config = self.json_manager.get_section('feishu', json_file)
        if not feishu_config:
            self.logger.warning("JSON文件中没有feishu配置")
            return None
        
        self.logger.info(f"从JSON文件加载飞书配置成功")
        self.logger.debug(f"飞书配置: {feishu_config}")
        
        # 保存配置
        self.feishu_config = feishu_config
        self.chat_id = feishu_config.get('chat_id', '')
        self.enabled = feishu_config.get('enabled', False)
        
        return feishu_config
    
    def get_chat_id(self) -> Optional[str]:
        """
        获取飞书chat_id（优先级：JSON配置 > 环境变量）
        
        Returns:
            str: 飞书chat_id，如果未配置则返回None
        """
        # 如果还未加载配置，先加载
        if self.feishu_config is None:
            self.load_feishu_config()
        
        # 优先级1: JSON配置（如果enabled为true）
        if self.enabled and self.chat_id:
            self.logger.info(f"从JSON文件读取飞书chat_id: {self.chat_id}")
            return self.chat_id
        
        # 不在这里打印warning，让调用者决定如何提示用户
        return None
    
    def is_enabled(self) -> bool:
        """
        检查飞书通知是否启用
        
        Returns:
            bool: 如果启用则返回True
        """
        # 如果还未加载配置，先加载
        if self.feishu_config is None:
            self.load_feishu_config()
        
        # 如果JSON中enabled为true，则启用
        if self.enabled:
            return True
        
        return False
    
    def build_custom_message(self, report_path: str, test_result: int,
                              excel_path: str = None, config_name: str = None, 
                              firmware_url: str = None, battery_power: str = None, 
                              load_power: str = None, test_data_url: str = None, 
                              test_duration: str = None, error_message: str = None,
                              module_power_values: dict = None, 
                              temperature_start: str = None, temperature_end: str = None) -> dict:
        """
        构建自定义的飞书消息
        
        Args:
            report_path: HTML报告文件路径
            test_result: 测试结果（0=成功，非0=失败）
            excel_path: Excel文件路径（可选）
            config_name: 测试配置名称（可选）
            firmware_url: 固件地址（可选，从环境变量或JSON获取）
            battery_power: 电池端功耗（可选）
            load_power: 负载端功耗（可选）
            test_data_url: 测试数据链接（可选）
            test_duration: 测试时长（秒，可选）
            error_message: 错误信息（可选）
            module_power_values: 模块功耗值字典（可选）
            temperature_start: 起始温度（可选）
            temperature_end: 结束温度（可选）
            
        Returns:
            dict: 构建好的飞书消息模板
        """
        # 加载基础模板
        config_file = self.project_root / "config.json"
        if not config_file.exists():
            self.logger.error(f"配置文件不存在: {config_file}")
            return None
        
        with open(config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        feishu_msg_template = json.loads(json.dumps(config['feishu_msg_template']))  # 深拷贝
        
        # 判断整体结果
        if test_result == 255:
            overall_result = False
            error_msg = "<font color='red'>测试过程中设备离线，终止测试</font>"
        elif test_result == 0:
            overall_result = True
            error_msg = None
        else:
            overall_result = False
            # 如果有传入的错误信息，使用传入的错误信息；否则使用默认的错误信息
            if error_message:
                self.logger.debug(f"使用传入的错误信息: {error_message}")
                error_msg = f"<font color='red'>{error_message}</font>"
            else:
                # 即使没有传入错误信息，测试失败时也显示默认错误信息
                self.logger.warning("未传入错误信息，使用默认错误信息")
                error_msg = "<font color='red'>测试失败，请查看日志获取详细信息</font>"
        
        # 设置标题颜色和内容（自定义功耗测试标题）
        if overall_result:
            result_text = "PASSED"
            feishu_msg_template['i18n_header']['zh_cn']['template'] = "green"
        else:
            result_text = "FAILED"
            feishu_msg_template['i18n_header']['zh_cn']['template'] = "red"
        
        # 自定义标题（功耗测试专用）
        dev = os.environ.get('FW_DEV', self.dev_name)
        
        # 统一数据源：优先从JSON文件读取，如果没有则从函数参数构建
        # 使用新的路径结构：PowerConsumption_Data/{统一文件夹名称}/power_test_result-{时间戳}.json
        test_result_file = None
        
        # 尝试从新的路径结构查找测试结果文件
        try:
            # 获取固件版本
            firmware_url = self.json_manager.get_value('firmware.download_url')
            firmware_version = 'unknown'
            if firmware_url:
                from src.app.PowerConsumption.PowerConsumption_utils import extract_firmware_version
                firmware_version = extract_firmware_version(firmware_url) or 'unknown'
            
            # 构建目录路径
            project_root = Path(__file__).parent.parent.parent.parent
            
            # 首先尝试查找统一文件夹（固件名称-测试次数-时间戳格式）
            unified_folder_pattern = f"{firmware_version}-Test*"
            result_dir = project_root / "PowerConsumption_Data"
            
            # 查找匹配的统一文件夹
            unified_folders = sorted(result_dir.glob(unified_folder_pattern), reverse=True)
            
            if unified_folders:
                # 使用最新的统一文件夹
                latest_unified_folder = unified_folders[0]
                self.logger.debug(f"找到统一文件夹: {latest_unified_folder}")
                
                # 在该文件夹中查找最新的测试结果文件
                result_files = sorted(latest_unified_folder.glob("power_test_result-*.json"), reverse=True)
                if result_files:
                    test_result_file = result_files[0]  # 使用最新的文件
                    self.logger.debug(f"找到测试结果文件: {test_result_file}")
                else:
                    self.logger.debug(f"统一文件夹中未找到测试结果文件: {latest_unified_folder}")
            else:
                # 如果没有统一文件夹，回退到旧的固件版本路径
                result_dir = project_root / "PowerConsumption_Data" / firmware_version
                
                # 查找最新的测试结果文件
                if result_dir.exists():
                    result_files = sorted(result_dir.glob("power_test_result-*.json"), reverse=True)
                    if result_files:
                        test_result_file = result_files[0]  # 使用最新的文件
                        self.logger.debug(f"找到测试结果文件: {test_result_file}")
                    else:
                        self.logger.debug(f"未找到测试结果文件: {result_dir}")
                else:
                    self.logger.debug(f"结果目录不存在: {result_dir}")
                
        except Exception as e:
            self.logger.debug(f"查找新路径测试结果文件失败: {e}")
        
        # 如果新路径找不到文件，尝试使用旧的路径结构
        if not test_result_file:
            test_result_file = Path(os.environ.get('REPORT_DIR', '.')) / "power_test_result.json"
        results = []
        is_test_all = False
        
        # 尝试从文件读取测试结果
        if test_result_file.exists():
            try:
                with open(test_result_file, 'r', encoding='utf-8') as f:
                    test_result_data = json.load(f)
                    is_test_all = test_result_data.get('test_all', False)
                    if 'results' in test_result_data and test_result_data['results']:
                        results = test_result_data['results']
                        self.logger.debug(f"从文件读取到 {len(results)} 个挡位测试结果")
            except Exception as e:
                self.logger.debug(f"读取测试结果文件失败: {e}")
        
        # 如果文件读取失败或没有results，从函数参数构建单挡位结果
        if not results:
            # 单挡位测试：从函数参数构建结果
            single_result = {
                'config_name': config_name or '未知',
                'battery_power': battery_power,
                'load_power': load_power,
                'error_message': error_message
            }
            results = [single_result]
            self.logger.debug("从函数参数构建单挡位测试结果")
        
        # 设置标题
        if is_test_all:
            # 多挡位测试，标题显示"全部挡位测试"
            title = f"📢 {dev}功耗测试结果（全部挡位测试）：{result_text}"
        elif config_name:
            title = f"📢 {dev}功耗测试结果（{config_name}）：{result_text}"
        else:
            title = f"📢 {dev}功耗测试结果：{result_text}"
        
        feishu_msg_template['i18n_header']['zh_cn']['title']['content'] = title
        
        # 构建基础信息（移除通过/失败用例数，添加固件地址、功耗数据等）
        context_parts = []
        
        # 固件地址（优先级：参数 > JSON配置 > 未配置）
        if not firmware_url:
            firmware_url = self.json_manager.get_value('firmware.download_url')
        
        if firmware_url:
            context_parts.append(f"🏷️ 固件地址：{firmware_url}")
        else:
            context_parts.append("🏷️ 固件地址：未配置")
        
        # 统一处理功耗数据（单挡位和多挡位使用相同的逻辑）
        power_parts = []
        module_power_parts = []
        for result_item in results:
            config_name_item = result_item.get('config_name', '')
            battery_power_item = result_item.get('battery_power')
            load_power_item = result_item.get('load_power')
            error_message_item = result_item.get('error_message')
            module_power_values_item = result_item.get('module_power_values', {})
            
            # 提取挡位名称（如 "4K30夜景_功耗测试" -> "4k30夜景"）
            if '_' in config_name_item:
                # 截取 "_" 前的所有内容，并转换为小写
                resolution = config_name_item.split('_')[0].lower()
            else:
                # 如果没有 "_"，使用整个配置名称的小写形式
                resolution = config_name_item.lower()
            
            # 构建功耗信息字符串
            power_info = f"{resolution}："
            if error_message_item:
                # 如果测试失败，显示错误信息
                power_info += f"<font color='red'>测试失败</font>"
            else:
                # 如果测试成功，显示功耗数据
                power_data_parts = []
                if battery_power_item:
                    power_data_parts.append(f"电池端：{battery_power_item}")
                if load_power_item:
                    power_data_parts.append(f"负载端：{load_power_item}")
                
                # 添加温度信息
                temperature_start_item = result_item.get('temperature_start')
                temperature_end_item = result_item.get('temperature_end')
                if temperature_start_item:
                    power_data_parts.append(f"起始温度：{temperature_start_item}")
                if temperature_end_item:
                    power_data_parts.append(f"结束温度：{temperature_end_item}")
                
                if power_data_parts:
                    power_info += "，".join(power_data_parts)
                else:
                    power_info += "无数据"
            
            power_parts.append(power_info)
            
            # 如果有模块功耗值，构建模块功耗信息
            if module_power_values_item:
                module_info_lines = []
                module_info_lines.append(f"{resolution}模块功耗：")
                
                # 从JSON配置中读取模块功耗单元格映射关系
                module_power_cells = self.json_manager.get_value('module_power_cells', default={})
                  
                # 收集所有模块功耗信息
                module_items = []
                for key, config in module_power_cells.items():
                    value = module_power_values_item.get(key)
                    display_name = config.get('display_name', key)
                    if value:
                        module_items.append(f"{display_name}：{value}")
                
                # 按每行4个模块进行格式化
                if module_items:
                    items_per_line = 4
                    for i in range(0, len(module_items), items_per_line):
                        line_items = module_items[i:i + items_per_line]
                        line = "   |   ".join(line_items)
                        module_info_lines.append(f"   {line}")
                
                if len(module_info_lines) > 1:
                    module_power_parts.extend(module_info_lines)
        
        # 添加功耗数据到消息
        if power_parts:
            context_parts.append("🏷️ 功耗数据：")
            for power_info in power_parts:
                context_parts.append(f"   {power_info}")
        
        # 添加模块功耗数据到消息
        if module_power_parts:
            context_parts.append("🏷️ 模块功耗：")
            for module_info in module_power_parts:
                context_parts.append(module_info)
        
        # 测试数据链接（优先级：参数 > Excel文件所在的数据文件夹 > 多挡位数据目录 > JSON配置）
        # 分离飞书链接和本地路径，两者都显示
        feishu_url = None
        local_path = None
        
        # 检查test_data_url是否是飞书链接
        if test_data_url and (test_data_url.startswith('https://') or test_data_url.startswith('http://')):
            # 检查是否是飞书链接
            if 'feishu.cn' in test_data_url or 'larkoffice.com' in test_data_url:
                feishu_url = test_data_url
                self.logger.debug(f"检测到飞书链接: {feishu_url}")
        
        # 获取本地路径（无论是否有飞书链接，都尝试获取本地路径）
        # 优先从excel_path获取数据文件夹路径（单挡位最准确）
        if excel_path:
            excel_path_obj = Path(excel_path)
            if excel_path_obj.exists():
                # 单挡位：使用Excel文件所在的目录（具体挡位文件夹）
                local_path = str(excel_path_obj.parent)
                self.logger.debug(f"单挡位从excel_path获取测试数据路径: {local_path}")
        elif is_test_all:
            # 多挡位：从测试结果中获取数据目录路径（固件版本目录）
            # 查找第一个有excel_file的结果，从中提取数据目录
            for result_item in results:
                excel_file = result_item.get('excel_file')
                if excel_file:
                    excel_path_obj = Path(excel_file)
                    if excel_path_obj.exists():
                        # 多挡位：使用固件版本目录（不包含具体挡位子目录）
                        local_path = str(excel_path_obj.parent.parent)
                        self.logger.debug(f"多挡位从测试结果获取数据目录路径: {local_path}")
                        break

        # 如果以上都没有，尝试从JSON配置读取
        if not local_path:
            local_path = self.json_manager.get_value('test_result.test_data_url')
            if local_path:
                self.logger.debug(f"从JSON配置获取测试数据路径: {local_path}")
        
        # 格式化测试数据链接显示（同时显示飞书链接和本地路径）
        if feishu_url or local_path:
            test_data_parts = []
            if feishu_url:
                # 飞书链接使用Markdown格式显示为可点击链接
                test_data_parts.append(f"[点击查看飞书文件夹]({feishu_url})")
            if local_path:
                # 本地路径直接显示
                test_data_parts.append(local_path)
            
            if test_data_parts:
                context_parts.append(f"🏷️ 测试数据：{' | '.join(test_data_parts)}")
        else:
            context_parts.append("🏷️ 测试数据：未配置")
        
        # 构建测试配置详细信息（包含分辨率、测试时长、setEnv配置等）
        config_info_parts = []
        
        # 1. 添加分辨率信息
        if config_name:
            resolution_match = re.search(r'(\d+[Kk]\d+)', config_name)
            if resolution_match:
                resolution = resolution_match.group(1).upper()  # 如 "4K60"
                config_info_parts.append(resolution)
        
        # 2. 添加测试时长（优先级：参数 > JSON配置中的record配置）
        if not test_duration and config_name:
            record_configs = self.json_manager.get_section('record')
            if record_configs:
                # 从record配置中查找匹配的配置名称
                for record_config in record_configs:
                    if record_config.get('name') == config_name:
                        test_duration = str(record_config.get('duration', ''))
                        break
        if test_duration:
            config_info_parts.append(f"测试时长: {test_duration}秒")
        
        # 3. 添加setEnv配置信息（从JSON读取）
        setenv_config = self.json_manager.get_section('setEnv')
        if setenv_config:
            # 构建setEnv配置字符串
            setenv_parts = []
            for key, value in setenv_config.items():
                field_name = SETENV_FIELD_NAMES.get(key, key)
                status = "开" if value else "关"
                setenv_parts.append(f"{field_name}: {status}")
            
            if setenv_parts:
                setenv_info = " | ".join(setenv_parts)
                config_info_parts.append(setenv_info)
        
        # 如果有配置信息，添加到消息中
        if config_info_parts:
            config_info = " | ".join(config_info_parts)
            context_parts.append(f"🏷️ 测试配置：{config_info}")
        else:
            self.logger.debug("测试配置信息为空，跳过显示")
        
        # 如果有错误信息，添加（放在最后，确保错误信息醒目）
        if error_msg:
            context_parts.append("")  # 添加空行分隔
            # error_msg 已经包含了 <font color='red'> 标签，直接使用
            # 注意：error_msg 可能已经包含 HTML 标签，直接拼接即可
            context_parts.append(f"❌ 错误原因：{error_msg}")
        
        context_base = "\n".join(context_parts) + "\n"
        
        # 设置消息内容到模板
        feishu_msg_template['i18n_elements']['zh_cn'][0]['content'] = context_base
        
        feishu_msg_template['i18n_elements']['zh_cn'] = [feishu_msg_template['i18n_elements']['zh_cn'][0]]
        
        # 调试日志：打印最终的消息模板
        self.logger.debug(f"最终消息模板的i18n_elements数量: {len(feishu_msg_template['i18n_elements']['zh_cn'])}")
        self.logger.debug(f"消息内容: {feishu_msg_template['i18n_elements']['zh_cn'][0].get('content', '')[:200]}")
        
        return feishu_msg_template
    
    def send_power_consumption_result(self, report_path: str, test_result: int = 0, 
                                     excel_path: str = None, config_name: str = None,
                                     firmware_url: str = None, battery_power: str = None,
                                     load_power: str = None, test_data_url: str = None,
                                     test_duration: str = None, error_message: str = None,
                                     module_power_values: dict = None,
                                     temperature_start: str = None, temperature_end: str = None) -> bool:
        """
        发送功耗测试结果到飞书
        
        职责说明：
        - 此方法只负责构建消息并调用底层发送
        - 上层（此方法）：构建消息字典
        - 底层（FeishuRequest.postCardMsg）：实际发送消息
        
        Args:
            report_path: HTML报告文件路径
            test_result: 测试结果（0=成功，非0=失败）
            excel_path: Excel文件路径（可选）
            config_name: 测试配置名称（可选，如 "4K60_功耗测试"）
            firmware_url: 固件地址（可选）
            battery_power: 电池端功耗（可选）
            load_power: 负载端功耗（可选）
            test_data_url: 测试数据链接（可选）
            test_duration: 测试时长（（秒，可选）
            error_message: 错误信息（可选）
            module_power_values: 模块功耗值字典（可选）
            temperature_start: 起始温度（可选）
            temperature_end: 结束温度（可选）
            
        Returns:
            bool: 发送是否成功
        """
        # 获取chat_id
        chat_id = self.get_chat_id()
        if not chat_id:
            self.logger.warning("未配置飞书chat_id，跳过飞书通知")
            return False
        
        # 检查是否启用
        if not self.is_enabled():
            self.logger.info("飞书通知已禁用（JSON配置中enabled=false）")
            return False
        
        try:
            # 步骤1：上层构建消息（只构建，不发送）
            feishu_msg_template = self.build_custom_message(
                report_path=report_path,
                test_result=test_result,
                excel_path=excel_path,
                config_name=config_name,
                firmware_url=firmware_url,
                battery_power=battery_power,
                load_power=load_power,
                test_data_url=test_data_url,  # 如果为None，build_custom_message会从excel_path获取
                test_duration=test_duration,
                error_message=error_message,
                module_power_values=module_power_values,
                temperature_start=temperature_start,
                temperature_end=temperature_end
            )
            
            if not feishu_msg_template:
                self.logger.error("自定义消息构建失败，无法发送飞书通知")
                return False
            
            # 步骤2：调用底层发送方法
            feishu_request = FeishuRequest(chat_id)
            result = feishu_request.postCardMsg(feishu_msg_template)
            self.logger.info(f"功耗测试结果已发送到飞书: {chat_id}")
            self.logger.debug(f"飞书API返回结果: {result}")
            return True
            
        except Exception as e:
            self.logger.error(f"发送飞书通知失败: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return False
    
    def save_error_message(self, message: str):
        """
        保存错误信息到环境变量和文件，供飞书通知使用
        
        Args:
            message: 错误信息
        """
        os.environ['POWER_TEST_ERROR_MESSAGE'] = message
        test_result_file = Path(os.environ.get('REPORT_DIR', '.')) / "power_test_result.json"
        try:
            test_result_data = {}
            if test_result_file.exists():
                with open(test_result_file, 'r', encoding='utf-8') as f:
                    test_result_data = json.load(f)
            test_result_data['error_message'] = message
            with open(test_result_file, 'w', encoding='utf-8') as f:
                json.dump(test_result_data, f, ensure_ascii=False, indent=2)
            self.logger.debug(f"错误信息已保存到文件: {test_result_file}")
        except Exception as e:
            self.logger.warning(f"保存错误信息到文件失败: {e}")



# ============= 测试用例 =============
def test_feishu_message_building():
    """
    测试飞书消息构建功能
    
    可以自定义测试数据，测试单挡位和多挡位两种情况
    """
    print("=" * 80)
    print("开始测试飞书消息构建功能")
    print("=" * 80)
    
    # 导入必要的模块
    from src.utils.config_manager import ConfigManager
    from src.utils.logger import Logger
    import tempfile
    import shutil
    
    # 初始化基础对象
    logger = Logger()
    config = ConfigManager()
    
    # 获取设备名称
    device_name = os.environ.get('FW_DEV', 'Z03')
    if device_name == 'Unknow':
        device_name = 'Z03'
    
    print(f"设备名称: {device_name}")
    
    # 创建飞书报告实例
    feishu_report = PowerConsumptionFeishuReport(config, logger, device_name)
    
    # 创建临时目录用于测试
    temp_dir = tempfile.mkdtemp(prefix="feishu_test_")
    report_dir = Path(temp_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    
    # 设置环境变量
    original_report_dir = os.environ.get('REPORT_DIR')
    os.environ['REPORT_DIR'] = str(report_dir)
    
    try:
        # 创建假的报告文件
        report_path = report_dir / "power_consumption_report.html"
        report_path.write_text("<html><body>Test Report</body></html>")
        
        # ========== 测试1: 单挡位测试（成功） ==========
        print("\n" + "-" * 80)
        print("测试1: 单挡位测试（成功）")
        print("-" * 80)
        
        test_result_file = report_dir / "power_test_result.json"
        test_result_data = {
            'test_all': False,
            'config_name': '4K60_功耗测试',
            'battery_power': '3000',
            'load_power': '2000',
            'excel_file': str(report_dir / "test_data.xlsx"),
            'test_duration': '10',
            'error_message': None
        }
        with open(test_result_file, 'w', encoding='utf-8') as f:
            json.dump(test_result_data, f, ensure_ascii=False, indent=2)
        
        # 构建消息
        feishu_msg = feishu_report.build_custom_message(
            report_path=str(report_path),
            test_result=0,  # 成功
            excel_path=str(report_dir / "test_data.xlsx"),
            config_name='4K60_功耗测试',
            firmware_url='https://conan.insta360.cn/ui/native/fw-dev/Z03/Z03_ALL_POST_CS/2026-01/Z03_V1.3.133_dev_20260119122304_z03_release_8625/ota/',
            battery_power='3000',
            load_power='2000',
            test_data_url=str(report_dir),
            test_duration='10',
            error_message=None
        )
        
        if feishu_msg:
            print("✓ 单挡位消息构建成功")
            print(f"标题: {feishu_msg['i18n_header']['zh_cn']['title']['content']}")
            print(f"内容预览:\n{feishu_msg['i18n_elements']['zh_cn'][0]['content'][:500]}...")
        else:
            print("✗ 单挡位消息构建失败")
        
        # ========== 测试2: 单挡位测试（失败） ==========
        print("\n" + "-" * 80)
        print("测试2: 单挡位测试（失败）")
        print("-" * 80)
        
        test_result_data['error_message'] = '视频分辨率验证失败'
        with open(test_result_file, 'w', encoding='utf-8') as f:
            json.dump(test_result_data, f, ensure_ascii=False, indent=2)
        
        feishu_msg = feishu_report.build_custom_message(
            report_path=str(report_path),
            test_result=1,  # 失败
            excel_path=str(report_dir / "test_data.xlsx"),
            config_name='4K60_功耗测试',
            firmware_url='https://conan.insta360.cn/ui/native/fw-dev/Z03/Z03_ALL_POST_CS/2026-01/Z03_V1.3.133_dev_20260119122304_z03_release_8625/ota/',
            battery_power='3000',
            load_power='2000',
            test_data_url=str(report_dir),
            test_duration='10',
            error_message='视频分辨率验证失败'
        )
        
        if feishu_msg:
            print("✓ 单挡位失败消息构建成功")
            print(f"标题: {feishu_msg['i18n_header']['zh_cn']['title']['content']}")
            print(f"内容预览:\n{feishu_msg['i18n_elements']['zh_cn'][0]['content'][:500]}...")
        else:
            print("✗ 单挡位失败消息构建失败")
        
        # ========== 测试3: 多挡位测试（全部成功） ==========
        print("\n" + "-" * 80)
        print("测试3: 多挡位测试（全部成功）")
        print("-" * 80)
        
        test_result_data = {
            'test_all': True,
            'results': [
                {
                    'config_name': '4K30_功耗测试',
                    'battery_power': '2500',
                    'load_power': '1800',
                    'error_message': None
                },
                {
                    'config_name': '4K60_功耗测试',
                    'battery_power': '3000',
                    'load_power': '2000',
                    'error_message': None
                },
                {
                    'config_name': '8K30_功耗测试',
                    'battery_power': '3500',
                    'load_power': '2500',
                    'error_message': None
                }
            ]
        }
        with open(test_result_file, 'w', encoding='utf-8') as f:
            json.dump(test_result_data, f, ensure_ascii=False, indent=2)
        
        feishu_msg = feishu_report.build_custom_message(
            report_path=str(report_path),
            test_result=0,  # 成功
            excel_path=str(report_dir / "test_data.xlsx"),
            config_name=None,  # 多挡位时不使用单个config_name
            firmware_url='https://conan.insta360.cn/ui/native/fw-dev/Z03/Z03_ALL_POST_CS/2026-01/Z03_V1.3.133_dev_20260119122304_z03_release_8625/ota/',
            test_data_url=str(report_dir)
        )
        
        if feishu_msg:
            print("✓ 多挡位消息构建成功")
            print(f"标题: {feishu_msg['i18n_header']['zh_cn']['title']['content']}")
            print(f"内容预览:\n{feishu_msg['i18n_elements']['zh_cn'][0]['content'][:800]}...")
        else:
            print("✗ 多挡位消息构建失败")
        
        # ========== 测试4: 多挡位测试（部分失败） ==========
        print("\n" + "-" * 80)
        print("测试4: 多挡位测试（部分失败）")
        print("-" * 80)
        
        test_result_data['results'][1]['error_message'] = '视频帧率验证失败'
        with open(test_result_file, 'w', encoding='utf-8') as f:
            json.dump(test_result_data, f, ensure_ascii=False, indent=2)
        
        feishu_msg = feishu_report.build_custom_message(
            report_path=str(report_path),
            test_result=1,  # 失败
            excel_path=str(report_dir / "test_data.xlsx"),
            config_name=None,
            firmware_url='https://conan.insta360.cn/ui/native/fw-dev/Z03/Z03_ALL_POST_CS/2026-01/Z03_V1.3.133_dev_20260119122304_z03_release_8625/ota/',
            test_data_url=str(report_dir)
        )
        
        if feishu_msg:
            print("✓ 多挡位部分失败消息构建成功")
            print(f"标题: {feishu_msg['i18n_header']['zh_cn']['title']['content']}")
            print(f"内容预览:\n{feishu_msg['i18n_elements']['zh_cn'][0]['content'][:800]}...")
        else:
            print("✗ 多挡位部分失败消息构建失败")
        
        # ========== 测试5: 自定义消息内容 ==========
        print("\n" + "-" * 80)
        print("测试5: 自定义消息内容")
        print("-" * 80)
        print("你可以修改下面的参数来自定义消息内容：")
        
        # 自定义参数
        custom_config_name = "4K120_功耗测试"
        custom_battery_power = "4500"
        custom_load_power = "3200"
        custom_firmware_url = "https://example.com/firmware"
        custom_error_message = None  # 设置为字符串表示失败，None表示成功
        
        test_result_data = {
            'test_all': False,
            'config_name': custom_config_name,
            'battery_power': custom_battery_power,
            'load_power': custom_load_power,
            'error_message': custom_error_message
        }
        with open(test_result_file, 'w', encoding='utf-8') as f:
            json.dump(test_result_data, f, ensure_ascii=False, indent=2)
        
        feishu_msg = feishu_report.build_custom_message(
            report_path=str(report_path),
            test_result=0 if custom_error_message is None else 1,
            excel_path=str(report_dir / "test_data.xlsx"),
            config_name=custom_config_name,
            firmware_url=custom_firmware_url,
            battery_power=custom_battery_power,
            load_power=custom_load_power,
            test_data_url=str(report_dir),
            test_duration='15',
            error_message=custom_error_message
        )
        
        if feishu_msg:
            print("✓ 自定义消息构建成功")
            print(f"标题: {feishu_msg['i18n_header']['zh_cn']['title']['content']}")
            print("\n完整消息内容:")
            print("-" * 80)
            print(feishu_msg['i18n_elements']['zh_cn'][0]['content'])
            print("-" * 80)
            
            # 可以选择是否实际发送（需要配置飞书chat_id）
            send_choice = input("\n是否发送到飞书？(y/n，默认n): ").strip().lower()
            if send_choice == 'y':
                success = feishu_report.send_power_consumption_result(
                    report_path=str(report_path),
                    test_result=0 if custom_error_message is None else 1,
                    excel_path=str(report_dir / "test_data.xlsx"),
                    config_name=custom_config_name,
                    firmware_url=custom_firmware_url,
                    battery_power=custom_battery_power,
                    load_power=custom_load_power,
                    test_data_url=str(report_dir),
                    test_duration='15',
                    error_message=custom_error_message
                )
                if success:
                    print("✓ 消息已发送到飞书")
                else:
                    print("✗ 消息发送失败（可能未配置chat_id或已禁用）")
            else:
                print("跳过发送，仅测试消息构建")
        else:
            print("✗ 自定义消息构建失败")
        
        print("\n" + "=" * 80)
        print("所有测试完成")
        print("=" * 80)
        
    finally:
        # 恢复环境变量
        if original_report_dir:
            os.environ['REPORT_DIR'] = original_report_dir
        elif 'REPORT_DIR' in os.environ:
            del os.environ['REPORT_DIR']
        
        # 清理临时目录
        try:
            shutil.rmtree(temp_dir)
            print(f"\n已清理临时目录: {temp_dir}")
        except Exception as e:
            print(f"\n清理临时目录失败: {e}")


if __name__ == "__main__":
    # 如果直接运行此文件，执行测试
    test_feishu_message_building()