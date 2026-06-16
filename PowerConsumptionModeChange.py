#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
功耗测试 - 相机配置模块
提供从JSON配置文件读取相机配置并设置相机的API
"""
import os
import time
import sys
import re
import json
from pathlib import Path

# 添加项目根目录到Python路径
current_file = Path(__file__).resolve()
project_root = current_file.parent.parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.utils.config_manager import ConfigManager
from src.utils.logger import Logger
from src.core.dev import InsDev
from src.app.media import InsMedia
from src.app.PowerConsumption.PowerConsumption_jsonManager import PowerConsumptionJsonManager


class PowerConsumptionModeChange(InsMedia):
    """
    功耗测试相机配置类
    继承自InsMedia，提供从JSON配置文件读取配置并设置相机的API
    """
    
    def __init__(self, dev: InsDev, config: ConfigManager, logger: Logger):
        super().__init__(dev, config, logger)
        self.record_config = None  # 当前录制的配置信息
        self.record_duration = 0  # 录制时长（秒）
        
        # JSON配置管理器
        dev_name = dev.name if hasattr(dev, 'name') else None
        self.json_manager = PowerConsumptionJsonManager(dev_name=dev_name, logger=self.logger)
    
    
    def prepare_for_power_test(self, log_dir=None) -> bool:
        """
        准备功耗测试环境
        
        Args:
            log_dir: 日志目录，如果为None则使用默认tmp目录
        
        Returns:
            bool: 准备是否成功
        """
        # 检查媒体环境
        if not self.check_media_env():
            self.logger.error("媒体环境检查失败")
            return False
        
        # 启动ipcmedia_client
        if not self.start_ipcmedia_client(log_dir):
            self.logger.error("ipcmedia_client启动失败")
            return False
        
        # 清理旧的core文件
        self.remove_coredump()
        
        return True
    
    def cleanup_after_power_test(self):
        """
        清理功耗测试环境
        """
        if self.ipcmedia_process:
            self.stop_ipcmedia_client()
            self.logger.info("已停止ipcmedia_client")
    
    def load_record_config(self, config_name: str = None, json_file: str = None) -> dict:
        """
        从JSON文件加载功耗测试配置
        
        Args:
            config_name: 配置名称（如 "4K60_功耗测试"），如果为None则使用第一个record配置
            json_file: JSON文件路径，如果为None则使用默认路径 data/{device}/power_consumption.json
        
        Returns:
            dict: 配置字典，包含 mode, config, duration, width, height 等字段，如果失败则返回None
        """
        # 直接获取 record section
        record_configs = self.json_manager.get_section('record', json_file)
        if not record_configs:
            self.logger.error("JSON文件中没有record配置")
            return None
        
        # 根据配置名称查找，如果未指定则使用第一个
        if config_name:
            for record_config in record_configs:
                if record_config.get('name') == config_name:
                    self.logger.info(f"找到配置: {config_name}")
                    return record_config
            self.logger.error(f"未找到配置: {config_name}")
            return None
        else:
            # 使用第一个record配置
            record_config = record_configs[0]
            config_name = record_config.get('name', '默认配置')
            self.logger.info(f"使用第一个配置: {config_name}")
            return record_config
    
    def setup_and_start_record(self, config_name: str = None, json_file: str = None, verify: bool = True) -> bool:
        """
        从JSON文件读取配置，设置相机并开启录制
        
        Args:
            config_name: 配置名称（如 "4K60_功耗测试"），如果为None则使用第一个record配置
            json_file: JSON文件路径，如果为None则使用默认路径
            verify: 是否验证设置成功，默认True
        
        Returns:
            bool: 设置和开启录制是否成功
        """
        # 加载配置
        record_config = self.load_record_config(config_name, json_file)
        if not record_config:
            self.logger.error("加载JSON配置失败")
            return False
        
        # 保存配置信息
        self.record_config = record_config
        self.record_duration = record_config.get('duration', 0)
        
        config_name_display = record_config.get('name', '未知配置')
        self.logger.info(f"开始设置相机配置: {config_name_display}")
        self.logger.info(f"录制时长: {self.record_duration}秒")
        
        result = True
        
        # 执行mode命令
        if 'mode' in record_config:
            mode_cmd = record_config['mode']
            self.logger.debug(f"执行mode命令: {mode_cmd}")
            success, response = self.execute_command(mode_cmd)
            if not success:
                self.logger.error(f"执行mode命令失败: {mode_cmd}")
                result = False
            elif not self.response_handle(response):
                self.logger.error(f"mode命令响应处理失败")
                result = False
            else:
                time.sleep(2)  # 等待模式切换完成
        
        # 执行config命令列表
        if 'config' in record_config and record_config['config']:
            config_list = record_config['config']
            for config_item in config_list:
                self.logger.debug(f"执行config命令: {config_item}")
                success, response = self.execute_command(config_item)
                if not success:
                    self.logger.error(f"执行config命令失败: {config_item}")
                    result = False
                elif not self.response_handle(response):
                    self.logger.warning(f"config命令响应处理失败: {config_item}")
                    # config命令失败不一定是致命错误，继续执行
                else:
                    time.sleep(0.5)  # 等待配置生效
        
        if not result:
            self.logger.error("相机配置设置失败")
            return False
        
        # 根据JSON配置决定是否开启录制
        should_record = record_config.get('record', True)
        
        if should_record:
            # 开启录制
            self.logger.debug("开启录制")
            success, response = self.execute_command("record start")
            if not success:
                self.logger.error("开启录制失败")
                return False
            elif not self.response_handle(response):
                self.logger.error("开启录制响应处理失败")
                return False
            
            time.sleep(2)  # 等待录制稳定
            self.logger.info(f"相机配置设置完成: {config_name_display}")
        else:
            # 预览模式，不开启录制
            self.logger.debug("预览模式，不开启录制")
            time.sleep(1)  # 等待预览稳定
            self.logger.info(f"相机配置设置完成: {config_name_display}")
        
        return True
