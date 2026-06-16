#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
功耗测试 - 固件下载和OTA升级模块
封装固件下载和OTA升级功能，提供简洁的接口供功耗测试使用
"""
import os
import sys
import time
import json
import re
from pathlib import Path

# 添加项目根目录到Python路径
current_file = Path(__file__).resolve()
project_root = current_file.parent.parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.utils.config_manager import ConfigManager
from src.utils.logger import Logger
from src.core.dev import InsDev
from src.app.ota import InsOTA
from src.app.PowerConsumption.PowerConsumption_jsonManager import PowerConsumptionJsonManager
from src.app.PowerConsumption.PowerConsumption_utils import is_local_path


class PowerConsumptionDownloadFirmware:
    """
    功耗测试固件下载和OTA升级类
    封装InsOTA功能，提供简洁的接口
    """
    
    def __init__(self, dev: InsDev, config: ConfigManager, logger: Logger):
        """
        初始化固件下载和OTA升级类
        
        Args:
            dev: 设备对象
            config: 配置管理器
            logger: 日志记录器
        """
        self.dev = dev
        self.config = config
        self.logger = logger
        self.ota = InsOTA(dev, config, logger)
        self.firmware_path = None  # 下载的固件本地路径
        self.remote_firmware_path = None  # 上传到设备的固件路径
        self.firmware_config = None  # 从JSON加载的固件配置
        
        # JSON配置管理器
        dev_name = dev.name if hasattr(dev, 'name') else None
        self.json_manager = PowerConsumptionJsonManager(dev_name=dev_name, logger=self.logger)
    
    def load_firmware_config(self, json_file: str = None) -> dict:
        """
        从JSON文件加载固件配置
        
        Args:
            json_file: JSON文件路径，如果为None则使用默认路径 data/{device}/power_consumption.json
        
        Returns:
            dict: 固件配置字典，包含 download_url, timeout, verify_version 等字段，如果失败则返回None
        """
        # 直接获取 firmware section
        firmware_config = self.json_manager.get_section('firmware', json_file)
        if not firmware_config:
            self.logger.warning("JSON文件中没有firmware配置，将使用默认值")
            return None
        
        self.logger.info(f"从JSON文件加载固件配置成功")
        self.logger.debug(f"固件配置: {firmware_config}")
        
        # 保存配置
        self.firmware_config = firmware_config
        
        return firmware_config
    
    def download_firmware(self, download_url: str = None, json_file: str = None) -> tuple[bool, str]:
        """
        从URL下载OTA固件
        
        Args:
            download_url: 固件下载URL（JFrog路径），如果为None则从JSON文件读取
            json_file: JSON文件路径，如果为None则使用默认路径
            
        Returns:
            tuple[bool, str]: (下载是否成功, 错误信息)
        """
        self.logger.info("开始下载OTA固件")
        
        # 如果未提供URL，尝试从JSON文件读取
        if not download_url:
            self.logger.info("未提供固件URL，尝试从JSON文件读取")
            firmware_config = self.load_firmware_config(json_file)
            
            if firmware_config and firmware_config.get('download_url'):
                download_url = firmware_config.get('download_url')
                self.logger.debug(f"从JSON文件读取到固件URL: {download_url}")
            else:
                error_msg = "固件下载URL为空，且JSON文件中也没有配置URL。请在JSON文件的firmware.download_url中配置固件URL，或通过参数传入"
                self.logger.error(error_msg)
                return False, error_msg
        
        if not download_url:
            error_msg = "固件下载URL为空"
            self.logger.error(error_msg)
            return False, error_msg
        
        self.logger.debug(f"固件下载URL: {download_url}")
        
        # 调用InsOTA的download方法
        firmware_path = self.ota.download(download_url)
        
        if not firmware_path:
            error_msg = "固件下载失败"
            self.logger.error(error_msg)
            return False, error_msg
        
        if not os.path.exists(firmware_path):
            error_msg = f"下载的固件文件不存在: {firmware_path}"
            self.logger.error(error_msg)
            return False, error_msg
        
        self.firmware_path = firmware_path
        firmware_name = os.path.basename(firmware_path)
        file_size = os.path.getsize(firmware_path) / (1024 * 1024)  # MB
        self.logger.info(f"固件下载成功: {firmware_name} ({file_size:.2f} MB)")
        
        return True, ""
    
    def load_firmware_from_local(self, local_firmware_path: str) -> tuple[bool, str]:
        """
        从本地路径加载固件文件
        
        Args:
            local_firmware_path: 本地固件文件路径（.bin文件）
            
        Returns:
            tuple[bool, str]: (加载是否成功, 错误信息)
        """
        self.logger.info(f"开始从本地路径加载固件: {local_firmware_path}")
        
        # 转换为Path对象
        firmware_path = Path(local_firmware_path)
        
        # 检查文件是否存在
        if not firmware_path.exists():
            error_msg = f"本地固件文件不存在: {local_firmware_path}"
            self.logger.error(error_msg)
            return False, error_msg
        
        # 检查是否为文件（不是目录）
        if not firmware_path.is_file():
            error_msg = f"指定的路径不是文件: {local_firmware_path}"
            self.logger.error(error_msg)
            return False, error_msg
        
        # 检查文件扩展名（可选，但建议是.bin）
        if firmware_path.suffix.lower() not in ['.bin', '.ota']:
            self.logger.warning(f"固件文件扩展名不是.bin或.ota: {firmware_path.suffix}")
        
        # 检查文件大小（应该大于0）
        file_size = firmware_path.stat().st_size
        if file_size == 0:
            error_msg = f"固件文件大小为0: {local_firmware_path}"
            self.logger.error(error_msg)
            return False, error_msg
        
        # 保存固件路径
        self.firmware_path = str(firmware_path.resolve())
        firmware_name = firmware_path.name
        file_size_mb = file_size / (1024 * 1024)  # MB
        self.logger.info(f"本地固件加载成功: {firmware_name} ({file_size_mb:.2f} MB)")
        
        return True, ""
    
    def upload_firmware_to_device(self) -> tuple[bool, str]:
        """
        将固件上传到设备（可以是下载的或本地加载的）
        
        Returns:
            tuple[bool, str]: (上传是否成功, 错误信息)
        """
        if not self.firmware_path:
            error_msg = "未找到固件文件，请先调用download_firmware()或load_firmware_from_local()"
            self.logger.error(error_msg)
            return False, error_msg
        
        self.logger.info("开始上传固件到设备")
        
        # 调用InsOTA的upload_firmware方法
        remote_path = self.ota.upload_firmware(self.firmware_path)
        
        if not remote_path:
            error_msg = "固件上传到设备失败"
            self.logger.error(error_msg)
            return False, error_msg
        
        self.remote_firmware_path = remote_path
        self.logger.info(f"固件上传成功: {remote_path}")
        
        return True, ""
    
    def start_ota_upgrade(self, log_dir: str = None, log_suffix: str = "") -> tuple[bool, str]:
        """
        启动OTA升级
        
        Args:
            log_dir: 日志目录，如果为None则使用环境变量REPORT_DIR
            log_suffix: 日志文件名后缀，用于区分多次OTA升级
            
        Returns:
            tuple[bool, str]: (启动是否成功, 错误信息)
        """
        if not self.remote_firmware_path:
            error_msg = "未找到设备上的固件，请先调用upload_firmware_to_device()"
            self.logger.error(error_msg)
            return False, error_msg
        
        self.logger.info("开始启动OTA升级")
        
        # 调用InsOTA的start_ota方法
        success = self.ota.start_ota(self.remote_firmware_path, log_dir=log_dir, log_suffix=log_suffix)
        
        if not success:
            error_msg = "OTA升级启动失败"
            self.logger.error(error_msg)
            return False, error_msg
        
        self.logger.info("OTA升级已启动，开始监控升级进度")
        
        return True, ""
    
    def monitor_ota_progress(self, timeout: int = 600) -> tuple[bool, str]:
        """
        监控OTA升级进度，通过检测设备是否在位来判断OTA状态
        
        Args:
            timeout: 超时时间（秒），默认600秒（10分钟）
            
        Returns:
            tuple[bool, str]: (是否检测到设备重启, 错误信息)
                - (True, "") 表示检测到设备重启（OTA可能完成）
                - (False, "错误信息") 表示超时或其他错误
        """
        self.logger.info("开始监控OTA升级进度（通过检测设备状态）")
        self.logger.debug(f"监控超时时间: {timeout}秒")
        
        start_time = time.time()
        check_interval = 5  # 每5秒检查一次设备状态
        last_info_log_time = start_time  # 上次打印INFO日志的时间
        info_log_interval = 30  # 每30秒打印一次INFO级别的提醒日志
        
        while time.time() - start_time < timeout:
            # 检查设备是否在位（ADB是否在线）
            is_online = self.dev.isOnline(timeout=3, _exit=False)
            
            if is_online:
                # 设备还在位，说明还在OTA升级中
                elapsed = int(time.time() - start_time)
                remaining = int(timeout - elapsed)
                
                # 每隔一定时间打印INFO级别的提醒日志
                current_time = time.time()
                if current_time - last_info_log_time >= info_log_interval:
                    self.logger.info(f"设备在线，OTA升级进行中... 已用时: {elapsed}秒，剩余: {remaining}秒")
                    last_info_log_time = current_time
                else:
                    # 其他时候打印DEBUG级别的详细日志
                    self.logger.debug(f"设备在线，OTA升级进行中... 已用时: {elapsed}秒，剩余: {remaining}秒")
            else:
                # 设备不在位，说明设备已重启，OTA升级可能完成
                elapsed = int(time.time() - start_time)
                self.logger.info(f"检测到设备离线（已用时: {elapsed}秒），设备可能已重启，退出监控")
                return True, ""
            
            time.sleep(check_interval)
        
        # 超时
        elapsed = int(time.time() - start_time)
        error_msg = f"OTA监控超时（{elapsed}秒），设备始终在线，未检测到重启"
        self.logger.warning(error_msg)
        return False, error_msg
    
    def wait_for_device_reboot(self, max_wait_time: int = 180) -> tuple[bool, str]:
        """
        等待设备重启并检测ADB是否重新在线
        
        Args:
            max_wait_time: 最大等待时间（秒），默认180秒
            
        Returns:
            tuple[bool, str]: (是否成功, 错误信息)
        """
        self.logger.info("等待设备重启，检测ADB是否重新在线...")
        self.logger.debug(f"最大等待时间: {max_wait_time}秒")
        
        start_time = time.time()
        check_interval = 5  # 每5秒检查一次
        
        while time.time() - start_time < max_wait_time:
            if self.dev.isOnline(timeout=3, _exit=False):
                elapsed = int(time.time() - start_time)
                self.logger.info(f"ADB连接已恢复（等待时间: {elapsed}秒）")
                
                # ADB连接恢复后，再等待一段时间确保设备完全启动
                self.logger.debug("等待设备完全启动...")
                time.sleep(10)
                
                # 再次验证ADB连接
                if not self.dev.isOnline(timeout=10, _exit=False):
                    error_msg = "ADB连接恢复后验证失败"
                    self.logger.error(error_msg)
                    return False, error_msg
                
                self.logger.info("设备已就绪")
                return True, ""
            else:
                elapsed = int(time.time() - start_time)
                remaining = int(max_wait_time - elapsed)
                if remaining > 0:
                    self.logger.debug(f"等待ADB重连... 已等待: {elapsed}秒，剩余: {remaining}秒")
                time.sleep(check_interval)
        
        # 超时
        error_msg = f"设备重启后ADB连接超时（等待{max_wait_time}秒）"
        self.logger.error(error_msg)
        return False, error_msg
    
    def verify_ota_result(self, old_version: str = None) -> tuple[bool, str]:
        """
        验证OTA升级结果
        
        Args:
            old_version: 升级前的版本号，用于版本对比
            
        Returns:
            tuple[bool, str]: (验证是否通过, 错误信息)
        """
        self.logger.info("开始验证OTA升级结果")
        
        # 1. 版本验证（如果提供了old_version）
        version_check_passed = True
        if old_version:
            new_version = self.ota.get_version()
            if not new_version:
                error_msg = "无法获取升级后的固件版本"
                self.logger.error(error_msg)
                return False, error_msg
            
            if new_version == old_version:
                self.logger.warning("版本未变化(如果是OTA到相同版本请忽略此条警告)")
            else:
                self.logger.info(f"版本已更新: {old_version} -> {new_version}")
        
        # 2. 检查关键进程（仅记录警告，不影响升级结果）
        self.logger.info("检查OTA升级后关键进程状态")
        success, failed_processes = self.ota.check_process_start()
        
        if not success:
            # 有关键进程未启动，记录警告但不判定为失败
            warning_msg = f"警告：以下关键进程未正常启动: {', '.join(failed_processes)}"
            self.logger.warning(warning_msg)
            self.logger.warning("进程检查失败不影响OTA升级结果判定，但建议检查设备状态")
        else:
            self.logger.info("所有关键进程运行正常")
        
        # 版本验证通过即认为升级成功（进程检查只作为警告）
        self.logger.info("OTA升级验证通过（进程检查仅作为警告）")
        return True, ""
    
    def get_current_version(self) -> str:
        """
        获取设备当前版本号
        
        Returns:
            str: 版本号，如果获取失败则返回None
        """
        version = self.ota.get_version()
        if version:
            self.logger.info(f"设备当前版本: {version}")
        else:
            self.logger.warning("获取设备版本失败")
        return version
    
    def extract_version_from_url(self, url: str) -> str | None:
        """
        从固件下载URL中提取版本号
        
        Args:
            url: 固件下载URL，例如: https://conan.insta360.cn/ui/native/fw-dev/Z03/Z03_ALL_POST_CS/2026-01/Z03_V1.3.133_dev_20260119122304_z03_release_8625/ota/
        
        Returns:
            str | None: 提取的版本号（例如: V1.3.133），如果提取失败则返回None
        """
        if not url:
            return None
        
        # 使用工具类直接提取V版本号
        from src.app.PowerConsumption.PowerConsumption_utils import extract_v_version
        version = extract_v_version(url)
        
        if version:
            self.logger.debug(f"从URL中提取到版本号: {version}")
            return version
        
        self.logger.warning(f"无法从URL中提取版本号: {url}")
        return None
    
    def extract_version_from_device(self, version_data) -> str | None:
        """
        从设备版本信息中提取版本号
        
        Args:
            version_data: get_current_version()返回的版本数据（可能是字符串或字典）
        
        Returns:
            str | None: 提取的版本号（例如: V1.3.133），如果提取失败则返回None
        """
        if not version_data:
            return None
        
        version_str = None
        
        # 如果version_data是字典，尝试从Insta360_Version字段提取
        if isinstance(version_data, dict):
            if 'Insta360_Version' in version_data:
                version_str = version_data['Insta360_Version']
            else:
                # 尝试直接查找包含Version的字段
                for key, value in version_data.items():
                    if isinstance(value, str) and 'Version:' in value:
                        version_str = value
                        break
        elif isinstance(version_data, str):
            version_str = version_data
        
        if not version_str:
            self.logger.warning(f"无法从版本数据中提取版本字符串: {version_data}")
            return None
        
        # 从 "Version:V1.3.133" 中提取 "V1.3.133"
        # 使用正则表达式匹配 V数字.数字.数字
        pattern = r'(V\d+\.\d+\.\d+)'
        match = re.search(pattern, version_str)
        
        if match:
            version = match.group(1)
            self.logger.debug(f"从设备版本信息中提取到版本号: {version}")
            return version
        else:
            self.logger.warning(f"无法从版本字符串中提取版本号: {version_str}")
            return None
    
    def check_version_match(self, url: str) -> tuple[bool, str | None, str | None]:
        """
        检查URL中的版本号是否与设备当前版本一致
        
        Args:
            url: 固件下载URL
        
        Returns:
            tuple[bool, str | None, str | None]: (是否一致, URL版本号, 设备版本号)
                如果版本一致返回 (True, url_version, device_version)
                如果版本不一致或无法比较返回 (False, url_version, device_version)
        """
        # 从URL中提取版本号
        url_version = self.extract_version_from_url(url)
        if not url_version:
            self.logger.warning("无法从URL中提取版本号，将跳过版本检查")
            return False, None, None
        
        # 获取设备当前版本
        device_version_data = self.get_current_version()
        if not device_version_data:
            self.logger.warning("无法获取设备版本，将跳过版本检查")
            return False, url_version, None
        
        # 从设备版本信息中提取版本号
        device_version = self.extract_version_from_device(device_version_data)
        if not device_version:
            self.logger.warning("无法从设备版本信息中提取版本号，将跳过版本检查")
            return False, url_version, None
        
        # 比较版本号
        if url_version == device_version:
            self.logger.info(f"版本号一致，URL版本: {url_version}, 设备版本: {device_version}")
            return True, url_version, device_version
        else:
            self.logger.info(f"版本号不一致，URL版本: {url_version}, 设备版本: {device_version}")
            return False, url_version, device_version
    
    def check_environment(self) -> bool:
        """
        检查OTA升级环境（ADB连接等）
        
        Returns:
            bool: 环境检查是否通过
        """
        self.logger.info("检查OTA升级环境")
        success = self.ota.check_env()
        if success:
            self.logger.info("环境检查通过")
        else:
            self.logger.error("环境检查失败")
        return success
    
    def download_and_upgrade(self, download_url: str = None, timeout: int = None, 
                           log_dir: str = None, log_suffix: str = "", 
                           verify_version: bool = None, json_file: str = None) -> tuple[bool, str]:
        """
        完整的OTA升级流程：自动检测是本地路径还是URL，然后执行相应的加载/下载流程
        -> 上传到设备 -> 启动升级 -> 监控进度 -> 等待重启 -> 验证结果
        
        Args:
            download_url: 固件下载URL或本地文件路径，如果为None则从JSON文件读取
            timeout: 升级监控超时时间（秒），如果为None则从JSON文件读取，默认600秒
            log_dir: 日志目录
            log_suffix: 日志文件名后缀
            verify_version: 是否验证版本号变化，如果为None则从JSON文件读取，默认True
            json_file: JSON文件路径，如果为None则使用默认路径
            
        Returns:
            tuple[bool, str]: (整个流程是否成功, 错误信息)
        """
        self.logger.info("开始执行完整的OTA升级流程")
        
        # 从JSON文件加载配置（优先从JSON读取，不再考虑pytest优先级）
        firmware_config = self.load_firmware_config(json_file)
        
        # 处理超时时间：优先从JSON文件读取
        if timeout is None:
            if firmware_config and 'timeout' in firmware_config:
                timeout = firmware_config.get('timeout')
                if isinstance(timeout, (int, float)) and timeout > 0:
                    timeout = int(timeout)
                    self.logger.info(f"从JSON文件读取OTA超时时间: {timeout}秒")
                else:
                    self.logger.warning(f"JSON文件中的timeout配置无效: {timeout}，使用默认值600秒")
                    timeout = 600
            else:
                self.logger.warning("JSON文件中未配置timeout，使用默认值600秒")
                timeout = 600
        else:
            self.logger.debug(f"使用传入的OTA超时时间: {timeout}秒")
        
        # 处理固件URL或本地路径：优先从JSON文件读取
        if not download_url:
            if firmware_config and 'download_url' in firmware_config:
                download_url = firmware_config.get('download_url')
                self.logger.debug(f"从JSON文件读取固件路径/URL: {download_url}")
            else:
                self.logger.warning("JSON文件中未配置download_url")
        
        if not download_url:
            error_msg = "未提供固件URL或本地路径，且JSON文件中也没有配置"
            self.logger.error(error_msg)
            return False, error_msg
        
        # 判断是本地路径还是URL
        is_local = is_local_path(download_url)
        
        if is_local:
            self.logger.info(f"检测到本地路径，将使用本地固件文件: {download_url}")
        else:
            self.logger.info(f"检测到URL，将从网络下载固件: {download_url}")
        
        # 处理版本验证：优先从JSON文件读取
        if verify_version is None:
            if firmware_config and 'verify_version' in firmware_config:
                verify_version = firmware_config.get('verify_version', True)
                self.logger.debug(f"从JSON文件读取verify_version: {verify_version}")
            else:
                verify_version = True
                self.logger.debug("JSON文件中未配置verify_version，使用默认值True")
        
        # 1. 检查环境
        if not self.check_environment():
            error_msg = "环境检查失败，终止OTA升级"
            self.logger.error(error_msg)
            return False, error_msg
        
        # 2. 检查版本是否一致，如果一致则跳过升级（仅对URL有效，本地路径无法提取版本号）
        if not is_local and download_url:
            version_match, url_version, device_version = self.check_version_match(download_url)
            if version_match:
                skip_message = f"设备当前版本({device_version})与要升级的版本({url_version})一致，跳过OTA升级"
                self.logger.info(skip_message)
                return True, "VERSION_MATCH_SKIP"
        
        # 3. 获取当前版本（如果需要验证版本变化）
        old_version = None
        if verify_version:
            old_version = self.get_current_version()
            if old_version:
                self.logger.info(f"升级前版本: {old_version}")
        
        # 4. 加载或下载固件
        if is_local:
            # 从本地路径加载固件
            success, error_msg = self.load_firmware_from_local(download_url)
            if not success:
                self.logger.error(f"本地固件加载失败，终止OTA升级: {error_msg}")
                return False, error_msg
        else:
            # 从URL下载固件
            success, error_msg = self.download_firmware(download_url, json_file)
            if not success:
                self.logger.error(f"固件下载失败，终止OTA升级: {error_msg}")
                return False, error_msg
        
        # 5. 上传固件到设备
        success, error_msg = self.upload_firmware_to_device()
        if not success:
            self.logger.error(f"固件上传失败，终止OTA升级: {error_msg}")
            return False, error_msg
        
        # 6. 启动OTA升级
        success, error_msg = self.start_ota_upgrade(log_dir=log_dir, log_suffix=log_suffix)
        if not success:
            self.logger.error(f"OTA升级启动失败，终止流程: {error_msg}")
            return False, error_msg
        
        # 7. 监控升级进度（检测设备是否在位）
        device_rebooted, error_msg = self.monitor_ota_progress(timeout=timeout)
        
        if not device_rebooted:
            # 监控超时，设备始终在线，未检测到重启
            self.logger.error(error_msg)
            return False, error_msg
        
        # 8. 等待设备重启并检测ADB重新在线
        adb_online, error_msg = self.wait_for_device_reboot(max_wait_time=180)
        
        if not adb_online:
            self.logger.error(error_msg)
            return False, error_msg
        
        # 9. 验证升级结果
        verify_success, error_msg = self.verify_ota_result(old_version=old_version if verify_version else None)
        
        if not verify_success:
            self.logger.error(error_msg)
            return False, error_msg
        
        self.logger.info("OTA升级流程完成")
        
        return True, ""