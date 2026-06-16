#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import time
import sys
import json
from pathlib import Path

# 尝试导入Windows API（用于控制窗口不置顶）
try:
    import win32gui
    import win32con
    WIN32_AVAILABLE = True
except ImportError:
    WIN32_AVAILABLE = False

# 添加项目根目录到Python路径
current_file = Path(__file__).resolve()
project_root = current_file.parent.parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.utils.config_manager import ConfigManager
from src.utils.logger import Logger
from src.core.dev import InsDev
from src.app.PowerConsumption.PowerConsumption_jsonManager import PowerConsumptionJsonManager

try:
    from selenium import webdriver
    from selenium.webdriver.edge.service import Service
    from selenium.webdriver.edge.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False

# ============= 常量定义 =============
# 注意：不再提供默认URL和坐标，必须从参数或JSON配置中提供

# 尝试导入webdriver-manager（自动管理EdgeDriver）
WEBDRIVER_MANAGER_AVAILABLE = False
EdgeDriverManager = None
try:
    from webdriver_manager.microsoft import EdgeChromiumDriverManager
    WEBDRIVER_MANAGER_AVAILABLE = True
except ImportError:
    WEBDRIVER_MANAGER_AVAILABLE = False



class PowerConsumptionOptQEPM:
    """
    功耗测试QEPM自动化操作类
    使用Selenium实现QEPM网页的自动化操作
    """
    
    def __init__(self, dev: InsDev, config: ConfigManager, logger: Logger, qepm_url: str = None, json_file: str = None):
        """
        初始化QEPM自动化操作类
        
        Args:
            dev: 设备对象
            config: 配置管理器
            logger: 日志记录器
            qepm_url: QEPM网页地址，如果为None则从config中读取
            json_file: JSON配置文件路径，如果为None则使用默认路径
        """
        self.dev = dev
        self.config = config
        self.logger = logger
        
        if not SELENIUM_AVAILABLE:
            self.logger.error("Selenium未安装，请运行: pip install selenium")
            raise ImportError("Selenium未安装")
        
        # JSON配置管理器
        dev_name = dev.name if (dev and hasattr(dev, 'name')) else None
        self.json_manager = PowerConsumptionJsonManager(dev_name=dev_name, logger=self.logger)
        
        # 加载QEPM配置（坐标和选项）
        self.qepm_config = self.load_qepm_config(json_file)
        if not self.qepm_config:
            self.qepm_config = {}
        
        # 获取QEPM URL（优先级：参数 > JSON配置，必须提供）
        if qepm_url:
            self.qepm_url = qepm_url
        elif 'url' in self.qepm_config:
            self.qepm_url = self.qepm_config['url']
        else:
            error_msg = "QEPM URL未配置，必须通过参数qepm_url或JSON配置文件中的qepm.url提供"
            self.logger.error(error_msg)
            raise ValueError(error_msg)
        
        # 验证按钮XPath配置（必须从JSON配置中提供）
        if 'button_coordinates' not in self.qepm_config:
            error_msg = "按钮XPath未配置，必须在JSON配置文件中的qepm.button_coordinates中提供（现在使用XPath而不是坐标）"
            self.logger.error(error_msg)
            raise ValueError(error_msg)
        
        button_xpaths = self.qepm_config['button_coordinates']
        required_buttons = ['start_button', 'stop_button', 'live_view_button', 'apply_button']
        missing_buttons = []
        for button in required_buttons:
            if button not in button_xpaths or not button_xpaths[button]:
                missing_buttons.append(button)
        
        if missing_buttons:
            error_msg = f"缺少必需的按钮XPath配置: {', '.join(missing_buttons)}，请在JSON配置文件中提供XPath"
            self.logger.error(error_msg)
            raise ValueError(error_msg)
        
        self.driver = None
    
    def load_qepm_config(self, json_file: str = None) -> dict:
        """
        从JSON文件加载QEPM配置
        
        Args:
            json_file: JSON文件路径，如果为None则使用默认路径 data/{device}/power_consumption.json
        
        Returns:
            dict: QEPM配置字典，如果失败则返回None
        """
        # 直接获取 qepm section
        qepm_config = self.json_manager.get_section('qepm', json_file)
        if not qepm_config:
            self.logger.error("JSON文件中没有qepm配置")
            return None
        
        # 转换字符串键为整数键（用于SPM编号）
        if 'spm_expand_coordinates' in qepm_config:
            qepm_config['spm_expand_coordinates'] = {
                int(k): v for k, v in qepm_config['spm_expand_coordinates'].items()
            }
        
        if 'spm_option_coordinates' in qepm_config:
            qepm_config['spm_option_coordinates'] = {
                int(k): v for k, v in qepm_config['spm_option_coordinates'].items()
            }
        
        self.logger.debug("QEPM配置加载成功")
        return qepm_config
    
    
    def _init_driver(self, headless: bool = False) -> bool:
        """初始化Selenium WebDriver（使用Edge浏览器）"""
        try:
            self.logger.info("初始化Selenium WebDriver (浏览器: Edge)")
            
            # 从JSON配置中获取原始数据存储路径作为下载目录
            raw_data_path = self.json_manager.get_value('data_path.raw_data_path', default='C:\\Users\\Yinshi\\Downloads')
            download_dir = Path(raw_data_path)
            # 确保目录存在，如果不存在则自动创建
            download_dir.mkdir(parents=True, exist_ok=True)
            download_dir_str = str(download_dir)
            self.logger.debug(f"浏览器下载目录设置为: {download_dir_str}")
            
            return self._init_edge_driver(headless, download_dir_str)
                
        except Exception as e:
            self.logger.error(f"WebDriver初始化失败: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return False
    
    def _init_edge_driver(self, headless: bool, download_dir: str) -> bool:
        """初始化Edge WebDriver"""
        try:
            self.logger.debug("初始化Edge WebDriver...")
            
            edge_options = Options()
            if headless:
                edge_options.add_argument('--headless')
            edge_options.add_argument('--no-sandbox')
            edge_options.add_argument('--disable-dev-shm-usage')
            edge_options.add_argument('--disable-gpu')
            edge_options.add_argument('--window-size=1920,1080')
            edge_options.add_argument('--disable-blink-features=AutomationControlled')
            
            # 抑制浏览器内部警告和错误输出
            edge_options.add_argument('--disable-logging')  # 禁用日志记录
            edge_options.add_argument('--log-level=3')  # 只显示严重错误（0=INFO, 1=WARNING, 2=ERROR, 3=FATAL）
            edge_options.add_argument('--disable-extensions')  # 禁用扩展（减少相关错误）
            edge_options.add_argument('--disable-component-extensions-with-background-pages')  # 禁用后台组件扩展
            edge_options.add_argument('--disable-background-networking')  # 禁用后台网络（减少LLM相关错误）
            edge_options.add_argument('--disable-sync')  # 禁用同步功能
            edge_options.add_argument('--disable-default-apps')  # 禁用默认应用
            
            # 禁用某些可能导致警告的功能
            edge_options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
            edge_options.add_experimental_option('useAutomationExtension', False)
            
            prefs = {
                "download.default_directory": download_dir,
                "download.prompt_for_download": False,
                "download.directory_upgrade": True,
                "safebrowsing.enabled": True
            }
            edge_options.add_experimental_option("prefs", prefs)
            
            service = None
            if WEBDRIVER_MANAGER_AVAILABLE:
                try:
                    service = Service(EdgeChromiumDriverManager().install())
                    self.logger.debug("webdriver-manager初始化成功")
                except Exception as e:
                    # webdriver-manager失败时静默处理，Edge浏览器可能已内置EdgeDriver或系统PATH中有
                    # 这不会影响浏览器启动，只是无法自动下载驱动
                    error_msg = str(e)
                    if "Could not reach host" in error_msg or "offline" in error_msg.lower():
                        self.logger.debug("webdriver-manager无法连接网络，将使用系统PATH中的EdgeDriver或Edge内置驱动")
                    else:
                        self.logger.debug(f"webdriver-manager初始化失败: {e}，将使用系统PATH中的EdgeDriver或Edge内置驱动")
            
            self.logger.debug("启动Edge浏览器...")
            # 注意：某些警告（如GPU驱动、QQ浏览器导入器、Edge LLM等）是Edge浏览器内部的错误输出
            # 这些警告通常不影响功能，可以安全忽略：
            # - GetGpuDriverOverlayInfo: GPU驱动信息获取失败（不影响基本功能）
            # - QQBrowser user data path not found: QQ浏览器数据导入器未找到（可选功能）
            # - Edge LLM errors: Edge AI功能相关错误（可选功能）
            # 这些警告无法通过启动参数完全抑制，但不会影响Selenium自动化操作
            self.driver = webdriver.Edge(service=service, options=edge_options) if service else webdriver.Edge(options=edge_options)
            
            # 如果不在headless模式，设置窗口不置顶（允许用户继续操作其他窗口）
            if not headless:
                self._set_window_not_topmost()
            
            self.driver.maximize_window()
            
            self.driver.set_page_load_timeout(30)
            self.driver.implicitly_wait(10)
            
            self.logger.debug("Edge WebDriver初始化成功")
            return True
            
        except Exception as e:
            self.logger.error(f"Edge WebDriver初始化失败: {e}")
            return False
    
    def _set_window_not_topmost(self):
        """
        设置浏览器窗口不置顶，允许用户继续操作其他窗口
        窗口仍然可见，但不会强制置顶
        """
        if not WIN32_AVAILABLE:
            self.logger.debug("win32gui未安装，无法设置窗口不置顶")
            return
        
        try:
            # 获取浏览器窗口句柄
            window_handles = self.driver.window_handles
            if not window_handles:
                return
            
            # 等待窗口完全加载
            time.sleep(0.2)
            
            # 尝试找到Edge窗口
            def find_edge_window(hwnd, windows):
                if win32gui.IsWindowVisible(hwnd):
                    window_text = win32gui.GetWindowText(hwnd)
                    class_name = win32gui.GetClassName(hwnd)
                    # Edge窗口的类名通常是 Chrome_WidgetWin_1 或 Edge_WidgetWin_1
                    if 'Edge' in class_name or 'Chrome_WidgetWin' in class_name:
                        windows.append(hwnd)
                return True
            
            edge_windows = []
            win32gui.EnumWindows(find_edge_window, edge_windows)
            
            if edge_windows:
                # 设置窗口不置顶
                hwnd = edge_windows[0]
                win32gui.SetWindowPos(
                    hwnd,
                    win32con.HWND_NOTOPMOST,  # 不置顶
                    0, 0, 0, 0,
                    win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_SHOWWINDOW
                )
                self.logger.debug("Edge浏览器窗口已设置为不置顶模式")
        except Exception as e:
            self.logger.debug(f"设置窗口不置顶失败（不影响功能）: {e}")
    
    def open_qepm(self, headless: bool = False) -> bool:
        """打开QEPM网页"""
        try:
            if self.driver is None:
                if not self._init_driver(headless):
                    self.logger.error("Edge浏览器初始化失败")
                    return False
            
            self.logger.debug(f"打开QEPM网页: {self.qepm_url}")
            self.driver.get(self.qepm_url)
            
            # 等待页面加载完成
            self.driver.implicitly_wait(5)
            time.sleep(0.5)  # 等待页面渲染
            
            # 等待页面就绪
            try:
                self.driver.execute_script("return document.readyState") == "complete"
            except:
                pass
            
            self.logger.debug("QEPM网页打开成功")
            return True
                
        except Exception as e:
            self.logger.error(f"打开QEPM网页失败: {e}")
            import traceback
            self.logger.debug(traceback.format_exc())
            return False
    
    def _click_by_xpath(self, xpath: str, description: str = "", wait_time: int = 10) -> bool:
        """
        通过XPath定位并点击元素
        
        Args:
            xpath: XPath表达式，如 "//button[@id='start']" 或 "//div[@class='button']"
            description: 元素描述，用于日志
            wait_time: 等待元素出现的超时时间（秒）
        
        Returns:
            bool: 点击是否成功
        """
        if not self.driver:
            self.logger.error("WebDriver未初始化，无法点击")
            return False
        
        if not xpath or not isinstance(xpath, str):
            self.logger.error(f"XPath配置无效: {xpath}")
            return False
        
        try:
            # 检查浏览器会话是否有效
            try:
                self.driver.current_url
            except Exception as session_error:
                self.logger.error(f"浏览器会话已断开: {session_error}")
                return False
            
            # 确保切换到当前窗口
            self.driver.switch_to.window(self.driver.current_window_handle)
            
            # 等待元素出现并可见
            try:
                wait = WebDriverWait(self.driver, wait_time)
                element = wait.until(EC.presence_of_element_located((By.XPATH, xpath)))
                
                # 检查元素类型，checkbox 需要特殊处理
                tag_name = element.tag_name.lower()
                element_type = element.get_attribute('type')
                element_id = element.get_attribute('id')
                is_checkbox = (tag_name == 'input' and element_type == 'checkbox') or (tag_name == 'input' and element_type == 'radio')
                
                if is_checkbox:
                    # 对于 checkbox/radio，直接设置checked属性（最快最可靠）
                    try:
                        # 一次性执行：设置checked并触发所有必要事件，不等待
                        checked = self.driver.execute_script("""
                            var elem = arguments[0];
                            elem.checked = true;
                            var clickEvent = new MouseEvent('click', { bubbles: true, cancelable: true });
                            elem.dispatchEvent(clickEvent);
                            var changeEvent = new Event('change', { bubbles: true });
                            elem.dispatchEvent(changeEvent);
                            var inputEvent = new Event('input', { bubbles: true });
                            elem.dispatchEvent(inputEvent);
                            return elem.checked;
                        """, element)
                        if checked:
                            if description:
                                self.logger.debug(f"✓ 选中 {description}")
                            return True
                        else:
                            # 如果设置失败，尝试直接点击
                            self.driver.execute_script("arguments[0].click();", element)
                            if self.driver.execute_script("return arguments[0].checked;", element):
                                if description:
                                    self.logger.debug(f"✓ 选中 {description} (通过点击)")
                                return True
                    except Exception as e:
                        self.logger.error(f"✗ 选中checkbox失败 {description}: {e}")
                        return False
                else:
                    # 对于非 checkbox 元素，使用普通点击
                    # 确保元素可点击
                    wait_clickable = WebDriverWait(self.driver, 2)
                    wait_clickable.until(EC.element_to_be_clickable((By.XPATH, xpath)))
                    
                    # 使用 JavaScript 的 element.click() 方法（不移动鼠标，不要求页面置顶）
                    self.driver.execute_script("arguments[0].click();", element)
                    
                    if description:
                        self.logger.debug(f"✓ 点击 {description} (XPath: {xpath})")
                    time.sleep(0.05)
                    return True
                
            except Exception as e:
                error_msg = str(e)
                # 提供更详细的错误信息
                if "no such element" in error_msg.lower() or "element not found" in error_msg.lower():
                    self.logger.error(f"✗ 元素未找到: {description} (XPath: {xpath})")
                    # 尝试查找所有匹配的元素用于调试
                    try:
                        all_elements = self.driver.find_elements(By.XPATH, "//*[@id]")
                        self.logger.debug(f"页面中存在的元素ID数量: {len(all_elements)}")
                    except:
                        pass
                elif "invalid session" in error_msg.lower():
                    self.logger.error(f"✗ 浏览器会话已断开: {description}")
                else:
                    self.logger.error(f"✗ 点击失败 {description} (XPath: {xpath}): {e}")
                return False
                
        except Exception as e:
            error_msg = str(e)
            if "invalid session" in error_msg.lower():
                self.logger.error(f"✗ 浏览器会话已断开: {description}")
            else:
                self.logger.error(f"✗ 点击失败 {description}: {e}")
            import traceback
            self.logger.debug(traceback.format_exc())
            return False
    
    
    def click_start(self) -> bool:
        """点击开始测试按钮（使用XPath）"""
        try:
            self.logger.info("点击开始测试按钮")
            
            button_xpaths = self.qepm_config.get('button_coordinates', {})
            start_xpath = button_xpaths.get('start_button')
            
            if not start_xpath:
                self.logger.error("start_button XPath未配置")
                return False
            
            if self._click_by_xpath(start_xpath, "开始测试按钮"):
                time.sleep(0.1)
                return True
            else:
                return False
            
        except KeyError as e:
            self.logger.error(f"缺少按钮XPath配置: {e}")
            return False
        except Exception as e:
            self.logger.error(f"点击开始测试按钮失败: {e}")
            return False
    
    def click_stop(self) -> bool:
        """点击停止测试按钮（使用XPath）"""
        try:
            self.logger.info("点击停止测试按钮")
            
            button_xpaths = self.qepm_config.get('button_coordinates', {})
            stop_xpath = button_xpaths.get('stop_button')
            
            if not stop_xpath:
                self.logger.error("stop_button XPath未配置")
                return False
            
            if self._click_by_xpath(stop_xpath, "停止测试按钮"):
                time.sleep(0.1)
                return True
            else:
                return False
            
        except KeyError as e:
            self.logger.error(f"缺少按钮XPath配置: {e}")
            return False
        except Exception as e:
            self.logger.error(f"点击停止测试按钮失败: {e}")
            return False
    
    def click_live_view(self) -> bool:
        """点击LIVE VIEW按钮（使用XPath）"""
        try:
            self.logger.info("点击LIVE VIEW按钮")
            
            # 确保页面已完全加载
            time.sleep(0.5)
            
            # 检查页面状态
            try:
                ready_state = self.driver.execute_script("return document.readyState")
                self.logger.debug(f"页面状态: {ready_state}")
            except:
                pass
            
            button_xpaths = self.qepm_config.get('button_coordinates', {})
            live_view_xpath = button_xpaths.get('live_view_button')
            
            if not live_view_xpath:
                self.logger.error("live_view_button XPath未配置")
                return False
            
            if self._click_by_xpath(live_view_xpath, "LIVE VIEW按钮"):
                time.sleep(0.2)
                return True
            else:
                self.logger.error("LIVE VIEW按钮点击失败")
                return False
            
        except KeyError as e:
            self.logger.error(f"缺少按钮XPath配置: {e}")
            return False
        except Exception as e:
            self.logger.error(f"点击LIVE VIEW按钮失败: {e}")
            import traceback
            self.logger.debug(traceback.format_exc())
            return False
    
    def configure_live_view(self) -> bool:
        """配置LIVE VIEW窗口：展开SPM1、SPM2、SPM3，选择Current、Power、Voltage，然后点击Apply（使用XPath）"""
        try:
            self.logger.debug("开始配置LIVE VIEW窗口")
            time.sleep(0.2)
            
            # 获取配置（提前获取，避免在循环中重复获取）
            spm_expand_xpaths = self.qepm_config.get('spm_expand_coordinates', {})
            spm_option_xpaths = self.qepm_config.get('spm_option_coordinates', {})
            options_to_select = self.qepm_config.get('options_to_select', ['Current', 'Power', 'Voltage'])
            
            # 对SPM1、SPM2、SPM3分别操作
            for spm_num in [1, 2, 3]:
                spm_name = f"SPM{spm_num}"
                self.logger.debug(f"配置 {spm_name}")
                
                # 点击展开按钮
                if spm_num in spm_expand_xpaths:
                    xpath = spm_expand_xpaths[spm_num]
                    if self._click_by_xpath(xpath, f"{spm_name} 展开按钮"):
                        time.sleep(0.05)
                    else:
                        self.logger.warning(f"{spm_name} 展开按钮点击失败，继续尝试选择选项")
                
                # 选择Current、Power、Voltage
                for option in options_to_select:
                    if spm_num in spm_option_xpaths and option in spm_option_xpaths[spm_num]:
                        xpath = spm_option_xpaths[spm_num][option]
                        self._click_by_xpath(xpath, f"{spm_name} -> {option}")
            
            # 点击Apply按钮
            self.logger.info("点击Apply按钮")
            button_xpaths = self.qepm_config.get('button_coordinates', {})
            apply_xpath = button_xpaths.get('apply_button')
            
            if not apply_xpath:
                self.logger.error("apply_button XPath未配置")
                return False
            
            if not self._click_by_xpath(apply_xpath, "Apply按钮"):
                self.logger.error("无法点击Apply按钮")
                return False
            time.sleep(0.3)
            
            self.logger.debug("LIVE VIEW配置完成")
            return True
            
        except Exception as e:
            self.logger.error(f"配置LIVE VIEW窗口失败: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return False
    
    def download_data(self) -> bool:
        """
        下载Excel源数据（使用XPath）
        操作步骤：
        1. 点击Live View按钮
        2. 点击Download as按钮
        3. 点击Excel CSV按钮
        4. 点击复选框
        5. 点击Download按钮
        
        Returns:
            bool: 下载是否成功
        """
        try:
            self.logger.debug("开始下载Excel源数据")
            time.sleep(0.3)  # 等待页面稳定
            
            # 获取下载XPath配置
            download_xpaths = self.qepm_config.get('download_coordinates', {})
            
            # 步骤1: 点击Live View按钮
            if 'live_view_button' in download_xpaths:
                xpath = download_xpaths['live_view_button']
                if not self._click_by_xpath(xpath, "Live View按钮"):
                    return False
                time.sleep(0.1)
            
            # 步骤2: 点击Download as按钮
            if 'download_as_button' in download_xpaths:
                xpath = download_xpaths['download_as_button']
                if not self._click_by_xpath(xpath, "Download as按钮"):
                    return False
                time.sleep(0.1)
            
            # 步骤3: 点击Excel CSV按钮
            if 'excel_csv_button' in download_xpaths:
                xpath = download_xpaths['excel_csv_button']
                if not self._click_by_xpath(xpath, "Excel CSV按钮"):
                    return False
                time.sleep(0.1)
            
            # 步骤4: 点击复选框
            if 'checkbox' in download_xpaths:
                xpath = download_xpaths['checkbox']
                if not self._click_by_xpath(xpath, "复选框"):
                    return False
                time.sleep(0.2)
            
            # 步骤5: 点击Download按钮
            if 'download_button' in download_xpaths:
                xpath = download_xpaths['download_button']
                if not self._click_by_xpath(xpath, "Download按钮"):
                    return False
                time.sleep(0.5)  # 等待下载开始
            
            self.logger.debug("Excel源数据下载操作完成")
            return True
            
        except Exception as e:
            self.logger.error(f"下载Excel源数据失败: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return False
    
    def close(self):
        """关闭浏览器"""
        try:
            if self.driver:
                self.logger.info("关闭浏览器")
                self.driver.quit()
                self.driver = None
        except Exception as e:
            self.logger.error(f"关闭浏览器时出错: {e}")
    
    def __enter__(self):
        """上下文管理器入口"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口，自动关闭浏览器"""
        self.close()

# 测试代码
def test_qepm_operations():
    """
    测试QEPM自动化操作功能（仅测试点击，不需要设备连接）
    
    测试步骤：
    1. 初始化QEPM类
    2. 打开QEPM网页
    3. 点击LIVE VIEW按钮
    4. 配置LIVE VIEW窗口
    5. 点击开始测试按钮
    6. 等待几秒
    7. 点击停止测试按钮
    8. 下载Excel数据
    9. 关闭浏览器
    """
    print("=" * 80)
    print("开始测试QEPM自动化操作功能（仅测试点击）")
    print("=" * 80)
    
    # 导入必要的模块
    from src.utils.config_manager import ConfigManager
    from src.utils.logger import Logger
    
    # 初始化基础对象
    logger = Logger()
    config = ConfigManager()
    
    # 获取设备名称（用于读取JSON配置）
    device_name = os.environ.get('FW_DEV', 'Z03')
    if device_name == 'Unknow':
        device_name = 'Z03'
    
    # 创建一个简单的mock设备对象（只需要name属性）
    class MockDev:
        def __init__(self, name):
            self.name = name
    
    dev = MockDev(device_name)
    print(f"✓ 使用设备配置: {device_name}（仅用于读取JSON配置）")
    
    # 创建QEPM实例
    try:
        qepm = PowerConsumptionOptQEPM(dev, config, logger)
        print(f"✓ QEPM实例创建成功")
        print(f"  QEPM URL: {qepm.qepm_url}")
        print(f"  按钮XPath配置:")
        button_xpaths = qepm.qepm_config.get('button_coordinates', {})
        for button_name, xpath in button_xpaths.items():
            if xpath:
                print(f"    {button_name}: {xpath}")
    except Exception as e:
        print(f"✗ QEPM实例创建失败: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # 测试步骤1: 打开QEPM网页
    print("\n步骤1: 打开QEPM网页")
    try:
        if qepm.open_qepm(headless=False):
            print("✓ QEPM网页打开成功")
            time.sleep(2)
        else:
            print("✗ QEPM网页打开失败")
            qepm.close()
            return
    except Exception as e:
        print(f"✗ 打开QEPM网页时出错: {e}")
        qepm.close()
        return
    
    # 测试步骤2: 点击LIVE VIEW按钮
    print("\n步骤2: 点击LIVE VIEW按钮")
    try:
        if qepm.click_live_view():
            print("✓ LIVE VIEW按钮点击成功")
            time.sleep(2)
        else:
            print("✗ LIVE VIEW按钮点击失败")
            qepm.close()
            return
    except Exception as e:
        print(f"✗ 点击LIVE VIEW按钮时出错: {e}")
        qepm.close()
        return
    
    # 测试步骤3: 配置LIVE VIEW窗口
    print("\n步骤3: 配置LIVE VIEW窗口")
    try:
        if qepm.configure_live_view():
            print("✓ LIVE VIEW窗口配置成功")
            time.sleep(2)
        else:
            print("✗ LIVE VIEW窗口配置失败")
            qepm.close()
            return
    except Exception as e:
        print(f"✗ 配置LIVE VIEW窗口时出错: {e}")
        qepm.close()
        return
    
    # 测试步骤4: 点击开始测试按钮
    print("\n步骤4: 点击开始测试按钮")
    try:
        if qepm.click_start():
            print("✓ 开始测试按钮点击成功")
            print("  等待5秒...")
            time.sleep(5)
        else:
            print("✗ 开始测试按钮点击失败")
            qepm.close()
            return
    except Exception as e:
        print(f"✗ 点击开始测试按钮时出错: {e}")
        qepm.close()
        return
    
    # 测试步骤5: 点击停止测试按钮
    print("\n步骤5: 点击停止测试按钮")
    try:
        if qepm.click_stop():
            print("✓ 停止测试按钮点击成功")
            time.sleep(2)
        else:
            print("✗ 停止测试按钮点击失败")
            qepm.close()
            return
    except Exception as e:
        print(f"✗ 点击停止测试按钮时出错: {e}")
        qepm.close()
        return
    
    # 测试步骤6: 下载Excel数据（可选，可能会失败如果页面状态不对）
    print("\n步骤6: 下载Excel数据（可选测试）")
    try:
        if qepm.download_data():
            print("✓ Excel数据下载操作成功")
        else:
            print("⚠️ Excel数据下载操作失败（可能是页面状态问题，不影响其他功能）")
    except Exception as e:
        print(f"⚠️ 下载Excel数据时出错（可能是页面状态问题）: {e}")
    
    # 关闭浏览器
    print("\n关闭浏览器")
    try:
        qepm.close()
        print("✓ 浏览器关闭成功")
    except Exception as e:
        print(f"⚠️ 关闭浏览器时出错: {e}")
    
    print("\n" + "=" * 80)
    print("QEPM自动化操作测试完成")
    print("=" * 80)


if __name__ == "__main__":
    # 如果直接运行此文件，执行测试
    test_qepm_operations()
