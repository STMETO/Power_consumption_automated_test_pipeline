"""
功耗测试 - 完整测试流程（基于JSON配置）
测试流程：
1. 根据JSON文件设置环境（setEnv）
2. 根据JSON文件设置相机模式并开启录制（record）
3. 根据JSON文件进行QEPM功耗测量（qepm）
4. 将得到的源数据进行Excel操作
"""
import os
import sys
import time
import argparse
import subprocess
from pathlib import Path
from datetime import datetime

# 添加路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.utils.logger import Logger
from src.utils.config_manager import ConfigManager
from src.core.dev import InsDev
from src.core.adb import Adb
from src.utils.report_manager import set_test_case

# 自定义异常类，替代pytest.fail和pytest.skip
class TestFailure(Exception):
    """测试失败异常"""
    pass

class TestSkip(Exception):
    """测试跳过异常"""
    pass

from src.app.PowerConsumption.PowerConsumption_modeChange import PowerConsumptionModeChange
from src.app.PowerConsumption.PowerConsumption_setUpTestEnv import PowerConsumptionSetUpTestEnv
from src.app.PowerConsumption.PowerConsumption_optQEPM import PowerConsumptionOptQEPM
from src.app.PowerConsumption.PowerConsumption_processExcelData import PowerConsumptionProcessExcelData
from src.app.PowerConsumption.PowerConsumption_feishuReport import PowerConsumptionFeishuReport
from src.app.PowerConsumption.PowerConsumption_downlodeFirmWare import PowerConsumptionDownloadFirmware
from src.app.PowerConsumption.PowerConsumption_getVedioInfo import PowerConsumptionGetVideoInfo
from src.app.PowerConsumption.PowerConsumption_jsonManager import PowerConsumptionJsonManager


# ============= 测试常量配置 =============

# QEPM 相关常量
# 注意：QEPM URL现在从JSON配置文件中读取，不再使用默认值
# QEPM_HEADLESS_MODE 可以通过环境变量或命令行参数 --qepm-show-browser 控制
# False=显示浏览器窗口但不置顶（默认，可随时查看），True=完全后台运行
QEPM_HEADLESS_MODE = os.environ.get('QEPM_HEADLESS_MODE', 'False').lower() == 'true'

# 温度检测相关常量
TEMPERATURE_THRESHOLD = 55.0  # 温度阈值（摄氏度）
TEMPERATURE_MAX_WAIT_TIME = 300  # 温度检测最大等待时间（秒）：5分钟
TEMPERATURE_CHECK_INTERVAL = 10  # 温度检测间隔（秒）

# 相机服务控制相关常量
CAMERA_START_CMD = "systemctl start ins_mediad"  # 启动相机服务命令
CAMERA_STOP_CMD = "systemctl stop ins_mediad"  # 停止相机服务命令

# 其他测试常量
TEST_RESULT_SUCCESS = 0  # 测试成功状态码
TEST_RESULT_FAILURE = 1  # 测试失败状态码
TEST_RESULT_SKIP = 0  # 测试跳过状态码（视为成功）

# 分离屏休眠等待时间
DISPLAY_SLEEP_WAIT_TIME = 70  # 分离屏休眠等待时间（秒）

#允许帧率误差范围
ALLOW_FRAME_RANGE = 5

def setup_test_environment():
    """
    设置测试环境变量（从命令行参数或默认值）
    这个函数在 pytest 运行前被调用
    """
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='运行功耗测试')
    parser.add_argument('--dev', type=str, help='测试设备类型，如: Z03, C9, IAC4，默认Z03')
    # 注意：QEPM URL和测试时长现在从JSON文件读取，不再使用命令行参数
    # parser.add_argument('--qepm-url', type=str, dest='qepm_url', help='QEPM网页地址')
    # parser.add_argument('--duration', type=int, dest='qepm_duration', help='QEPM测试时长（秒），会覆盖JSON中的duration')
    parser.add_argument('--test', '--test-name', dest='test_name', type=str, help='运行特定的测试用例')
    parser.add_argument('--timeout', type=int, help='单个测试超时时间（秒），默认300秒')
    parser.add_argument('-v', '--verbose', action='store_true', help='显示详细输出')
    parser.add_argument('-m', '--markers', nargs='*', help='指定测试标记')
    parser.add_argument('--config-name', type=str, help='JSON配置中的record配置名称，如: 4K60_功耗测试')
    parser.add_argument('--qepm-show-browser', action='store_true', help='显示QEPM浏览器窗口（用于调试，默认后台运行）')
    
    # 解析所有参数（包括pytest参数）
    # 使用 parse_known_args 来分离我们的参数和pytest参数
    args, unknown_args = parser.parse_known_args()
    
    # 获取项目根目录
    aipl_test_dir = Path(__file__).parent.parent.parent.absolute()
    
    # 创建日志目录
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    logs_dir = aipl_test_dir / "reports" / timestamp
    logs_dir.mkdir(parents=True, exist_ok=True)
    
    # 设置环境变量
    os.environ['LOG_DIR'] = str(logs_dir)
    os.environ['REPORT_DIR'] = str(logs_dir)
    
    # 设置设备类型（FW_DEV）
    if args.dev:
        os.environ['FW_DEV'] = args.dev
    elif not os.environ.get('FW_DEV'):
        os.environ['FW_DEV'] = 'Z03'
        print(f"未指定设备类型，使用默认值: {os.environ['FW_DEV']}")
    
    print(f"测试设备为: {os.environ['FW_DEV']}")
    print(f"报告目录: {logs_dir}")
    
    # 设置配置名称到环境变量（如果指定了）
    if args.config_name:
        os.environ['RECORD_CONFIG_NAME'] = args.config_name
        print(f"使用指定的配置名称: {args.config_name}")
    else:
        print("注意：未指定配置名称，将使用JSON文件中的第一个配置")
    
    # 设置QEPM浏览器显示模式
    # 默认显示但不置顶（可随时查看，不影响操作）
    if args.qepm_show_browser:
        os.environ['QEPM_HEADLESS_MODE'] = 'False'
        print("QEPM浏览器窗口：显示但不置顶（可随时查看，不影响操作）")
    else:
        # 默认也是显示但不置顶
        os.environ['QEPM_HEADLESS_MODE'] = 'False'
        print("QEPM浏览器窗口：显示但不置顶（可随时查看，不影响操作）")
    
    print("注意：其他配置（QEPM URL、测试时长等）将从JSON文件读取")
    
    return args, logs_dir


