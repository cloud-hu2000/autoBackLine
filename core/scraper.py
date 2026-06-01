"""
数据抓取模块
实现从网站抓取数据
"""

from typing import List, Dict, Any, Optional
from datetime import datetime

from browser.browser_manager import BrowserManager
import config


class DataScraper:
    """数据抓取器"""

    def __init__(self, browser: BrowserManager):
        self.browser = browser
        self.data: List[Dict[str, Any]] = []

    def scrape(self, url: str = None, max_pages: int = None) -> List[Dict[str, Any]]:
        """
        抓取数据

        Args:
            url: 数据页面URL，默认从配置读取
            max_pages: 最大抓取页数，默认从配置读取

        Returns:
            List[Dict[str, Any]]: 抓取的数据列表
        """
        url = url or config.SCRAPE_CONFIG.get("data_url")
        max_pages = max_pages or config.SCRAPE_CONFIG["pagination"]["max_pages"]

        print(f"开始抓取数据，URL: {url}")
        self.browser.navigate(url)
        self.browser.wait_for_navigation()

        # 抓取第一页
        page_data = self._scrape_page()
        self.data.extend(page_data)
        print(f"第1页: 抓取到 {len(page_data)} 条数据")

        # 翻页抓取
        pagination_config = config.SCRAPE_CONFIG.get("pagination", {})
        if pagination_config.get("enabled", False):
            next_button = pagination_config.get("next_button")
            for page in range(2, max_pages + 1):
                if not self._go_to_next_page(next_button):
                    print(f"无法翻到第 {page} 页，停止抓取")
                    break

                page_data = self._scrape_page()
                self.data.extend(page_data)
                print(f"第{page}页: 抓取到 {len(page_data)} 条数据")

        print(f"总计抓取: {len(self.data)} 条数据")
        return self.data

    def _scrape_page(self) -> List[Dict[str, Any]]:
        """抓取当前页面的数据"""
        page_data = []
        try:
            # 获取表格或数据容器
            table_selector = config.SCRAPE_CONFIG.get("table_selector")
            rows_selector = config.SCRAPE_CONFIG.get("rows_selector")
            columns_config = config.SCRAPE_CONFIG.get("columns", [])

            if not table_selector or not rows_selector:
                print("警告: 未配置表格选择器")
                return page_data

            # 等待表格加载
            self.browser.wait_for_selector(table_selector, timeout=10000)

            # 获取所有行
            rows = self.browser.page.query_selector_all(rows_selector)

            for idx, row in enumerate(rows):
                row_data = {}
                for col in columns_config:
                    col_name = col["name"]
                    col_selector = col["selector"]
                    try:
                        cell = row.query_selector(col_selector)
                        row_data[col_name] = cell.inner_text().strip() if cell else ""
                    except Exception:
                        row_data[col_name] = ""

                row_data["抓取时间"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                page_data.append(row_data)

        except Exception as e:
            print(f"抓取页面数据时出错: {e}")

        return page_data

    def _go_to_next_page(self, next_button_selector: str) -> bool:
        """翻到下一页"""
        try:
            # 检查是否有下一页
            next_btn = self.browser.page.query_selector(next_button_selector)
            if not next_btn:
                print("未找到下一页按钮")
                return False

            # 检查按钮是否可用（可能被禁用）
            if next_btn.is_disabled() or next_btn.is_hidden():
                print("已到达最后一页")
                return False

            # 点击下一页
            next_btn.click()
            self.browser.wait_for_navigation()
            return True

        except Exception as e:
            print(f"翻页失败: {e}")
            return False

    def get_data(self) -> List[Dict[str, Any]]:
        """获取已抓取的数据"""
        return self.data

    def clear_data(self):
        """清空数据"""
        self.data = []

    def export_to_dict(self) -> List[Dict[str, Any]]:
        """导出为字典列表"""
        return self.data
