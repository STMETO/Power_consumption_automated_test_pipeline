import os
import json
import requests
import sys
import hashlib
import urllib.parse
import re
from typing import Dict, Any, Tuple, Optional, List
from pathlib import Path

# 添加项目根目录到Python路径
current_file = Path(__file__).resolve()
project_root = current_file.parent.parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.utils.logger import Logger
from src.utils.config_manager import ConfigManager
from src.app.PowerConsumption.PowerConsumption_jsonManager import PowerConsumptionJsonManager

# API 端点
AUTH_URL = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
UPLOAD_ALL_URL = "https://open.feishu.cn/open-apis/drive/v1/files/upload_all"
UPLOAD_PREPARE_URL = "https://open.feishu.cn/open-apis/drive/v1/files/upload_prepare"
UPLOAD_PART_URL = "https://open.feishu.cn/open-apis/drive/v1/files/upload_part"
UPLOAD_FINISH_URL = "https://open.feishu.cn/open-apis/drive/v1/files/upload_finish"
CREATE_FOLDER_URL = "https://open.feishu.cn/open-apis/drive/v1/files/create_folder"
GET_ROOT_FOLDER_URL = "https://open.feishu.cn/open-apis/drive/explorer/v2/root_folder/meta"
GET_FOLDER_FILES_URL = "https://open.feishu.cn/open-apis/drive/v1/files"
DELETE_FILE_URL = "https://open.feishu.cn/open-apis/drive/v1/files/{file_token}"
# 文件导入相关API
UPLOAD_MEDIA_URL = "https://open.feishu.cn/open-apis/drive/v1/medias/upload_all"  # 上传素材
CREATE_IMPORT_TASK_URL = "https://open.feishu.cn/open-apis/drive/v1/import_tasks"  # 创建导入任务
GET_IMPORT_TASK_URL = "https://open.feishu.cn/open-apis/drive/v1/import_tasks/{ticket}"  # 查询导入任务结果

# 常量
SMALL_FILE_THRESHOLD = 4 * 1024 * 1024  # 4MB
DEFAULT_PAGE_SIZE = 100
REQUEST_TIMEOUT = 60  # 请求超时时间（秒）


