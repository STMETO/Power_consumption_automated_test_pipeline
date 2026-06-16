#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
功耗测试 - 视频信息获取模块
从设备拉取视频文件，解析视频信息（码率、帧率、分辨率等）
"""
import os
import sys
import time
import tempfile
from pathlib import Path

# 添加项目根目录到Python路径
current_file = Path(__file__).resolve()
project_root = current_file.parent.parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.utils.config_manager import ConfigManager
from src.utils.logger import Logger
from src.core.dev import InsDev
from src.app.PowerConsumption.PowerConsumption_jsonManager import PowerConsumptionJsonManager

# 尝试导入pymediainfo
try:
    from pymediainfo import MediaInfo
    PYMEDIAINFO_AVAILABLE = True
except ImportError:
    PYMEDIAINFO_AVAILABLE = False


# ============= 路径常量（统一管理） =============

# 设备视频路径
DEVICE_VIDEO_PATH = '/mnt/sdcard/DCIM/Camera01/'  # 设备上的视频存储路径


class PowerConsumptionGetVideoInfo:
    """
    功耗测试视频信息获取类
    用于从设备拉取视频文件并解析视频信息
    """
    
    def __init__(self, dev: InsDev, config: ConfigManager = None, logger: Logger = None, unified_folder_name: str = None):
        """
        初始化视频信息获取类
        
        Args:
            dev: 设备对象，用于执行ADB命令
            config: 配置管理器（可选）
            logger: 日志记录器（可选）
            unified_folder_name: 统一文件夹名称（可选）
        """
        self.dev = dev
        self.config = config or ConfigManager()
        self.logger = logger or Logger()
        
        # 项目根目录
        self.project_root = project_root
        
        # 获取固件名称（设备类型）
        self.firmware_name = dev.name if dev else 'Z03'
        
        # JSON配置管理器
        self.json_manager = PowerConsumptionJsonManager(dev_name=self.firmware_name, logger=self.logger)
        
        # 从JSON配置中获取固件版本目录
        firmware_url = self.json_manager.get_value('firmware.download_url')
        self.firmware_version_dir = self._extract_firmware_version_from_url(firmware_url)
        
        # 统一文件夹名称
        self.unified_folder_name = unified_folder_name
        
        if not PYMEDIAINFO_AVAILABLE:
            self.logger.warning("pymediainfo未安装，视频信息解析功能将不可用")
            self.logger.warning("请运行: pip install pymediainfo")
    
    def _extract_firmware_version_from_url(self, url: str) -> str:
        """
        从固件下载URL中提取版本号作为目录名

        Args:
            url: 固件下载URL

        Returns:
            str: 提取的版本号，如果提取失败则返回默认值
        """
        if not url:
            self.logger.warning("固件URL为空，使用默认版本目录")
            return f"{self.firmware_name}_unknown_version"

        try:
            # 使用工具类提取固件版本
            from src.app.PowerConsumption.PowerConsumption_utils import extract_firmware_version
            version = extract_firmware_version(url)

            if version:
                self.logger.debug(f"从URL中提取到固件版本: {version}")
                return version
            else:
                self.logger.warning(f"无法从URL中提取版本号: {url}")
                return f"{self.firmware_name}_unknown_version"

        except Exception as e:
            self.logger.error(f"提取固件版本失败: {e}")
            return f"{self.firmware_name}_unknown_version"
    
    def find_video_files_on_device(self) -> list:
        """
        查找设备上的所有.MP4视频文件
        
        Returns:
            list: 视频文件路径列表，如果失败则返回空列表
        """
        self.logger.debug(f"查找设备上的视频文件: {DEVICE_VIDEO_PATH}")
        
        # 在同一个shell会话中先cd再ls（同时查找大小写）
        commands = [
            f"cd {DEVICE_VIDEO_PATH}",
            "ls *.mp4 *.MP4 2>/dev/null"
        ]
        response = self.dev.run_adb_shell_interactive(commands, timeout_per_cmd=10, print_live=False, allow_nonzero=True)
        
        if not response or len(response) < 2:
            self.logger.warning(f"查找视频文件失败或返回为空")
            return []
        
        # response是一个列表，最后一个元素是ls命令的输出
        ls_output = response[-1] if isinstance(response, list) else response
        
        # 解析文件列表（同时支持大小写）
        video_files = []
        for line in ls_output.strip().split('\n'):
            line = line.strip()
            if line and line.lower().endswith('.mp4'):
                # 构建完整路径
                if line.startswith('/'):
                    video_files.append(line)
                else:
                    video_files.append(f"{DEVICE_VIDEO_PATH}{line}")
        
        self.logger.debug(f"找到 {len(video_files)} 个视频文件")
        for video_file in video_files:
            self.logger.debug(f"  - {video_file}")
        
        return video_files
    
    def pull_video_from_device(self, device_video_path: str, save_dir: Path, config_name: str) -> dict:
        """
        从设备拉取视频文件到本地保存目录，并解析视频信息
        
        Args:
            device_video_path: 设备上的视频文件路径
            save_dir: 本地保存目录
            config_name: 挡位名称，用于生成文件名
            
        Returns:
            dict: 视频信息字典，如果失败则返回None
        """
        try:
            # 提取原文件名
            video_filename = os.path.basename(device_video_path)
            
            # 生成新文件名: 挡位-时间戳.扩展名
            import datetime
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            file_ext = os.path.splitext(video_filename)[1]
            new_filename = f"{config_name}-{timestamp}.{file_ext}"
            local_video_path = save_dir / new_filename
            
            self.logger.info(f"从设备拉取视频: {device_video_path} -> {local_video_path}")
            
            # 确保本地目录存在
            save_dir.mkdir(parents=True, exist_ok=True)
            self.logger.info(f"保存目录: {save_dir}, 存在: {save_dir.exists()}")
            
            # 使用download方法下载文件
            self.logger.info(f"开始下载文件...")
            success = self.dev.download(device_video_path, str(local_video_path))
            self.logger.info(f"下载结果: {success}")
            
            if not success:
                self.logger.error(f"视频文件拉取失败: {device_video_path}")
                return None
            
            if not local_video_path.exists():
                self.logger.error(f"视频文件拉取失败: 文件不存在于 {local_video_path}")
                return None
            
            file_size = local_video_path.stat().st_size
            self.logger.debug(f"视频文件拉取成功: {local_video_path.name} ({file_size / 1024 / 1024:.2f} MB)")
            
            # 等待文件完全写入（确保文件）完整性）
            # 检查文件大小是否稳定（连续2次检查大小不变）
            file_size_stable = False
            last_size = 0
            for _ in range(5):  # 最多检查5次
                time.sleep(0.5)
                current_size = local_video_path.stat().st_size
                if current_size == last_size and current_size > 0:
                    file_size_stable = True
                    break
                last_size = current_size
            
            if not file_size_stable:
                self.logger.warning(f"文件大小可能仍在变化: {local_video_path.name}，但继续解析")
            
            # 解析视频信息
            video_info = self.get_video_info(local_video_path)
            if video_info:
                self.logger.info(f"视频文件处理成功: {local_video_path.name}")
            else:
                self.logger.warning(f"解析视频信息失败: {video_filename}")
            
            return video_info
            
        except Exception as e:
            self.logger.error(f"处理视频文件时出错: {device_video_path}, 错误: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return None
    
    def delete_all_files_on_device(self) -> bool:
        """
        删除设备上 /mnt/sdcard/DCIM/Camera01/ 路径下的所有文件
        
        Returns:
            bool: 删除是否成功
        """
        self.logger.debug(f"删除设备上的所有文件: {DEVICE_VIDEO_PATH}")
        
        # 使用 clear_folder 方法清空目录
        self.dev.clear_folder(DEVICE_VIDEO_PATH)
        
        self.logger.debug(f"设备目录清空完成: {DEVICE_VIDEO_PATH}")
        return True
    
    def get_video_info(self, video_path: Path) -> dict:
        """
        使用pymediainfo解析视频信息
        
        Args:
            video_path: 视频文件路径
            
        Returns:
            dict: 视频信息字典，包含码率、帧率、分辨率等信息，如果失败则返回None
        """
        if not video_path.exists():
            self.logger.error(f"视频文件不存在: {video_path}")
            return None
        
        if not PYMEDIAINFO_AVAILABLE:
            self.logger.error("pymediainfo未安装，无法解析视频信息")
            return None
        
        try:
            self.logger.info(f"使用pymediainfo解析视频信息: {video_path.name}")
            media_info = MediaInfo.parse(str(video_path))
            
            video_info = {
                'file_path': str(video_path),
                'file_name': video_path.name,
                'file_size': video_path.stat().st_size,
            }
            
            # 遍历所有轨道，查找视频轨道
            for track in media_info.tracks:
                if track.track_type == 'Video':
                    # 分辨率
                    video_info['width'] = int(track.width) if hasattr(track, 'width') and track.width else None
                    video_info['height'] = int(track.height) if hasattr(track, 'height') and track.height else None
                    
                    # 帧率
                    if hasattr(track, 'frame_rate') and track.frame_rate:
                        try:
                            video_info['frame_rate'] = float(track.frame_rate)
                        except (ValueError, TypeError):
                            video_info['frame_rate'] = None
                    else:
                        video_info['frame_rate'] = None
                    
                    # 码率
                    if hasattr(track, 'bit_rate') and track.bit_rate:
                        try:
                            video_info['bit_rate'] = int(track.bit_rate)
                        except (ValueError, TypeError):
                            video_info['bit_rate'] = None
                    else:
                        video_info['bit_rate'] = None
                    
                    # 编码格式
                    video_info['codec'] = track.codec_name if hasattr(track, 'codec_name') else None
                    
                    # 时长
                    if hasattr(track, 'duration') and track.duration:
                        try:
                            video_info['duration_ms'] = int(track.duration)
                            video_info['duration_sec'] = video_info['duration_ms'] / 1000.0
                        except (ValueError, TypeError):
                            video_info['duration_ms'] = None
                            video_info['duration_sec'] = None
                    else:
                        video_info['duration_ms'] = None
                        video_info['duration_sec'] = None
                    
                    # 总帧数
                    if hasattr(track, 'frame_count') and track.frame_count:
                        try:
                            video_info['frame_count'] = int(track.frame_count)
                        except (ValueError, TypeError):
                            video_info['frame_count'] = None
                    else:
                        video_info['frame_count'] = None
                    
                    break  # 只取第一个视频轨道
            
            self.logger.debug("视频信息解析成功:")
            self.logger.debug(f"  分辨率: {video_info.get('width')}x{video_info.get('height')}")
            self.logger.debug(f"  帧率: {video_info.get('frame_rate')} fps")
            self.logger.debug(f"  码率: {video_info.get('bit_rate')} bps")
            self.logger.debug(f"  编码: {video_info.get('codec')}")
            self.logger.debug(f"  时长: {video_info.get('duration_sec')} 秒")
            
            return video_info
            
        except Exception as e:
            self.logger.error(f"pymediainfo解析失败: {e}")
            import traceback
            self.logger.debug(traceback.format_exc())
            return None
    
    def verify_video_info(self, video_info: dict, expected_width: int = None, expected_height: int = None, 
                          expected_fps: float = None, fps_tolerance: float = 5.0) -> tuple[bool, str]:
        """
        验证视频信息是否与期望值匹配
        
        Args:
            video_info: 视频信息字典（从get_video_info获取）
            expected_width: 期望的分辨率宽度
            expected_height: 期望的分辨率高度
            expected_fps: 期望的帧率
            fps_tolerance: 帧率允许的误差范围（默认5帧）
        
        Returns:
            tuple[bool, str]: (是否验证通过, 错误信息或成功信息)
        """
        if not video_info:
            return False, "视频信息为空"
        
        actual_width = video_info.get('width')
        actual_height = video_info.get('height')
        actual_fps = video_info.get('frame_rate')
        
        error_messages = []
        
        # 验证分辨率宽度
        if expected_width is not None:
            if actual_width is None:
                error_messages.append(f"无法获取视频分辨率宽度")
            elif actual_width != expected_width:
                error_messages.append(f"视频分辨率宽度不匹配: 期望 {expected_width}, 实际 {actual_width}")
        
        # 验证分辨率高度
        if expected_height is not None:
            if actual_height is None:
                error_messages.append(f"无法获取视频分辨率高度")
            elif actual_height != expected_height:
                error_messages.append(f"视频分辨率高度不匹配: 期望 {expected_height}, 实际 {actual_height}")
        
        # 验证帧率（允许误差）
        if expected_fps is not None:
            if actual_fps is None:
                error_messages.append(f"无法获取视频帧率")
            else:
                fps_diff = abs(actual_fps - expected_fps)
                if fps_diff > fps_tolerance:
                    error_messages.append(f"视频帧率不匹配: 期望 {expected_fps}, 实际 {actual_fps}, 误差 {fps_diff:.2f} (允许误差: {fps_tolerance})")
        
        if error_messages:
            error_msg = "; ".join(error_messages)
            self.logger.error(f"视频信息验证失败: {error_msg}")
            return False, error_msg
        else:
            success_msg = "视频信息验证通过"
            if expected_width is not None and expected_height is not None:
                success_msg += f" (分辨率: {actual_width}x{actual_height})"
            if expected_fps is not None:
                success_msg += f" (帧率: {actual_fps:.2f} fps, 期望: {expected_fps} fps)"
            self.logger.info(success_msg)
            return True, success_msg
    
    def pull_and_analyze_videos(self, config_name: str = None) -> list:
        """
        从设备拉取所有视频文件，保存到指定目录并解析
        
        Args:
            config_name: 配置名称（挡位名称），用于生成文件名
        
        Returns:
            list: 视频信息字典列表，如果失败则返回空列表
        """
        self.logger.info("开始拉取并分析视频文件")
        
        # 查找设备上的视频文件
        video_files = self.find_video_files_on_device()
        
        if not video_files:
            self.logger.warning("未找到视频文件")
            return []
        
        # 使用传入的配置名称，如果没有则使用默认值
        if not config_name:
            config_name = 'unknown'
        
        # 优先使用统一文件夹名称，如果没有则使用固件版本目录
        if self.unified_folder_name:
            save_folder = self.unified_folder_name
            self.logger.info(f"使用统一文件夹: {save_folder}")
        else:
            save_folder = self.firmware_version_dir
            self.logger.info(f"使用固件版本目录: {save_folder}")
        
        self.logger.info(f"配置名称（挡位）: {config_name}")
        self.logger.info(f"项目根目录: {self.project_root}")
        
        # 构建保存目录: {项目根目录}\PowerConsumption_Data\{统一文件夹名称}\vedio\
        save_dir = self.project_root / "PowerConsumption_Data" / save_folder / "vedio"
        save_dir.mkdir(parents=True, exist_ok=True)
        self.logger.info(f"视频文件保存目录: {save_dir}")
        self.logger.info(f"保存目录是否存在: {save_dir.exists()}")
        
        # 遍历每个视频文件并处理
        video_info_list = []
        for device_video_path in video_files:
            video_info = self.pull_video_from_device(device_video_path, save_dir, config_name)
            if video_info:
                video_info_list.append(video_info)
        
        # 所有视频处理完成后，清理设备目录下的所有文件（无论成功与否都清理）
        if video_files:
            self.logger.debug("开始清理设备上的视频文件...")
            try:
                self.delete_all_files_on_device()
            except Exception as e:
                self.logger.warning(f"清理设备文件时出错: {e}")
        
        self.logger.info(f"视频文件处理完成，共处理 {len(video_info_list)} 个视频")
        
        return video_info_list