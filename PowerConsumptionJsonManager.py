#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
功耗测试 - JSON配置文件管理模块
提供统一的JSON文件读取和写入功能，简化各模块的JSON操作
"""
import os
import sys
import json
from pathlib import Path
from typing import Optional, Dict, Any, Union

# 添加项目根目录到Python路径
current_file = Path(__file__).resolve()
project_root = current_file.parent.parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.utils.logger import Logger


class PowerConsumptionJsonManager:
    """
    功耗测试JSON配置文件管理类
    提供统一的JSON文件读取和写入功能
    """
    
    def __init__(self, dev_name: str = None, logger: Logger = None):
        """
        初始化JSON管理器
        
        Args:
            dev_name: 设备名称（如 'Z03'），如果为None则从环境变量FW_DEV获取
            logger: 日志记录器，如果为None则创建新的Logger
        """
        self.logger = logger or Logger()
        
        # 确定设备名称
        if not dev_name:
            dev_name = os.environ.get('FW_DEV', 'Z03')
            if dev_name == 'Unknow':
                dev_name = 'Z03'
        self.dev_name = dev_name
        
        # 获取项目根目录
        self.project_root = project_root
        
        # 默认JSON文件路径
        self.default_json_file = self.project_root / "data" / self.dev_name / "power_consumption.json"
        
        # JSON配置缓存（避免重复读取）
        self._config_cache: Dict[str, Dict] = {}
    
    def get_default_json_path(self) -> Path:
        """
        获取默认JSON文件路径
        
        Returns:
            Path: 默认JSON文件路径
        """
        return self.default_json_file
    
    def _resolve_json_path(self, json_file: Union[str, Path, None]) -> Path:
        """
        解析JSON文件路径
        
        Args:
            json_file: JSON文件路径，如果为None则使用默认路径
            
        Returns:
            Path: 解析后的JSON文件路径
        """
        if json_file is None:
            return self.default_json_file
        else:
            return Path(json_file)
    
    def load_json(self, json_file: Union[str, Path, None] = None, use_cache: bool = True) -> Optional[Dict]:
        """
        从JSON文件加载完整配置
        
        Args:
            json_file: JSON文件路径，如果为None则使用默认路径 data/{device}/power_consumption.json
            use_cache: 是否使用缓存，默认为True
            
        Returns:
            dict: 完整配置字典，如果失败则返回None
        """
        json_path = self._resolve_json_path(json_file)
        json_path_str = str(json_path)
        
        # 检查缓存
        if use_cache and json_path_str in self._config_cache:
            self.logger.debug(f"从缓存加载JSON配置: {json_path_str}")
            return self._config_cache[json_path_str]
        
        if not json_path.exists():
            self.logger.warning(f"JSON配置文件不存在: {json_path}")
            return None
        
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
            
            # 缓存配置
            if use_cache:
                self._config_cache[json_path_str] = config_data
            
            self.logger.debug(f"从JSON文件加载配置成功: {json_path_str}")
            return config_data
            
        except json.JSONDecodeError as e:
            self.logger.error(f"JSON文件解析失败: {json_path_str}, 错误: {e}")
            return None
        except Exception as e:
            self.logger.error(f"读取JSON配置文件失败: {json_path_str}, 错误: {e}")
            return None
    
    def get_value(self, key: str, json_file: Union[str, Path, None] = None, 
                  default: Any = None, use_cache: bool = True) -> Any:
        """
        获取JSON配置中指定键的值
        
        Args:
            key: 键名，支持点号分隔的嵌套键（如 'firmware.timeout'）
            json_file: JSON文件路径，如果为None则使用默认路径
            default: 如果键不存在时返回的默认值
            use_cache: 是否使用缓存，默认为True
            
        Returns:
            Any: 键对应的值，如果不存在则返回default
        """
        config_data = self.load_json(json_file, use_cache=use_cache)
        if config_data is None:
            return default
        
        # 支持点号分隔的嵌套键
        keys = key.split('.')
        value = config_data
        
        try:
            for k in keys:
                if isinstance(value, dict) and k in value:
                    value = value[k]
                else:
                    return default
            return value
        except (TypeError, KeyError):
            return default
    
    def get_section(self, section_name: str, json_file: Union[str, Path, None] = None,
                    use_cache: bool = True) -> Optional[Union[Dict, list]]:
        """
        获取JSON配置中的某个section（顶级键及其内容）
        
        Args:
            section_name: section名称（顶级键），如 'firmware', 'qepm', 'setEnv', 'record' 等
            json_file: JSON文件路径，如果为None则使用默认路径
            use_cache: 是否使用缓存，默认为True
            
        Returns:
            dict 或 list: section的内容，如果不存在则返回None
            注意：record 是 list 类型，其他通常是 dict 类型
        """
        config_data = self.load_json(json_file, use_cache=use_cache)
        if config_data is None:
            return None
        
        if section_name in config_data:
            section_value = config_data[section_name]
            # 支持返回 dict 或 list 类型（record 是 list）
            if isinstance(section_value, (dict, list)):
                return section_value
            else:
                self.logger.debug(f"JSON配置中的section '{section_name}' 类型不正确（期望 dict 或 list）")
                return None
        else:
            self.logger.debug(f"JSON配置中不存在section: {section_name}")
            return None
    
    def write_json(self, data: Dict, json_file: Union[str, Path, None] = None,
                   indent: int = 2, ensure_ascii: bool = False) -> bool:
        """
        将数据写入JSON文件
        
        Args:
            data: 要写入的数据字典
            json_file: JSON文件路径，如果为None则使用默认路径
            indent: JSON格式化缩进，默认为2
            ensure_ascii: 是否确保ASCII编码，默认为False（支持中文）
            
        Returns:
            bool: 写入是否成功
        """
        json_path = self._resolve_json_path(json_file)
        
        try:
            # 确保目录存在
            json_path.parent.mkdir(parents=True, exist_ok=True)
            
            # 写入文件
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=ensure_ascii, indent=indent)
            
            # 更新缓存
            self._config_cache[str(json_path)] = data
            
            self.logger.debug(f"写入JSON文件成功: {json_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"写入JSON文件失败: {json_path}, 错误: {e}")
            return False
    
    def update_value(self, key: str, value: Any, json_file: Union[str, Path, None] = None,
                     create_if_not_exists: bool = False) -> bool:
        """
        更新JSON配置中指定键的值
        
        Args:
            key: 键名，支持点号分隔的嵌套键（如 'firmware.timeout'）
            value: 要设置的值
            json_file: JSON文件路径，如果为None则使用默认路径
            create_if_not_exists: 如果键不存在，是否创建，默认为False
            
        Returns:
            bool: 更新是否成功
        """
        json_path = self._resolve_json_path(json_file)
        
        # 加载现有配置
        config_data = self.load_json(json_file, use_cache=False)
        if config_data is None:
            if create_if_not_exists:
                config_data = {}
            else:
                self.logger.error(f"无法更新JSON配置，文件不存在或无法读取: {json_path}")
                return False
        
        # 支持点号分隔的嵌套键
        keys = key.split('.')
        current = config_data
        
        try:
            # 导航到目标位置
            for k in keys[:-1]:
                if k not in current:
                    if create_if_not_exists:
                        current[k] = {}
                    else:
                        self.logger.error(f"键路径不存在: {key}")
                        return False
                current = current[k]
            
            # 设置值
            current[keys[-1]] = value
            
            # 写回文件
            return self.write_json(config_data, json_file)
            
        except (TypeError, KeyError) as e:
            self.logger.error(f"更新JSON配置失败: {key}, 错误: {e}")
            return False
    
    def clear_cache(self, json_file: Union[str, Path, None] = None):
        """
        清除JSON配置缓存
        
        Args:
            json_file: JSON文件路径，如果为None则清除所有缓存
        """
        if json_file is None:
            self._config_cache.clear()
            self.logger.debug("已清除所有JSON配置缓存")
        else:
            json_path_str = str(self._resolve_json_path(json_file))
            if json_path_str in self._config_cache:
                del self._config_cache[json_path_str]
                self.logger.debug(f"已清除JSON配置缓存: {json_path_str}")
    
    def reload_json(self, json_file: Union[str, Path, None] = None) -> Optional[Dict]:
        """
        重新加载JSON文件（清除缓存后重新读取）
        
        Args:
            json_file: JSON文件路径，如果为None则使用默认路径
            
        Returns:
            dict: 完整配置字典，如果失败则返回None
        """
        self.clear_cache(json_file)
        return self.load_json(json_file, use_cache=True)