class PowerConsumptionFeishuDriveClient:
    """功耗数据上传飞书云文档客户端"""
    
    def __init__(self, config: ConfigManager = None, logger: Logger = None, dev_name: str = None):
        """初始化客户端
        
        Args:
            config: 配置管理器（可选）
            logger: 日志记录器（可选）
            dev_name: 设备名称（可选）
        """
        self.config = config or ConfigManager()
        self.logger = logger or Logger()
        self.dev_name = dev_name or os.environ.get('FW_DEV', 'Z03')
        
        # 从JSON配置中获取飞书配置
        self.json_manager = PowerConsumptionJsonManager(dev_name=self.dev_name, logger=self.logger)
        feishu_config = self.json_manager.get_section('feishu')
        
        # 获取应用ID和密钥
        self.app_id = feishu_config.get('app_id', '')
        self.app_secret = feishu_config.get('app_secret', '')
        self.default_parent_node = feishu_config.get('default_parent_node', '')
        # 获取上传功能开关
        self.upload_enabled = feishu_config.get('upload_enabled', True)  # 默认启用
        
        if not self.app_id or not self.app_secret:
            self.logger.warning("飞书应用ID或密钥未配置，文件上传功能将不可用")
        
        self.access_token = None
    
    def _get_tenant_access_token(self) -> str:
        """获取访问令牌
        
        Returns:
            str: 访问令牌
            
        Raises:
            Exception: 获取令牌失败
        """
        if self.access_token:
            return self.access_token
            
        payload = {"app_id": self.app_id, "app_secret": self.app_secret}
        headers = {"Content-Type": "application/json; charset=utf-8"}
        
        try:
            self.logger.debug(f"POST: {AUTH_URL}")
            response = requests.post(AUTH_URL, json=payload, headers=headers, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            
            result = response.json()
            if result.get("code", 0) != 0:
                raise Exception(f"获取访问令牌失败: {result.get('msg', 'unknown error')}")
            
            self.access_token = result["tenant_access_token"]
            self.logger.debug("访问令牌获取成功")
            return self.access_token
            
        except Exception as e:
            self.logger.error(f"获取访问令牌错误: {e}")
            raise
    
    def _upload_small_file(self, file_path: str, parent_node: str, file_type: Optional[str] = None) -> str:
        """上传小文件（≤4MB）
        
        Args:
            file_path: 本地文件路径
            parent_node: 目标文件夹token
            file_type: 文件类型（如 "sheet" 表示电子表格），为空则自动判断
            
        Returns:
            str: 文件token
            
        Raises:
            Exception: 上传失败
        """
        access_token = self._get_tenant_access_token()
        file_name = os.path.basename(file_path)
        file_size = os.path.getsize(file_path)
        
        with open(file_path, 'rb') as f:
            file_content = f.read()
        
        headers = {"Authorization": f"Bearer {access_token}"}
        files = {'file': (file_name, file_content, 'application/octet-stream')}
        data = {
            'file_name': file_name,
            'parent_type': 'explorer',
            'parent_node': parent_node,
            'size': str(file_size)
        }
        
        # 如果指定了文件类型（如电子表格），添加到请求数据中
        if file_type:
            data['file_type'] = file_type
            self.logger.debug(f"指定文件类型: {file_type}")
        
        try:
            self.logger.debug(f"POST: {UPLOAD_ALL_URL}")
            self.logger.info(f"上传文件: {file_name} (大小: {file_size} 字节)")
            response = requests.post(UPLOAD_ALL_URL, headers=headers, data=data, files=files, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            
            result = response.json()
            self.logger.debug(f"上传响应: {json.dumps(result, ensure_ascii=False)}")
            
            if result.get("code", 0) != 0:
                error_msg = f"上传文件失败: {result.get('msg', 'unknown error')}"
                self.logger.error(error_msg)
                raise Exception(error_msg)
            
            file_token = result["data"]["file_token"]
            self.logger.info(f"文件上传成功，文件token: {file_token}")
            return file_token
            
        except requests.exceptions.Timeout:
            self.logger.error(f"上传文件超时: {file_name} (超过 {REQUEST_TIMEOUT} 秒)")
            raise Exception(f"上传文件超时: {file_name}")
        except requests.exceptions.RequestException as e:
            self.logger.error(f"上传文件网络错误: {e}")
            raise Exception(f"上传文件网络错误: {e}")
        except Exception as e:
            self.logger.error(f"上传文件错误: {e}")
            raise
    
    def _upload_large_file(self, file_path: str, parent_node: str, file_type: Optional[str] = None) -> str:
        """上传大文件（>4MB）使用分片上传
        
        Args:
            file_path: 本地文件路径
            parent_node: 目标文件夹token
            file_type: 文件类型（如 "sheet" 表示电子表格），为空则自动判断
            
        Returns:
            str: 文件token
            
        Raises:
            Exception: 上传失败
        """
        access_token = self._get_tenant_access_token()
        file_name = os.path.basename(file_path)
        file_size = os.path.getsize(file_path)
        
        # 1. 预上传
        prepare_data = {
            "file_name": file_name,
            "parent_type": "explorer",
            "parent_node": parent_node,
            "size": file_size
        }
        
        # 如果指定了文件类型（如电子表格），添加到请求数据中
        if file_type:
            prepare_data['file_type'] = file_type
            self.logger.debug(f"指定文件类型: {file_type}")
        prepare_headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; charset=utf-8"
        }
        
        try:
            self.logger.debug(f"POST: {UPLOAD_PREPARE_URL}")
            response = requests.post(UPLOAD_PREPARE_URL, headers=prepare_headers, json=prepare_data, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            
            result = response.json()
            if result.get("code", 0) != 0:
                raise Exception(f"预上传失败: {result.get('msg', 'unknown error')}")
            
            upload_id = result["data"]["upload_id"]
            block_size = result["data"]["block_size"]
            block_num = result["data"]["block_num"]
            
            self.logger.info(f"预上传成功. upload_id: {upload_id}, 分片大小: {block_size}, 分片数量: {block_num}")
            
            # 2. 上传分片
            with open(file_path, 'rb') as f:
                for seq in range(block_num):
                    if seq == block_num - 1:
                        size = file_size - seq * block_size
                    else:
                        size = block_size
                    
                    chunk = f.read(size)
                    
                    files = {'file': (file_name, chunk, 'application/octet-stream')}
                    data = {
                        'upload_id': upload_id,
                        'seq': str(seq),
                        'size': str(size)
                    }
                    
                    self.logger.info(f"上传分片 {seq + 1}/{block_num} (大小: {size} 字节)")
                    part_response = requests.post(
                        UPLOAD_PART_URL, 
                        headers={"Authorization": f"Bearer {access_token}"}, 
                        data=data, 
                        files=files,
                        timeout=REQUEST_TIMEOUT
                    )
                    part_response.raise_for_status()
                    
                    part_result = part_response.json()
                    if part_result.get("code", 0) != 0:
                        raise Exception(f"上传分片 {seq + 1} 失败: {part_result.get('msg', 'unknown error')}")
            
            # 3. 完成上传
            finish_data = {"upload_id": upload_id, "block_num": block_num}
            finish_headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json; charset=utf-8"
            }
            
            self.logger.debug(f"POST: {UPLOAD_FINISH_URL}")
            finish_response = requests.post(UPLOAD_FINISH_URL, headers=finish_headers, json=finish_data, timeout=REQUEST_TIMEOUT)
            finish_response.raise_for_status()
            
            finish_result = finish_response.json()
            if finish_result.get("code", 0) != 0:
                raise Exception(f"完成上传失败: {finish_result.get('msg', 'unknown error')}")
            
            file_token = finish_result["data"]["file_token"]
            self.logger.info("大文件上传成功")
            return file_token
            
        except Exception as e:
            self.logger.error(f"大文件上传错误: {e}")
            raise
    
    def _upload_media_for_import(self, file_path: str) -> str:
        """上传素材用于导入（步骤一）
        
        Args:
            file_path: 本地Excel文件路径
            
        Returns:
            str: 素材文件token
            
        Raises:
            Exception: 上传失败
        """
        access_token = self._get_tenant_access_token()
        file_name = os.path.basename(file_path)
        file_size = os.path.getsize(file_path)
        
        with open(file_path, 'rb') as f:
            file_content = f.read()
        
        headers = {"Authorization": f"Bearer {access_token}"}
        files = {'file': (file_name, file_content, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')}
        data = {
            'file_name': file_name,
            'parent_type': 'ccm_import_open',
            'size': str(file_size),
            'extra': json.dumps({
                'obj_type': 'sheet',
                'file_extension': 'xlsx'
            })
        }
        
        try:
            self.logger.debug(f"POST: {UPLOAD_MEDIA_URL}")
            self.logger.info(f"上传素材用于导入: {file_name} (大小: {file_size} 字节)")
            response = requests.post(UPLOAD_MEDIA_URL, headers=headers, data=data, files=files, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            
            result = response.json()
            self.logger.debug(f"上传素材响应: {json.dumps(result, ensure_ascii=False)}")
            
            if result.get("code", 0) != 0:
                error_msg = f"上传素材失败: {result.get('msg', 'unknown error')}"
                self.logger.error(error_msg)
                raise Exception(error_msg)
            
            file_token = result["data"]["file_token"]
            self.logger.info(f"素材上传成功，文件token: {file_token}")
            return file_token
            
        except requests.exceptions.Timeout:
            self.logger.error(f"上传素材超时: {file_name}")
            raise Exception(f"上传素材超时: {file_name}")
        except requests.exceptions.RequestException as e:
            self.logger.error(f"上传素材网络错误: {e}")
            raise Exception(f"上传素材网络错误: {e}")
        except Exception as e:
            self.logger.error(f"上传素材错误: {e}")
            raise
    
    def _create_import_task(self, file_token: str, file_name: str, parent_node: str) -> str:
        """创建导入任务（步骤二）
        
        Args:
            file_token: 素材文件token
            file_name: 文件名称
            parent_node: 目标文件夹token
            
        Returns:
            str: 导入任务ticket
            
        Raises:
            Exception: 创建导入任务失败
        """
        access_token = self._get_tenant_access_token()
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; charset=utf-8"
        }
        
        import_data = {
            "file_extension": "xlsx",
            "file_token": file_token,
            "type": "sheet",
            "file_name": file_name,
            "point": {
                "mount_type": 1,  # 1表示挂载到指定文件夹
                "mount_key": parent_node
            }
        }
        
        try:
            self.logger.debug(f"POST: {CREATE_IMPORT_TASK_URL}")
            self.logger.info(f"创建导入任务: {file_name}")
            response = requests.post(CREATE_IMPORT_TASK_URL, headers=headers, json=import_data, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            
            result = response.json()
            self.logger.debug(f"创建导入任务响应: {json.dumps(result, ensure_ascii=False)}")
            
            if result.get("code", 0) != 0:
                error_msg = f"创建导入任务失败: {result.get('msg', 'unknown error')}"
                self.logger.error(error_msg)
                raise Exception(error_msg)
            
            ticket = result["data"]["ticket"]
            self.logger.info(f"导入任务创建成功，ticket: {ticket}")
            return ticket
            
        except requests.exceptions.Timeout:
            self.logger.error(f"创建导入任务超时: {file_name}")
            raise Exception(f"创建导入任务超时: {file_name}")
        except requests.exceptions.RequestException as e:
            self.logger.error(f"创建导入任务网络错误: {e}")
            raise Exception(f"创建导入任务网络错误: {e}")
        except Exception as e:
            self.logger.error(f"创建导入任务错误: {e}")
            raise
    
    def _get_import_task_result(self, ticket: str, max_wait_time: int = 300) -> Optional[str]:
        """查询导入任务结果（步骤三）
        
        Args:
            ticket: 导入任务ticket
            max_wait_time: 最大等待时间（秒），默认5分钟
            
        Returns:
            str: 转换后的电子表格file_token，如果失败或超时返回None
        """
        access_token = self._get_tenant_access_token()
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; charset=utf-8"
        }
        
        import time
        start_time = time.time()
        check_interval = 2  # 每2秒查询一次
        empty_status_count = 0  # 记录状态为空的次数
        max_empty_status_retries = 30  # 如果状态为空超过30次（60秒），尝试其他判断方式
        
        while time.time() - start_time < max_wait_time:
            try:
                url = GET_IMPORT_TASK_URL.format(ticket=ticket)
                self.logger.debug(f"GET: {url}")
                response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
                response.raise_for_status()
                
                result = response.json()
                self.logger.debug(f"查询导入任务响应: {json.dumps(result, ensure_ascii=False)}")
                
                if result.get("code", 0) != 0:
                    error_msg = f"查询导入任务失败: {result.get('msg', 'unknown error')}"
                    self.logger.error(error_msg)
                    return None
                
                task_data = result.get("data", {})
                
                # 尝试多种可能的响应结构
                # 结构1: data.result.status
                result_status = task_data.get("result", {})
                status = result_status.get("status", "")
                
                # 结构2: data.status (如果result中没有status，尝试直接从data获取)
                if not status:
                    status = task_data.get("status", "")
                
                # 结构3: 检查飞书API的实际响应格式
                # 根据实际响应，成功时会有: result.job_status = 0, result.job_error_msg = "success", result.token
                job_status = result_status.get("job_status")
                job_error_msg = result_status.get("job_error_msg", "")
                token = result_status.get("token", "")
                
                # 如果job_status为0且job_error_msg为"success"，说明任务成功完成
                if job_status == 0 and job_error_msg == "success":
                    if token:
                        self.logger.info(f"导入任务完成，电子表格token: {token}")
                        return token
                    else:
                        self.logger.info("导入任务完成（job_status=0, job_error_msg=success），但未返回token")
                        # 即使没有token，也认为任务成功完成
                        return "success"  # 返回一个标识表示成功
                
                # 检查是否有file_token直接返回（表示已完成）
                file_token = None
                if result_status:
                    file_token = result_status.get("file_token", "")
                if not file_token:
                    file_token = task_data.get("file_token", "")
                
                # 如果已经有file_token，说明任务已完成
                if file_token:
                    self.logger.info(f"导入任务完成，电子表格token: {file_token}")
                    return file_token
                
                # 根据状态处理
                if status == "success":
                    file_token = result_status.get("file_token", "") or task_data.get("file_token", "")
                    if file_token:
                        self.logger.info(f"导入任务完成，电子表格token: {file_token}")
                        return file_token
                    else:
                        self.logger.warning("导入任务成功但未返回file_token")
                        return None
                elif status == "fail":
                    error_msg = result_status.get("fail_reason", "") or task_data.get("fail_reason", "未知错误")
                    self.logger.error(f"导入任务失败: {error_msg}")
                    return None
                elif status == "processing" or status == "pending":
                    self.logger.debug(f"导入任务处理中（状态: {status}），等待 {check_interval} 秒后重试...")
                    time.sleep(check_interval)
                elif not status:
                    empty_status_count += 1
                    # 状态为空时，检查job_status和job_error_msg
                    if job_status == 0 and job_error_msg == "success":
                        if token:
                            self.logger.info(f"导入任务完成（状态为空但job_status=0），电子表格token: {token}")
                            return token
                        else:
                            self.logger.info("导入任务完成（状态为空但job_status=0, job_error_msg=success）")
                            return "success"
                    
                    # 如果状态为空超过一定次数，检查是否有成功标志
                    if empty_status_count >= max_empty_status_retries:
                        # 再次检查job_status和job_error_msg
                        if job_status == 0 and job_error_msg == "success":
                            if token:
                                self.logger.info(f"导入任务完成（状态为空但job_status=0），电子表格token: {token}")
                                return token
                            else:
                                self.logger.info("导入任务完成（状态为空但job_status=0, job_error_msg=success）")
                                return "success"
                        
                        self.logger.warning(f"导入任务状态一直为空（已查询{empty_status_count}次），但根据经验任务可能已完成")
                        self.logger.warning(f"完整响应: {json.dumps(task_data, ensure_ascii=False)}")
                        # 尝试从响应中提取任何可能的token或file_token
                        if "result" in task_data and isinstance(task_data["result"], dict):
                            # 尝试从result中提取token或file_token
                            possible_token = task_data["result"].get("token", "") or task_data["result"].get("file_token", "")
                            if possible_token:
                                self.logger.info(f"从result中提取到token: {possible_token}")
                                return possible_token
                        
                        # 如果仍然没有token，但job_status=0且job_error_msg=success，认为成功
                        if job_status == 0 and job_error_msg == "success":
                            self.logger.info("导入任务完成（job_status=0, job_error_msg=success，但无token）")
                            return "success"
                        
                        # 如果仍然没有成功标志，记录警告但继续尝试
                        self.logger.warning("未找到成功标志，但任务可能已完成，继续等待...")
                        empty_status_count = 0  # 重置计数器，继续尝试
                    
                    # 如果状态为空且没有成功标志，可能是任务还在处理中
                    if empty_status_count <= 5:  # 前几次才记录详细日志
                        self.logger.debug(f"导入任务状态为空（第{empty_status_count}次），完整响应: {json.dumps(task_data, ensure_ascii=False)}")
                    else:
                        self.logger.debug(f"导入任务状态为空（第{empty_status_count}次），等待 {check_interval} 秒后重试...")
                    time.sleep(check_interval)
                else:
                    self.logger.warning(f"未知的导入任务状态: {status}，完整响应: {json.dumps(task_data, ensure_ascii=False)}")
                    time.sleep(check_interval)
                    
            except requests.exceptions.Timeout:
                self.logger.error("查询导入任务超时")
                return None
            except requests.exceptions.RequestException as e:
                self.logger.error(f"查询导入任务网络错误: {e}")
                return None
            except Exception as e:
                self.logger.error(f"查询导入任务错误: {e}")
                return None
        
        self.logger.error(f"导入任务超时（超过 {max_wait_time} 秒）")
        return None
    
    def import_excel_as_sheet(self, file_path: str, parent_node: str, file_name: str = None) -> Optional[str]:
        """将Excel文件导入为飞书电子表格（完整流程）
        
        Args:
            file_path: 本地Excel文件路径
            parent_node: 目标文件夹token
            file_name: 文件名称，如果为None则使用文件路径中的文件名
            
        Returns:
            str: 转换后的电子表格file_token，失败返回None
        """
        if not os.path.exists(file_path):
            self.logger.error(f"文件不存在: {file_path}")
            return None
        
        if file_name is None:
            file_name = os.path.basename(file_path)
        
        try:
            # 步骤一：上传素材
            self.logger.info(f"步骤1: 上传素材用于导入: {file_name}")
            file_token = self._upload_media_for_import(file_path)
            
            # 步骤二：创建导入任务
            self.logger.info(f"步骤2: 创建导入任务: {file_name}")
            ticket = self._create_import_task(file_token, file_name, parent_node)
            
            # 步骤三：查询导入任务结果
            self.logger.info(f"步骤3: 查询导入任务结果: {file_name}")
            sheet_token = self._get_import_task_result(ticket)
            
            if sheet_token:
                self.logger.info(f"Excel文件成功转换为电子表格: {file_name} -> {sheet_token}")
                return sheet_token
            else:
                self.logger.error(f"Excel文件转换为电子表格失败: {file_name}")
                return None
                
        except Exception as e:
            self.logger.error(f"导入Excel为电子表格失败: {file_name}, 错误: {e}")
            import traceback
            self.logger.debug(traceback.format_exc())
            return None
    
    def upload_file(self, file_path: str, parent_node: Optional[str] = None, file_type: Optional[str] = None) -> str:
        """上传文件到飞书云文档
        
        Args:
            file_path: 本地文件路径
            parent_node: 目标文件夹token，为空则使用默认文件夹
            file_type: 文件类型（如 "sheet" 表示电子表格），为空则自动判断
            
        Returns:
            str: 文件token
            
        Raises:
            Exception: 上传失败
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"文件不存在: {file_path}")
        
        if parent_node is None:
            parent_node = self.default_parent_node
            if not parent_node:
                raise ValueError("未配置默认父文件夹token，请检查配置文件")
        
        file_size = os.path.getsize(file_path)
        self.logger.info(f"文件大小: {file_size} 字节")
        
        # 根据文件大小选择上传方式
        if file_size <= SMALL_FILE_THRESHOLD:
            self.logger.debug("使用小文件上传方式 (≤4MB)")
            return self._upload_small_file(file_path, parent_node, file_type)
        else:
            self.logger.debug("使用大文件上传方式 (>4MB)")
            return self._upload_large_file(file_path, parent_node, file_type)
    


    def create_folder(self, folder_name: str, parent_folder_token: str = "") -> str:
        """创建文件夹并返回文件夹token
        
        Args:
            folder_name: 文件夹名称
            parent_folder_token: 父文件夹token，为空则创建到根目录
            
        Returns:
            str: 文件夹token
            
        Raises:
            Exception: 创建失败
        """
        access_token = self._get_tenant_access_token()
        
        data = {
            "name": folder_name,
            "parent_type": "explorer"
        }
        
        if parent_folder_token:
            data["folder_token"] = parent_folder_token
        
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; charset=utf-8"
        }
        
        try:
            self.logger.debug(f"POST: {CREATE_FOLDER_URL}")
            response = requests.post(CREATE_FOLDER_URL, headers=headers, json=data, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            
            result = response.json()
            if result.get("code", 0) != 0:
                error_msg = f"创建文件夹失败: {result.get('msg', 'unknown error')}"
                self.logger.error(error_msg)
                raise Exception(error_msg)
            
            folder_token = result["data"]["token"]
            self.logger.info(f"文件夹创建成功: {folder_name}")
            self.logger.debug(f"文件夹token: {folder_token}")
            
            return folder_token
            
        except requests.exceptions.RequestException as e:
            self.logger.error(f"创建文件夹请求错误: {e}")
            if hasattr(e, 'response') and e.response is not None:
                self.logger.error(f"响应内容: {e.response.text}")
            raise e
        except Exception as e:
            self.logger.error(f"创建文件夹错误: {e}")
            raise e

    def is_upload_enabled(self) -> bool:
        """
        检查文件上传功能是否启用
        
        Returns:
            bool: 如果启用则返回True
        """
        # 重新读取配置（可能配置已更新）
        feishu_config = self.json_manager.get_section('feishu')
        if feishu_config:
            self.upload_enabled = feishu_config.get('upload_enabled', True)
        
        return self.upload_enabled
    
    def upload_power_consumption_data(self, unified_folder_name: str) -> Dict[str, Any]:
        """上传功耗测试数据到飞书云文档
        
        Args:
            unified_folder_name: 统一文件夹名称
            
        Returns:
            Dict[str, Any]: 上传结果信息
        """
        result = {
            "success": False,
            "folder_created": False,
            "files_uploaded": [],
            "errors": []
        }
        
        # 检查上传功能是否启用
        if not self.is_upload_enabled():
            result["errors"].append("文件上传功能已禁用（JSON配置中upload_enabled=false）")
            self.logger.info("文件上传功能已禁用（JSON配置中upload_enabled=false），跳过上传")
            return result
        
        if not unified_folder_name:
            result["errors"].append("必须提供统一文件夹名称")
            self.logger.error("必须提供统一文件夹名称")
            return result
        
        try:
            # 获取默认父文件夹token
            feishu_config = self.json_manager.get_section('feishu')
            default_parent_token = feishu_config.get('default_parent_node', '')
            
            if not default_parent_token:
                result["errors"].append("未配置飞书默认父文件夹token")
                self.logger.error("未配置飞书默认父文件夹token")
                return result
            
            # 使用统一文件夹名称
            folder_name = unified_folder_name
            self.logger.info(f"使用统一文件夹名称: {folder_name}")
            
            # 创建飞书文件夹
            try:
                folder_token = self.create_folder(folder_name, default_parent_token)
                result["folder_created"] = True
                result["folder_token"] = folder_token
                result["folder_name"] = folder_name
                self.logger.info(f"飞书文件夹创建成功: {folder_name}")
            except Exception as folder_error:
                result["errors"].append(f"创建飞书文件夹失败: {folder_error}")
                self.logger.error(f"创建飞书文件夹失败: {folder_error}")
                return result
            
            # 递归查找并上传所有Excel和JSON文件
            project_root = Path(__file__).parent.parent.parent.parent
            
            # 确定数据目录
            data_directory = project_root / "PowerConsumption_Data" / unified_folder_name
            
            self.logger.info(f"查找数据目录: {data_directory}")
            
            if data_directory.exists():
                # 只上传总汇总文件（ALL-GEARS.xlsx），其他文件不再上传
                # # 查找所有Excel文件
                # excel_files = list(data_directory.rglob("*.xlsx"))
                # # 查找所有JSON文件
                # json_files = list(data_directory.rglob("*.json"))
                # 
                # all_files = excel_files + json_files
                
                # 只查找总汇总文件（ALL-GEARS.xlsx）
                all_gears_files = list(data_directory.rglob("*ALL-GEARS*.xlsx"))
                
                if not all_gears_files:
                    self.logger.warning(f"在数据目录 {data_directory} 中未找到总汇总文件（ALL-GEARS.xlsx）")
                else:
                    self.logger.info(f"找到 {len(all_gears_files)} 个总汇总文件需要上传")
                    
                    for file_path in all_gears_files:
                        try:
                            # 上传总汇总Excel文件
                            file_token = self.upload_file(str(file_path), folder_token)
                            file_type = "Excel"
                            success = True
                            
                            if success:
                                result["files_uploaded"].append({
                                    "name": file_path.name,
                                    "type": file_type,
                                    "path": str(file_path)
                                })
                                self.logger.info(f"{file_type}文件上传成功: {file_path.name}")
                            else:
                                result["errors"].append(f"{file_type}文件上传失败: {file_path.name}")
                                self.logger.error(f"{file_type}文件上传失败: {file_path.name}")
                                
                        except Exception as e:
                            error_msg = f"上传文件失败 {file_path.name}: {e}"
                            result["errors"].append(error_msg)
                            self.logger.error(error_msg)
                    
                    # # 注释掉：不再上传其他文件（非总汇总文件）
                    # for file_path in all_files:
                    #     try:
                    #         if file_path.suffix.lower() == '.xlsx':
                    #             # 上传Excel文件
                    #             file_token = self.upload_file(str(file_path), folder_token)
                    #             file_type = "Excel"
                    #             success = True
                    #         else:
                    #             # 上传JSON文件
                    #             file_token = self.upload_file(str(file_path), folder_token)
                    #             file_type = "JSON"
                    #             success = True
                    #         
                    #         if success:
                    #             result["files_uploaded"].append({
                    #                 "name": file_path.name,
                    #                 "type": file_type,
                    #                 "path": str(file_path)
                    #             })
                    #             self.logger.info(f"{file_type}文件上传成功: {file_path.name}")
                    #         else:
                    #             result["errors"].append(f"{file_type}文件上传失败: {file_path.name}")
                    #             self.logger.error(f"{file_type}文件上传失败: {file_path.name}")
                    #             
                    #     except Exception as e:
                    #         error_msg = f"上传文件失败 {file_path.name}: {e}"
                    #         result["errors"].append(error_msg)
                    #         self.logger.error(error_msg)
            else:
                self.logger.warning(f"数据目录不存在: {data_directory}")
            
            # 设置folder_url（只要文件夹创建成功就设置，即使没有文件上传）
            if result.get("folder_created") and result.get("folder_token"):
                result["folder_url"] = f"https://insta360.feishu.cn/drive/folder/{folder_token}"
                self.logger.debug(f"飞书文件夹URL: {result['folder_url']}")
            
            # 设置上传成功标志（如果有文件上传成功）
            if result["files_uploaded"]:
                result["success"] = True
            
        except Exception as e:
            result["errors"].append(f"上传功耗测试数据失败: {e}")
            self.logger.error(f"上传功耗测试数据失败: {e}")
        
        return result

    # 文件夹同步功能
    def get_root_folder_meta(self) -> Dict[str, Any]:
        """获取根文件夹元数据
        
        Returns:
            Dict[str, Any]: 根文件夹元数据
            
        Raises:
            Exception: 获取失败
        """
        access_token = self._get_tenant_access_token()
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; charset=utf-8"
        }
        
        try:
            self.logger.debug(f"GET: {GET_ROOT_FOLDER_URL}")
            response = requests.get(GET_ROOT_FOLDER_URL, headers=headers, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            
            result = response.json()
            if result.get("code", 0) != 0:
                raise Exception(f"获取根文件夹元数据失败: {result.get('msg', 'unknown error')}")
            
            return result.get("data", {})
            
        except Exception as e:
            self.logger.error(f"获取根文件夹元数据错误: {e}")
            raise
    
    def get_folder_files(self, folder_token: str, page_size: int = DEFAULT_PAGE_SIZE) -> List[Dict[str, Any]]:
        """获取文件夹中的文件清单
        
        Args:
            folder_token: 文件夹token
            page_size: 每页大小
            
        Returns:
            List[Dict[str, Any]]: 文件列表
            
        Raises:
            Exception: 获取失败
        """
        access_token = self._get_tenant_access_token()
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; charset=utf-8"
        }
        
        all_files = []
        page_token = ""
        
        while True:
            params = {
                "folder_token": folder_token,
                "page_size": page_size
            }
            if page_token:
                params["page_token"] = page_token
                
            try:
                self.logger.debug(f"GET: {GET_FOLDER_FILES_URL} with params: {params}")
                response = requests.get(GET_FOLDER_FILES_URL, headers=headers, params=params, timeout=REQUEST_TIMEOUT)
                response.raise_for_status()
                
                result = response.json()
                if result.get("code", 0) != 0:
                    raise Exception(f"获取文件夹文件清单失败: {result.get('msg', 'unknown error')}")
                
                data = result.get("data", {})
                files = data.get("files", [])
                all_files.extend(files)
                
                if not data.get("has_more", False):
                    break
                page_token = data.get("next_page_token", "")
                
            except Exception as e:
                self.logger.error(f"获取文件夹文件错误: {e}")
                raise
        
        return all_files
    
    def find_folder_by_name(self, parent_folder_token: str, folder_name: str) -> Optional[str]:
        """在指定文件夹中查找同名文件夹
        
        Args:
            parent_folder_token: 父文件夹token
            folder_name: 要查找的文件夹名称
            
        Returns:
            Optional[str]: 文件夹token，如果不存在返回None
            
        Raises:
            Exception: 查找失败
        """
        files = self.get_folder_files(parent_folder_token)
        
        for file in files:
            if file.get("type") == "folder" and file.get("name") == folder_name:
                return file.get("token")
        
        return None
    
    def delete_file_or_folder(self, file_token: str, file_type: str = "folder") -> str:
        """删除文件或文件夹
        
        Args:
            file_token: 文件或文件夹token
            file_type: 文件类型，默认为"folder"
            
        Returns:
            str: 任务ID
            
        Raises:
            Exception: 删除失败
        """
        access_token = self._get_tenant_access_token()
        url = DELETE_FILE_URL.format(file_token=urllib.parse.quote(file_token))
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; charset=utf-8"
        }
        params = {"type": file_type}
        
        try:
            self.logger.debug(f"DELETE: {url} with params: {params}")
            response = requests.delete(url, headers=headers, params=params, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            
            result = response.json()
            if result.get("code", 0) != 0:
                raise Exception(f"删除文件或文件夹失败: {result.get('msg', 'unknown error')}")
            
            task_id = result.get("data", {}).get("task_id", "")
            self.logger.info(f"删除操作成功，任务ID: {task_id}")
            return task_id
            
        except Exception as e:
            self.logger.error(f"删除文件或文件夹错误: {e}")
            raise
    
 
    def extract_summary_folder_from_firmware_url(self, firmware_url: str) -> str:
        """从固件URL中提取汇总文件夹
        
        Args:
            firmware_url: 固件下载URL
            
        Returns:
            str: 提取的汇总文件夹，如 "2026-01"
        """
        if not firmware_url:
            self.logger.warning("固件URL为空，无法提取汇总文件夹")
            return ""
        
        try:
            # 使用工具类提取年月信息
            from src.app.PowerConsumption.PowerConsumption_utils import extract_year_month
            year_month = extract_year_month(firmware_url)
            
            if year_month:
                self.logger.info(f"从固件URL提取汇总文件夹: {year_month}")
                return year_month
            
            self.logger.warning(f"无法从URL中提取有效汇总文件夹: {firmware_url}")
            return ""
            
        except Exception as e:
            self.logger.error(f"解析固件URL失败: {e}")
            return ""
    
    def sync_folder_to_feishu(self, local_folder_path: str, target_folder_name: str, 
                             parent_folder_token: Optional[str] = None) -> Optional[str]:
        """将本地文件夹同步到飞书云文档
        
        Args:
            local_folder_path: 本地文件夹路径
            target_folder_name: 目标文件夹名称
            parent_folder_token: 父文件夹token，为空则使用默认文件夹
            
        Returns:
            Optional[str]: 文件夹token，如果同步失败则返回None
        """
        if not os.path.exists(local_folder_path) or not os.path.isdir(local_folder_path):
            self.logger.error(f"本地文件夹不存在或不是目录: {local_folder_path}")
            return None
        
        if parent_folder_token is None:
            parent_folder_token = self.default_parent_node
        
        try:
            # 1. 查找是否已存在同名文件夹
            existing_folder_token = self.find_folder_by_name(parent_folder_token, target_folder_name)
            
            if existing_folder_token:
                self.logger.info(f"发现已存在的文件夹: {target_folder_name}")
                # 可以选择删除或跳过，这里选择删除后重新创建
                try:
                    self.delete_file_or_folder(existing_folder_token, "folder")
                    self.logger.info(f"已删除现有文件夹: {target_folder_name}")
                except Exception as e:
                    self.logger.warning(f"删除现有文件夹失败，尝试继续: {e}")
            
            # 2. 创建新文件夹
            folder_token = self.create_folder(target_folder_name, parent_folder_token)
            
            # 3. 只上传总汇总文件（ALL-GEARS.xlsx），其他文件不再上传
            uploaded_count = 0
            for root, dirs, files in os.walk(local_folder_path):
                for file in files:
                    # 跳过临时文件
                    if file.startswith('~$'):
                        continue
                    
                    # 只处理总汇总文件（ALL-GEARS.xlsx），跳过其他文件
                    if 'ALL-GEARS' not in file or not file.endswith('.xlsx'):
                        continue
                    
                    file_path = os.path.join(root, file)
                    try:
                        # 检查是否是总汇总文件（ALL-GEARS.xlsx），如果是则使用导入流程转换为电子表格
                        if 'ALL-GEARS' in file and file.endswith('.xlsx'):
                            self.logger.info(f"检测到总汇总文件，将通过导入流程转换为电子表格: {file}")
                            sheet_token = self.import_excel_as_sheet(file_path, folder_token, file)
                            if sheet_token:
                                self.logger.info(f"总汇总文件成功转换为电子表格: {file} -> {sheet_token}")
                                uploaded_count += 1
                            else:
                                self.logger.error(f"总汇总文件转换为电子表格失败: {file}")
                        # # 注释掉：不再上传其他文件（非总汇总文件）
                        # else:
                        #     # 普通文件使用常规上传方式
                        #     file_token = self.upload_file(file_path, folder_token)
                        #     self.logger.info(f"文件上传成功: {file} -> {file_token}")
                        #     uploaded_count += 1
                    except Exception as e:
                        self.logger.error(f"文件上传失败 {file}: {e}")
            
            self.logger.info(f"文件夹同步完成，共上传 {uploaded_count} 个文件")
            return folder_token
            
        except Exception as e:
            self.logger.error(f"文件夹同步失败: {e}")
            return None
    
    def sync_summary_folder_to_feishu(self, firmware_url: str, local_base_path: str = None) -> Dict[str, Any]:
        """将汇总文件夹同步到飞书云文档，确保与URL中的文件夹路径匹配
        
        Args:
            firmware_url: 固件下载URL
            local_base_path: 本地基础路径，默认为项目根目录下的PowerConsumption_Data
            
        Returns:
            Dict[str, Any]: 同步结果，包含 success 和 folder_url
        """
        result = {
            "success": False,
            "folder_url": None,
            "folder_token": None,
            "folder_name": None
        }
        # 检查上传功能是否启用
        if not self.is_upload_enabled():
            self.logger.info("文件上传功能已禁用（JSON配置中upload_enabled=false），跳过汇总文件夹同步")
            return result
        
        if not firmware_url:
            self.logger.error("固件URL为空，无法同步汇总文件夹")
            return result
        
        # 从URL中提取汇总文件夹
        year_month = self.extract_summary_folder_from_firmware_url(firmware_url)
        if not year_month:
            self.logger.error("无法从固件URL中提取汇总文件夹")
            return result
        
        # 构建本地文件夹路径
        if local_base_path is None:
            # 使用正确的项目根目录路径
            current_file = Path(__file__).resolve()
            project_root = current_file.parent.parent.parent.parent
            local_base_path = str(project_root / "PowerConsumption_Data")
        
        # 从URL中提取完整的文件夹路径用于目标文件夹名称
        try:
            parsed_url = urllib.parse.urlparse(firmware_url)
            path = parsed_url.path
            
            # 移除开头的斜杠和末尾的ota/部分
            if path.startswith('/'):
                path = path[1:]
            
            if path.endswith('/ota/'):
                path = path[:-5]
            
            # 提取路径中的关键部分（从fw-dev之后的部分）
            if '/fw-dev/' in path:
                # 获取/fw-dev/之后的部分
                path_parts = path.split('/fw-dev/')
                if len(path_parts) > 1:
                    folder_path = path_parts[1]
                    
                    # 构建本地汇总文件夹路径
                    # 直接在PowerConsumption_Data根目录下查找以年月开头的文件夹
                    local_year_month_folder = None
                    
                    # 搜索PowerConsumption_Data目录下所有以年月开头的文件夹
                    self.logger.info(f"搜索本地文件夹: {local_base_path}, 匹配模式: {year_month}*")
                    if os.path.exists(local_base_path) and os.path.isdir(local_base_path):
                        for item in os.listdir(local_base_path):
                            item_path = os.path.join(local_base_path, item)
                            if os.path.isdir(item_path) and item.startswith(year_month):
                                local_year_month_folder = item_path
                                self.logger.info(f"找到匹配的文件夹: {item}")
                                break
                    
                    if local_year_month_folder and os.path.exists(local_year_month_folder) and os.path.isdir(local_year_month_folder):
                        self.logger.info(f"找到本地汇总文件夹: {local_year_month_folder}")
                        
                        # 使用本地文件夹的实际名称作为目标文件夹名称
                        target_folder_name = os.path.basename(local_year_month_folder)
                        self.logger.info(f"使用本地文件夹名称: {target_folder_name}")
                        
                        # 同步文件夹到飞书云文档
                        sync_success = self.sync_folder_to_feishu(local_year_month_folder, target_folder_name)
                        if sync_success:
                            # 获取文件夹token并构建URL
                            try:
                                # 获取默认父文件夹token
                                feishu_config = self.json_manager.get_section('feishu')
                                default_parent_token = feishu_config.get('default_parent_node', '')
                                
                                # 查找文件夹token
                                folder_token = self.find_folder_by_name(default_parent_token, target_folder_name)
                                if folder_token:
                                    result["success"] = True
                                    result["folder_token"] = folder_token
                                    result["folder_name"] = target_folder_name
                                    result["folder_url"] = f"https://insta360.feishu.cn/drive/folder/{folder_token}"
                                    self.logger.info(f"总汇总文件夹URL: {result['folder_url']}")
                                else:
                                    self.logger.warning(f"无法找到文件夹token: {target_folder_name}")
                            except Exception as e:
                                self.logger.warning(f"获取文件夹URL失败: {e}")
                        else:
                            self.logger.error("同步文件夹到飞书失败")
                    else:
                        self.logger.error(f"本地汇总文件夹不存在，搜索路径: {local_base_path}, 匹配模式: {year_month}*")
            else:
                self.logger.warning(f"固件URL中不包含有效路径: {firmware_url}")
                
        except Exception as e:
            self.logger.error(f"构建文件夹路径失败: {e}")
        
        return result
