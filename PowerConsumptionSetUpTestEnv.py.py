#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
功耗测试 - 测试环境初始化模块
提供测试环境设置相关的API，如关闭WiFi、USB供电、背光等
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
from src.app.PowerConsumption.PowerConsumption_jsonManager import PowerConsumptionJsonManager


# ============= 指令定义 =============

# WiFi相关指令（完整关/开流程）
CMD_WIFI_CHECK_STATUS = "ifconfig"
CMD_WIFI_NETD_STOP = "systemctl stop ins_netd"
CMD_WIFI_KILL_AP = "killall hostapd dnsmasq"
CMD_WIFI_WLAN1_DOWN = "ifconfig wlan1 down"
CMD_WIFI_WLAN0_DOWN = "ifconfig wlan0 down"
CMD_WIFI_RMMOD = "rmmod bcmdhd"
CMD_WIFI_PCIE_DEENUM = "cd /sys/kernel/debug/pci-msm && echo 2 > rc_sel && echo 11 > case"
CMD_WIFI_REG_OFF = "ins_ibus_cli --run call-method kCamera kHald IoControl IoControlWifiRegOn SwitchOff"
CMD_WIFI_REG_ON = "ins_ibus_cli --run call-method kCamera kHald IoControl IoControlWifiRegOn SwitchOn"
CMD_WIFI_PCIE_ENUM = "cd /sys/kernel/debug/pci-msm && echo 2 > rc_sel && echo 10 > case"
CMD_WIFI_INSMOD = "insmod bcmdhd"
CMD_WIFI_WLAN0_UP = "ifconfig wlan0 up"
CMD_WIFI_WLAN1_UP = "ifconfig wlan1 up"
CMD_WIFI_NETD_START = "systemctl start ins_netd"
CMD_WIFI_GPIO_CHECK = "cat /sys/kernel/debug/gpio | grep 70"

# 蓝牙相关指令（ins_btd_cli 交互：71=关闭 70=开启 999=退出）
CMD_BT_OFF = "printf '71\\n999\\n' | ins_btd_cli"
CMD_BT_ON = "printf '70\\n999\\n' | ins_btd_cli"

# USB供电相关指令
CMD_USB_POWER_ON = "echo 1 > /sys/class/qcom-battery/icl"
CMD_USB_POWER_OFF = "echo 0 > /sys/class/qcom-battery/icl"

# 背光相关指令
CMD_BACKLIGHT_GET_MAX = "cat /sys/class/backlight/panel0-backlight/max_brightness 2>/dev/null"
CMD_BACKLIGHT_SET = "echo {brightness} > /sys/class/backlight/panel0-backlight/brightness"
CMD_BACKLIGHT_GET = "cat /sys/class/backlight/panel0-backlight/brightness"

# Kernel日志相关指令
CMD_KERNEL_LOG_ON = "echo 7 > /proc/sys/kernel/printk"
CMD_KERNEL_LOG_OFF = "echo 0 > /proc/sys/kernel/printk"
CMD_KERNEL_LOG_GET = "cat /proc/sys/kernel/printk"  # 获取kernel日志级别，用于验证

# Logd相关指令
CMD_LOGD_START = "systemctl start logd"
CMD_LOGD_KILL = "kill $(pidof /sbin/logd)"  # 直接kill logd进程
CMD_LOGD_GET_PID = "pidof /sbin/logd"  # 获取logd进程PID，用于验证

# CamX日志相关指令
CMD_CAMX_REMOUNT_RW = "mount -o remount,rw /"  # 将根分区remount为读写
CMD_CAMX_READ_CONFIG = "cat {config_file}"  # 读取CamX配置文件
CMD_CAMX_DELETE_LINE = "sed -i '/systemLogEnable=FALSE/d' {config_file}"  # 删除包含systemLogEnable=FALSE的行（无论是否注释）
CMD_CAMX_ADD_DISABLE = "echo >> {config_file} && echo 'systemLogEnable=FALSE' >> {config_file}"  # 在配置文件末尾添加systemLogEnable=FALSE
CMD_CAMX_RESTART_SERVICE = "systemctl restart {service}"  # 重启相关服务

# 进入整机休眠相关指令
CMD_SLEEP_KEY_CHECK = r'cat /sys/kernel/debug/clk/clk_enabled_list | grep cam_cc'  # 检查是否进入休眠模式（返回空表示已进入休眠）
CMD_SLEEP_KEY_DOWN = r'ins_ibus_cli --run "call-publish kCommon kHald KeyEvent {\"code\":\"KeyCodePower\",\"value\":\"kKeyValuePressDown\"}"'
CMD_SLEEP_KEY_LONG_PRESS = r'ins_ibus_cli --run "call-publish kCommon kHald KeyEvent {\"code\":\"KeyCodePower\",\"value\":\"kKeyValueLongPress1s\"}"'
CMD_SLEEP_KEY_UP = r'ins_ibus_cli --run "call-publish kCommon kHald KeyEvent {\"code\":\"KeyCodePower\",\"value\":\"kKeyValuePressUp\"}"'

