"""
Excel数据处理模块
使用pandas和openpyxl处理Excel文件
"""

import os
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime

import pandas as pd
from openpyxl import load_workbook, Workbook
from openpyxl.styles import Font, Alignment, PatternFill

import config


class ExcelHandler:
    """Excel处理器"""

    def __init__(self):
        self.input_file = config.EXCEL_CONFIG["input_file"]
        self.output_file = config.EXCEL_CONFIG["output_file"]
        self.input_sheet = config.EXCEL_CONFIG["input_sheet"]
        self.output_sheet = config.EXCEL_CONFIG["output_sheet"]
        self._ensure_directories()

    def _ensure_directories(self):
        """确保目录存在"""
        Path(self.output_file).parent.mkdir(parents=True, exist_ok=True)

    def read_keywords(self, column: str = None) -> List[str]:
        """
        从Excel读取搜索关键词

        Args:
            column: 列名，默认从配置读取

        Returns:
            List[str]: 关键词列表
        """
        column = column or config.EXCEL_CONFIG["input_keyword_column"]

        try:
            df = pd.read_excel(self.input_file, sheet_name=self.input_sheet)
            if column not in df.columns:
                print(f"列 '{column}' 不存在于Excel中")
                print(f"可用列: {list(df.columns)}")
                return []

            keywords = df[column].dropna().tolist()
            # 确保都是字符串
            keywords = [str(k) for k in keywords if str(k).strip()]
            print(f"从Excel读取到 {len(keywords)} 个关键词")
            return keywords

        except FileNotFoundError:
            print(f"输入文件不存在: {self.input_file}")
            return []
        except Exception as e:
            print(f"读取Excel文件失败: {e}")
            return []

    def read_all_data(self) -> pd.DataFrame:
        """读取整个Excel文件"""
        try:
            df = pd.read_excel(self.input_file, sheet_name=self.input_sheet)
            print(f"读取到 {len(df)} 行数据")
            return df
        except FileNotFoundError:
            print(f"文件不存在: {self.input_file}")
            return pd.DataFrame()
        except Exception as e:
            print(f"读取Excel失败: {e}")
            return pd.DataFrame()

    def write_data(self, data: List[Dict[str, Any]], columns: List[str] = None) -> bool:
        """
        将数据写入Excel

        Args:
            data: 数据列表
            columns: 列名列表，默认从配置读取

        Returns:
            bool: 是否成功
        """
        if not data:
            print("没有数据可写入")
            return False

        columns = columns or config.EXCEL_CONFIG["output_columns"]

        try:
            df = pd.DataFrame(data, columns=columns)

            # 追加模式：如果文件存在，则追加数据
            if os.path.exists(self.output_file):
                existing_df = pd.read_excel(self.output_file, sheet_name=self.output_sheet)
                df = pd.concat([existing_df, df], ignore_index=True)

            with pd.ExcelWriter(self.output_file, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name=self.output_sheet, index=False)

            print(f"成功写入 {len(data)} 条数据到: {self.output_file}")
            return True

        except Exception as e:
            print(f"写入Excel失败: {e}")
            return False

    def append_data(self, data: List[Dict[str, Any]]) -> bool:
        """追加数据到现有Excel"""
        if not data:
            return True

        try:
            # 读取现有数据
            if os.path.exists(self.output_file):
                existing_df = pd.read_excel(self.output_file, sheet_name=self.output_sheet)
                new_df = pd.DataFrame(data)
                df = pd.concat([existing_df, new_df], ignore_index=True)
            else:
                df = pd.DataFrame(data)

            # 写入
            with pd.ExcelWriter(self.output_file, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name=self.output_sheet, index=False)

            print(f"成功追加 {len(data)} 条数据")
            return True

        except Exception as e:
            print(f"追加数据失败: {e}")
            return False

    def read_output_data(self) -> pd.DataFrame:
        """读取输出文件的数据"""
        try:
            if os.path.exists(self.output_file):
                return pd.read_excel(self.output_file, sheet_name=self.output_sheet)
            return pd.DataFrame()
        except Exception as e:
            print(f"读取输出文件失败: {e}")
            return pd.DataFrame()

    def create_sample_input_file(self, keywords: List[str] = None):
        """创建示例输入文件"""
        if keywords is None:
            keywords = ["示例关键词1", "示例关键词2", "示例关键词3"]

        df = pd.DataFrame({
            config.EXCEL_CONFIG["input_keyword_column"]: keywords,
            "域名": ["example1.com", "example2.com", "example3.com"],  # Semrush用的域名
            "__gmitm参数": [config.SEMRUSH_CONFIG["params"].get("__gmitm", "")] * 3,  # 追踪参数
        })
        os.makedirs(os.path.dirname(self.input_file), exist_ok=True)
        df.to_excel(self.input_file, sheet_name=self.input_sheet, index=False)
        print(f"示例输入文件已创建: {self.input_file}")

    def create_sample_output_file(self):
        """创建示例输出文件"""
        sample_data = [
            {
                "序号": 1,
                "关键词": "示例",
                "搜索结果标题": "示例标题",
                "结果内容": "示例内容",
                "链接": "https://example.com",
                "抓取时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
        ]
        columns = config.EXCEL_CONFIG["output_columns"]
        df = pd.DataFrame(sample_data, columns=columns)
        df.to_excel(self.output_file, sheet_name=self.output_sheet, index=False)
        print(f"示例输出文件已创建: {self.output_file}")
