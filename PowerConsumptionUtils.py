"""
功耗测试工具类
提供统一的固件URL解析和格式化功能
"""

import re
from typing import Optional, Dict, Any
from pathlib import Path
from urllib.parse import urlparse


class PowerConsumptionUtils:
    """功耗测试工具类，提供固件URL解析和格式化功能"""
    
    @staticmethod
    def extract_firmware_version(firmware_url: str) -> Optional[str]:
        """从固件URL中提取固件版本号
        
        Args:
            firmware_url: 固件下载URL
            
        Returns:
            固件版本号，如 "Z03_V2.0.79_dev_20260127021704"，如果无法提取则返回None
        """
        if not firmware_url:
            return None
            
        # 匹配固件版本格式：Z03_V2.0.79_dev_20260127021704
        pattern = r'([A-Z]\d+_[Vv]\d+(?:\.\d+)*(?:_[a-z]+)*_\d{14})'
        match = re.search(pattern, firmware_url)
        
        return match.group(1) if match else None
    
    @staticmethod
    def extract_year_month(firmware_url: str) -> Optional[str]:
        """从固件URL中提取年月信息
        
        Args:
            firmware_url: 固件下载URL
            
        Returns:
            年月字符串，如 "2026-01"，如果无法提取则返回None
        """
        if not firmware_url:
            return None
            
        # 匹配年月格式：2026-01
        pattern = r'/(\d{4}-\d{2})/'
        match = re.search(pattern, firmware_url)
        
        return match.group(1) if match else None
    
    @staticmethod
    def extract_v_version(firmware_url: str) -> Optional[str]:
        """从固件URL中提取V版本号（如 V1.3.133）
        
        Args:
            firmware_url: 固件下载URL
            
        Returns:
            V版本号，如 "V1.3.133"，如果无法提取则返回None
        """
        if not firmware_url:
            return None
            
        # 先提取完整版本号
        full_version = PowerConsumptionUtils.extract_firmware_version(firmware_url)
        if not full_version:
            return None
            
        # 从完整版本号中提取 V数字.数字.数字 部分
        pattern = r'V(\d+\.\d+\.\d+)'
        match = re.search(pattern, full_version)
        
        return f"V{match.group(1)}" if match else None
    
    @staticmethod
    def extract_date_from_url(firmware_url: str) -> Optional[str]:
        """从固件URL中提取日期信息（兼容extract_year_month）
        
        Args:
            firmware_url: 固件下载URL
            
        Returns:
            日期字符串，如 "2026-01"，如果无法提取则返回None
        """
        return PowerConsumptionUtils.extract_year_month(firmware_url)
    
    @staticmethod
    def extract_folder_path_from_url(firmware_url: str) -> Optional[str]:
        """从固件URL中提取文件夹路径
        
        Args:
            firmware_url: 固件下载URL
            
        Returns:
            文件夹路径，如 "Z03/Z03_BETA_2.0/2026-01/Z03_V2.0.79_dev_20260127021704_z03_release_8625"，如果无法提取则返回None
        """
        if not firmware_url:
            return None
            
        try:
            parsed_url = urlparse(firmware_url)
            path = parsed_url.path
            
            # 移除开头的斜杠和末尾的ota/部分
            if path.startswith('/'):
                path = path[1:]
            
            if path.endswith('/ota/'):
                path = path[:-5]
            
            # 提取路径中的关键部分（从fw-dev之后的部分）
            if '/fw-dev/' in path:
                path_parts = path.split('/fw-dev/')
                if len(path_parts) > 1:
                    return path_parts[1]
            
            return None
            
        except Exception:
            return None
    
    @staticmethod
    def get_folder_name_for_feishu(firmware_url: str) -> str:
        """获取用于飞书云文档的文件夹名称
        
        Args:
            firmware_url: 固件下载URL
            
        Returns:
            文件夹名称，如 "Z03_Z03_BETA_2.0_2026-01_Z03_V2.0.79_dev_20260127021704_z03_release_8625"
        """
        folder_path = PowerConsumptionUtils.extract_folder_path_from_url(firmware_url)
        if folder_path:
            return folder_path.replace('/', '_')
        return "unknown_folder"
    
    @staticmethod
    def get_year_month_folder_name(firmware_url: str) -> Optional[str]:
        """获取年月文件夹名称
        
        Args:
            firmware_url: 固件下载URL
            
        Returns:
            年月文件夹名称，如 "2026-01"，如果无法提取则返回None
        """
        return PowerConsumptionUtils.extract_year_month(firmware_url)
    
    @staticmethod
    def parse_firmware_url(firmware_url: str) -> Dict[str, Any]:
        """完整解析固件URL，返回所有相关信息
        
        Args:
            firmware_url: 固件下载URL
            
        Returns:
            包含所有解析信息的字典
        """
        return {
            'firmware_version': PowerConsumptionUtils.extract_firmware_version(firmware_url),
            'year_month': PowerConsumptionUtils.extract_year_month(firmware_url),
            'folder_path': PowerConsumptionUtils.extract_folder_path_from_url(firmware_url),
            'feishu_folder_name': PowerConsumptionUtils.get_folder_name_for_feishu(firmware_url),
            'original_url': firmware_url
        }
    
    @staticmethod
    def validate_firmware_url(firmware_url: str) -> bool:
        """验证固件URL格式是否有效
        
        Args:
            firmware_url: 固件下载URL
            
        Returns:
            URL格式是否有效
        """
        if not firmware_url:
            return False
            
        # 检查是否包含关键路径组件
        required_components = ['/fw-dev/', '/ota/']
        return all(comp in firmware_url for comp in required_components)
    
    @staticmethod
    def is_local_path(path_or_url: str) -> bool:
        """判断给定的字符串是本地路径还是URL
        
        Args:
            path_or_url: 路径或URL字符串
            
        Returns:
            bool: True表示是本地路径，False表示是URL
        """
        if not path_or_url:
            return False
        
        # 如果以http://或https://开头，肯定是URL
        if path_or_url.startswith(('http://', 'https://')):
            return False
        
        # 检查是否是有效的文件路径（文件存在）
        firmware_path = Path(path_or_url)
        if firmware_path.exists() and firmware_path.is_file():
            return True
        
        # 如果路径看起来像Windows路径（如 C:\ 或 D:\）或Unix路径（以 / 开头且不是URL）
        if (len(path_or_url) >= 3 and path_or_url[1] == ':' and path_or_url[2] in ['\\', '/']) or \
           (path_or_url.startswith('/') and not path_or_url.startswith('//')):
            return True
        
        return False


# 提供便捷的静态方法调用
extract_firmware_version = PowerConsumptionUtils.extract_firmware_version
extract_year_month = PowerConsumptionUtils.extract_year_month
extract_v_version = PowerConsumptionUtils.extract_v_version
extract_date_from_url = PowerConsumptionUtils.extract_date_from_url
extract_folder_path_from_url = PowerConsumptionUtils.extract_folder_path_from_url
get_folder_name_for_feishu = PowerConsumptionUtils.get_folder_name_for_feishu
get_year_month_folder_name = PowerConsumptionUtils.get_year_month_folder_name
parse_firmware_url = PowerConsumptionUtils.parse_firmware_url
validate_firmware_url = PowerConsumptionUtils.validate_firmware_url
is_local_path = PowerConsumptionUtils.is_local_path