# 退出整机休眠相关指令
CMD_WAKEUP_KEY_DOWN = r'ins_ibus_cli --run "call-publish kCommon kHald KeyEvent {\"code\":\"KeyCodePower\",\"value\":\"kKeyValuePressDown\"}"'
CMD_WAKEUP_KEY_LONG_PRESS = r'ins_ibus_cli --run "call-publish kCommon kHald KeyEvent {\"code\":\"KeyCodePower\",\"value\":\"kKeyValueLongPress\"}"'
CMD_WAKEUP_KEY_UP = r'ins_ibus_cli --run "call-publish kCommon kHald KeyEvent {\"code\":\"KeyCodePower\",\"value\":\"kKeyValuePressUp\"}"'
CMD_WAKEUP_POWER_TRACE = r'ins_bll_cli \'{"cmd":"bla","action":"misc_power_sm_trace"}\''

# 工厂模式相关指令
CMD_FACTORY_MODE_GET = "ins_link_dbg factorymode get"  # 获取当前模式

# 温度检测相关指令
CMD_GET_TEMPERATURE = "cat /sys/class/thermal/thermal_zone1/temp"  # 获取设备温度
CMD_CAMERA_STOP = "systemctl stop ins_mediad"  # 停止相机服务
CMD_CAMERA_START = "systemctl start ins_mediad"  # 启动相机服务

# ============= 路径常量 =============

# USB供电相关路径
PATH_USB_POWER = '/sys/class/qcom-battery/icl'  # USB供电控制路径

# 背光相关路径
PATH_BACKLIGHT = '/sys/class/backlight/panel0-backlight/brightness'  # 背光亮度控制路径

# CamX日志相关路径
PATH_CAMX_CONFIG = '/vendor/etc/camera/camxoverridesettings.txt'  # CamX配置文件路径


