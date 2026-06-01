"""
浏览器管理模块
封装Playwright的浏览器操作
"""

import os
import re
import time
import random
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any

from playwright.sync_api import sync_playwright, Browser, Page, BrowserContext
from fake_useragent import UserAgent

import config
from utils.retry import retry_on_failure


class BrowserManager:
    """浏览器管理器"""

    def __init__(self):
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.ua = UserAgent()

    def start(self):
        """启动浏览器"""
        self.playwright = sync_playwright().start()

        use_existing = config.BROWSER_CONFIG.get("use_existing_chrome", False)

        if use_existing:
            # 使用已有的Chrome浏览器（通过远程调试连接）
            print("尝试连接已有Chrome浏览器...")
            try:
                import socket
                import json
                import urllib.request

                debug_port = config.BROWSER_CONFIG.get("chrome_remote_debugging_port", 9222)

                # 等待Chrome调试端口就绪
                max_retries = 10
                for i in range(max_retries):
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    result = sock.connect_ex(('127.0.0.1', debug_port))
                    sock.close()
                    if result == 0:
                        print(f"端口 {debug_port} 已就绪")
                        break
                    print(f"等待Chrome调试端口就绪... ({i+1}/{max_retries})")
                    time.sleep(1)

                # 获取WebSocket连接URL
                print("获取Chrome DevTools WebSocket地址...")
                ws_url = None
                for attempt in range(20):  # 增加重试次数到20次
                    try:
                        time.sleep(1)  # 每次尝试前等待1秒
                        req = urllib.request.Request(f"http://localhost:{debug_port}/json/version")
                        with urllib.request.urlopen(req, timeout=10) as response:
                            data = json.loads(response.read().decode())
                            ws_url = data.get("webSocketDebuggerUrl")
                            if ws_url:
                                print(f"获取到WebSocket地址: {ws_url[:50]}...")
                                break
                    except Exception as e:
                        print(f"获取WebSocket地址尝试 {attempt+1}/20 失败: {e}")
                        time.sleep(1)

                if not ws_url:
                    raise Exception("无法获取Chrome DevTools WebSocket地址")

                # 通过WebSocket连接
                self.browser = self.playwright.chromium.connect_over_cdp(ws_url)
                print(f"成功连接到已有Chrome浏览器")

                # 获取现有context
                contexts = self.browser.contexts
                if contexts:
                    self.context = contexts[0]
                    pages = self.context.pages
                    if pages:
                        self.page = pages[0]
                    else:
                        self.page = self.context.new_page()
                else:
                    # 如果没有context，创建新的
                    self.context = self.browser.new_context()
                    self.page = self.context.new_page()

            except Exception as e:
                print(f"连接已有Chrome失败: {e}")
                print("将使用系统Chrome启动新浏览器...")
                chrome_path = config.BROWSER_CONFIG.get("chrome_path")
                launch_options = {"headless": False}
                if chrome_path:
                    launch_options["executable_path"] = chrome_path
                self.browser = self.playwright.chromium.launch(**launch_options)
                self.context = self.browser.new_context()
                self.page = self.context.new_page()
        else:
            # 浏览器启动参数优化
            launch_options = {
                "headless": config.BROWSER_CONFIG["headless"],
                "slow_mo": config.BROWSER_CONFIG["slow_mo"],
            }

            self.browser = self.playwright.chromium.launch(**launch_options)

            # 创建浏览器上下文，添加性能优化
            context_options = {
                "viewport": config.BROWSER_CONFIG["viewport"],
                "user_agent": self.ua.random,
                "ignore_https_errors": True,
            }

            self.context = self.browser.new_context(**context_options)
            self.page = self.context.new_page()

        # 设置请求拦截，进一步提升速度
        if config.BROWSER_CONFIG.get("disable_images"):
            def handle_route(route):
                resource_type = route.request.resource_type
                if resource_type in ["image", "font", "media"]:
                    route.abort()
                elif resource_type in ["document", "script", "xhr", "fetch"]:
                    route.continue_()
                else:
                    route.continue_()
            self.page.route("**/*", handle_route)

        self._ensure_directories()
        return self

    def _ensure_directories(self):
        """确保必要的目录存在"""
        Path(config.BROWSER_CONFIG["user_data_dir"]).mkdir(parents=True, exist_ok=True)
        Path(config.BROWSER_CONFIG["screenshot_dir"]).mkdir(parents=True, exist_ok=True)

    def navigate(self, url: str, wait_until: str = "domcontentloaded") -> bool:
        """导航到指定URL"""
        try:
            self.page.goto(url, timeout=config.SITE_CONFIG["timeout"], wait_until=wait_until)
            # 跳过耗时的 networkidle 等待，改用固定短延迟
            time.sleep(1)
            return True
        except Exception as e:
            print(f"导航失败: {url}, 错误: {e}")
            return False

    def wait_for_selector(self, selector: str, timeout: int = 30000) -> Optional[Page]:
        """等待元素出现"""
        try:
            return self.page.wait_for_selector(selector, timeout=timeout)
        except Exception as e:
            print(f"等待元素失败: {selector}, 错误: {e}")
            return None

    def click(self, selector: str, force: bool = False) -> bool:
        """
        点击元素

        Args:
            selector: CSS 选择器
            force: True 时绕过等待，直接用 JS 点击（用于被遮挡的元素）
        """
        if force:
            try:
                self.page.evaluate(f"""
                    () => {{
                        const el = document.querySelector('{selector}');
                        if (el) el.click();
                    }}
                """)
                self.random_delay()
                return True
            except Exception as e:
                print(f"JS点击失败: {selector}, 错误: {e}")
                return False

        try:
            self.page.click(selector)
            self.random_delay()
            return True
        except Exception as e:
            print(f"点击失败: {selector}, 错误: {e}")
            try:
                self.page.evaluate(f"""
                    () => {{
                        const el = document.querySelector('{selector}');
                        if (el) el.click();
                    }}
                """)
                self.random_delay()
                return True
            except:
                return False

    def fill(self, selector: str, value: str) -> bool:
        """填写表单"""
        try:
            self.page.fill(selector, value)
            return True
        except Exception as e:
            print(f"填写失败: {selector}, 错误: {e}")
            return False

    def type_slowly(self, selector: str, text: str, delay: int = 50) -> bool:
        """模拟人工输入"""
        try:
            self.page.type(selector, text, delay=delay)
            self.random_delay()
            return True
        except Exception as e:
            print(f"输入失败: {selector}, 错误: {e}")
            return False

    def get_text(self, selector: str) -> Optional[str]:
        """获取元素文本"""
        try:
            element = self.page.query_selector(selector)
            return element.inner_text() if element else None
        except Exception as e:
            print(f"获取文本失败: {selector}, 错误: {e}")
            return None

    def get_attribute(self, selector: str, attribute: str) -> Optional[str]:
        """获取元素属性"""
        try:
            element = self.page.query_selector(selector)
            return element.get_attribute(attribute) if element else None
        except Exception as e:
            print(f"获取属性失败: {selector}, 错误: {e}")
            return None

    def get_all_text(self, selector: str) -> list:
        """获取所有匹配元素的文本"""
        try:
            elements = self.page.query_selector_all(selector)
            return [el.inner_text() for el in elements]
        except Exception as e:
            print(f"获取所有文本失败: {selector}, 错误: {e}")
            return []

    def evaluate(self, script: str) -> Any:
        """执行JavaScript代码"""
        try:
            return self.page.evaluate(script)
        except Exception as e:
            print(f"执行JS失败: {script[:50]}..., 错误: {e}")
            return None

    def save_screenshot(self, name: Optional[str] = None) -> str:
        """保存截图"""
        if name is None:
            name = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", str(name))
        if len(safe_name) > 200:
            safe_name = safe_name[:200]
        filepath = os.path.join(
            config.BROWSER_CONFIG["screenshot_dir"],
            f"{safe_name}.png"
        )
        try:
            self.page.screenshot(path=filepath, full_page=True)
        except Exception as e:
            print(f"截图保存失败 [{filepath}]: {e}")
        return filepath

    def save_cookies(self, filepath: str):
        """保存Cookies"""
        cookies = self.context.cookies()
        import json
        with open(filepath, 'w') as f:
            json.dump(cookies, f)

    def load_cookies(self, filepath: str):
        """加载Cookies"""
        import json
        try:
            with open(filepath, 'r') as f:
                cookies = json.load(f)
            self.context.add_cookies(cookies)
            return True
        except FileNotFoundError:
            print(f"Cookie文件不存在: {filepath}")
            return False
        except Exception as e:
            print(f"加载Cookie失败: {e}")
            return False

    def is_logged_in(self) -> bool:
        """检查是否已登录"""
        try:
            current_url = self.page.url
            
            print(f"当前URL用于登录检测: {current_url}")
            
            # 获取URL的hash部分（#后面的内容）
            if '#' in current_url:
                hash_part = current_url.split('#')[-1]
            else:
                hash_part = ''
            
            print(f"Hash部分: {hash_part}")
            
            # 检查hash是否是登录相关路径（精确匹配）
            # 常见登录路径: /login, /login/, #/login
            if hash_part in ['/login', '/login/', '/signin', '/signin/', '/zh-Hans/login', '/zh-Hans/login/']:
                print(f"检测到未登录状态，hash为: {hash_part}")
                return False
            
            # 检查URL是否仍然包含login但不是登录后跳转的页面
            if 'login' in current_url.lower() and '/page/' not in hash_part and '/home' not in hash_part:
                print("URL中包含login但不是有效页面")
                return False
            
            # 如果hash包含有效页面路径（不是login），则认为已登录
            if hash_part and '/page/' in hash_part:
                print(f"检测到已登录，hash为: {hash_part}")
                # 额外检查：也可以尝试查找登录成功的标识元素
                indicator = config.LOGIN_SELECTORS.get("logged_in_indicator")
                if indicator:
                    try:
                        element = self.page.query_selector(indicator)
                        if element is not None:
                            print("通过元素选择器检测到已登录")
                            return True
                    except:
                        pass
                return True
            
            # 备选：如果不在登录页面，也认为已登录
            if not hash_part.startswith('/login') and not hash_part.startswith('/signin'):
                if hash_part and len(hash_part) > 1:
                    print(f"通过hash判断已登录: {hash_part}")
                    return True
            
            return False
        except Exception as e:
            print(f"检查登录状态出错: {e}")
            return False

    def random_delay(self):
        """随机延迟，模拟人工操作"""
        delay = random.uniform(
            config.ANTI_BAN_CONFIG["random_delay_min"],
            config.ANTI_BAN_CONFIG["random_delay_max"]
        )
        time.sleep(delay)

    def scroll_to_bottom(self):
        """滚动到页面底部"""
        self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        self.random_delay()

    def scroll_to_element(self, selector: str):
        """滚动到指定元素"""
        try:
            self.page.evaluate(f"""
                const element = document.querySelector('{selector}');
                if (element) element.scrollIntoView();
            """)
            self.random_delay()
        except Exception as e:
            print(f"滚动到元素失败: {selector}, 错误: {e}")

    def wait_for_navigation(self, timeout: int = 30000):
        """等待导航完成"""
        try:
            # 使用 commit 等待，比 networkidle 快很多
            self.page.wait_for_load_state("commit", timeout=timeout)
            time.sleep(0.5)  # 短暂等待DOM渲染
        except Exception as e:
            print(f"等待导航失败: {e}")

    def close(self):
        """关闭浏览器"""
        use_existing = config.BROWSER_CONFIG.get("use_existing_chrome", False)

        try:
            if use_existing:
                # 连接到外部 Chrome 时只断开 CDP，不关闭页面或默认上下文。
                # 否则会把 debug Chrome 一起关掉，后续插件上传步骤会失去 9222 端口。
                if self.browser:
                    self.browser.close()
                if self.playwright:
                    self.playwright.stop()
                print("已断开与Chrome的连接")
                return

            if self.page:
                self.page.close()
            if self.context:
                self.context.close()

            # 使用Playwright启动的浏览器，正常关闭
            if self.browser:
                self.browser.close()
            if self.playwright:
                self.playwright.stop()
        except Exception as e:
            print(f"关闭浏览器时出错: {e}")

    def __enter__(self):
        return self.start()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
