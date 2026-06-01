"""
节点选择模块
实现选择节点和打开连接的功能
"""

import time
import re
from typing import Optional

from browser.browser_manager import BrowserManager
import config


class NodeSelector:
    """节点选择器"""

    def __init__(self, browser: BrowserManager):
        self.browser = browser

    def navigate_to_home(self) -> bool:
        """导航到首页"""
        home_url = config.SITE_CONFIG.get("home_url")
        if home_url:
            print(f"导航到首页: {home_url}")
            self.browser.navigate(home_url)
            time.sleep(2)
            return True
        return False

    def select_node(self, node_text: str = None) -> bool:
        """
        选择节点

        Args:
            node_text: 节点名称/文本，如果为None则使用配置中的默认节点

        Returns:
            bool: 是否选择成功
        """
        node_text = node_text or config.NODE_CONFIG.get("default_node")

        if not node_text:
            print("错误: 未指定节点名称")
            return False

        print(f"开始选择节点: {node_text}")

        # 获取节点选择器配置
        selectors = config.NODE_SELECTORS

        # 保存点击前的页面状态
        self.browser.save_screenshot("before_click_dropdown")

        # ====== 首先尝试直接点击 nb-select 按钮打开下拉框 ======
        print("尝试点击 nb-select 按钮...")
        try:
            # 查找 select-button 元素
            select_button = self.browser.page.query_selector("nb-select button.select-button")
            if select_button:
                print("找到 select-button，点击它...")
                select_button.click()
                print("点击成功")
                time.sleep(1)
        except Exception as e:
            print(f"点击 select-button 失败: {e}")
            # 备选：尝试点击 nb-select
            try:
                nb_select = self.browser.page.query_selector("nb-select")
                if nb_select:
                    nb_select.click()
                    print("点击 nb-select 成功")
                    time.sleep(1)
            except Exception as e2:
                print(f"点击 nb-select 也失败: {e2}")

        # 保存点击下拉框后的页面状态
        self.browser.save_screenshot("after_click_dropdown")

        try:
            # 等待下拉选项出现 - 使用 nb-option-list 或 nb-option
            print("等待下拉选项出现...")
            try:
                # 尝试等待 nb-option-list
                self.browser.page.wait_for_selector("nb-option-list", timeout=3000)
                print("nb-option-list 已出现")
            except:
                try:
                    # 尝试等待 nb-option
                    self.browser.page.wait_for_selector("nb-option", timeout=3000)
                    print("nb-option 已出现")
                except Exception as e:
                    print(f"等待选项出现超时: {e}")
                    # 保存页面HTML用于调试
                    print("保存当前页面HTML...")
                    html = self.browser.page.content()
                    with open("logs/debug_page_html.html", "w", encoding="utf-8") as f:
                        f.write(html)

            # ====== 方式1: 查找 nb-option 元素 ======
            found = False
            options = self.browser.page.query_selector_all("nb-option")
            print(f"找到 {len(options)} 个 nb-option 选项")

            if options:
                for option in options:
                    try:
                        option_text = option.inner_text()
                        print(f"  选项: '{option_text}'")
                        if node_text in option_text:
                            print(f"匹配到目标节点: '{node_text}' 在 '{option_text}' 中")
                            option.click()
                            print(f"已选择节点: {option_text}")
                            found = True
                            time.sleep(1)
                            break
                    except Exception as e:
                        print(f"处理节点选项出错: {e}")
                        continue

            # ====== 方式2: 如果 nb-option 没找到，查找 nb-select-option ======
            if not found:
                options = self.browser.page.query_selector_all("nb-select-option")
                print(f"找到 {len(options)} 个 nb-select-option 选项")

                for option in options:
                    try:
                        option_text = option.inner_text()
                        print(f"  选项: '{option_text}'")
                        if node_text in option_text:
                            print(f"匹配到目标节点: '{node_text}' 在 '{option_text}' 中")
                            option.click()
                            print(f"已选择节点: {option_text}")
                            found = True
                            time.sleep(1)
                            break
                    except Exception as e:
                        print(f"处理节点选项出错: {e}")
                        continue

            # ====== 方式3: 如果方式1和2都没找到，查找按钮元素 ======
            if not found:
                print(f"在选项列表中未找到'{node_text}'，尝试查找按钮元素...")
                buttons = self.browser.page.query_selector_all("button")
                print(f"找到 {len(buttons)} 个按钮")

                for i, btn in enumerate(buttons):
                    try:
                        btn_text = btn.inner_text()
                        print(f"  Button {i+1}: '{btn_text[:80]}'")
                        if node_text in btn_text:
                            print(f"匹配到目标节点按钮: '{node_text}'")
                            btn.click()
                            print(f"已点击节点按钮")
                            found = True
                            time.sleep(1)
                            break
                    except Exception as e:
                        print(f"点击按钮出错: {e}")
                        continue

            # ====== 方式4: 使用 XPath ======
            if not found:
                print(f"尝试使用XPath按文本选择...")
                xpath_selectors = [
                    f"//nb-option[contains(text(), '{node_text}')]",
                    f"//nb-select-option[contains(text(), '{node_text}')]",
                    f"//button[contains(text(), '{node_text}')]",
                ]
                for xpath_selector in xpath_selectors:
                    print(f"尝试 XPath: {xpath_selector}")
                    try:
                        self.browser.page.click(xpath_selector)
                        print(f"已通过XPath选择节点: {node_text}")
                        found = True
                        time.sleep(1)
                        break
                    except Exception as e:
                        print(f"XPath {xpath_selector} 失败: {e}")
                        continue

            if not found:
                print(f"未找到包含'{node_text}'的节点")
                # 列出所有按钮用于调试
                print("列出所有按钮元素:")
                buttons = self.browser.page.query_selector_all("button")
                for i, btn in enumerate(buttons[:10]):
                    try:
                        btn_text = btn.inner_text()[:80]
                        print(f"  Button {i+1}: {btn_text}")
                    except:
                        pass

            return found

        except Exception as e:
            print(f"选择节点出错: {e}")
            import traceback
            print(traceback.format_exc())
            return False

    def click_open_button(self) -> bool:
        """点击打开按钮"""
        print("点击打开按钮...")

        selectors = config.NODE_SELECTORS
        open_button = selectors.get("open_button")
        print(f"打开按钮选择器: {open_button}")

        if open_button:
            # 先尝试用 Playwright 的 click() 方法（支持 :has-text 等 Playwright 专属语法）
            try:
                # 记录点击前的页面数量
                pages_before = len(self.browser.context.pages)
                print(f"点击前页面数: {pages_before}")

                print(f"尝试使用Playwright点击: {open_button}")
                self.browser.page.click(open_button, timeout=5000)
                print("已点击打开按钮")
                time.sleep(2)

                # 检查是否打开了新标签页
                pages_after = len(self.browser.context.pages)
                print(f"点击后页面数: {pages_after}")

                if pages_after > pages_before:
                    # 切换到新标签页
                    new_page = self.browser.context.pages[-1]
                    self.browser.page = new_page
                    print(f"已切换到新标签页: {new_page.url}")

                return True
            except Exception as e:
                print(f"Playwright点击失败: {e}")
                print("尝试备选选择器...")

        # 备选：逐个尝试 Playwright 支持的选择器
        backup_selectors = [
            'button:has-text("打开")',
            'button.nb-button',
            'button.appearance-filled',
            'nb-button',
        ]
        for sel in backup_selectors:
            print(f"尝试备选选择器: {sel}")
            try:
                pages_before = len(self.browser.context.pages)
                self.browser.page.click(sel, timeout=5000)
                print(f"已通过Playwright点击: {sel}")
                time.sleep(2)

                pages_after = len(self.browser.context.pages)
                if pages_after > pages_before:
                    new_page = self.browser.context.pages[-1]
                    self.browser.page = new_page
                    print(f"已切换到新标签页: {new_page.url}")

                return True
            except Exception as e2:
                print(f"选择器 {sel} 失败: {e2}")
                continue

        print("所有打开按钮选择器都失败了")
        return False

    def select_node_and_open(self, node_text: str = None) -> bool:
        """
        选择节点并打开连接

        Args:
            node_text: 节点名称

        Returns:
            bool: 是否成功
        """
        print("\n" + "=" * 50)
        print("步骤2: 选择节点并打开")
        print("=" * 50)

        # 先导航到首页（如果不在首页）
        current_url = self.browser.page.url
        print(f"当前URL: {current_url}")
        if '/page/m/home' not in current_url:
            print("当前不在首页，导航到首页...")
            self.navigate_to_home()
        else:
            print("已在首页")

        # 等待页面加载
        time.sleep(2)

        # 保存页面截图用于调试
        self.browser.save_screenshot("before_select_node")

        # 选择节点
        print(f"准备选择节点: {node_text}")
        if not self.select_node(node_text):
            print("选择节点失败")
            self.browser.save_screenshot("select_node_failed")
            return False
        print("节点选择成功")

        # 点击打开按钮
        print("准备点击打开按钮...")
        if not self.click_open_button():
            print("点击打开按钮失败")
            self.browser.save_screenshot("click_open_failed")
            return False
        print("打开按钮点击成功")

        print("节点选择并打开成功!")
        return True

    def get_next_node(self, current_node: str) -> Optional[str]:
        """根据当前节点名称返回下一个节点名称（如 节点17 → 节点18）"""
        match = re.search(r'\d+', current_node)
        if not match:
            return None
        num = int(match.group())
        next_num = num + 1
        next_node = re.sub(r'\d+', str(next_num), current_node, count=1)
        print(f"当前节点: {current_node} → 下一个节点: {next_node}")
        return next_node