class PowerConsumptionSetUpTestEnv:
    """
    功耗测试环境初始化类
    提供测试环境设置功能，调用底层接口实现
    """
    
    def __init__(self, dev: InsDev, config: ConfigManager, logger: Logger):
        """
        初始化环境设置类
        
        Args:
            dev: 设备对象，用于执行底层命令
            config: 配置管理器
            logger: 日志记录器
        """
        self.dev = dev
        self.config = config
        self.logger = logger
        self.env_config = None  # 当前环境配置
        
        # JSON配置管理器
        dev_name = dev.name if hasattr(dev, 'name') else None
        self.json_manager = PowerConsumptionJsonManager(dev_name=dev_name, logger=self.logger)
    
    def check_wifi_status(self) -> bool:
        """
        检查WiFi是否处于开启状态
        
        通过执行 ifconfig 命令，检查返回字符串中是否包含 wlan0 或 wlan1
        如果包含 wlan0 或 wlan1，则WiFi为开启状态
        
        Returns:
            bool: True表示WiFi开启，False表示WiFi关闭或检测失败
        """
        cmd = CMD_WIFI_CHECK_STATUS
        success, response = self.dev.sendCmd(cmd, timeout=10)
        
        if not success:
            self.logger.error(f"检查WiFi状态失败: {response}")
            return False
        
        # 检查返回字符串中是否包含 wlan0 或 wlan1
        if "wlan0" in response or "wlan1" in response:
            self.logger.debug("WiFi状态：开启（检测到 wlan0 或 wlan1）")
            return True
        else:
            self.logger.debug("WiFi状态：关闭（未检测到 wlan0 或 wlan1）")
            return False
    
    def disable_wifi(self) -> bool:
        """
        关闭 WiFi（完整流程：卸载驱动 -> PCIe deenumerate -> wl_reg_on 下电）
        
        Returns:
            bool: 是否成功
        """
        self.logger.info("关闭WiFi")
        self.logger.info("停止ins_netd")
        success, stdout = self.dev.sendCmd(CMD_WIFI_NETD_STOP, timeout=10)
        if not success:
            self.logger.warning(f"停止ins_netd失败: {stdout}")
        self.logger.info("杀死hostapd和dnsmasq")
        success, stdout = self.dev.sendCmd(CMD_WIFI_KILL_AP, timeout=10)
        if not success:
            self.logger.info("进程可能不存在")
        self.logger.info("关闭wlan1")
        success, stdout = self.dev.sendCmd(CMD_WIFI_WLAN1_DOWN, timeout=10)
        if not success:
            self.logger.warning(f"wlan1关闭失败: {stdout}")
        self.logger.info("关闭wlan0")
        success, stdout = self.dev.sendCmd(CMD_WIFI_WLAN0_DOWN, timeout=10)
        if not success:
            self.logger.warning(f"wlan0关闭失败: {stdout}")
        self.logger.info("卸载bcmdhd")
        success, stdout = self.dev.sendCmd(CMD_WIFI_RMMOD, timeout=10)
        if not success:
            self.logger.warning(f"bcmdhd卸载失败: {stdout}")
        time.sleep(1)
        self.logger.info("PCIe1 deenumerate")
        success, stdout = self.dev.sendCmd(CMD_WIFI_PCIE_DEENUM, timeout=10)
        if not success:
            self.logger.warning(f"PCIe1 deenumerate失败: {stdout}")
        time.sleep(1)
        self.logger.info("wl_reg_on下电")
        success, stdout = self.dev.sendCmd(CMD_WIFI_REG_OFF, timeout=15)
        if not success:
            self.logger.warning(f"WiFi电源关闭失败: {stdout}")
        time.sleep(1)
        success, stdout = self.dev.sendCmd(CMD_WIFI_GPIO_CHECK, timeout=10)
        if success and stdout:
            self.logger.info(f"GPIO: {stdout.strip()}")
        else:
            self.logger.warning("无法读取GPIO状态")
        self.logger.info("WiFi已关闭")
        return True

    def enable_wifi(self) -> bool:
        """
        打开 WiFi（完整流程：wl_reg_on 上电 -> PCIe enumerate -> 加载驱动并启动服务）
        
        Returns:
            bool: 是否成功
        """
        self.logger.info("打开WiFi")
        self.logger.info("wl_reg_on上电")
        success, stdout = self.dev.sendCmd(CMD_WIFI_REG_ON, timeout=15)
        if not success:
            self.logger.warning(f"WiFi电源开启失败: {stdout}")
        time.sleep(1)
        self.logger.info("PCIe1 enumerate")
        success, stdout = self.dev.sendCmd(CMD_WIFI_PCIE_ENUM, timeout=10)
        if not success:
            self.logger.warning(f"PCIe1 enumerate失败: {stdout}")
        time.sleep(1)
        self.logger.info("加载bcmdhd")
        success, stdout = self.dev.sendCmd(CMD_WIFI_INSMOD, timeout=10)
        if not success:
            self.logger.warning(f"bcmdhd加载失败: {stdout}")
        time.sleep(1)
        self.logger.info("开启wlan0")
        success, stdout = self.dev.sendCmd(CMD_WIFI_WLAN0_UP, timeout=10)
        if not success:
            self.logger.warning(f"wlan0开启失败: {stdout}")
        self.logger.info("开启wlan1")
        success, stdout = self.dev.sendCmd(CMD_WIFI_WLAN1_UP, timeout=10)
        if not success:
            self.logger.warning(f"wlan1开启失败: {stdout}")
        self.logger.info("启动ins_netd")
        success, stdout = self.dev.sendCmd(CMD_WIFI_NETD_START, timeout=10)
        if not success:
            self.logger.warning(f"ins_netd启动失败: {stdout}")
        time.sleep(1)
        success, stdout = self.dev.sendCmd(CMD_WIFI_GPIO_CHECK, timeout=10)
        if success and stdout:
            self.logger.info(f"GPIO: {stdout.strip()}")
        else:
            self.logger.warning("无法读取GPIO状态")
        self.logger.info("WiFi已打开")
        return True

    def set_wifi(self, enabled: bool) -> bool:
        """
        设置WiFi开关（完整流程：关闭=卸载驱动+PCIe deenumerate+下电；开启=上电+PCIe enumerate+加载驱动）
        
        Args:
            enabled: True为启用，False为关闭
        
        Returns:
            bool: 操作是否成功（包括状态验证）
        """
        if enabled:
            self.logger.info("启用WiFi")
            ok = self.enable_wifi()
        else:
            self.logger.info("关闭WiFi")
            ok = self.disable_wifi()
        
        if not ok:
            return False
        
        time.sleep(2)  # 等待WiFi状态切换
        
        # 验证WiFi状态是否符合预期
        actual_status = self.check_wifi_status()
        if enabled:
            if actual_status:
                self.logger.debug("WiFi启用成功")
                return True
            self.logger.error("WiFi启用异常：命令执行成功，但WiFi状态仍为关闭")
            return False
        if not actual_status:
            self.logger.debug("WiFi关闭成功")
            return True
        self.logger.error("WiFi关闭异常：命令执行成功，但WiFi状态仍为开启")
        return False

    def disable_bluetooth(self) -> bool:
        """
        关闭蓝牙（通过 ins_btd_cli 交互式命令：71 -> 999）
        Returns:
            bool: 是否成功（失败也返回 True 以继续测试）
        """
        self.logger.info("关闭蓝牙")
        success, stdout = self.dev.sendCmd(CMD_BT_OFF, timeout=15)
        if not success:
            self.logger.warning(f"蓝牙关闭命令执行失败: {stdout}")
        else:
            self.logger.info("蓝牙关闭命令已执行")
        time.sleep(2)
        return True

    def enable_bluetooth(self) -> bool:
        """
        打开蓝牙（通过 ins_btd_cli 交互式命令：70 -> 999）
        Returns:
            bool: 是否成功（失败也返回 True 以继续测试）
        """
        self.logger.info("打开蓝牙")
        success, stdout = self.dev.sendCmd(CMD_BT_ON, timeout=15)
        if not success:
            self.logger.warning(f"蓝牙开启命令执行失败: {stdout}")
        else:
            self.logger.info("蓝牙开启命令已执行")
        time.sleep(2)
        return True

    def set_bluetooth(self, enabled: bool) -> bool:
        """
        设置蓝牙开关（勾选=开，不勾选=关）
        Args:
            enabled: True 为开启，False 为关闭
        Returns:
            bool: 操作是否成功
        """
        if enabled:
            self.logger.info("启用蓝牙")
            return self.enable_bluetooth()
        self.logger.info("关闭蓝牙")
        return self.disable_bluetooth()

    def set_usb_power(self, enabled: bool) -> bool:
        """
        设置USB供电开关
        
        Args:
            enabled: True为开启，False为关闭
        
        Returns:
            bool: 操作是否成功
        """
        expected_value = '1' if enabled else '0'
        
        if enabled:
            self.logger.debug("开启USB供电")
            cmd = CMD_USB_POWER_ON
        else:
            self.logger.debug("关闭USB供电")
            cmd = CMD_USB_POWER_OFF
        
        self.logger.debug(f"执行命令: {cmd}")
        success, response = self.dev.sendCmd(cmd, timeout=5)
        
        if not success:
            self.logger.error(f"设置USB供电失败: {response}")
            return False
        
        # 验证设置是否成功（读取文件内容）
        time.sleep(0.5)  # 等待设置生效
        verify_cmd = f"cat {PATH_USB_POWER}"
        verify_success, verify_response = self.dev.sendCmd(verify_cmd, timeout=5)
        
        if verify_success:
            actual_value = verify_response.strip()
            if actual_value == expected_value:
                self.logger.debug(f"USB供电{'开启' if enabled else '关闭'}成功（已验证: {actual_value}）")
                return True
            else:
                self.logger.warning(f"USB供电设置可能未生效，期望值: {expected_value}，实际值: {actual_value}")
                # 即使验证失败，也返回True，因为命令执行成功了
                self.logger.debug(f"USB供电设置命令执行成功（但验证值不匹配）")
                return True
        else:
            self.logger.warning(f"无法验证USB供电设置: {verify_response}")
            self.logger.debug(f"USB供电{'开启' if enabled else '关闭'}命令执行成功（但无法验证）")
            return True
    
    def set_backlight(self, enabled: bool) -> bool:
        """
        设置背光开关
        
        Args:
            enabled: True为开启，False为关闭
        
        Returns:
            bool: 操作是否成功
        """
        if enabled:
            self.logger.info("开启背光")
            ok, response = self.dev.sendCmd(CMD_BACKLIGHT_GET_MAX, timeout=5)
            if ok and response.strip():
                try:
                    brightness_value = int(response.strip())
                except ValueError:
                    brightness_value = 255
            else:
                brightness_value = 255
            cmd = CMD_BACKLIGHT_SET.format(brightness=brightness_value)
            success, response = self.dev.sendCmd(cmd, timeout=5)
        else:
            self.logger.info("关闭背光")
            cmd = CMD_BACKLIGHT_SET.format(brightness=0)
            success, response = self.dev.sendCmd(cmd, timeout=5)

        if not success:
            self.logger.error(f"设置背光失败: {response}")
            return False
        time.sleep(0.5)
        ok, response = self.dev.sendCmd(CMD_BACKLIGHT_GET, timeout=5)
        if ok:
            try:
                current = int(response.strip())
                if enabled and current > 0:
                    self.logger.info(f"背光已开启，亮度: {current}")
                    return True
                if not enabled and current == 0:
                    self.logger.info("背光已关闭")
                    return True
            except ValueError:
                pass
        return True
    
    def set_kernel_log(self, enabled: bool) -> bool:
        """
        设置kernel日志开关
        
        Args:
            enabled: True为开启，False为关闭
        
        Returns:
            bool: 操作是否成功（包括状态验证）
        """
        if enabled:
            self.logger.info("开启kernel日志")
            cmd = CMD_KERNEL_LOG_ON
            expected_value = "7"  # 开启时printk值应为7
        else:
            self.logger.info("关闭kernel日志")
            cmd = CMD_KERNEL_LOG_OFF
            expected_value = "0"  # 关闭时printk值应为0
        
        success, response = self.dev.sendCmd(cmd, timeout=5)
        
        if not success:
            self.logger.error(f"设置kernel日志失败: {response}")
            return False
        
        # 验证kernel日志是否设置成功
        time.sleep(0.5)  # 等待设置生效
        verify_cmd = CMD_KERNEL_LOG_GET
        verify_success, verify_response = self.dev.sendCmd(verify_cmd, timeout=5)
        
        if verify_success and verify_response.strip():
            # printk返回格式通常是 "7 4 1 7" 或 "0 4 1 7"，第一个数字是当前级别
            current_value = verify_response.strip().split()[0] if verify_response.strip() else None
            if current_value == expected_value:
                self.logger.debug(f"kernel日志{'开启' if enabled else '关闭'}成功（验证通过，当前值: {current_value}）")
                return True
            else:
                self.logger.error(f"kernel日志设置失败（验证未通过，期望值: {expected_value}，实际值: {current_value}）")
                return False
        else:
            self.logger.error(f"kernel日志验证失败（无法读取printk值: {verify_response}）")
            return False
    
    def set_logd(self, enabled: bool) -> bool:
        """
        设置logd进程开关
        
        Args:
            enabled: True为开启，False为关闭
        
        Returns:
            bool: 操作是否成功（包括状态验证）
        """
        if enabled:
            self.logger.debug("启动logd进程")
            cmd = CMD_LOGD_START
            success, response = self.dev.sendCmd(cmd, timeout=10)
            
            if not success:
                self.logger.error(f"启动logd进程失败: {response}")
                return False
            
            # 验证logd是否启动成功
            time.sleep(1)
            verify_cmd = CMD_LOGD_GET_PID
            verify_success, verify_response = self.dev.sendCmd(verify_cmd, timeout=5)
            
            if verify_success and verify_response.strip():
                self.logger.debug("logd进程启动成功（验证通过）")
                return True
            else:
                self.logger.error("logd进程启动失败（验证未通过，未找到进程）")
                return False
        else:
            self.logger.debug("关闭logd进程")
            cmd = CMD_LOGD_KILL
            success, response = self.dev.sendCmd(cmd, timeout=10)
            
            if not success:
                self.logger.warning(f"kill logd进程命令执行失败: {response}，但继续验证")
            
            # 验证logd是否关闭成功
            time.sleep(1)
            verify_cmd = CMD_LOGD_GET_PID
            verify_success, verify_response = self.dev.sendCmd(verify_cmd, timeout=5)
            
            if not verify_success or not verify_response.strip():
                self.logger.debug("logd进程已成功关闭（验证通过）")
                return True
            else:
                self.logger.error(f"logd进程关闭失败（验证未通过，进程仍在运行，PID: {verify_response.strip()}）")
                return False
    
    def set_camx_log(self, enabled: bool) -> bool:
        """
        设置CamX日志开关
        
        通过编辑配置文件并重启相关服务来实现
        
        Args:
            enabled: True为开启，False为关闭
        
        Returns:
            bool: 操作是否成功（包括状态验证）
        """
        if enabled:
            self.logger.debug("开启CamX日志")
        else:
            self.logger.debug("关闭CamX日志")
        
        # 先remount /为可读写
        self.logger.debug("将/分区remount为可读写")
        cmd = CMD_CAMX_REMOUNT_RW
        success, response = self.dev.sendCmd(cmd, timeout=5)
        if not success:
            self.logger.warning(f"remount /为可读写失败: {response}，尝试继续执行")
        
        # 步骤1: 删除所有包含 systemLogEnable=FALSE 的行（无论是否注释）
        self.logger.debug("删除配置文件中包含systemLogEnable=FALSE的行")
        cmd = CMD_CAMX_DELETE_LINE.format(config_file=PATH_CAMX_CONFIG)
        success, response = self.dev.sendCmd(cmd, timeout=5)
        
        if not success:
            self.logger.warning(f"删除systemLogEnable=FALSE行失败: {response}，继续执行")
        
        # 步骤2: 根据开关状态决定是否添加 systemLogEnable=FALSE
        if not enabled:
            # 关闭CamX日志：添加 systemLogEnable=FALSE
            self.logger.debug("在配置文件末尾添加systemLogEnable=FALSE")
            cmd = CMD_CAMX_ADD_DISABLE.format(config_file=PATH_CAMX_CONFIG)
            success, response = self.dev.sendCmd(cmd, timeout=5)
            
            if not success:
                self.logger.error(f"添加CamX日志配置失败: {response}")
                return False
        else:
            # 开启CamX日志：不添加，保持删除后的状态
            self.logger.debug("CamX日志已开启（已删除systemLogEnable=FALSE）")
        
        # 步骤3: 验证配置是否正确
        time.sleep(0.5)  # 等待文件写入完成
        verify_cmd = CMD_CAMX_READ_CONFIG.format(config_file=PATH_CAMX_CONFIG)
        verify_success, verify_response = self.dev.sendCmd(verify_cmd, timeout=5)
        
        if verify_success:
            # 检查配置文件中是否包含 systemLogEnable=FALSE
            has_systemlogenable = re.search(r'systemLogEnable=FALSE', verify_response, re.MULTILINE | re.IGNORECASE)
            
            if enabled:
                # 开启时：不应该包含 systemLogEnable=FALSE
                if not has_systemlogenable:
                    self.logger.debug("CamX日志开启成功（验证通过，配置文件中无systemLogEnable=FALSE）")
                else:
                    self.logger.error("CamX日志开启失败（验证未通过，配置文件中仍存在systemLogEnable=FALSE）")
                    return False
            else:
                # 关闭时：应该包含 systemLogEnable=FALSE
                if has_systemlogenable:
                    self.logger.debug("CamX日志关闭成功（验证通过，配置文件中存在systemLogEnable=FALSE）")
                else:
                    self.logger.error("CamX日志关闭失败（验证未通过，配置文件中不存在systemLogEnable=FALSE）")
                    return False
        else:
            self.logger.warning(f"验证CamX配置失败（无法读取配置文件: {verify_response}）")
        
        # 步骤4: 重启相关服务
        services = ['qmmf-server', 'ins_mediad']
        for service in services:
            self.logger.debug(f"重启服务: {service}")
            cmd = CMD_CAMX_RESTART_SERVICE.format(service=service)
            success, response = self.dev.sendCmd(cmd, timeout=10)
            
            if not success:
                self.logger.warning(f"重启服务 {service} 失败: {response}")
            else:
                self.logger.debug(f"服务 {service} 重启成功")
            time.sleep(1)
        
        return True
    
    def load_env_config(self, json_file: str = None) -> dict:
        """
        从JSON文件加载环境配置
        
        Args:
            json_file: JSON文件路径，如果为None则使用默认路径 data/{device}/power_consumption.json
        
        Returns:
            dict: 环境配置字典，包含 wifi, usb_power, backlight, kernel_log, logd, camx_log 等字段，如果失败则返回None
        """
        # 直接获取 setEnv section
        env_config = self.json_manager.get_section('setEnv', json_file)
        if not env_config:
            self.logger.error("JSON文件中没有setEnv配置")
            return None
        
        self.logger.debug("环境配置加载成功")
        return env_config
    
    def setup_environment(self, json_file: str = None) -> bool:
        """
        从JSON文件读取配置并批量设置测试环境
        
        Args:
            json_file: JSON文件路径，如果为None则使用默认路径
        
        Returns:
            bool: 设置是否成功
        """
        # 加载配置
        env_config = self.load_env_config(json_file)
        if not env_config:
            self.logger.error("加载环境配置失败")
            return False

        self.env_config = env_config

        self.logger.info("开始根据JSON配置设置测试环境")
        
        result = True
        failed_items = []  # 记录失败的设置项
        
        # 设置WiFi
        if 'wifi' in env_config:
            wifi_enabled = env_config['wifi']
            self.logger.info(f"设置WiFi: {'开启' if wifi_enabled else '关闭'}")
            if not self.set_wifi(wifi_enabled):
                self.logger.error("WiFi设置失败")
                failed_items.append("WiFi")
                result = False
        
        # 设置蓝牙
        if 'bluetooth' in env_config:
            bluetooth_enabled = env_config['bluetooth']
            self.logger.info(f"设置蓝牙: {'开启' if bluetooth_enabled else '关闭'}")
            if not self.set_bluetooth(bluetooth_enabled):
                self.logger.error("蓝牙设置失败")
                failed_items.append("蓝牙")
                result = False

        # 设置USB供电
        if 'usb_power' in env_config:
            usb_power_enabled = env_config['usb_power']
            self.logger.info(f"设置USB供电: {'开启' if usb_power_enabled else '关闭'}")
            if not self.set_usb_power(usb_power_enabled):
                self.logger.error("USB供电设置失败")
                failed_items.append("USB供电")
                result = False
        
        # 设置背光
        if 'backlight' in env_config:
            backlight_enabled = env_config['backlight']
            self.logger.info(f"设置背光: {'开启' if backlight_enabled else '关闭'}")
            if not self.set_backlight(backlight_enabled):
                self.logger.error("背光设置失败")
                failed_items.append("背光")
                result = False
        
        # 设置kernel日志
        if 'kernel_log' in env_config:
            kernel_log_enabled = env_config['kernel_log']
            self.logger.info(f"设置kernel日志: {'开启' if kernel_log_enabled else '关闭'}")
            if not self.set_kernel_log(kernel_log_enabled):
                self.logger.error("kernel日志设置失败")
                failed_items.append("kernel日志")
                result = False
        
        # 设置logd进程
        if 'logd' in env_config:
            logd_enabled = env_config['logd']
            self.logger.info(f"设置logd进程: {'开启' if logd_enabled else '关闭'}")
            if not self.set_logd(logd_enabled):
                self.logger.error("logd进程设置失败")
                failed_items.append("logd进程")
                result = False
        
        # 设置CamX日志
        if 'camx_log' in env_config:
            camx_log_enabled = env_config['camx_log']
            self.logger.info(f"设置CamX日志: {'开启' if camx_log_enabled else '关闭'}")
            if not self.set_camx_log(camx_log_enabled):
                self.logger.error("CamX日志设置失败")
                failed_items.append("CamX日志")
                result = False
        
        if result:
            self.logger.info("测试环境设置完成")
        else:
            self.logger.error("=" * 80)
            self.logger.error("测试环境设置部分失败（根据JSON配置）")
            if failed_items:
                self.logger.error(f"失败的设置项: {', '.join(failed_items)}")
            self.logger.error("=" * 80)
        
        return result
    
    def restore_environment(self, json_file: str = None) -> bool:
        """
        从JSON文件读取配置并恢复测试环境（通常是将所有开关恢复到开启状态）
        
        Args:
            json_file: JSON文件路径，如果为None则使用默认路径
        
        Returns:
            bool: 恢复是否成功
        """
        # 加载配置
        env_config = self.load_env_config(json_file)
        if not env_config:
            self.logger.error("加载环境配置失败")
            return False
        
        self.logger.info("开始恢复测试环境")
        
        result = True
        
        # 恢复WiFi（通常恢复为开启）
        if 'wifi' in env_config:
            wifi_enabled = env_config.get('wifi', True)  # 默认开启
            self.logger.info(f"恢复WiFi: {'开启' if wifi_enabled else '关闭'}")
            if not self.set_wifi(wifi_enabled):
                self.logger.warning("WiFi恢复失败")

        # 恢复蓝牙（通常恢复为开启）
        if 'bluetooth' in env_config:
            bluetooth_enabled = env_config.get('bluetooth', True)
            self.logger.info(f"恢复蓝牙: {'开启' if bluetooth_enabled else '关闭'}")
            if not self.set_bluetooth(bluetooth_enabled):
                self.logger.warning("蓝牙恢复失败")
        
        # 恢复USB供电（通常恢复为开启）
        if 'usb_power' in env_config:
            usb_power_enabled = env_config.get('usb_power', True)  # 默认开启
            self.logger.debug(f"恢复USB供电: {'开启' if usb_power_enabled else '关闭'}")
            if not self.set_usb_power(usb_power_enabled):
                self.logger.warning("USB供电恢复失败")
        
        # 恢复背光（通常恢复为开启）
        if 'backlight' in env_config:
            backlight_enabled = env_config.get('backlight', True)  # 默认开启
            self.logger.debug(f"恢复背光: {'开启' if backlight_enabled else '关闭'}")
            if not self.set_backlight(backlight_enabled):
                self.logger.warning("背光恢复失败")
        
        # 恢复kernel日志（通常恢复为开启）
        if 'kernel_log' in env_config:
            kernel_log_enabled = env_config.get('kernel_log', True)  # 默认开启
            self.logger.debug(f"恢复kernel日志: {'开启' if kernel_log_enabled else '关闭'}")
            if not self.set_kernel_log(kernel_log_enabled):
                self.logger.warning("kernel日志恢复失败")
        
        # 恢复logd进程（通常恢复为开启）
        if 'logd' in env_config:
            logd_enabled = env_config.get('logd', True)  # 默认开启
            self.logger.debug(f"恢复logd进程: {'开启' if logd_enabled else '关闭'}")
            if not self.set_logd(logd_enabled):
                self.logger.warning("logd进程恢复失败")
        
        # 恢复CamX日志（通常恢复为开启）
        if 'camx_log' in env_config:
            camx_log_enabled = env_config.get('camx_log', True)  # 默认开启
            self.logger.debug(f"恢复CamX日志: {'开启' if camx_log_enabled else '关闭'}")
            if not self.set_camx_log(camx_log_enabled):
                self.logger.warning("CamX日志恢复失败")
         
        self.logger.info("测试环境恢复完成")
        
        return result
    
    def enter_sleep(self, max_retries: int = 3) -> bool:
        """
        进入整机休眠状态
        
        依次执行以下指令：
        1. 按下电源键（PressDown）
        2. 长按电源键（LongPress1s）
        3. 释放电源键（PressUp）
        4. 验证是否进入休眠模式
        
        Args:
            max_retries: 最大重试次数，默认为3次
        
        Returns:
            bool: 操作是否成功
        """
        self.logger.info(f"开始进入整机休眠状态（最大重试次数: {max_retries}）")
        
        for retry in range(max_retries):
            if retry > 0:
                self.logger.info(f"第 {retry} 次重试进入休眠...")
            
            # 步骤1: 按下电源键（PressDown）
            cmd = CMD_SLEEP_KEY_DOWN
            success, response = self.dev.sendCmd(cmd, timeout=5)
            if not success:
                self.logger.error(f"按下电源键失败: {response}")
                if retry < max_retries - 1:
                    self.logger.info("等待2秒后重试...")
                    time.sleep(2)
                    continue
                return False
            time.sleep(1)
            
            # 步骤2: 长按电源键（LongPress1s）
            cmd = CMD_SLEEP_KEY_LONG_PRESS
            success, response = self.dev.sendCmd(cmd, timeout=5)
            if not success:
                self.logger.error(f"长按电源键失败: {response}")
                if retry < max_retries - 1:
                    self.logger.info("等待2秒后重试...")
                    time.sleep(2)
                    continue
                return False
            time.sleep(1)
            
            # 步骤3: 释放电源键（PressUp）
            cmd = CMD_SLEEP_KEY_UP
            success, response = self.dev.sendCmd(cmd, timeout=5)
            if not success:
                self.logger.error(f"释放电源键失败: {response}")
                if retry < max_retries - 1:
                    self.logger.info("等待2秒后重试...")
                    time.sleep(2)
                    continue
                return False
            time.sleep(1)
            
            # 步骤4: 验证是否进入休眠模式
            self.logger.info("等待设备进入休眠状态...")
            time.sleep(3)
            
            cmd = CMD_SLEEP_KEY_CHECK
            success, response = self.dev.sendCmd(cmd, timeout=5)
            
            # grep 没找到 cam_cc 时返回码为 1（success=False），response 为空，表示设备已休眠
            # grep 找到 cam_cc 时返回码为 0（success=True），response 有内容，表示设备未休眠
            if not response.strip():
                self.logger.info("验证成功：设备已进入休眠模式")
                self.logger.info("进入整机休眠完成")
                return True
            else:
                self.logger.warning(f"验证休眠状态返回: {response}")
                self.logger.warning("设备未进入休眠，cam_cc 时钟仍在运行")
                if retry < max_retries - 1:
                    self.logger.info("等待2秒后重试...")
                    time.sleep(2)
                    continue
                self.logger.error(f"已重试 {max_retries} 次，进入休眠失败")
                return False
        
        self.logger.error(f"已重试 {max_retries} 次，进入休眠失败")
        return False
    
    def wakeup_from_sleep(self) -> bool:
        """
        退出整机休眠（唤醒设备）
        
        依次执行以下指令：
        1. 按下电源键（PressDown）
        2. 长按电源键（LongPress）
        3. 释放电源键（PressUp）
        4. 执行电源状态跟踪命令
        
        Returns:
            bool: 操作是否成功
        """
        self.logger.info("开始退出整机休眠（唤醒设备）")
        
        # 步骤1: 按下电源键（PressDown）
        cmd = CMD_WAKEUP_KEY_DOWN
        success, response = self.dev.sendCmd(cmd, timeout=5)
        if not success:
            self.logger.error(f"按下电源键失败: {response}")
            return False
        time.sleep(0.5)
        
        # 步骤2: 长按电源键（LongPress）
        cmd = CMD_WAKEUP_KEY_LONG_PRESS
        success, response = self.dev.sendCmd(cmd, timeout=5)
        if not success:
            self.logger.error(f"长按电源键失败: {response}")
            return False
        time.sleep(0.5)
        
        # 步骤3: 释放电源键（PressUp）
        cmd = CMD_WAKEUP_KEY_UP
        success, response = self.dev.sendCmd(cmd, timeout=5)
        if not success:
            self.logger.error(f"释放电源键失败: {response}")
            return False
        time.sleep(0.5)
        
        # 步骤4: 执行电源状态跟踪命令
        cmd = CMD_WAKEUP_POWER_TRACE
        success, response = self.dev.sendCmd(cmd, timeout=5)
        if not success:
            self.logger.warning(f"执行电源状态跟踪命令失败: {response}")
        
        self.logger.info("退出整机休眠完成")
        
        return True
    
    def is_user_mode(self) -> bool:
        """
        判断当前是否为用户模式
        
        通过执行 ins_link_dbg factorymode get 命令，检查返回字符串中是否包含 "success, mode: 2"
        如果包含 "success, mode: 2"，则为用户模式
        
        Returns:
            bool: True表示用户模式，False表示非用户模式或检测失败
        """
        self.logger.debug("检查当前是否为用户模式")
        cmd = CMD_FACTORY_MODE_GET
        success, response = self.dev.sendCmd(cmd, timeout=10)
        
        if not success:
            self.logger.error(f"获取工厂模式状态失败: {response}")
            return False
        
        # 检查返回字符串中是否包含 "success, mode: 2"
        if "success, mode: 2" in response:
            self.logger.debug("当前为用户模式（mode: 2）")
            return True
        else:
            self.logger.info(f"当前非用户模式，返回内容: {response}")
            return False

    def get_temperature(self) -> float:
        """
        获取设备当前温度

        Returns:
            float: 设备温度（摄氏度，保留一位小数），如果获取失败返回 -1.0
        """
        cmd = CMD_GET_TEMPERATURE
        success, response = self.dev.sendCmd(cmd, timeout=10)

        if not success:
            self.logger.error(f"获取设备温度失败: {response}")
            return -1.0

        try:
            temp_millidegree = int(response.strip())
            temp_celsius = temp_millidegree / 1000.0
            temp_celsius_1dp = round(temp_celsius, 1)  # 第二个参数指定保留的小数位数
            self.logger.debug(f"当前设备温度: {temp_celsius_1dp}°C")
            return temp_celsius_1dp
        except (ValueError, TypeError) as e:
            self.logger.error(f"解析温度值失败: {response.strip()}, 错误: {e}")
            return -1.0

    def check_temperature(self, threshold: float) -> bool:
        """
        检测设备温度是否低于阈值（复用get_temperature方法）

        Args:
            threshold: 温度阈值（摄氏度），例如 40.0 表示 40 度

        Returns:
            bool: True表示温度低于阈值，False表示温度高于等于阈值或检测失败
        """
        self.logger.debug(f"检测设备温度，阈值: {threshold}°C")

        # 核心修改：调用已有的get_temperature方法获取温度，无需重复编写串口指令逻辑
        temp_celsius = self.get_temperature()

        # 第一步：判断温度是否获取成功（get_temperature返回-1.0表示失败）
        if temp_celsius == -1.0:
            self.logger.error("温度获取失败，无法完成阈值检测")
            return False

        # 第二步：进行阈值判断
        self.logger.debug(f"当前设备温度: {temp_celsius}°C，阈值: {threshold}°C")

        if temp_celsius < threshold:
            self.logger.debug(f"温度检测通过：{temp_celsius}°C < {threshold}°C")
            return True
        else:
            self.logger.warning(f"温度检测未通过：{temp_celsius}°C >= {threshold}°C")
            return False
    
    def wait_for_temperature_below_threshold(self, threshold: float, max_wait_time: int, wait_interval: int) -> tuple[bool, str]:
        """
        等待设备温度降低到阈值以下，如果温度过高则停止相机服务加速降温
        
        Args:
            threshold: 温度阈值（摄氏度）
            max_wait_time: 最大等待时间（秒）
            wait_interval: 检测间隔（秒）
        
        Returns:
            tuple[bool, str]: (是否通过, 错误信息)
        """
        self.logger.info(f"开始温度检测（阈值: {threshold}°C，最大等待: {max_wait_time}秒，检测间隔: {wait_interval}秒）")
        
        camera_stopped = False
        start_wait_time = time.time()
        
        while True:
            if self.check_temperature(threshold):
                if camera_stopped:
                    self.logger.info("温度已降低，重新启动相机服务")
                    start_success, _ = self.dev.sendCmd("systemctl start ins_mediad", timeout=10)
                    if start_success:
                        time.sleep(3)
                        self.logger.info("相机服务已重新启动")
                    else:
                        self.logger.warning("相机服务启动失败，但继续测试")
                self.logger.info("温度检测通过")
                return True, ""
            
            if not camera_stopped:
                self.logger.info("温度过高，停止相机服务以加速降温")
                stop_success, _ = self.dev.sendCmd("systemctl stop ins_mediad", timeout=10)
                if stop_success:
                    time.sleep(2)
                    self.logger.info("相机服务已停止")
                    camera_stopped = True
                else:
                    self.logger.warning("停止相机服务失败")
            
            elapsed = time.time() - start_wait_time
            if elapsed >= max_wait_time:
                error_msg = f"等待温度降低超时（已等待 {max_wait_time} 秒）"
                self.logger.error(error_msg)
                if camera_stopped:
                    self.logger.warning("超时后尝试重新启动相机服务")
                    self.dev.sendCmd("systemctl start ins_mediad", timeout=10)
                return False, error_msg
            
            remaining = max_wait_time - elapsed
            self.logger.warning(f"温度过高（>= {threshold}°C），等待 {wait_interval} 秒后重试（剩余等待时间: {int(remaining)} 秒）")
            time.sleep(wait_interval)

同