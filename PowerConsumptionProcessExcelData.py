#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
功耗测试 - Excel数据处理模块
处理从QEPM下载的CSV数据文件，并将数据导入Excel模板
改进版：修复复制问题，确保多次复制数据间隔一列不覆盖
"""
import os
import shutil
import sys
import csv
import re
import time
from pathlib import Path
from datetime import datetime

# 添加项目根目录到sys.path，确保模块导入正确
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from src.utils.logger import Logger
from src.utils.config_manager import ConfigManager
from src.app.PowerConsumption.PowerConsumption_jsonManager import PowerConsumptionJsonManager

# 尝试导入openpyxl（用于操作Excel文件）
try:
    from openpyxl import load_workbook
    from openpyxl.utils import get_column_letter
    OPENPYXL_AVAILABLE = True
except ImportError:
    OPENPYXL_AVAILABLE = False

# 尝试导入win32com（用于Excel操作）
try:
    import win32com.client as win32
    WIN32COM_AVAILABLE = True
except ImportError:
    WIN32COM_AVAILABLE = False


class PowerConsumptionProcessExcelData:
    """
    功耗测试Excel数据处理类
    用于处理从QEPM下载的CSV数据文件
    """
    
    def __init__(self, config: ConfigManager = None, logger: Logger = None, unified_folder_name: str = None):
        """
        初始化Excel数据处理类
        """
        self.config = config or ConfigManager()
        self.logger = logger or Logger()

        # 项目根目录
        self.project_root = Path(__file__).parent.parent.parent.parent

        # 获取固件名称（设备类型）
        self.firmware_name = os.environ.get('FW_DEV', 'Z03')

        # JSON配置管理器
        self.json_manager = PowerConsumptionJsonManager(dev_name=self.firmware_name, logger=self.logger)

        # 从JSON配置中获取固件版本目录
        firmware_url = self.json_manager.get_value('firmware.download_url')
        self.firmware_version_dir = self._extract_firmware_version_from_url(firmware_url)

        # 数据存储目录：使用统一文件夹名称或固件版本目录
        self.unified_folder_name = unified_folder_name
        if unified_folder_name:
            self.data_dir = self.project_root / "PowerConsumption_Data" / unified_folder_name
            self.logger.info(f"使用统一文件夹: {unified_folder_name}")
        else:
            self.data_dir = self.project_root / "PowerConsumption_Data" / self.firmware_version_dir
            self.logger.info(f"使用固件版本目录: {self.firmware_version_dir}")

        # Excel模板文件路径
        self.template_file = self.project_root / "PowerConsumption_Data" / "Z03-Template.xlsx"
        
        # 从JSON配置中获取原始数据存储路径
        raw_data_path = self.json_manager.get_value('data_path.raw_data_path', default='C:\\Users\\Yinshi\\Downloads')
        self.raw_data_path = Path(raw_data_path)
        # 确保目录存在，如果不存在则自动创建
        self.raw_data_path.mkdir(parents=True, exist_ok=True)
        self.logger.debug(f"原始数据存储路径: {self.raw_data_path}")
        
        # 关键：初始化目标文件列缓存（存储每个目标文件下一次查找的起始列）
        self._target_file_col_cache = {}  # 格式：{target_file_path: next_search_col}
        
        if not OPENPYXL_AVAILABLE:
            self.logger.warning("openpyxl未安装，Excel操作功能将不可用")
            self.logger.warning("请运行: pip install openpyxl")
        
        if not WIN32COM_AVAILABLE:
            self.logger.warning("win32com未安装，Excel高级操作功能将不可用")
            self.logger.warning("请运行: pip install pywin32")

    def _extract_firmware_version_from_url(self, url: str) -> str:
        """
        从固件下载URL中提取版本号作为目录名
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
    
    def get_next_test_run_number(self, firmware_version: str) -> int:
        """获取下一个测试次数"""
        import re
        
        # 使用PowerConsumption_Data根目录，而不是具体的测试文件夹
        power_data_dir = self.project_root / "PowerConsumption_Data"
        power_data_dir.mkdir(parents=True, exist_ok=True)
        
        # 查找该固件版本已有的测试次数
        existing_runs = []
        for item in power_data_dir.iterdir():
            if item.is_dir() and firmware_version in item.name and "Test" in item.name:
                # 匹配格式: firmware_version-TestXX-YYYYMMDD_HHMMSS
                match = re.search(rf'{re.escape(firmware_version)}-Test(\d+)-', item.name)
                if match:
                    existing_runs.append(int(match.group(1)))
                else:
                    # 尝试更宽松的匹配模式
                    match = re.search(r'-Test(\d+)-', item.name)
                    if match:
                        existing_runs.append(int(match.group(1)))
        
        # 返回下一个测试次数
        return max(existing_runs) + 1 if existing_runs else 1
    
    def _extract_date_from_url(self, url: str) -> str:
        """从固件URL中提取日期作为文件夹名称"""
        if not url:
            self.logger.warning("固件URL为空，无法提取日期")
            return None
        
        try:
            from src.app.PowerConsumption.PowerConsumption_utils import extract_year_month
            date_str = extract_year_month(url)
            
            if date_str:
                self.logger.debug(f"从URL中提取到日期: {date_str}")
                return date_str
            else:
                self.logger.warning(f"无法从URL中提取日期: {url}")
                return None
                
        except Exception as e:
            self.logger.error(f"提取日期失败: {e}")
            return None
    
    def _create_date_folder_and_copy_templates(self, date_str: str) -> Path:
        """创建日期文件夹并复制模板文件"""
        if not date_str:
            self.logger.error("日期字符串为空，无法创建文件夹")
            return None
        
        # 创建日期文件夹路径
        date_folder = self.project_root / "PowerConsumption_Data" / date_str
        
        # 如果文件夹已存在，直接返回
        if date_folder.exists():
            self.logger.info(f"日期文件夹已存在: {date_folder}")
            return date_folder
        
        # 创建文件夹
        date_folder.mkdir(parents=True, exist_ok=True)
        self.logger.info(f"创建日期文件夹: {date_folder}")
        
        # 检查模板文件是否存在
        template_file = self.project_root / "PowerConsumption_Data" / "Z03-DailyTest-Template.xlsx"
        if not template_file.exists():
            self.logger.warning(f"模板文件不存在: {template_file}")
            return date_folder
        
        # 获取所有挡位配置，并提前创建所有目标文件
        try:
            json_config = self.json_manager.load_json()
            if json_config and 'record' in json_config:
                for record_config in json_config['record']:
                    config_name = record_config.get('name', '')
                    if config_name:
                        # 处理挡位名称：提取关键信息
                        match = re.search(r'^(.+?)(?:_功耗测试)?$', config_name)
                        if match:
                            test_scheme = match.group(1).lower()
                            # 创建模板副本
                            template_copy = date_folder / f"{date_str}-{test_scheme}.xlsx"
                            
                            if not template_copy.exists():
                                shutil.copy2(template_file, template_copy)
                                self.logger.info(f"创建汇总文件: {template_copy.name}")
                            else:
                                self.logger.debug(f"汇总文件已存在: {template_copy.name}")
            else:
                self.logger.warning("JSON配置中未找到挡位配置，将无法自动创建汇总文件")
        except Exception as e:
            self.logger.error(f"创建汇总文件失败: {e}")
        
        return date_folder
    
    def _copy_power_data_to_daily_files(self, source_folder: Path, date_folder: Path) -> bool:
        """
        将功耗数据复制到每日汇总文件中（改进版：支持多次复制，数据间隔一列）
        关键改进：
        1. 使用持久化的列位置记录文件，确保每次复制都能找到正确的位置
        2. 按文件名排序，确保处理顺序一致
        """
        if not source_folder.exists():
            self.logger.error(f"源数据文件夹不存在: {source_folder}")
            return False
        
        if not date_folder.exists():
            self.logger.error(f"日期文件夹不存在: {date_folder}")
            return False
        
        try:
            # 查找源文件夹中的所有Excel文件（排除临时文件）
            excel_files = []
            for file_path in source_folder.rglob("*.xlsx"):
                # 排除Excel临时文件（以~$开头的文件）
                if not file_path.name.startswith('~$'):
                    excel_files.append(file_path)
            
            if not excel_files:
                self.logger.warning(f"在源文件夹中未找到Excel文件: {source_folder}")
                return False
            
            # 按文件名排序，确保处理顺序一致
            excel_files.sort(key=lambda x: x.name)
            
            success_count = 0
            
            for source_excel in excel_files:
                # 从文件名提取挡位信息
                file_stem = source_excel.stem
                # 匹配挡位名称（如4k30夜景-20260128_120000 -> 4k30夜景）
                match = re.search(r'^([^-]+)', file_stem)
                if not match:
                    self.logger.warning(f"无法从文件名提取挡位信息: {source_excel.name}")
                    continue
                
                test_scheme = match.group(1)
                
                # 获取日期文件夹名称（如2026-01）
                date_str = date_folder.name
                
                # 构建目标文件名（如2026-01-4k30.xlsx）
                target_filename = f"{date_str}-{test_scheme}.xlsx"
                target_file = date_folder / target_filename
                
                # 如果目标文件不存在，从模板创建
                if not target_file.exists():
                    template_file = self.project_root / "PowerConsumption_Data" / "Z03-DailyTest-Template.xlsx"
                    if template_file.exists():
                        shutil.copy2(template_file, target_file)
                        self.logger.info(f"创建目标文件: {target_filename}")
                    else:
                        self.logger.warning(f"模板文件不存在，无法创建目标文件: {target_filename}")
                        continue
                
                target_files = [target_file]
                
                target_excel = target_files[0]
                
                # 关键改进：使用列位置日志文件实现持久化
                col_log_file = target_excel.parent / f"{target_excel.stem}_col_position.txt"
                
                # 如果列位置日志文件存在，读取上次的列位置
                if col_log_file.exists():
                    try:
                        with open(col_log_file, 'r') as f:
                            last_col = int(f.read().strip())
                            # 更新缓存
                            target_file_key = str(target_excel.resolve())
                            self._target_file_col_cache[target_file_key] = last_col
                            self.logger.info(f"从日志文件读取列位置: {get_column_letter(last_col) if hasattr(get_column_letter, '__call__') else f'列{last_col}'}")
                    except Exception as e:
                        self.logger.warning(f"读取列位置日志失败: {e}")
                
                # 复制数据
                if self._copy_excel_columns(source_excel, target_excel):
                    success_count += 1
                    
                    # 保存列位置到日志文件
                    target_file_key = str(target_excel.resolve())
                    if target_file_key in self._target_file_col_cache:
                        try:
                            with open(col_log_file, 'w') as f:
                                f.write(str(self._target_file_col_cache[target_file_key]))
                            self.logger.debug(f"保存列位置到日志: {col_log_file.name}")
                        except Exception as e:
                            self.logger.warning(f"保存列位置日志失败: {e}")
                    
                    self.logger.info(f"成功复制数据: {source_excel.name} -> {target_excel.name}")
                else:
                    self.logger.error(f"复制数据失败: {source_excel.name} -> {target_excel.name}")
            
            self.logger.info(f"数据汇总完成，成功处理 {success_count}/{len(excel_files)} 个文件")
            
            # 更新总汇总文件（包含所有挡位）
            if success_count > 0:
                try:
                    self.update_consolidated_summary_file(date_folder)
                except Exception as e:
                    self.logger.warning(f"更新总汇总文件失败: {e}，但不影响挡位汇总")
            
            return success_count > 0
            
        except Exception as e:
            self.logger.error(f"数据汇总失败: {e}")
            return False
    
    def _copy_excel_columns(self, source_file: Path, target_file: Path) -> bool:
        """
        复制Excel文件的D、E、F、G列到目标文件
        """
        if not WIN32COM_AVAILABLE:
            self.logger.error("win32com不可用，无法执行Excel复制操作")
            return False
        
        excel_app = None
        source_wb = None
        target_wb = None
        
        try:
            # 1. 启动Excel应用（增加防锁定配置）
            excel_app = win32.Dispatch('Excel.Application')
            excel_app.Visible = False
            excel_app.DisplayAlerts = False
            excel_app.Calculation = -4135  # xlCalculationManual
            excel_app.ScreenUpdating = False  # 关闭屏幕更新，提升速度
            
            # 2. 打开源文件和目标文件（绝对路径，避免路径解析错误）
            source_file_abs = str(source_file.resolve().absolute())
            target_file_abs = str(target_file.resolve().absolute())
            
            source_wb = excel_app.Workbooks.Open(source_file_abs)
            source_ws = source_wb.ActiveSheet
            target_wb = excel_app.Workbooks.Open(target_file_abs)
            target_ws = target_wb.ActiveSheet
            
            # 3. 核心改进：使用多行检测查找第一个空白列
            def is_column_empty(col_idx, check_rows=3):
                """检查指定列的前几行是否都为空"""
                for row in range(1, check_rows + 1):
                    cell_value = target_ws.Cells(row, col_idx).Value
                    if cell_value is not None and str(cell_value).strip() != "":
                        return False
                return True
            
            target_file_key = str(target_file.resolve())
            start_search_col = 4  # 默认从D列（第4列）开始查找
            
            # 从缓存中获取上一次的查找起始位置
            if target_file_key in self._target_file_col_cache:
                start_search_col = self._target_file_col_cache[target_file_key]
                self.logger.debug(f"从缓存获取查找起始列: {get_column_letter(start_search_col)}")
            
            current_copy_start_col = None
            max_col = 200  # 最大列限制，避免无限循环
            
            # 逐列查找第一个空白列（检查前3行都为空）
            for col in range(start_search_col, max_col + 1):
                if is_column_empty(col, check_rows=3):
                    current_copy_start_col = col
                    self.logger.debug(f"找到空白列: {get_column_letter(col)}（前3行均为空）")
                    break
            
            # 4. 校验查找结果
            if current_copy_start_col is None:
                self.logger.error(f"目标文件已达最大列限制（{max_col}列），无可用空白列")
                return False
            
            # 5. 备份目标区域的格式（避免破坏原有格式）
            self._backup_target_format(target_ws, current_copy_start_col, current_copy_start_col + 3)
            
            # 6. 修改源文件的D1和F1单元格标题
            self._update_source_cell_titles(source_ws)
            
            # 强制保存源文件，确保修改生效
            source_wb.Save()
            
            # 7. 获取源文件的有效数据区域（D-G列，行号取实际有数据的行）
            source_start_col = 4  # 源文件D列
            source_end_col = 7  # 源文件G列
            
            # 精准获取源文件有数据的最大行
            source_max_row = 1
            for row in range(1, 1001):
                row_has_data = False
                for col in range(source_start_col, source_end_col + 1):
                    cell_val = source_ws.Cells(row, col).Value
                    if cell_val is not None and (not isinstance(cell_val, str) or cell_val.strip() != ""):
                        row_has_data = True
                        break
                if row_has_data:
                    source_max_row = row
                else:
                    # 连续10行无数据，判定为数据结束
                    if row - source_max_row > 10:
                        break
            
            if source_max_row < 1:
                self.logger.warning("源文件无有效数据，跳过复制")
                return False
            
            # 定义源数据区域（D-G列，第1行到最后一行有数据的行）
            source_range = source_ws.Range(
                source_ws.Cells(1, source_start_col),
                source_ws.Cells(source_max_row, source_end_col)
            )
            
            # 7. 定义目标粘贴区域（从找到的空白列开始，粘贴4列数据）
            current_copy_end_col = current_copy_start_col + 3  # 粘贴4列（D-G对应）
            target_range = target_ws.Range(
                target_ws.Cells(1, current_copy_start_col),
                target_ws.Cells(source_max_row, current_copy_end_col)
            )
            
            self.logger.debug(f"本次粘贴：从{get_column_letter(current_copy_start_col)}列到{get_column_letter(current_copy_end_col)}列")
            
            # 8. 执行复制粘贴（先值后格式，避免公式关联）
            # 粘贴值（仅复制数据，不复制公式、格式）
            source_range.Copy()
            target_range.PasteSpecial(Paste=-4163, Operation=-4142)  # xlPasteValues, xlNone
            
            # 粘贴格式（保持样式一致）
            source_range.Copy()
            target_range.PasteSpecial(Paste=-4122, Operation=-4142)  # xlPasteFormats, xlNone
            
            # 取消剪贴板残留，释放资源
            excel_app.CutCopyMode = False
            
            # 9. 处理合并单元格
            self._handle_merged_cells(source_ws, target_ws, 
                                    source_start_col, source_end_col,
                                    current_copy_start_col, source_max_row)
            
            # 10. 更新缓存（下一次从本次粘贴结束列的下一列开始查找，自然间隔）
            self._target_file_col_cache[target_file_key] = current_copy_end_col + 1
            self.logger.debug(f"更新缓存：下一次从{get_column_letter(current_copy_end_col + 1)}列开始查找")
            
            # 11. 强制保存目标文件
            target_wb.Save()
            self.logger.debug(f"成功复制 {source_max_row} 行数据，粘贴到{get_column_letter(current_copy_start_col)}列开始的区域")
            
            return True
                    
        except Exception as e:
            self.logger.error(f"复制Excel列数据失败: {str(e)}")
            return False
        finally:
            # 12. 强制清理Excel资源（关键：避免进程残留、文件锁定）
            self._cleanup_excel_objects(excel_app, source_wb, target_wb)
    
    def _update_source_cell_titles(self, source_ws):
        """更新源文件的D1和F1单元格标题，显示实际固件URL"""
        try:
            # 获取固件URL
            firmware_url = self.json_manager.get_value('firmware.download_url')
            if not firmware_url:
                firmware_url = "固件链接未设置"
            
            # 源文件的D1和F1单元格位置（固定位置）
            d1_cell = source_ws.Cells(1, 4)  # D列是第4列
            f1_cell = source_ws.Cells(1, 6)  # F列是第6列
            
            # 设置新的标题内容，包含实际固件URL
            d1_cell.Value = f"{firmware_url}\n负载端功耗（mW）"
            f1_cell.Value = f"{firmware_url}\n电池端功耗（mW）"
            
            # 设置单元格格式为自动换行
            d1_cell.WrapText = True
            f1_cell.WrapText = True
            
            self.logger.debug(f"已更新源文件D1和F1单元格标题，包含固件URL: {firmware_url}")
            
        except Exception as e:
            self.logger.warning(f"更新源文件单元格标题时出错: {str(e)}")
    
    def _cleanup_excel_objects(self, excel_app, source_wb, target_wb):
        """安全清理Excel COM对象，避免进程残留"""
        try:
            # 强制释放COM对象
            if source_wb is not None:
                try:
                    source_wb.Close(SaveChanges=False)
                except:
                    pass
                finally:
                    source_wb = None
            
            if target_wb is not None:
                try:
                    target_wb.Close(SaveChanges=True)
                except:
                    pass
                finally:
                    target_wb = None
            
            if excel_app is not None:
                try:
                    excel_app.ScreenUpdating = True
                    excel_app.Quit()
                except:
                    pass
                finally:
                    # 强制垃圾回收
                    import gc
                    excel_app = None
                    gc.collect()
                    
        except Exception as e:
            self.logger.warning(f"清理Excel资源时出错: {str(e)}")
    
    def _backup_target_format(self, target_ws, start_col, end_col):
        """
        备份目标区域的格式，避免破坏原有格式
        关键改进：检查并处理目标区域的合并单元格
        """
        try:
            # 检查目标区域是否有合并单元格
            if hasattr(target_ws.UsedRange, 'MergeAreas'):
                merged_in_range = False
                for merged_area in target_ws.UsedRange.MergeAreas:
                    merge_col1 = merged_area.Column
                    merge_col2 = merged_area.Column + merged_area.Columns.Count - 1
                    # 检查合并区域是否与目标区域重叠
                    if not (merge_col2 < start_col or merge_col1 > end_col):
                        merged_in_range = True
                        self.logger.debug(f"目标区域 {start_col}-{end_col} 与合并单元格重叠")
                        break
                
                if merged_in_range:
                    # 如果是第一次使用该区域，可能需要调整格式
                    self._adjust_target_format(target_ws, start_col, end_col)
                        
        except Exception as e:
            self.logger.debug(f"备份格式时出现警告: {str(e)}")
    
    def _adjust_target_format(self, target_ws, start_col, end_col):
        """调整目标区域的格式，避免格式冲突"""
        try:
            # 取消目标区域内的合并单元格
            if hasattr(target_ws.UsedRange, 'MergeAreas'):
                for merged_area in target_ws.UsedRange.MergeAreas:
                    merge_col1 = merged_area.Column
                    merge_col2 = merged_area.Column + merged_area.Columns.Count - 1
                    merge_row1 = merged_area.Row
                    merge_row2 = merged_area.Row + merged_area.Rows.Count - 1
                    
                    # 只取消与目标区域重叠的合并单元格
                    if (start_col <= merge_col1 <= end_col or 
                        start_col <= merge_col2 <= end_col or
                        merge_col1 <= start_col <= merge_col2 or
                        merge_col1 <= end_col <= merge_col2):
                        
                        # 获取合并区域
                        merge_range = target_ws.Range(
                            target_ws.Cells(merge_row1, merge_col1),
                            target_ws.Cells(merge_row2, merge_col2)
                        )
                        
                        if merge_range.MergeCells:
                            merge_range.UnMerge()
                            self.logger.debug(f"取消合并单元格: 行{merge_row1}-{merge_row2}，列{merge_col1}-{merge_col2}")
            
            # 清除目标区域的内容和格式
            target_range = target_ws.Range(
                target_ws.Cells(1, start_col),
                target_ws.Cells(100, end_col)  # 假设最多100行
            )
            
            # 清除内容
            target_range.ClearContents()
            
            self.logger.debug(f"已清除目标区域 {start_col}-{end_col} 的格式和内容")
            
        except Exception as e:
            self.logger.warning(f"调整目标格式时出错: {str(e)}")
    
    def _handle_merged_cells(self, source_ws, target_ws, source_start_col, source_end_col, 
                        target_start_col, max_row):
        """
        处理合并单元格（适配新的空白列查找逻辑，仅复制有效区域内的合并单元格）
        """
        try:
            # 仅处理源文件D-G列内的合并单元格
            if not hasattr(source_ws.UsedRange, 'MergeAreas'):
                self.logger.debug("源工作表无合并单元格，跳过处理")
                return
            
            merged_areas = source_ws.UsedRange.MergeAreas
            
            for merged_area in merged_areas:
                # 提取合并区域的行列范围
                merge_row1 = merged_area.Row
                merge_row2 = merged_area.Row + merged_area.Rows.Count - 1
                merge_col1 = merged_area.Column
                merge_col2 = merged_area.Column + merged_area.Columns.Count - 1
                
                # 过滤：仅处理D-G列范围内的合并单元格
                if not (source_start_col <= merge_col1 <= source_end_col and 
                        source_start_col <= merge_col2 <= source_end_col):
                    continue
                
                # 过滤：仅处理有效数据行范围内的合并单元格
                if merge_row1 > max_row or merge_row2 < 1:
                    continue
                
                # 计算目标区域的列位置（对应本次粘贴的起始列）
                target_merge_col1 = target_start_col + (merge_col1 - source_start_col)
                target_merge_col2 = target_start_col + (merge_col2 - source_start_col)
                
                # 取消目标区域已有合并（避免格式冲突）
                target_merge_range = target_ws.Range(
                    target_ws.Cells(merge_row1, target_merge_col1),
                    target_ws.Cells(merge_row2, target_merge_col2)
                )
                
                if target_merge_range.MergeCells:
                    target_merge_range.UnMerge()
                
                # 重新合并并复制格式
                target_merge_range.Merge()
                merged_area.Copy()
                target_merge_range.PasteSpecial(Paste=-4122)  # xlPasteFormats
                target_ws.Application.CutCopyMode = False
                
                self.logger.debug(f"成功处理合并单元格: 行{merge_row1}-{merge_row2}，列{target_merge_col1}-{target_merge_col2}")
        
        except Exception as e:
            self.logger.debug(f"处理合并单元格时出现警告: {str(e)}")
    
    def summarize_power_data_to_daily_files(self, firmware_url: str = None) -> bool:
        """汇总功耗数据到每日文件中（支持保留多组数据）"""
        # 获取固件URL
        if not firmware_url:
            firmware_url = self.json_manager.get_value('firmware.download_url')
        
        if not firmware_url:
            self.logger.error("无法获取固件URL")
            return False
        
        # 提取日期
        date_str = self._extract_date_from_url(firmware_url)
        if not date_str:
            self.logger.error("无法从URL提取日期")
            return False
        
        # 创建日期文件夹和模板文件
        date_folder = self._create_date_folder_and_copy_templates(date_str)
        if not date_folder:
            self.logger.error("创建日期文件夹失败")
            return False
        
        # 使用指定的测试数据文件夹
        data_dir = self.project_root / "PowerConsumption_Data"
        
        if self.unified_folder_name:
            # 使用指定的文件夹
            specified_folder = data_dir / self.unified_folder_name
            if specified_folder.exists():
                self.logger.info(f"使用指定的测试数据文件夹: {self.unified_folder_name}")
                test_folder = specified_folder
            else:
                self.logger.warning(f"指定的测试数据文件夹不存在: {self.unified_folder_name}")
                return False
        else:
            # 查找最新的测试文件夹（按修改时间排序）
            test_folders = []
            for item in data_dir.iterdir():
                if item.is_dir() and "Test" in item.name:
                    test_folders.append(item)
            
            if not test_folders:
                self.logger.warning("未找到测试数据文件夹")
                return False
            
            # 按修改时间排序，获取最新的文件夹
            latest_folder = max(test_folders, key=lambda f: f.stat().st_mtime)
            self.logger.info(f"找到最新的测试数据文件夹: {latest_folder.name}")
            test_folder = latest_folder
        
        # 复制数据到每日汇总文件
        success = self._copy_power_data_to_daily_files(test_folder, date_folder)
        
        if success:
            self.logger.info(f"功耗数据汇总完成: {test_folder.name} -> {date_folder.name}")
        else:
            self.logger.error(f"功耗数据汇总失败")
        
        return success
    
    def create_consolidated_summary_file(self, date_folder: Path) -> bool:
        """
        创建包含所有挡位汇总的总Excel文件
        
        文件结构：
        - 文件名：{date_str}-ALL-GEARS.xlsx
        - 每个工作表：对应一个挡位的汇总文件
        - 工作表名称：挡位名称（如 4k30, 4k60 等）
        
        Args:
            date_folder: 日期文件夹路径（如 2026-01）
            
        Returns:
            bool: 是否创建成功
        """
        if not WIN32COM_AVAILABLE:
            self.logger.warning("win32com不可用，无法创建总汇总文件")
            return False
        
        if not date_folder.exists():
            self.logger.error(f"日期文件夹不存在: {date_folder}")
            return False
        
        try:
            # 1. 扫描日期文件夹中的所有挡位汇总文件（排除总汇总文件本身）
            date_str = date_folder.name
            gear_summary_files = []
            for file_path in date_folder.glob("*.xlsx"):
                # 排除总汇总文件和临时文件
                if file_path.name.startswith('~$') or 'ALL-GEARS' in file_path.name:
                    continue
                
                # 提取挡位名称（从文件名如 "2026-01-4k30.xlsx" 提取 "4k30"）
                match = re.search(rf'^{re.escape(date_str)}-(.+?)\.xlsx$', file_path.name)
                if match:
                    gear_name = match.group(1)
                    gear_summary_files.append((gear_name, file_path))
            
            if not gear_summary_files:
                self.logger.warning(f"未找到挡位汇总文件，无法创建总汇总文件")
                return False
            
            # 按挡位名称排序
            gear_summary_files.sort(key=lambda x: x[0])
            
            self.logger.info(f"找到 {len(gear_summary_files)} 个挡位汇总文件，开始创建总汇总文件")
            
            # 2. 创建总汇总文件
            consolidated_file = date_folder / f"{date_str}-ALL-GEARS.xlsx"
            
            # 3. 使用 win32com 创建总汇总文件并复制所有工作表
            excel_app = None
            consolidated_wb = None
            
            try:
                # 启动Excel应用
                excel_app = win32.Dispatch('Excel.Application')
                excel_app.Visible = False
                excel_app.DisplayAlerts = False
                excel_app.Calculation = -4135  # xlCalculationManual
                excel_app.ScreenUpdating = False
                
                # 创建新的工作簿
                consolidated_wb = excel_app.Workbooks.Add()
                
                # 删除默认的工作表（只保留一个）
                while consolidated_wb.Worksheets.Count > 1:
                    consolidated_wb.Worksheets(consolidated_wb.Worksheets.Count).Delete()
                
                # 重命名第一个工作表为第一个挡位名称
                first_gear_name = gear_summary_files[0][0]
                # Excel工作表名称限制：最大31字符，不能包含某些特殊字符
                sheet_name = self._sanitize_sheet_name(first_gear_name)
                consolidated_ws = consolidated_wb.Worksheets(1)
                consolidated_ws.Name = sheet_name
                
                # 4. 为每个挡位汇总文件创建对应的工作表并复制内容
                # 注意：每个挡位只复制第一个工作表（通常是主要数据工作表）
                success_count = 0
                
                for gear_name, gear_file in gear_summary_files:
                    try:
                        # 打开挡位汇总文件
                        gear_wb = excel_app.Workbooks.Open(str(gear_file.resolve().absolute()))
                        
                        # 只复制第一个工作表（主要数据工作表）
                        source_ws = gear_wb.Worksheets(1)
                        
                        # 工作表名称：直接使用挡位名称（不添加索引）
                        new_sheet_name = self._sanitize_sheet_name(gear_name)
                        
                        # 如果是第一个挡位，直接使用已存在的工作表
                        if gear_name == first_gear_name:
                            target_ws = consolidated_ws
                            # 确保工作表名称正确（可能之前已经重命名了）
                            if target_ws.Name != new_sheet_name:
                                target_ws.Name = new_sheet_name
                        else:
                            # 检查工作表名称是否已存在
                            existing_names = [ws.Name for ws in consolidated_wb.Worksheets]
                            if new_sheet_name in existing_names:
                                # 如果已存在，添加后缀（这种情况应该很少见）
                                counter = 1
                                while f"{new_sheet_name}_{counter}" in existing_names:
                                    counter += 1
                                new_sheet_name = f"{new_sheet_name}_{counter}"
                            
                            # 创建新工作表
                            target_ws = consolidated_wb.Worksheets.Add()
                            target_ws.Name = new_sheet_name
                        
                        # 复制整个工作表内容（包括格式、公式等）
                        source_ws.UsedRange.Copy()
                        target_ws.Paste()
                        excel_app.CutCopyMode = False
                        
                        self.logger.debug(f"已复制工作表: {gear_name} -> {target_ws.Name}")
                        
                        # 关闭挡位汇总文件
                        gear_wb.Close(SaveChanges=False)
                        success_count += 1
                        
                    except Exception as e:
                        self.logger.error(f"复制挡位 {gear_name} 的数据失败: {e}")
                        try:
                            gear_wb.Close(SaveChanges=False)
                        except:
                            pass
                        continue
                
                # 5. 保存总汇总文件
                if success_count > 0:
                    consolidated_wb.SaveAs(str(consolidated_file.resolve().absolute()))
                    self.logger.info(f"总汇总文件创建成功: {consolidated_file.name}，包含 {success_count} 个挡位")
                    return True
                else:
                    self.logger.error("没有成功复制任何挡位数据")
                    return False
                    
            except Exception as e:
                self.logger.error(f"创建总汇总文件失败: {e}")
                return False
            finally:
                # 清理Excel对象
                try:
                    if consolidated_wb is not None:
                        consolidated_wb.Close(SaveChanges=False)
                except:
                    pass
                
                try:
                    if excel_app is not None:
                        excel_app.ScreenUpdating = True
                        excel_app.Quit()
                except:
                    pass
                
        except Exception as e:
            self.logger.error(f"创建总汇总文件时发生错误: {e}")
            return False
    
    def _sanitize_sheet_name(self, name: str) -> str:
        """
        清理工作表名称，确保符合Excel要求
        
        Excel工作表名称限制：
        - 最大31字符
        - 不能包含: \ / ? * [ ]
        - 不能为空
        """
        # 替换不允许的字符
        invalid_chars = ['\\', '/', '?', '*', '[', ']']
        for char in invalid_chars:
            name = name.replace(char, '_')
        
        # 截断到31字符
        if len(name) > 31:
            name = name[:31]
        
        # 确保不为空
        if not name:
            name = "Sheet1"
        
        return name
    
    def update_consolidated_summary_file(self, date_folder: Path) -> bool:
        """
        更新总汇总文件（删除后重新创建）
        
        Args:
            date_folder: 日期文件夹路径
            
        Returns:
            bool: 是否更新成功
        """
        if not date_folder.exists():
            self.logger.error(f"日期文件夹不存在: {date_folder}")
            return False
        
        try:
            date_str = date_folder.name
            consolidated_file = date_folder / f"{date_str}-ALL-GEARS.xlsx"
            
            # 1. 如果总文件存在，尝试删除它
            if consolidated_file.exists():
                try:
                    # 检查文件是否被锁定
                    # 尝试以写入模式打开，如果失败说明文件被锁定
                    try:
                        with open(consolidated_file, 'r+b'):
                            pass
                    except PermissionError:
                        self.logger.warning(f"总汇总文件被锁定，无法删除: {consolidated_file.name}，跳过本次更新")
                        return False
                    
                    # 删除文件
                    consolidated_file.unlink()
                    self.logger.info(f"已删除旧的总汇总文件: {consolidated_file.name}")
                    
                    # 等待一小段时间，确保文件系统操作完成
                    import time
                    time.sleep(0.5)
                    
                except Exception as e:
                    self.logger.warning(f"删除旧的总汇总文件失败: {e}，尝试继续创建新文件")
            
            # 2. 重新创建总汇总文件
            return self.create_consolidated_summary_file(date_folder)
            
        except Exception as e:
            self.logger.error(f"更新总汇总文件失败: {e}")
            return False
    
    def find_latest_csv(self, directory: Path = None) -> Path:
        """查找指定目录下最新的CSV文件"""
        # 如果没有指定目录，使用原始数据存储路径
        search_dir = directory or self.raw_data_path
        
        if not search_dir.exists():
            self.logger.error(f"下载目录不存在: {search_dir}")
            return None
        
        # 查找所有CSV文件
        csv_files = list(search_dir.glob("*.csv"))
        
        if not csv_files:
            self.logger.warning(f"在 {search_dir} 目录下未找到CSV文件")
            return None
        
        # 按修改时间排序，获取最新的文件
        latest_file = max(csv_files, key=lambda f: f.stat().st_mtime)
        
        self.logger.debug(f"找到最新的CSV文件: {latest_file.name}")
        self.logger.debug(f"文件修改时间: {datetime.fromtimestamp(latest_file.stat().st_mtime)}")
        
        return latest_file
    
    def copy_csv_to_project(self, csv_file: Path = None, timestamp: str = None) -> Path:
        """将CSV文件剪切到配置的原始数据存储目录"""
        # 如果没有指定文件，则查找最新的CSV文件
        if csv_file is None:
            csv_file = self.find_latest_csv()
            if csv_file is None:
                return None
        
        if not csv_file.exists():
            error_msg = f"CSV文件不存在: {csv_file}"
            self.logger.error(error_msg)
            raise FileNotFoundError(error_msg)
        
        # 生成时间戳（如果未提供）
        if timestamp is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # 创建目标目录（从JSON配置读取）
        target_dir = self.raw_data_path
        target_dir.mkdir(parents=True, exist_ok=True)
        
        self.logger.debug(f"创建目标目录: {target_dir}")
        
        # 剪切文件
        target_file = target_dir / csv_file.name
        
        try:
            # 使用move进行剪切操作
            shutil.move(str(csv_file), str(target_file))
            self.logger.debug(f"剪切CSV文件: {csv_file.name} -> {target_file.name}")
            
            # 验证文件是否存在（move后源文件应该不存在）
            if csv_file.exists():
                self.logger.warning(f"警告：源文件仍然存在: {csv_file}")
            else:
                self.logger.debug(f"源文件已成功移除: {csv_file.name}")
            
            # 验证目标文件是否存在
            if not target_file.exists():
                error_msg = f"剪切失败：目标文件不存在: {target_file}"
                self.logger.error(error_msg)
                raise FileNotFoundError(error_msg)
            
            return target_file
            
        except FileNotFoundError:
            # 重新抛出FileNotFoundError
            raise
        except Exception as e:
            error_msg = f"剪切CSV文件失败: {e}"
            self.logger.error(error_msg)
            raise RuntimeError(error_msg) from e
    
    def import_csv_to_excel(self, csv_file: Path, excel_file: Path, sheet_name: str = "1. 原始数据-SPM1") -> bool:
        """将CSV数据导入到Excel工作表中"""
        if not OPENPYXL_AVAILABLE:
            self.logger.error("openpyxl未安装，无法操作Excel文件")
            return False
        
        try:
            self.logger.debug(f"开始将CSV数据导入Excel: {csv_file.name} -> {excel_file.name}")
            
            # 打开Excel文件
            wb = load_workbook(excel_file)
            
            # 检查工作表是否存在
            if sheet_name not in wb.sheetnames:
                self.logger.error(f"工作表 '{sheet_name}' 不存在")
                self.logger.debug(f"可用的工作表: {wb.sheetnames}")
                return False
            
            ws = wb[sheet_name]
            
            # 读取CSV文件
            self.logger.debug(f"读取CSV文件: {csv_file.name}")
            with open(csv_file, 'r', encoding='utf-8') as f:
                csv_reader = csv.reader(f)
                rows = list(csv_reader)
            
            if not rows:
                self.logger.warning("CSV文件为空")
                return False
            
            # 清空工作表中的所有数据
            self.logger.debug(f"清空工作表 '{sheet_name}' 中的旧数据")
            ws.delete_rows(1, ws.max_row)  # 删除所有行
            
            # 辅助函数：尝试将字符串转换为数字类型
            def convert_to_number(value):
                """尝试将字符串转换为数字类型（整数或浮点数）"""
                if not value or value.strip() == '':
                    return None
                
                # 尝试转换为整数
                try:
                    return int(value)
                except ValueError:
                    pass
                
                # 尝试转换为浮点数
                try:
                    return float(value)
                except ValueError:
                    pass
                
                # 如果都失败，返回原始字符串
                return value
            
            # 将新数据写入工作表
            self.logger.debug(f"将数据写入工作表 '{sheet_name}'（自动转换数字类型）")
            for row_idx, row_data in enumerate(rows, start=1):
                for col_idx, cell_value in enumerate(row_data, start=1):
                    # 尝试转换为数字类型
                    converted_value = convert_to_number(cell_value)
                    ws.cell(row=row_idx, column=col_idx, value=converted_value)
            
            # 保存Excel文件
            wb.save(excel_file)
            wb.close()
            
            self.logger.debug(f"成功导入 {len(rows)} 行数据到工作表 '{sheet_name}'")
            return True
            
        except Exception as e:
            self.logger.error(f"导入CSV数据到Excel失败: {e}")
            return False
    
    def set_active_sheet(self, excel_file: Path, sheet_name: str) -> bool:
        """设置Excel的默认活动工作表"""
        if not OPENPYXL_AVAILABLE:
            self.logger.error("openpyxl未安装，无法操作Excel文件")
            return False
        
        try:
            wb = load_workbook(excel_file)
            
            if sheet_name not in wb.sheetnames:
                self.logger.error(f"工作表 '{sheet_name}' 不存在")
                return False
            
            # 设置活动工作表
            wb.active = wb[sheet_name]
            wb.save(excel_file)
            wb.close()
            
            self.logger.debug(f"设置活动工作表为 '{sheet_name}'")
            return True
            
        except Exception as e:
            self.logger.error(f"设置活动工作表失败: {e}")
            return False
    
    def get_cell_value(self, excel_file: Path, cell_address: str, sheet_name: str = "3. 模块功耗", as_integer: bool = True) -> str:
        """从Excel文件中读取指定单元格的值"""
        result = None
        excel_app = None
        wb_excel = None
        
        try:
            if not excel_file.exists():
                self.logger.error(f"Excel文件不存在: {excel_file}")
                return result
            
            self.logger.debug(f"开始读取单元格 {cell_address}: {excel_file.name}")
            
            excel_app = win32.Dispatch("Excel.Application")
            excel_app.Visible = False
            excel_app.DisplayAlerts = False
            excel_app.Calculation = -4105  # xlCalculationAutomatic
            
            # 打开Excel文件
            wb_excel = excel_app.Workbooks.Open(str(excel_file.absolute()))
            ws_excel = wb_excel.Worksheets(sheet_name)
            
            # 强制计算所有公式
            ws_excel.Calculate()
            
            # 读取指定单元格
            try:
                cell_value = ws_excel.Range(cell_address).Value
                self.logger.debug(f"{cell_address}单元格值: {cell_value} (类型: {type(cell_value)})")
                
                if cell_value is not None:
                    # 将单元格的值转化为数字
                    if isinstance(cell_value, (int, float)):
                        num_value = float(cell_value)
                    else:
                        try:
                            num_value = float(cell_value)
                        except (ValueError, TypeError):
                            num_value = None
                    
                    if num_value is not None:
                        if as_integer:
                            # 丢弃小数点（转换为整数）
                            result = str(int(num_value))
                        else:
                            result = str(num_value)
                        self.logger.debug(f"读取单元格 {cell_address}: {result}")
                    else:
                        self.logger.warning(f"{cell_address}单元格值无法转换为数字: {cell_value}")
                else:
                    self.logger.warning(f"{cell_address}单元格值为空")
            except Exception as e:
                self.logger.warning(f"读取{cell_address}单元格失败: {e}")
            
            return result
            
        except ImportError:
            self.logger.error("win32com未安装，无法读取Excel文件")
            self.logger.error("请安装: pip install pywin32")
            return result
        except Exception as e:
            self.logger.error(f"读取单元格值失败: {e}")
            return result
        finally:
            # 确保Excel应用被正确关闭，避免COM对象泄漏
            try:
                if wb_excel is not None:
                    wb_excel.Close(SaveChanges=False)
                if excel_app is not None:
                    excel_app.Quit()
                    del wb_excel, excel_app
            except Exception as cleanup_e:
                self.logger.warning(f"清理Excel资源时出错: {cleanup_e}")
    
    def get_module_power_values(self, excel_file: Path, sheet_name: str = "3. 模块功耗") -> dict:
        """从Excel文件中读取所有模块功耗值"""
        result = {}
        
        try:
            if not excel_file.exists():
                self.logger.error(f"Excel文件不存在: {excel_file}")
                return result
            
            self.logger.debug(f"开始读取模块功耗值: {excel_file.name}")
            
            # 从JSON配置中读取单元格映射关系
            module_power_cells = self.json_manager.get_value('module_power_cells', default={})
            
            if not module_power_cells:
                self.logger.warning("未配置module_power_cells，无法读取模块功耗值")
                return result
            
            # 遍历配置，读取对应的单元格值
            for key, config in module_power_cells.items():
                cell_address = config.get('cell')
                if cell_address:
                    result[key] = self.get_cell_value(excel_file, cell_address, sheet_name)
            
            self.logger.info(f"读取模块功耗值完成，共读取 {len(result)} 个模块")
            return result
            
        except Exception as e:
            self.logger.error(f"读取模块功耗值失败: {e}")
            return result
    
    def process_downloaded_data(self, config_name: str = None) -> Path:
        """处理下载的数据"""
        self.logger.debug("开始处理下载的功耗数据")
        self.logger.debug(f"原始数据目录: {self.raw_data_path}, 数据存储目录: {self.data_dir}")
        
        # 检查模板文件是否存在
        if not self.template_file.exists():
            self.logger.error(f"Excel模板文件不存在: {self.template_file}")
            return None
        
        # 查找最新的CSV文件（从raw_data_path）
        csv_file = self.find_latest_csv()
        
        # 如果raw_data_path中没有找到，直接返回错误（不再去默认路径查找）
        if csv_file is None:
            error_msg = f"未找到CSV文件：在原始数据目录 {self.raw_data_path} 中未找到CSV文件，可能是QEPM下载失败"
            self.logger.error(error_msg)
            raise FileNotFoundError(error_msg)
        
        # 确保文件在raw_data_path中（如果不在，说明有问题）
        if csv_file.parent != self.raw_data_path:
            error_msg = f"CSV文件不在原始数据目录中: {csv_file.parent}，期望: {self.raw_data_path}，可能是QEPM下载失败"
            self.logger.error(error_msg)
            raise FileNotFoundError(error_msg)
        
        # 获取测试方案名称
        if config_name is None:
            config_name = os.environ.get('RECORD_CONFIG_NAME', '')
        
        # 处理测试方案名称：提取关键信息
        if config_name:
            match = re.search(r'^(.+?)(?:_功耗测试)?$', config_name)
            if match:
                test_scheme = match.group(1).lower()
            else:
                test_scheme = config_name.lower()
        else:
            test_scheme = "unknown"
        
        # 生成时间戳
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # 创建目标目录
        target_dir_name = f"{test_scheme}-{timestamp}"
        target_dir = self.data_dir / target_dir_name
        target_dir.mkdir(parents=True, exist_ok=True)
        self.logger.debug(f"创建目标目录: {target_dir}")
        
        # 生成文件名并复制模板
        excel_filename = f"{test_scheme}-{timestamp}.xlsx"
        excel_file = target_dir / excel_filename
        try:
            shutil.copy2(self.template_file, excel_file)
            self.logger.debug(f"复制模板文件: {excel_file.name}")
        except Exception as e:
            self.logger.error(f"复制模板文件失败: {e}")
            return None
        
        # 剪切CSV文件从raw_data_path到目标目录
        csv_filename = f"{test_scheme}-{timestamp}.csv"
        csv_target = target_dir / csv_filename
        try:
            # 使用move进行剪切操作（从raw_data_path剪切到目标目录）
            shutil.move(str(csv_file), str(csv_target))
            self.logger.debug(f"剪切CSV文件: {csv_file.name} -> {csv_target.name}")
            
            # 验证文件是否成功剪切
            if csv_file.exists():
                self.logger.warning(f"警告：源文件仍然存在: {csv_file}")
            else:
                self.logger.debug(f"源文件已成功移除: {csv_file.name}")
            
            # 验证目标文件是否存在
            if not csv_target.exists():
                error_msg = f"剪切失败：目标文件不存在: {csv_target}"
                self.logger.error(error_msg)
                raise FileNotFoundError(error_msg)
        except FileNotFoundError:
            # 重新抛出FileNotFoundError
            raise
        except Exception as e:
            error_msg = f"剪切CSV文件失败: {e}"
            self.logger.error(error_msg)
            raise RuntimeError(error_msg) from e
        
        # 将CSV数据导入Excel（使用剪切后的文件路径）
        if not self.import_csv_to_excel(csv_target, excel_file, sheet_name="1. 原始数据-SPM1"):
            self.logger.error("导入CSV数据到Excel失败")
            return None
        
        # 设置活动工作表
        if not self.set_active_sheet(excel_file, sheet_name="3. 模块功耗"):
            self.logger.warning("设置活动工作表失败，但不影响数据导入")
        
        self.logger.info(f"功耗数据处理完成，文件: {excel_file.name}")
        
        return excel_file

    def check_cell_value_in_range(self, excel_file: Path, cell_address: str,
                                lower_limit: float, upper_limit: float,
                                sheet_name: str = None) -> tuple[bool, str]:
        """检查Excel文件中指定单元格的值是否在给定的上下限范围内"""
        if not WIN32COM_AVAILABLE:
            self.logger.error("win32com不可用，无法检查单元格值")
            return False, "win32com不可用"

        if not excel_file.exists():
            self.logger.error(f"Excel文件不存在: {excel_file}")
            return False, f"文件不存在: {excel_file}"

        try:
            # 创建Excel应用程序实例
            excel_app = win32.Dispatch("Excel.Application")
            excel_app.Visible = False  # 不显示Excel窗口

            # 打开Excel文件
            workbook = excel_app.Workbooks.Open(str(excel_file.resolve()))

            try:
                # 获取指定工作表或第一个工作表
                if sheet_name:
                    try:
                        worksheet = workbook.Sheets(sheet_name)
                    except:
                        self.logger.warning(f"工作表 '{sheet_name}' 不存在，使用第一个工作表")
                        worksheet = workbook.Sheets(1)
                else:
                    worksheet = workbook.Sheets(1)

                # 读取指定单元格的值
                cell_value = worksheet.Range(cell_address).Value

                # 关闭工作簿和Excel应用
                workbook.Close(SaveChanges=False)
                excel_app.Quit()

                # 检查值是否为数字
                try:
                    numeric_value = float(cell_value)
                except (ValueError, TypeError):
                    return False, f"单元格值不是数字: {cell_value}"

                # 检查是否在范围内
                if lower_limit <= numeric_value <= upper_limit:
                    return True, f"正常: {numeric_value}"
                elif numeric_value > upper_limit:
                    return False, f"过高: {numeric_value}"
                else:
                    return False, f"过低: {numeric_value}"

            except Exception as e:
                workbook.Close(SaveChanges=False)
                excel_app.Quit()
                raise e

        except Exception as e:
            self.logger.error(f"检查单元格值失败: {e}")
            return False, f"检查失败: {str(e)}"