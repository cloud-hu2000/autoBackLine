"""
搜索模块
实现读取Excel数据并在网站上进行批量搜索
"""

import time

from typing import List, Dict, Any, Optional
from datetime import datetime

from browser.browser_manager import BrowserManager
import config
from data.excel_handler import ExcelHandler


class SearchHandler:
    """搜索处理器"""

    def __init__(self, browser: BrowserManager):
        self.browser = browser
        self.excel_handler = ExcelHandler()
        self.search_url = config.SEARCH_CONFIG.get("search_url")

    def search_keyword(self, keyword: str) -> List[Dict[str, Any]]:
        """
        搜索单个关键词

        Args:
            keyword: 搜索关键词

        Returns:
            List[Dict[str, Any]]: 搜索结果列表
        """
        results = []
        try:
            print(f"搜索关键词: {keyword}")

            # 导航到搜索页面
            self.browser.navigate(self.search_url)
            self.browser.wait_for_navigation()

            # 输入搜索关键词
            search_input = config.SEARCH_CONFIG.get("search_input")
            if search_input:
                self.browser.fill(search_input, keyword)
                print(f"已输入关键词: {keyword}")
            else:
                print("错误: 未配置搜索输入框选择器")
                return results

            # 点击搜索按钮
            search_button = config.SEARCH_CONFIG.get("search_button")
            if search_button:
                self.browser.click(search_button)
                print("已点击搜索按钮")
            else:
                print("错误: 未配置搜索按钮选择器")
                return results

            # 等待结果加载
            self.browser.wait_for_navigation()

            # 抓取结果
            results = self._parse_search_results(keyword)
            print(f"找到 {len(results)} 条结果")

        except Exception as e:
            print(f"搜索关键词 '{keyword}' 时出错: {e}")
            self.browser.save_screenshot(f"search_error_{keyword}")

        return results

    def search_from_excel(self, keywords: List[str] = None) -> List[Dict[str, Any]]:
        """
        从Excel读取关键词并批量搜索

        Args:
            keywords: 关键词列表，默认从Excel读取

        Returns:
            List[Dict[str, Any]]: 所有搜索结果
        """
        if keywords is None:
            keywords = self.excel_handler.read_keywords()

        if not keywords:
            print("没有可搜索的关键词")
            return []

        all_results = []

        for idx, keyword in enumerate(keywords, 1):
            print(f"\n[{idx}/{len(keywords)}] 搜索: {keyword}")
            results = self.search_keyword(keyword)

            # 为每个结果添加序号和关键词
            for i, result in enumerate(results):
                result["序号"] = len(all_results) + i + 1
                result["关键词"] = keyword
                result["抓取时间"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            all_results.extend(results)

            # 保存进度
            if results:
                self.excel_handler.append_data(results)
                print(f"已保存 {len(results)} 条结果到Excel")

            # 随机延迟，避免请求过快
            if idx < len(keywords):
                import random
                delay = random.uniform(2, 5)
                print(f"等待 {delay:.1f} 秒后继续...")
                time.sleep(delay)

        print(f"\n批量搜索完成，总计: {len(all_results)} 条结果")
        return all_results

    def _parse_search_results(self, keyword: str) -> List[Dict[str, Any]]:
        """解析搜索结果页面"""
        results = []
        try:
            result_selector = config.SEARCH_CONFIG.get("result_selector")
            if not result_selector:
                print("未配置搜索结果选择器")
                return results

            # 等待结果加载
            self.browser.wait_for_selector(result_selector, timeout=10000)

            # 获取所有结果项
            result_items = self.browser.page.query_selector_all(result_selector)
            item_selectors = config.SEARCH_CONFIG.get("result_item_selectors", {})

            for item in result_items:
                result_data = {}

                # 提取标题
                title_selector = item_selectors.get("title", "")
                if title_selector:
                    try:
                        title_elem = item.query_selector(title_selector)
                        result_data["搜索结果标题"] = title_elem.inner_text().strip() if title_elem else ""
                    except Exception:
                        result_data["搜索结果标题"] = ""
                else:
                    result_data["搜索结果标题"] = ""

                # 提取内容
                content_selector = item_selectors.get("content", "")
                if content_selector:
                    try:
                        content_elem = item.query_selector(content_selector)
                        result_data["结果内容"] = content_elem.inner_text().strip() if content_elem else ""
                    except Exception:
                        result_data["结果内容"] = ""
                else:
                    result_data["结果内容"] = ""

                # 提取链接
                link_selector = item_selectors.get("link", "a")
                try:
                    link_elem = item.query_selector(link_selector)
                    result_data["链接"] = link_elem.get_attribute("href") if link_elem else ""
                except Exception:
                    result_data["链接"] = ""

                results.append(result_data)

        except Exception as e:
            print(f"解析搜索结果时出错: {e}")

        return results