class TestPowerConsumption:
    """功耗测试类（基于JSON配置）"""
    
    def _load_json_config(self):
        """从JSON文件加载完整配置"""
        import json
        device_name = self.dev.name if hasattr(self.dev, 'name') else 'Z03'
        current_file = Path(__file__).resolve()
        project_root = current_file.parent.parent.parent
        json_file = project_root / "data" / device_name / "power_consumption.json"
        
        if not json_file.exists():
            self.logger.error(f"JSON配置文件不存在: {json_file}")
            self.json_config = None
            return
        
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                self.json_config = json.load(f)
            self.logger.info(f"成功加载JSON配置: {json_file}")
        except Exception as e:
            self.logger.error(f"读取JSON配置文件失败: {e}")
            self.json_config = None
    
    def __init__(self):
        """初始化测试类，手动创建所需的对象"""
        # 创建基础对象
        self.logger = Logger()
        self.config = ConfigManager()
        
        # 创建ADB和设备对象
        adb = Adb(self.logger)
        dev_name = os.getenv("FW_DEV", "Unknow")
        self.dev = InsDev(dev_name, adb, self.config, self.logger)
        
        # 初始化各个模块
        self.mode_change = PowerConsumptionModeChange(self.dev, self.config, self.logger)
        self.env_setup = PowerConsumptionSetUpTestEnv(self.dev, self.config, self.logger)
        self.data_processor = None  # 延迟初始化，需要统一文件夹名称
        self.feishu_report = PowerConsumptionFeishuReport(self.config, self.logger, self.dev.name)
        self.firmware_downloader = PowerConsumptionDownloadFirmware(self.dev, self.config, self.logger)
        self.video_info_getter = None  # 延迟初始化，需要统一文件夹名称
        
        # 初始化QEPM自动化模块（延迟初始化）
        self.qepm = None
        
        # 从JSON文件加载配置（用于后续使用）
        self.json_config = None
        self._load_json_config()
        
        # 测试次数计数相关
        self.unified_folder_name = None
        self.test_run_number = None
    
    def setup(self):
        """测试前的设置"""

        # ========== 步骤0: 固件下载和OTA升级 ==========
        # 步骤0: 固件下载和OTA升级（如果配置了固件URL）
        self.logger.info("步骤0: 固件下载和OTA升级")
        
        # 检查是否配置了固件URL
        firmware_config = self.firmware_downloader.load_firmware_config()
        if firmware_config and firmware_config.get('download_url'):
            self.logger.info("检测到固件配置，开始执行OTA升级流程")
            
            # 获取日志目录
            log_dir = os.environ.get('REPORT_DIR')
            
            # 执行完整的OTA升级流程
            ota_success, error_msg = self.firmware_downloader.download_and_upgrade(
                download_url=None,  # 从JSON读取
                timeout=None,  # 从JSON读取
                log_dir=log_dir,
                log_suffix="before_power_test",
                verify_version=firmware_config.get('verify_version', True),
                json_file=None  # 使用默认路径
            )
            
            if not ota_success:
                # OTA升级失败，保存错误信息并终止测试
                error_message = f"OTA升级失败: {error_msg}"
                self.logger.error(error_message)
                self.feishu_report.save_error_message(error_message)
                raise TestFailure(error_message)
            
            # 检查是否是版本一致跳过升级
            if error_msg == "VERSION_MATCH_SKIP":
                # 版本一致，跳过升级，设备未重启，不需要唤醒
                self.logger.info("版本一致，已跳过OTA升级，继续执行功耗测试")
            else:
                # OTA升级成功，设备已重启，需要唤醒关机充电状态
                self.logger.info("OTA升级成功，唤醒关机充电状态")
                if not self.env_setup.wakeup_from_sleep():
                    error_message = "设备唤醒失败"
                    self.logger.error(error_message)
                    self.feishu_report.save_error_message(error_message)
                    raise TestFailure(error_message)
                
                self.logger.info("设备已唤醒，继续执行功耗测试")
        else:
            self.logger.info("未配置固件URL，跳过OTA升级步骤")
        # ========== OTA流程结束 ==========
        
        # 删除SD卡中的所有视频数据
        self.logger.info("删除SD卡中的所有视频数据（OTA升级后清理）")
        try:
            # 初始化video_info_getter（如果还未初始化）
            if self.video_info_getter is None:
                from src.app.PowerConsumption.PowerConsumption_getVedioInfo import PowerConsumptionGetVideoInfo
                self.video_info_getter = PowerConsumptionGetVideoInfo(
                    self.dev, self.config, self.logger, unified_folder_name="temp_ota_cleanup"
                )
            
            # 删除SD卡中的所有视频文件
            if self.video_info_getter.delete_all_files_on_device():
                self.logger.info("✓ SD卡视频数据删除成功")
            else:
                self.logger.warning("SD卡视频数据删除失败，但继续执行测试")
        except Exception as e:
            self.logger.warning(f"删除SD卡视频数据时出错: {e}，但继续执行测试")
            import traceback
            self.logger.debug(traceback.format_exc())
        
        # 步骤1: 检测用户模式（必须在设置环境之前）
        self.logger.info("步骤1: 检测设备用户模式")
        
        if not self.env_setup.is_user_mode():
            error_msg = "设备不是用户模式，无法继续测试。请确保设备处于用户模式（mode: 2）"
            self.logger.error(error_msg)
            self.feishu_report.save_error_message(error_msg)
            raise TestFailure(error_msg)
        else:
            self.logger.info("设备用户模式检测通过")

        # 等待分离屏休眠
        self.logger.info(f"等待分离屏休眠（{DISPLAY_SLEEP_WAIT_TIME}秒）...")
        time.sleep(DISPLAY_SLEEP_WAIT_TIME)
        self.logger.info("分离屏休眠等待完成")

        # 步骤2: 根据JSON文件设置环境
        self.logger.info("步骤2: 根据JSON文件设置测试环境")
        
        if not self.env_setup.setup_environment():
            self.logger.warning("环境设置失败，继续测试")
        else:
            # 保存setEnv配置到环境变量，供飞书通知使用
            if hasattr(self.env_setup, 'env_config') and self.env_setup.env_config:
                import json
                os.environ['POWER_SETENV_CONFIG'] = json.dumps(self.env_setup.env_config)
        
        # 准备功耗测试环境（启动ipcmedia_client等）
        log_dir = os.environ.get('REPORT_DIR')
        if not self.mode_change.prepare_for_power_test(log_dir):
            raise TestSkip("功耗测试环境准备失败")
        
        # 记录测试开始时间
        test_start_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        os.environ['TEST_START_TIME'] = test_start_time
    
    def teardown(self):
        """测试后的清理"""
        # 清理测试环境
        self.logger.info("=" * 80)
        self.logger.info("开始清理测试环境")
        self.logger.info("=" * 80)
        
        if hasattr(self, 'mode_change') and self.mode_change:
            self.mode_change.cleanup_after_power_test()
        
        # 恢复测试环境（根据JSON配置恢复）
        if hasattr(self, 'env_setup') and self.env_setup:
            self.logger.info("恢复测试环境（根据JSON配置）")
            self.env_setup.restore_environment()
        
        # 关闭QEPM浏览器（如果已打开）
        if hasattr(self, 'qepm') and self.qepm:
            try:
                self.qepm.close()
            except Exception as e:
                self.logger.warning(f"关闭QEPM浏览器时出错: {e}")
        
        self.logger.info("测试环境清理完成")
        
        # 注意：飞书通知在main()函数中统一发送，避免重复发送
    
    def _test_shutdown_charge_mode(self, config_name: str) -> dict:
        """
        测试关机充电模式
        
        Args:
            config_name: 配置名称（"关机充电_功耗测试"）
            
        Returns:
            dict: 测试结果，包含 config_name, load_power, battery_power, excel_file, test_duration, should_record, error_message
        """
        result = {
            'config_name': config_name,
            'load_power': None,
            'battery_power': None,
            'excel_file': None,
            'test_duration': None,
            'should_record': None,
            'error_message': None,
            'temperature_start': None,
            'temperature_end': None
        }
        
        try:
            set_test_case("test_power_consumption", f"功耗测试（基于JSON配置: {config_name}）")
            self.logger.info("=" * 80)
            self.logger.info(f"开始执行功耗测试（基于JSON配置: {config_name}）")
            self.logger.info("=" * 80)
            
            # 步骤1: 进入关机充电模式
            self.logger.info("步骤2: 进入关机充电模式")
            if not self.env_setup.enter_sleep(5):
                error_msg = "进入关机充电模式失败"
                self.logger.error(error_msg)
                self.feishu_report.save_error_message(error_msg)
                raise TestFailure(error_msg)
            
            # 步骤2: 等待设备进入休眠状态
            self.logger.info("步骤3: 等待设备进入休眠状态")
            time.sleep(5)
            
            # 步骤3: 获取测试时长（从JSON中的duration读取）
            record_config = self.mode_change.load_record_config(config_name)
            if not record_config:
                error_msg = f"加载JSON配置失败: {config_name}"
                self.logger.error(error_msg)
                self.feishu_report.save_error_message(error_msg)
                raise TestFailure(error_msg)
            
            test_duration = int(record_config.get('duration', 60))
            self.logger.info(f"测试时长: {test_duration}秒")

            # 步骤4: 关闭USB供电
            self.logger.info("步骤1: 关闭USB供电")
            if not self.env_setup.set_usb_power(False):
                self.logger.warning("关闭USB供电失败，继续测试")
            else:
                self.logger.info("USB供电已关闭")
                time.sleep(0.5)
            
            # 步骤5: 根据JSON文件进行QEPM功耗测量
            self.logger.info("步骤4: 根据JSON文件进行QEPM功耗测量")
            
            # 5.1: 初始化并打开QEPM
            self.logger.info("步骤4.1: 打开QEPM网页")
            try:
                # QEPM URL从JSON配置文件中读取
                self.qepm = PowerConsumptionOptQEPM(self.dev, self.config, self.logger, qepm_url=None)
                
                if not self.qepm.open_qepm(headless=QEPM_HEADLESS_MODE):
                    error_msg = "QEPM网页打开失败"
                    self.logger.error(error_msg)
                    self.feishu_report.save_error_message(error_msg)
                    raise TestFailure(error_msg)
                else:
                    self.logger.info("QEPM网页打开成功")
                    time.sleep(2)
            except Exception as e:
                error_msg = f"初始化QEPM失败: {e}"
                self.logger.error(error_msg)
                self.feishu_report.save_error_message(error_msg)
                raise TestFailure(error_msg)
            
            # 5.2: 点击LIVE VIEW按钮
            self.logger.info("步骤4.2: 点击LIVE VIEW按钮")
            if not self.qepm.click_live_view():
                error_msg = "LIVE VIEW按钮点击失败"
                self.logger.error(error_msg)
                self.feishu_report.save_error_message(error_msg)
                raise TestFailure(error_msg)
            else:
                self.logger.info("LIVE VIEW按钮点击成功")
                time.sleep(2)
            
            # 5.3: 配置LIVE VIEW窗口（根据JSON配置）
            self.logger.info("步骤4.3: 配置LIVE VIEW窗口（根据JSON配置）")
            if not self.qepm.configure_live_view():
                error_msg = "LIVE VIEW窗口配置失败"
                self.logger.error(error_msg)
                self.feishu_report.save_error_message(error_msg)
                raise TestFailure(error_msg)
            else:
                self.logger.info("LIVE VIEW窗口配置成功")
                time.sleep(2)
            
            # 5.4: 点击QEPM开始测试按钮并记录开始温度
            self.logger.info("步骤4.4: 点击QEPM开始测试按钮")
            if not self.qepm.click_start():
                error_msg = "QEPM开始测试按钮点击失败"
                self.logger.error(error_msg)
                self.feishu_report.save_error_message(error_msg)
                raise TestFailure(error_msg)
            else:
                self.logger.info("QEPM开始测试按钮点击成功")
                time.sleep(1)
                
                # 记录开始温度
                temperature_start = self.env_setup.get_temperature()
                if temperature_start >= 0:
                    result['temperature_start'] = temperature_start
                    self.logger.info(f"功耗测试开始温度: {temperature_start}°C")
                else:
                    self.logger.warning("获取开始温度失败")
            
            # 5.5: 等待测量完成
            self.logger.info(f"步骤4.5: 等待测量完成（{test_duration}秒）...")
            start_time = time.time()
            check_interval = 10
            elapsed = 0
            while elapsed < test_duration:
                time.sleep(min(check_interval, test_duration - elapsed))
                elapsed = int(time.time() - start_time)
                remaining = test_duration - elapsed
                if remaining > 0:
                    self.logger.info(f"测试进行中... 已用时: {elapsed}秒，剩余: {remaining}秒")
            self.logger.info(f"测试时长达到 {test_duration} 秒")
            
            # 5.6: 点击QEPM停止测试按钮并记录结束温度
            self.logger.info("步骤4.6: 点击QEPM停止测试按钮")
            if not self.qepm.click_stop():
                self.logger.warning("QEPM停止测试按钮点击失败")
            else:
                self.logger.info("QEPM停止测试按钮点击成功")
                time.sleep(1)
                
                # 记录结束温度
                temperature_end = self.env_setup.get_temperature()
                if temperature_end >= 0:
                    result['temperature_end'] = temperature_end
                    self.logger.info(f"功耗测试结束温度: {temperature_end}°C")
                else:
                    self.logger.warning("获取结束温度失败")
            
            # 5.7: 下载Excel源数据
            self.logger.info("步骤4.7: 下载Excel源数据")
            if not self.qepm.download_data():
                error_msg = "Excel源数据下载失败"
                self.logger.error(error_msg)
                self.feishu_report.save_error_message(error_msg)
                raise TestFailure(error_msg)
            else:
                self.logger.info("Excel源数据下载操作完成")
                time.sleep(3)
            
            # 步骤6: 处理下载的数据（导入Excel）
            self.logger.info("步骤5: 处理下载的数据（导入Excel）")
            excel_file = self.data_processor.process_downloaded_data(config_name)
            if not excel_file:
                error_msg = "Excel数据处理失败"
                self.logger.error(error_msg)
                self.feishu_report.save_error_message(error_msg)
                raise TestFailure(error_msg)
            else:
                self.logger.info(f"Excel数据处理成功，文件保存在: {excel_file}")
            
            # 步骤7: 从Excel文件中读取功耗值
            load_power = None
            battery_power = None
            module_power_values = {}
            if excel_file:
                try:
                    load_power = self.data_processor.get_cell_value(excel_file, 'D2')
                    battery_power = self.data_processor.get_cell_value(excel_file, 'F2')
                    self.logger.info(f"读取功耗值成功: 负载端={load_power}, 电池端={battery_power}")
                    
                    # 读取模块功耗值
                    module_power_values = self.data_processor.get_module_power_values(excel_file)
                    self.logger.info(f"读取模块功耗值完成")
                except Exception as e:
                    self.logger.warning(f"读取功耗值失败: {e}")
            
            # 保存测试结果
            result['load_power'] = str(load_power) if load_power else None
            result['battery_power'] = str(battery_power) if battery_power else None
            result['excel_file'] = str(excel_file) if excel_file else None
            result['test_duration'] = str(test_duration)
            result['should_record'] = str(False)
            result['module_power_values'] = module_power_values
            
            # 步骤8: 关机充电模式：唤醒设备
            self.logger.info("步骤6: 唤醒设备（退出关机充电模式）")
            if not self.env_setup.wakeup_from_sleep():
                error_msg = "唤醒设备失败"
                self.logger.error(error_msg)
                self.feishu_report.save_error_message(error_msg)
                raise TestFailure(error_msg)
            
            self.logger.info("=" * 80)
            self.logger.info(f"功耗测试完成（基于JSON配置: {config_name}）")
            self.logger.info("=" * 80)
            
        except TestFailure as e:
            result['error_message'] = str(e)
            self.logger.error(f"测试失败: {result['error_message']}")
        
        except Exception as e:
            result['error_message'] = f"测试执行异常: {str(e)}"
            self.logger.error(result['error_message'])
            import traceback
            self.logger.error(traceback.format_exc())
        
        return result
    
    
    def _test_single_config(self, config_name: str) -> dict:
        """
        测试单个配置挡位
        
        Args:
            config_name: 配置名称
            
        Returns:
            dict: 测试结果，包含 config_name, load_power, battery_power, excel_file, test_duration, should_record, error_message
        """
        result = {
            'config_name': config_name,
            'load_power': None,
            'battery_power': None,
            'excel_file': None,
            'test_duration': None,
            'should_record': None,
            'error_message': None
        }
        
        try:
            set_test_case("test_power_consumption", f"功耗测试（基于JSON配置: {config_name}）")
            self.logger.info("=" * 80)
            self.logger.info(f"开始执行功耗测试（基于JSON配置: {config_name}）")
            self.logger.info("=" * 80)
            
            # 在切换挡位前，先停止录制（如果正在录制）
            self.logger.info("停止当前录制（如果正在录制）")
            try:
                success, response = self.mode_change.execute_command("record stop")
                if success:
                    self.logger.debug("停止录制成功")
                    time.sleep(1)  # 等待录制完全停止
                else:
                    self.logger.debug("停止录制命令执行失败（可能未在录制）")
            except Exception as e:
                self.logger.debug(f"停止录制时出错（可能未在录制）: {e}")
            
            # 在切换挡位前，先删除设备上的所有视频文件（避免拉取到上一个挡位的视频）
            self.logger.info("清理设备上的视频文件（避免拉取到上一个挡位的视频）")
            try:
                self.video_info_getter.delete_all_files_on_device()
                self.logger.debug("设备视频文件清理完成")
                time.sleep(0.5)  # 等待删除完成
            except Exception as e:
                self.logger.warning(f"清理设备视频文件时出错: {e}")
            
            # 检查是否是关机充电模式
            if config_name == "关机充电_功耗测试":
                self.logger.info("检测到关机充电模式，执行关机充电功耗测试")
                return self._test_shutdown_charge_mode(config_name)
            
            # 步骤3: 根据JSON文件设置相机模式（根据JSON配置决定是否开启录制）
            self.logger.info("步骤3: 根据JSON文件设置相机模式")
            
            # 先加载配置以检查是否需要录制
            record_config = self.mode_change.load_record_config(config_name)
            if not record_config:
                error_msg = f"加载JSON配置失败: {config_name}"
                self.logger.error(error_msg)
                self.feishu_report.save_error_message(error_msg)
                raise TestFailure(error_msg)
            
            should_record = record_config.get('record', True)
            expected_width = record_config.get('width')
            expected_height = record_config.get('height')
            expected_fps = None
            # 从config中解析帧率（例如 "config spec InsMediaResRatioFps kRes4K kRatio16x9 k30"）
            config_lines = record_config.get('config', [])
            for config_line in config_lines:
                if 'k30' in config_line:
                    expected_fps = 30
                elif 'k60' in config_line:
                    expected_fps = 60
                elif 'k120' in config_line:
                    expected_fps = 120
            
            if should_record:
                self.logger.info("JSON配置要求开启录制")
            else:
                self.logger.info("JSON配置要求预览模式（不开启录制）")
            
            if not self.mode_change.setup_and_start_record(config_name):
                if should_record:
                    error_msg = f"设置相机配置并开启录制失败: {config_name}"
                else:
                    error_msg = f"设置相机配置失败: {config_name}"
                self.logger.error(error_msg)
                self.feishu_report.save_error_message(error_msg)
                raise TestFailure(error_msg)
            
            if should_record:
                self.logger.info(f"成功设置相机配置并已开启录制: {config_name}")
            else:
                self.logger.info(f"成功设置相机配置（预览模式）: {config_name}")
            
            self.logger.info(f"测试时长: {self.mode_change.record_duration}秒")
            time.sleep(2)
            
            # 步骤4: 在测试功耗前进行5秒左右的录制，检查视频信息
            if should_record:
                self.logger.info("步骤4: 录制5秒视频并检查视频信息")
                
                # 等待5秒录制
                self.logger.info("等待5秒录制...")
                time.sleep(5)
                
                # 停止录制，确保视频文件完全写入
                self.logger.info("停止录制，确保视频文件完全写入...")
                success, response = self.mode_change.execute_command("record stop")
                if not success:
                    self.logger.warning("停止录制命令执行失败，但继续尝试拉取视频")
                else:
                    self.logger.info("停止录制成功")
                    # 等待文件完全写入（给系统一些时间完成文件写入）
                    time.sleep(2)
                
                # 拉取并分析视频
                video_info_list = self.video_info_getter.pull_and_analyze_videos(config_name)
                
                # 重新开启录制（因为后续还要进行功耗测试）
                if video_info_list:
                    self.logger.info("重新开启录制，准备进行功耗测试...")
                    success, response = self.mode_change.execute_command("record start")
                    if not success:
                        error_msg = "重新开启录制失败"
                        self.logger.error(error_msg)
                        self.feishu_report.save_error_message(error_msg)
                        raise TestFailure(error_msg)
                    else:
                        self.logger.info("重新开启录制成功")
                        time.sleep(2)  # 等待录制稳定
                        
                        # 记录开始温度
                        temperature_start = self.env_setup.get_temperature()
                        if temperature_start >= 0:
                            result['temperature_start'] = temperature_start
                            self.logger.info(f"功耗测试开始温度: {temperature_start}°C")
                        else:
                            self.logger.warning("获取开始温度失败")
                
                if not video_info_list:
                    error_msg = "未找到视频文件或视频信息解析失败"
                    self.logger.error(error_msg)
                    self.feishu_report.save_error_message(error_msg)
                    raise TestFailure(error_msg)
                
                # 检查第一个视频的信息
                video_info = video_info_list[0]
                actual_width = video_info.get('width')
                actual_height = video_info.get('height')
                actual_fps = video_info.get('frame_rate')
                
                self.logger.info(f"视频信息检查:")
                self.logger.info(f"  期望分辨率: {expected_width}x{expected_height}")
                self.logger.info(f"  实际分辨率: {actual_width}x{actual_height}")
                self.logger.info(f"  期望帧率: {expected_fps}")
                self.logger.info(f"  实际帧率: {actual_fps}")
                
                # 使用验证函数进行验证（帧率允许误差5帧）
                verify_success, verify_message = self.video_info_getter.verify_video_info(
                    video_info=video_info,
                    expected_width=expected_width,
                    expected_height=expected_height,
                    expected_fps=expected_fps,
                    fps_tolerance=ALLOW_FRAME_RANGE  # 允许误差5.0帧
                )
                
                if not verify_success:
                    test_error_message = f"视频信息验证失败: {verify_message}"
                    self.logger.error(test_error_message)
                    # 保存错误信息到文件，供main函数中的飞书通知使用
                    self.feishu_report.save_error_message(test_error_message)
                    raise TestFailure(verify_message)
                
                self.logger.info(f"✓ {verify_message}")
            
            # 获取测试时长（从JSON中的duration读取）
            test_duration = int(self.mode_change.record_duration)
            self.logger.info(f"QEPM测试时长: {test_duration}秒（从JSON配置读取）")
            
            # 步骤5: 根据JSON文件进行QEPM功耗测量（无论录制模式还是预览模式）
            self.logger.info("步骤5: 根据JSON文件进行QEPM功耗测量")

            # 5.1: 初始化并打开QEPM
            self.logger.info("步骤5.1: 打开QEPM网页")
            try:
                # QEPM URL从JSON配置文件中读取
                self.qepm = PowerConsumptionOptQEPM(self.dev, self.config, self.logger, qepm_url=None)

                if not self.qepm.open_qepm(headless=QEPM_HEADLESS_MODE):
                    error_msg = "QEPM网页打开失败"
                    self.logger.error(error_msg)
                    self.feishu_report.save_error_message(error_msg)
                    raise TestFailure(error_msg)
                else:
                    self.logger.info("QEPM网页打开成功")
                    time.sleep(2)
            except Exception as e:
                error_msg = f"初始化QEPM失败: {e}"
                self.logger.error(error_msg)
                self.feishu_report.save_error_message(error_msg)
                raise TestFailure(error_msg)
            
            # 5.2: 点击LIVE VIEW按钮
            self.logger.info("步骤5.2: 点击LIVE VIEW按钮")
            if not self.qepm.click_live_view():
                error_msg = "LIVE VIEW按钮点击失败"
                self.logger.error(error_msg)
                self.feishu_report.save_error_message(error_msg)
                raise TestFailure(error_msg)
            else:
                self.logger.info("LIVE VIEW按钮点击成功")
                time.sleep(2)
            
            # 5.3: 配置LIVE VIEW窗口（根据JSON配置）
            self.logger.info("步骤5.3: 配置LIVE VIEW窗口（根据JSON配置）")
            if not self.qepm.configure_live_view():
                error_msg = "LIVE VIEW窗口配置失败"
                self.logger.error(error_msg)
                self.feishu_report.save_error_message(error_msg)
                raise TestFailure(error_msg)
            else:
                self.logger.info("LIVE VIEW窗口配置成功")
                time.sleep(2)
            
            # 5.4: 在QEPM开始测试前再次确认关闭USB供电
            self.logger.info("步骤5.4: 在QEPM开始测试前再次确认关闭USB供电")
            if not self.env_setup.set_usb_power(False):
                self.logger.warning("再次关闭USB供电失败，继续测试")
            else:
                self.logger.info("USB供电已再次确认关闭")
                time.sleep(0.5)
            
            # 5.5: 点击QEPM开始测试按钮
            self.logger.info("步骤5.5: 点击QEPM开始测试按钮")
            if not self.qepm.click_start():
                error_msg = "QEPM开始测试按钮点击失败"
                self.logger.error(error_msg)
                self.feishu_report.save_error_message(error_msg)
                raise TestFailure(error_msg)
            else:
                self.logger.info("QEPM开始测试按钮点击成功")
                time.sleep(1)
            
            # 5.6: 等待测试时长
            self.logger.info(f"步骤5.6: 等待测试时长 {test_duration} 秒（QEPM持续测量功耗）")
            start_time = time.time()
            check_interval = 10
            elapsed = 0
            while elapsed < test_duration:
                time.sleep(min(check_interval, test_duration - elapsed))
                elapsed = int(time.time() - start_time)
                remaining = test_duration - elapsed
                if remaining > 0:
                    self.logger.info(f"测试进行中... 已用时: {elapsed}秒，剩余: {remaining}秒")
            self.logger.info(f"测试时长达到 {test_duration} 秒")
            
            # 5.7: 点击QEPM停止测试按钮
            self.logger.info("步骤5.7: 点击QEPM停止测试按钮")
            if not self.qepm.click_stop():
                self.logger.warning("QEPM停止测试按钮点击失败")
            else:
                self.logger.info("QEPM停止测试按钮点击成功")
                time.sleep(1)
                
                # 记录结束温度
                temperature_end = self.env_setup.get_temperature()
                if temperature_end >= 0:
                    result['temperature_end'] = temperature_end
                    self.logger.info(f"功耗测试结束温度: {temperature_end}°C")
                else:
                    self.logger.warning("获取结束温度失败")
            
            # 5.8: 下载Excel源数据
            self.logger.info("步骤5.8: 下载Excel源数据")
            if not self.qepm.download_data():
                error_msg = "Excel源数据下载失败"
                self.logger.error(error_msg)
                self.feishu_report.save_error_message(error_msg)
                raise TestFailure(error_msg)
            else:
                self.logger.info("Excel源数据下载操作完成")
                time.sleep(3)  # 等待下载完成
            
            # 步骤6: 将得到的源数据进行Excel操作
            self.logger.info("步骤6: 将得到的源数据进行Excel操作")
            
            # 传递配置名称用于生成文件名
            try:
                excel_file = self.data_processor.process_downloaded_data(config_name=config_name)
                if not excel_file:
                    error_msg = "Excel数据处理失败"
                    self.logger.error(error_msg)
                    self.feishu_report.save_error_message(error_msg)
                    raise TestFailure(error_msg)
            except (FileNotFoundError, RuntimeError) as e:
                # 如果从raw_data_path剪切数据失败，说明没有最新的原始数据，即QEPM出现错误
                error_msg = f"QEPM数据获取失败: {str(e)}"
                self.logger.error(error_msg)
                self.feishu_report.save_error_message(error_msg)
                raise TestFailure(error_msg)
            else:
                self.logger.info(f"Excel数据处理成功，文件保存在: {excel_file}")
            
                # 从Excel文件中读取功耗值（电池端和负载端）
                load_power = None
                battery_power = None
                module_power_values = {}
                if excel_file:
                    try:
                        load_power = self.data_processor.get_cell_value(excel_file, 'D2')
                        battery_power = self.data_processor.get_cell_value(excel_file, 'F2')
                        self.logger.info(f"读取功耗值成功: 负载端={load_power}, 电池端={battery_power}")
                        
                        # 读取模块功耗值
                        module_power_values = self.data_processor.get_module_power_values(excel_file)
                        self.logger.info(f"读取模块功耗值完成")
                    except Exception as e:
                        self.logger.warning(f"读取功耗值失败: {e}")

            # 保存测试结果（录制模式和预览模式都保存）
            result['load_power'] = str(load_power) if load_power else None
            result['battery_power'] = str(battery_power) if battery_power else None
            result['excel_file'] = str(excel_file) if excel_file else None
            result['test_duration'] = str(test_duration)
            result['should_record'] = str(should_record)
            result['module_power_values'] = module_power_values
            
            # 测试完成后，停止录制（为下一个挡位做准备）
            self.logger.info("测试完成，停止录制")
            try:
                success, response = self.mode_change.execute_command("record stop")
                if success:
                    self.logger.debug("停止录制成功")
                    time.sleep(1)  # 等待录制完全停止
                else:
                    self.logger.debug("停止录制命令执行失败（可能未在录制）")
            except Exception as e:
                self.logger.debug(f"停止录制时出错（可能未在录制）: {e}")
            
            self.logger.info("=" * 80)
            self.logger.info(f"功耗测试完成（基于JSON配置: {config_name}）")
            self.logger.info("=" * 80)
            
        except TestFailure as e:
            result['error_message'] = str(e)
            self.logger.error(f"测试失败: {result['error_message']}")
            # 测试失败时也要停止录制
            try:
                self.logger.info("测试失败，停止录制")
                success, response = self.mode_change.execute_command("record stop")
                if success:
                    self.logger.debug("停止录制成功")
                    time.sleep(1)  # 等待录制完全停止
            except Exception as e:
                self.logger.debug(f"停止录制时出错: {e}")
        except Exception as e:
            import traceback
            error_msg = f"测试异常: {str(e)}"
            result['error_message'] = error_msg
            self.logger.error(error_msg)
            self.logger.debug(f"异常堆栈信息:\n{traceback.format_exc()}")
            # 测试异常时也要停止录制
            try:
                self.logger.info("测试异常，停止录制")
                success, response = self.mode_change.execute_command("record stop")
                if success:
                    self.logger.debug("停止录制成功")
                    time.sleep(1)  # 等待录制完全停止
            except Exception as e:
                self.logger.debug(f"停止录制时出错: {e}")
        
        return result
    
    def test_power_consumption(self):
        """
        测试流程：
        1. 根据JSON文件设置环境（setEnv）- 在setup_and_teardown中完成
        2. 根据JSON文件设置相机模式并开启录制（record）
        3. 在测试功耗前进行5秒左右的录制，检查视频信息是否与设置的相机模式一致
        4. 根据JSON文件进行QEPM功耗测量（qepm）
        5. 将得到的源数据进行Excel操作
        
        切换挡位前会检测温度，只有温度在40度以下才继续下一个挡位的测试
        """
        # 获取配置名称（从环境变量读取）
        config_name = os.environ.get('RECORD_CONFIG_NAME')
        
        # 检查JSON配置
        if not self.json_config or 'record' not in self.json_config or not self.json_config['record']:
            raise TestFailure("无法从JSON文件加载配置")
        
        # 确定要测试的配置列表
        configs_to_test = []
        
        if config_name and config_name.lower() != "testall":
            # 指定了单个配置名称，只测试该配置
            configs_to_test = [config_name]
            self.logger.info(f"测试单个挡位: {config_name}")
        else:
            # 未指定配置名称或指定为testAll，测试所有挡位
            for record_config in self.json_config['record']:
                config_name_single = record_config.get('name')
                if config_name_single:
                    configs_to_test.append(config_name_single)
            self.logger.info("=" * 80)
            self.logger.info(f"将依次测试所有挡位（共 {len(configs_to_test)} 个）")
            self.logger.info("=" * 80)
        
        if not configs_to_test:
            raise TestFailure("没有找到可测试的配置")
        
        # 收集所有挡位的测试结果
        all_results = []
        is_batch_mode = len(configs_to_test) > 1
        
        # 生成统一文件夹名称（单次测试也视为批量测试的特殊形式）
        from src.app.PowerConsumption.PowerConsumption_jsonManager import PowerConsumptionJsonManager
        json_manager = PowerConsumptionJsonManager(dev_name=self.dev.name, logger=self.logger)
        firmware_url = json_manager.get_value('firmware.download_url')
        
        # 提取固件版本
        firmware_version = 'unknown'
        if firmware_url:
            import re
            pattern = r'([A-Z]\d+_[Vv]\d+(?:\.\d+)*(?:_[a-z]+)*_\d{14})'
            match = re.search(pattern, firmware_url)
            if match:
                firmware_version = match.group(1)
        
        # 先初始化Excel数据处理实例（使用固件版本目录）
        self.data_processor = PowerConsumptionProcessExcelData(
            self.config, 
            self.logger
        )
        
        # 获取测试次数并生成统一文件夹名称
        self.test_run_number = self.data_processor.get_next_test_run_number(firmware_version)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.unified_folder_name = f"{firmware_version}-Test{self.test_run_number:02d}-{timestamp}"
        
        self.logger.info("=" * 80)
        self.logger.info(f"测试标识符: {self.unified_folder_name}")
        self.logger.info(f"测试次数: {self.test_run_number}")
        self.logger.info(f"固件版本: {firmware_version}")
        self.logger.info("=" * 80)
        
        # 提前创建统一文件夹
        project_root = Path(__file__).parent.parent.parent
        unified_folder_path = project_root / "PowerConsumption_Data" / self.unified_folder_name
        unified_folder_path.mkdir(parents=True, exist_ok=True)
        self.logger.info(f"创建统一文件夹: {unified_folder_path}")
        
        # 重新初始化Excel数据处理实例（使用统一文件夹名称）
        self.data_processor = PowerConsumptionProcessExcelData(
            self.config, 
            self.logger, 
            self.unified_folder_name
        )
        self.logger.info("Excel数据处理实例已初始化（使用统一文件夹）")
        
        # 重新初始化视频信息获取实例（使用统一文件夹名称）
        from src.app.PowerConsumption.PowerConsumption_getVedioInfo import PowerConsumptionGetVideoInfo
        self.video_info_getter = PowerConsumptionGetVideoInfo(
            self.dev,
            self.config,
            self.logger,
            self.unified_folder_name
        )
        self.logger.info("视频信息获取实例已初始化（使用统一文件夹）")
        
        # 遍历所有要测试的挡位
        for idx, config_name_single in enumerate(configs_to_test):
            self.logger.info("")
            self.logger.info("=" * 80)
            self.logger.info(f"开始测试挡位 {idx + 1}/{len(configs_to_test)}: {config_name_single}")
            self.logger.info("=" * 80)
            
            # 批量模式：切换挡位前检测温度（第一个挡位不需要检测）
            if is_batch_mode and idx > 0:
                self.logger.info(f"批量测试模式：检测设备温度")
                temperature_passed, error_msg = self.env_setup.wait_for_temperature_below_threshold(
                    threshold=TEMPERATURE_THRESHOLD,
                    max_wait_time=TEMPERATURE_MAX_WAIT_TIME,
                    wait_interval=TEMPERATURE_CHECK_INTERVAL
                )
                
                if not temperature_passed:
                    self.logger.error(f"温度检测失败，跳过挡位 {config_name_single}")
                    all_results.append({
                        'config_name': config_name_single,
                        'load_power': None,
                        'battery_power': None,
                        'excel_file': None,
                        'test_duration': None,
                        'should_record': None,
                        'error_message': error_msg,
                        'temperature_start': None,
                        'temperature_end': None
                    })
                    continue  # 跳过当前挡位，继续下一个
            
            # 测试单个挡位
            try:
                result = self._test_single_config(config_name_single)
                all_results.append(result)
                
                # 如果测试失败，记录错误但继续测试下一个挡位（批量模式）
                if result['error_message']:
                    self.logger.error(f"挡位 {config_name_single} 测试失败: {result['error_message']}")
                else:
                    self.logger.info(f"挡位 {config_name_single} 测试成功")
            except Exception as e:
                # 捕获异常，记录到结果中，继续测试下一个挡位（批量模式）
                error_msg = f"挡位测试异常: {str(e)}"
                self.logger.error(f"挡位 {config_name_single} 测试异常: {error_msg}")
                all_results.append({
                    'config_name': config_name_single,
                    'load_power': None,
                    'battery_power': None,
                    'excel_file': None,
                    'test_duration': None,
                    'should_record': None,
                    'error_message': error_msg,
                    'temperature_start': None,
                    'temperature_end': None
                })
            
            # 批量模式：测试间隔，等待设备稳定（最后一个挡位不需要等待）
            if is_batch_mode and idx < len(configs_to_test) - 1:
                self.logger.info("等待设备稳定...")
                time.sleep(2)
        
        # 保存所有挡位的测试结果到文件
        # 构建保存路径: {项目根目录}\PowerConsumption_Data\{统一文件夹名称}\power_test_result-{时间戳}.json
        
        # 生成时间戳
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # 构建完整路径
        project_root = Path(__file__).parent.parent.parent
        
        # 使用统一文件夹名称（如果存在），否则使用固件版本
        if hasattr(self, 'unified_folder_name') and self.unified_folder_name:
            test_result_file = project_root / "PowerConsumption_Data" / self.unified_folder_name / f"power_test_result-{timestamp}.json"
            self.logger.info(f"使用统一文件夹: {self.unified_folder_name}")
        else:
            # 回退到旧的固件版本路径
            json_manager = PowerConsumptionJsonManager(dev_name=self.dev.name, logger=self.logger)
            firmware_url = json_manager.get_value('firmware.download_url')
            
            # 从URL中提取固件版本
            import re
            firmware_version = 'unknown'
            if firmware_url:
                pattern = r'([A-Z]\d+_[Vv]\d+(?:\.\d+)*(?:_[a-z]+)*_\d{14})'
                match = re.search(pattern, firmware_url)
                if match:
                    firmware_version = match.group(1)
            
            test_result_file = project_root / "PowerConsumption_Data" / firmware_version / f"power_test_result-{timestamp}.json"
            self.logger.info(f"使用固件版本文件夹: {firmware_version}")
        
        test_result_file.parent.mkdir(parents=True, exist_ok=True)
        
        self.logger.info(f"测试结果文件路径: {test_result_file}")
        self.logger.info(f"测试结果文件父目录: {test_result_file.parent}")
        self.logger.info(f"测试结果文件父目录是否存在: {test_result_file.parent.exists()}")
        
        test_result_data = {
            'test_all': is_batch_mode,
            'results': all_results
        }
        
        # 保存setEnv配置
        setenv_config = os.environ.get('POWER_SETENV_CONFIG')
        if setenv_config:
            test_result_data['setenv_config'] = setenv_config
        
        try:
            import json
            self.logger.info(f"准备保存测试结果数据...")
            self.logger.info(f"文件路径: {test_result_file}")
            self.logger.info(f"文件父目录: {test_result_file.parent}")
            self.logger.info(f"文件父目录存在: {test_result_file.parent.exists()}")
            
            with open(test_result_file, 'w', encoding='utf-8') as f:
                json.dump(test_result_data, f, ensure_ascii=False, indent=2)
            
            self.logger.info(f"文件保存成功: {test_result_file}")
            self.logger.info(f"文件存在: {test_result_file.exists()}")
            
            if is_batch_mode:
                self.logger.info(f"所有挡位测试结果已保存到: {test_result_file}")
            else:
                self.logger.info(f"测试结果数据已保存到: {test_result_file}")
        except Exception as e:
            self.logger.error(f"保存测试结果数据失败: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
        
        # 检查是否有失败的挡位
        failed_configs = [r for r in all_results if r.get('error_message')]
        if failed_configs:
            # 如果有失败的挡位，收集具体的错误消息并抛出异常
            failed_messages = []
            for r in failed_configs:
                error_msg_item = r.get('error_message', '')
                if error_msg_item:
                    # 直接使用错误消息（错误消息中通常已包含挡位名称）
                    failed_messages.append(error_msg_item)
            
            if failed_messages:
                # 如果有多个失败挡位，用分号分隔；如果只有一个，直接使用
                if len(failed_messages) > 1:
                    error_msg = "；".join(failed_messages)
                else:
                    error_msg = failed_messages[0]
            else:
                # 如果没有错误消息，回退到只显示挡位名称
                failed_names = [r.get('config_name', '未知') for r in failed_configs]
                error_msg = f"部分挡位测试失败: {', '.join(failed_names)}"
            
            self.logger.error(error_msg)
            raise TestFailure(error_msg)
        
        if is_batch_mode:
            self.logger.info("")
            self.logger.info("=" * 80)
            self.logger.info("所有挡位测试完成")
            self.logger.info("=" * 80)


# 如果直接运行此文件，直接执行测试（不使用pytest）
if __name__ == "__main__":
    # 设置测试环境
    args, logs_dir = setup_test_environment()
    
    # 创建测试实例
    test_instance = TestPowerConsumption()
    
    # 测试结果
    test_result = TEST_RESULT_SUCCESS  # 0=成功，非0=失败
    error_message = None
    
    try:
        # 执行测试前的设置
        test_instance.setup()
        
        # 执行主测试
        test_instance.test_power_consumption()
        
        print("-" * 80)
        print("测试完成，退出码: 0 (成功)")
        
    except TestSkip as e:
        # 测试被跳过
        test_result = TEST_RESULT_SKIP
        print(f"测试被跳过: {e}")
        test_instance.logger.info(f"测试被跳过: {e}")
        
    except TestFailure as e:
        # 测试失败
        test_result = TEST_RESULT_FAILURE
        error_message = str(e)
        print(f"测试失败: {error_message}")
        test_instance.logger.error(f"测试失败: {error_message}")
        test_instance.feishu_report.save_error_message(error_message)
        
    except Exception as e:
        # 其他异常
        test_result = TEST_RESULT_FAILURE
        import traceback
        error_message = f"测试执行异常: {str(e)}"
        print(f"测试执行异常: {error_message}")
        test_instance.logger.error(error_message)
        test_instance.logger.debug(f"异常堆栈信息:\n{traceback.format_exc()}")
        test_instance.feishu_report.save_error_message(error_message)
        
    finally:
        # 执行测试后的清理
        try:
            test_instance.teardown()
        except Exception as e:
            print(f"清理测试环境时出错: {e}")
            test_instance.logger.warning(f"清理测试环境时出错: {e}")
    
    # 发送飞书通知（使用PowerConsumptionFeishuReport模块）
    try:
        # 创建飞书报告实例
        from src.utils.config_manager import ConfigManager
        from src.utils.logger import Logger
        from src.app.PowerConsumption.PowerConsumption_feishuReport import PowerConsumptionFeishuReport
        
        device_name = os.environ.get('FW_DEV', 'Z03')
        if device_name == 'Unknow':
            device_name = 'Z03'
        
        config = ConfigManager()
        logger = Logger()
        feishu_report = PowerConsumptionFeishuReport(config, logger, device_name)
        
        # 获取日志路径（上传后的URL或本地路径）
        log_path = os.environ.get('LOG_URL')
        
        # 如果没有上传URL，使用新的路径结构
        if not log_path:
            # 构建路径: {项目根目录}\PowerConsumption_Data\{固件版本}
            json_manager = PowerConsumptionJsonManager(dev_name=device_name, logger=logger)
            firmware_url = json_manager.get_value('firmware.download_url')
            
            # 使用工具类提取固件版本
            from src.app.PowerConsumption.PowerConsumption_utils import extract_firmware_version
            firmware_version = extract_firmware_version(firmware_url) or 'unknown'
            
            # 构建目录路径
            project_root = Path(__file__).parent.parent.parent
            log_path = str(project_root / "PowerConsumption_Data" / firmware_version)
        
        # 报告文件路径（用于飞书通知）
        report_filename = "power_consumption_report.html"
        report_path = Path(log_path) / report_filename
        
        # 从文件读取测试结果数据
        # 构建路径: {项目根目录}\PowerConsumption_Data\{固件版本}\power_test_result-{时间戳}.json
        json_manager = PowerConsumptionJsonManager(dev_name=device_name, logger=logger)
        firmware_url = json_manager.get_value('firmware.download_url')
        
        # 使用工具类提取固件版本
        from src.app.PowerConsumption.PowerConsumption_utils import extract_firmware_version
        firmware_version = extract_firmware_version(firmware_url) or 'unknown'
        
        # 构建目录路径
        project_root = Path(__file__).parent.parent.parent
        result_dir = project_root / "PowerConsumption_Data" / firmware_version
        
        # 查找最新的测试结果文件
        test_result_file = None
        if result_dir.exists():
            # 查找所有 power_test_result-*.json 文件
            result_files = sorted(result_dir.glob("power_test_result-*.json"), reverse=True)
            if result_files:
                test_result_file = result_files[0]  # 使用最新的文件
                print(f"找到测试结果文件: {test_result_file}")
            else:
                pass  # 未找到测试结果文件
        else:
            pass  # 测试结果目录不存在
        load_power = None
        battery_power = None
        excel_file = None
        config_name = None
        test_duration = None
        should_record = None
        setenv_config = None
        # 优先从测试结果文件读取错误消息，如果没有则使用异常中的错误消息
        error_message_final = None
        is_test_all = False
        module_power_values = None
        
        if test_result_file and test_result_file.exists():
            try:
                import json
                with open(test_result_file, 'r', encoding='utf-8') as f:
                    test_result_data = json.load(f)
                
                # 检查是否是多挡位测试
                is_test_all = test_result_data.get('test_all', False)
                
                if is_test_all:
                    # 多挡位测试：使用第一个挡位的配置名称作为标题，或者使用"全部挡位测试"
                    results = test_result_data.get('results', [])
                    if results:
                        # 使用第一个挡位的配置名称
                        config_name = results[0].get('config_name', '全部挡位测试')
                        # 如果有错误，收集所有错误信息（直接使用具体的错误消息）
                        error_messages = []
                        for result_item in results:
                            error_msg_item = result_item.get('error_message')
                            if error_msg_item:
                                # 直接使用错误消息（错误消息中通常已包含挡位名称）
                                error_messages.append(error_msg_item)
                        if error_messages:
                            # 如果有多个失败挡位，用分号分隔；如果只有一个，直接使用
                            if len(error_messages) > 1:
                                error_message_final = "；".join(error_messages)
                            else:
                                error_message_final = error_messages[0]
                    else:
                        config_name = "全部挡位测试"
                else:
                    # 单挡位测试：使用原有逻辑
                    results = test_result_data.get('results', [])
                    if results:
                        result_item = results[0]
                        load_power = result_item.get('load_power')
                        battery_power = result_item.get('battery_power')
                        excel_file = result_item.get('excel_file')
                        config_name = result_item.get('config_name')
                        test_duration = result_item.get('test_duration')
                        should_record = result_item.get('should_record')
                        # 优先使用测试结果文件中的错误消息
                        if result_item.get('error_message'):
                            error_message_final = result_item.get('error_message')
                        elif not error_message_final:
                            error_message_final = error_message  # 如果没有，使用异常中的错误消息
                        module_power_values = result_item.get('module_power_values')
                    else:
                        # 向后兼容：从根级别读取
                        load_power = test_result_data.get('load_power')
                        battery_power = test_result_data.get('battery_power')
                        excel_file = test_result_data.get('excel_file')
                        config_name = test_result_data.get('config_name')
                        test_duration = test_result_data.get('test_duration')
                        should_record = test_result_data.get('should_record')
                        # 优先使用测试结果文件中的错误消息
                        if test_result_data.get('error_message'):
                            error_message_final = test_result_data.get('error_message')
                        elif not error_message_final:
                            error_message_final = error_message  # 如果没有，使用异常中的错误消息
                        module_power_values = test_result_data.get('module_power_values')
                
                setenv_config = test_result_data.get('setenv_config')
                print(f"✓ 从文件读取测试结果数据: {test_result_file}")
                if is_test_all:
                    print(f"  检测到多挡位测试，共 {len(test_result_data.get('results', []))} 个挡位")
            except Exception as e:
                print(f"⚠️ 读取测试结果数据失败: {e}")
                # 如果读取失败，使用异常中的错误消息
                if not error_message_final:
                    error_message_final = error_message
        else:
            # 如果文件不存在，尝试从环境变量读取（向后兼容）
            load_power = os.environ.get('POWER_LOAD')
            battery_power = os.environ.get('POWER_BATTERY')
            excel_file = os.environ.get('POWER_EXCEL_FILE')
            config_name = os.environ.get('POWER_CONFIG_NAME')
            test_duration = os.environ.get('POWER_TEST_DURATION')
            should_record = os.environ.get('POWER_SHOULD_RECORD')
            setenv_config = os.environ.get('POWER_SETENV_CONFIG')
            # 优先使用测试结果文件中的错误消息，如果没有则使用环境变量或异常中的错误消息
            if not error_message_final:
                error_message_final = os.environ.get('POWER_TEST_ERROR_MESSAGE') or error_message
        
        # 如果从文件读取到setenv_config，设置到环境变量供build_custom_message使用
        if setenv_config:
            os.environ['POWER_SETENV_CONFIG'] = setenv_config
        
        # 调试日志：打印读取的值（已移除详细数据打印）
        
        # 获取固件URL（从环境变量或JSON配置）
        firmware_url = os.environ.get('URL') or os.environ.get('BUILD_URL')
        if not firmware_url:
            try:
                json_file = Path(__file__).parent.parent.parent / "data" / device_name / "power_consumption.json"
                if json_file.exists():
                    import json
                    with open(json_file, 'r', encoding='utf-8') as f:
                        json_config = json.load(f)
                        if 'firmware' in json_config and 'download_url' in json_config['firmware']:
                            firmware_url = json_config['firmware']['download_url']
            except Exception as e:
                logger.debug(f"从JSON读取固件URL失败: {e}")
        
        # 多挡位测试时，config_name 应该为 "全部挡位测试" 或 None（让飞书通知自动处理）
        if is_test_all:
            config_name_for_feishu = "全部挡位测试"
            # 多挡位测试时，不传递单个挡位的功耗值，让飞书通知从文件读取多挡位数据
            battery_power = None
            load_power = None
            
            # 检查是否有失败的挡位，如果有则整体测试结果标记为失败
            if test_result_file.exists():
                try:
                    import json
                    with open(test_result_file, 'r', encoding='utf-8') as f:
                        test_result_data = json.load(f)
                        if test_result_data.get('test_all'):
                            results = test_result_data.get('results', [])
                            failed_results = [r for r in results if r.get('error_message')]
                            if failed_results:
                                # 如果有失败的挡位，整体测试结果标记为失败
                                test_result = 1
                                # 收集所有失败挡位的具体错误消息（直接使用错误消息，不添加额外格式）
                                failed_messages = []
                                for r in failed_results:
                                    error_msg_item = r.get('error_message', '')
                                    if error_msg_item:
                                        # 直接使用错误消息（错误消息中通常已包含挡位名称）
                                        failed_messages.append(error_msg_item)
                                if failed_messages:
                                    # 如果有多个失败挡位，用分号分隔；如果只有一个，直接使用
                                    if len(failed_messages) > 1:
                                        error_message_final = "；".join(failed_messages)
                                    else:
                                        error_message_final = failed_messages[0]
                                elif not error_message_final:
                                    # 如果没有错误消息且error_message_final为空，回退到只显示挡位名称
                                    failed_names = [r.get('config_name', '未知') for r in failed_results]
                                    error_message_final = f"部分挡位测试失败: {', '.join(failed_names)}"
                except Exception:
                    pass
        else:
            config_name_for_feishu = config_name
        
        # 注释掉：不再上传测试数据文件夹（如 Z03_V1.3.240_dev_20290203034800-Test04-20260209_152013）
        # # 上传测试数据到飞书云文档（只上传JSON文件，Excel文件已在每个挡位测试完成后上传）
        # upload_result = {"success": False, "folder_url": None}
        # 
        # # 检查测试是否成功（没有错误信息）
        # if not error_message_final:
        #     try:
        #         from src.app.PowerConsumption.PowerConsumption_feishuDriveClient import PowerConsumptionFeishuDriveClient
        #         from src.utils.config_manager import ConfigManager
        #         from src.utils.logger import Logger
        #         
        #         # 创建飞书云文档客户端
        #         config = ConfigManager()
        #         logger = Logger()
        #         drive_client = PowerConsumptionFeishuDriveClient(config, logger, device_name)
        #         
        #         # 使用封装函数上传功耗测试数据（递归查找所有文件）
        #         upload_result = drive_client.upload_power_consumption_data(
        #             unified_folder_name=test_instance.unified_folder_name
        #         )
        #     
        #         # 打印上传结果
        #         if upload_result and upload_result.get('success'):
        #             print("功耗测试数据上传成功")
        #             print(f"上传了 {len(upload_result.get('files_uploaded', []))} 个文件")
        #         else:
        #             print("功耗测试数据上传失败")
        #             if upload_result:
        #                 for error in upload_result.get('errors', []):
        #                     print(f"  - {error}")
        #             else:
        #                 print("  - 上传结果为空")
        #                 
        #     except Exception as e:
        #         print(f"文件上传功能执行失败: {e}")
        #         import traceback
        #         traceback.print_exc()
        # else:
        #     print("测试失败，跳过数据上传到飞书")
        
        # 自动将测试数据复制到汇总Excel文件
        try:
            print("=" * 80)
            print("开始自动复制测试数据到汇总Excel文件...")
            
            # 创建Excel数据处理实例（使用统一文件夹名称）
            excel_processor = PowerConsumptionProcessExcelData(
                config=config,
                logger=logger,
                unified_folder_name=test_instance.unified_folder_name
            )
            
            # 执行数据汇总
            if firmware_url:
                success = excel_processor.summarize_power_data_to_daily_files(firmware_url)
                if success:
                    print("测试数据自动复制到汇总Excel文件成功")
                    
                    # 检查生成的汇总文件
                    date_str = excel_processor._extract_date_from_url(firmware_url)
                    if date_str:
                        date_folder = project_root / "PowerConsumption_Data" / date_str
                        if date_folder.exists():
                            summary_files = list(date_folder.glob("*.xlsx"))
                            if summary_files:
                                print(f"生成的汇总文件:")
                                
                                # 分离总汇总文件和挡位汇总文件
                                consolidated_file = None
                                gear_files = []
                                
                                for summary_file in summary_files:
                                    if 'ALL-GEARS' in summary_file.name:
                                        consolidated_file = summary_file
                                    else:
                                        gear_files.append(summary_file)
                                
                                # 先显示挡位汇总文件
                                if gear_files:
                                    print(f"  挡位汇总文件 ({len(gear_files)} 个):")
                                    for gear_file in sorted(gear_files, key=lambda x: x.name):
                                        print(f"    - {gear_file.name}")
                                
                                # 显示总汇总文件（包含所有挡位）
                                if consolidated_file:
                                    print(f"  总汇总文件（包含所有挡位）:")
                                    print(f"    - {consolidated_file.name}")
                                    
                                    # 尝试显示总汇总文件包含的工作表信息
                                    try:
                                        import win32com.client as win32
                                        excel_app = win32.Dispatch('Excel.Application')
                                        excel_app.Visible = False
                                        excel_app.DisplayAlerts = False
                                        
                                        wb = excel_app.Workbooks.Open(str(consolidated_file.resolve().absolute()))
                                        sheet_count = wb.Worksheets.Count
                                        sheet_names = [ws.Name for ws in wb.Worksheets]
                                        
                                        wb.Close(SaveChanges=False)
                                        excel_app.Quit()
                                        
                                        print(f"      包含 {sheet_count} 个工作表:")
                                        for i, sheet_name in enumerate(sheet_names, 1):
                                            print(f"        {i}. {sheet_name}")
                                    except Exception as e:
                                        # 如果无法读取工作表信息，只显示文件名
                                        print(f"      (无法读取工作表信息: {e})")
                                    
                                    # 保存总汇总文件路径，用于后续上传到飞书
                                    consolidated_file_path = str(consolidated_file)
                                else:
                                    print(f"  注意: 总汇总文件未生成（可能所有挡位数据尚未汇总）")
                                    consolidated_file_path = None
                else:
                    print("测试数据自动复制到汇总Excel文件失败")
            else:
                print("无法获取固件URL，跳过数据复制")
                
            print("=" * 80)
        except Exception as e:
            print(f"自动复制测试数据失败: {e}")
            import traceback
            traceback.print_exc()
        
        # 上传总汇总文件夹（年月文件夹，如 2026-02）到飞书云文档
        summary_folder_result = {"success": False, "folder_url": None}
        try:
            from src.app.PowerConsumption.PowerConsumption_feishuDriveClient import PowerConsumptionFeishuDriveClient
            feishu_drive_client = PowerConsumptionFeishuDriveClient()
            
            if firmware_url:
                print("开始上传总汇总文件夹到飞书云文档...")
                summary_folder_result = feishu_drive_client.sync_summary_folder_to_feishu(firmware_url)
                if summary_folder_result and summary_folder_result.get('success'):
                    print("总汇总文件夹上传成功!")
                    print(f"总汇总文件夹URL: {summary_folder_result.get('folder_url')}")
                else:
                    print("总汇总文件夹上传失败或文件夹不存在")
            else:
                print("固件URL为空，跳过年月文件夹上传")
        except Exception as e:
            print(f"文件夹上传过程中发生错误: {e}")
            import traceback
            traceback.print_exc()
        
        # 发送飞书通知
        feishu_report.send_power_consumption_result(
            report_path=str(report_path),
            test_result=test_result,
            excel_path=excel_file,
            config_name=config_name_for_feishu,
            firmware_url=firmware_url,
            battery_power=battery_power,
            load_power=load_power,
            test_data_url=summary_folder_result.get('folder_url') if summary_folder_result and summary_folder_result.get('folder_url') else None,  # 使用总汇总文件夹URL
            test_duration=test_duration,
            error_message=error_message_final,  # 传递错误信息
            module_power_values=module_power_values,  # 传递模块功耗值
            temperature_start=None,  # 不传递，让build_custom_message从文件读取
            temperature_end=None  # 不传递，让build_custom_message从文件读取
        )
    except Exception as e:
        print(f"发送飞书通知失败: {e}")
        import traceback
        traceback.print_exc()
    
    sys.exit(test_result)
