"""
登录模块
实现网站自动登录功能
"""

import os
import time
from pathlib import Path
from typing import Optional
from datetime import datetime

from browser.browser_manager import BrowserManager
import config


class LoginHandler:
    """登录处理器"""

    def __init__(self, browser: BrowserManager):
        self.browser = browser
        self.cookie_file = os.path.join(
            config.BROWSER_CONFIG["user_data_dir"],
            "cookies.json"
        )
        self.gmitm: Optional[str] = None  # 登录成功后从URL中提取

    def _extract_gmitm_from_url(self, url: str) -> Optional[str]:
        """从URL中提取 __gmitm 参数"""
        try:
            from urllib.parse import parse_qs, urlparse
            parsed = urlparse(url)
            query_params = parse_qs(parsed.query)
            gmitm_list = query_params.get("__gmitm", [])
            if gmitm_list:
                return gmitm_list[0]
        except Exception as e:
            print(f"提取 __gmitm 失败: {e}")
        return None

    def _fetch_gmitm(self) -> bool:
        """
        登录成功后，访问 Semrush 首页以获取 __gmitm 参数
        """
        try:
            backlinks_url = config.SEMRUSH_CONFIG.get("backlinks_url", "https://sem.3ue.co/analytics/backlinks/backlinks/")
            print(f"访问 Semrush 页面以获取 __gmitm: {backlinks_url}")
            self.browser.navigate(backlinks_url)
            time.sleep(2)
            current_url = self.browser.page.url
            print(f"Semrush 当前URL: {current_url}")
            self.gmitm = self._extract_gmitm_from_url(current_url)
            if self.gmitm:
                print(f"已获取 __gmitm: {self.gmitm}")
                return True
            else:
                print("警告: 未能从URL中提取 __gmitm")
                return False
        except Exception as e:
            print(f"获取 __gmitm 出错: {e}")
            return False

    def login(self, username: str = None, password: str = None, force: bool = False) -> bool:
        """
        执行登录操作

        Args:
            username: 用户名，默认从配置读取
            password: 密码，默认从配置读取

        Returns:
            bool: 登录是否成功
        """
        username = username or config.LOGIN_CREDENTIALS.get("username")
        password = password or config.LOGIN_CREDENTIALS.get("password")

        if force:
            self._remove_cookies()

        # 如果当前已在首页，说明浏览器已有有效会话，跳过登录
        try:
            current_url = self.browser.page.url
        except Exception:
            current_url = ""

        if self._is_logged_in_page(current_url):
            print("检测到浏览器已在首页，跳过登录")
            return True

        # 尝试加载 Cookie 恢复登录状态
        if not force and self._load_cookies():
            print("已加载保存的Cookie，导航到首页...")
            self.browser.navigate(config.SITE_CONFIG["url"])
            # SPA页面需要时间重定向，等待并检测是否到达首页
            if self._wait_for_home_page(timeout=120):
                print("Cookie有效，已登录")
                return True
            print("Cookie可能已过期，需要重新登录")

        # 需要重新登录
        return self._do_login(username, password)

    def is_on_login_page(self) -> bool:
        """判断当前页面是否是登录页。"""
        try:
            url = self.browser.page.url
            hash_part = url.split("#")[-1] if "#" in url else url
            if "/login" in hash_part or "/signin" in hash_part:
                return True
            visible_text = self._get_body_text()
            if self._looks_like_login_text(visible_text):
                return True
        except Exception:
            return False
        return False

    def _get_body_text(self) -> str:
        try:
            return self.browser.page.locator("body").inner_text(timeout=1000)
        except Exception:
            return ""

    def _looks_like_login_text(self, text: str) -> bool:
        if not text:
            return False
        logged_in_markers = [
            "用户中心",
            "套餐中心",
            "我的订阅",
            "我的工单",
            "使用兑换码",
        ]
        if any(marker in text for marker in logged_in_markers):
            return False
        login_markers = [
            "登录",
            "Welcome",
            "用户名",
            "密码",
            "没有账号",
            "去注册",
        ]
        return sum(1 for marker in login_markers if marker in text) >= 2

    def _wait_for_home_page(self, timeout: int = 120) -> bool:
        """
        轮询等待URL变为首页，成功返回True，超时返回False
        """
        print("等待页面跳转到首页...")
        start = time.time()
        while time.time() - start < timeout:
            try:
                url = self.browser.page.url
                if "/page/m/home" in url or self._is_logged_in_page(url):
                    print(f"已检测到登录成功页面: {url}")
                    return True
            except Exception:
                pass
            time.sleep(0.5)
        print(f"等待首页跳转超时（{timeout}秒）")
        return False

    def _is_logged_in_page(self, url: str = "") -> bool:
        """判断当前页面是否已经处于登录后状态。"""
        try:
            url = url or self.browser.page.url
            hash_part = url.split("#")[-1] if "#" in url else ""

            if "/login" in hash_part or "/signin" in hash_part:
                return False

            username = config.LOGIN_CREDENTIALS.get("username", "")
            visible_text = self._get_body_text()
            if self._looks_like_login_text(visible_text):
                return False

            logged_in_text_markers = [
                username,
                "用户中心",
                "套餐中心",
                "我的订阅",
                "我的工单",
                "使用兑换码",
            ]
            if visible_text and any(marker and marker in visible_text for marker in logged_in_text_markers):
                return True

            if "/page/" in hash_part or "/page/" in url:
                return True

            indicators = [
                config.LOGIN_SELECTORS.get("logged_in_indicator", ""),
                ".user-info",
                ".username",
                "[data-testid='user-menu']",
            ]
            for selector in [s for s in indicators if s]:
                try:
                    locator = self.browser.page.locator(selector).first
                    if locator.count() > 0 and locator.is_visible(timeout=1000):
                        return True
                except Exception:
                    continue
        except Exception:
            return False
        return False

    def _click_login_button(self, selector: str) -> bool:
        """Click the enabled Nebular submit button observed on the login page."""
        page = self.browser.page
        selectors = [s.strip() for s in selector.split(",") if s.strip()]
        selectors.extend([
            "button[nbbutton]",
            "button[type='submit']",
            "button.appearance-filled",
            "input[type='submit']",
        ])

        for candidate in selectors:
            try:
                locator = page.locator(candidate).first
                if locator.count() == 0:
                    continue
                locator.wait_for(state="visible", timeout=3000)
                locator.scroll_into_view_if_needed(timeout=3000)
                handle = locator.element_handle(timeout=3000)
                if handle:
                    try:
                        page.wait_for_function(
                            "(el) => !el.disabled && el.getAttribute('aria-disabled') !== 'true'",
                            arg=handle,
                            timeout=10000,
                        )
                    except Exception:
                        pass
                try:
                    locator.click(timeout=5000)
                except Exception:
                    locator.click(timeout=5000, force=True)
                print(f"已点击登录按钮: {candidate}")
                return True
            except Exception as e:
                print(f"登录按钮点击尝试失败: {candidate}, {e}")

        try:
            password_input = config.LOGIN_SELECTORS.get("password_input")
            if password_input:
                page.locator(password_input).first.press("Enter", timeout=3000)
                print("已通过密码框回车提交登录")
                return True
        except Exception as e:
            print(f"回车提交登录失败: {e}")

        return False

    def _ensure_login_submitted(self):
        """Submit again if the first click did not move the SPA away from login."""
        try:
            time.sleep(3)
            current_url = self.browser.page.url
            hash_part = current_url.split("#")[-1] if "#" in current_url else current_url
            if "/login" not in hash_part:
                return

            password_input = config.LOGIN_SELECTORS.get("password_input")
            if password_input:
                try:
                    self.browser.page.locator(password_input).first.press("Enter", timeout=3000)
                    print("登录页仍未跳转，已通过密码框回车再次提交")
                    time.sleep(2)
                except Exception as e:
                    print(f"密码框回车提交失败: {e}")

            current_url = self.browser.page.url
            hash_part = current_url.split("#")[-1] if "#" in current_url else current_url
            if "/login" not in hash_part:
                return

            clicked = self.browser.page.evaluate(
                """
                () => {
                  const buttons = Array.from(document.querySelectorAll('button, [role="button"], input[type="submit"]'));
                  const target = buttons.find((el) => {
                    const text = (el.innerText || el.value || '').trim();
                    return el.type === 'submit' || el.hasAttribute('nbbutton') || text.includes('登录');
                  });
                  if (!target) return false;
                  target.click();
                  return true;
                }
                """
            )
            if clicked:
                print("登录页仍未跳转，已通过页面脚本再次点击登录")
        except Exception as e:
            print(f"登录兜底提交失败: {e}")

    def _type_login_field(self, selector: str, value: str, field_name: str) -> bool:
        """Type into Angular controls so validation and submit state update."""
        try:
            locator = self.browser.page.locator(selector).first
            locator.wait_for(state="visible", timeout=15000)
            locator.click(timeout=5000)
            locator.press("Control+A", timeout=3000)
            locator.type(value, delay=35, timeout=30000)
            actual = locator.input_value(timeout=3000)
            if actual != value:
                print(f"{field_name} 输入后值不一致，尝试 fill 兜底")
                locator.fill(value, timeout=5000)
                actual = locator.input_value(timeout=3000)
            if actual != value:
                print(f"{field_name} 输入失败")
                return False
            return True
        except Exception as e:
            print(f"{field_name} 输入失败: {e}")
            return False

    def _wait_login_button_enabled(self) -> bool:
        """Wait for the login button to become enabled after form validation."""
        try:
            self.browser.page.wait_for_function(
                """
                () => Array.from(document.querySelectorAll('button, input[type="submit"]'))
                  .some((el) => {
                    const text = (el.innerText || el.value || '').trim();
                    return (el.type === 'submit' || el.hasAttribute('nbbutton') || text.includes('登录'))
                      && !el.disabled
                      && el.getAttribute('aria-disabled') !== 'true';
                  })
                """,
                timeout=15000,
            )
            return True
        except Exception as e:
            print(f"登录按钮未在预期时间内变为可点击: {e}")
            return False

    def _do_login(self, username: str, password: str) -> bool:
        """执行实际的登录操作"""
        try:
            # 导航到登录页面
            login_url = config.SITE_CONFIG.get("login_url", config.SITE_CONFIG["url"])
            print(f"导航到登录页面: {login_url}")
            self.browser.navigate(login_url)

            # 等待页面加载
            self.browser.wait_for_navigation()

            # 获取选择器
            selectors = config.LOGIN_SELECTORS

            # 输入用户名
            username_input = selectors.get("username_input")
            if username_input:
                if not self._type_login_field(username_input, username, "用户名"):
                    self.browser.save_screenshot("login_username_input_failed")
                    return False
                print(f"已输入用户名: {username}")
            else:
                print("错误: 未找到用户名输入框选择器")
                return False

            # 输入密码
            password_input = selectors.get("password_input")
            if password_input:
                if not self._type_login_field(password_input, password, "密码"):
                    self.browser.save_screenshot("login_password_input_failed")
                    return False
                print("已输入密码")
            else:
                print("错误: 未找到密码输入框选择器")
                return False

            if not self._wait_login_button_enabled():
                self.browser.save_screenshot("login_button_disabled")
                return False

            # 点击登录按钮
            submit_button = selectors.get("submit_button")
            if submit_button:
                print(f"使用选择器: {submit_button}")
                if not self._click_login_button(submit_button):
                    self.browser.save_screenshot("login_button_not_found")
                    print("登录按钮点击失败，请检查截图")
                    return False
                self._ensure_login_submitted()

                # 等待登录结果，轮询检测是否跳转到首页
                if self._wait_for_home_page(timeout=180):
                    print("登录成功!")
                    self._save_cookies()
                    return True
                # 超时说明登录失败
                self.browser.save_screenshot("login_failed")
                print("登录超时，请检查截图")
                return False
            else:
                print("错误: 未找到登录按钮选择器")
                return False

        except Exception as e:
            print(f"登录过程出错: {e}")
            self.browser.save_screenshot("login_error")
            return False

    def _save_cookies(self):
        """保存Cookies"""
        Path(config.BROWSER_CONFIG["user_data_dir"]).mkdir(parents=True, exist_ok=True)
        self.browser.save_cookies(self.cookie_file)
        print(f"Cookies已保存到: {self.cookie_file}")

    def _load_cookies(self) -> bool:
        """加载Cookies"""
        if not os.path.exists(self.cookie_file):
            return False
        return self.browser.load_cookies(self.cookie_file)

    def _remove_cookies(self):
        """删除本地保存的 Cookie，避免 token 过期后重复误判。"""
        try:
            if os.path.exists(self.cookie_file):
                os.remove(self.cookie_file)
                print(f"已删除过期Cookie: {self.cookie_file}")
        except Exception as e:
            print(f"删除Cookie失败: {e}")

    def logout(self) -> bool:
        """退出登录"""
        try:
            # 导航到退出登录URL（如果有）
            logout_url = config.SITE_CONFIG.get("logout_url")
            if logout_url:
                self.browser.navigate(logout_url)

            # 删除Cookie文件
            if os.path.exists(self.cookie_file):
                os.remove(self.cookie_file)
                print("已清除登录状态")

            return True
        except Exception as e:
            print(f"退出登录时出错: {e}")
            return False

    def is_logged_in(self) -> bool:
        """检查当前是否已登录"""
        return self.browser.is_logged_in()
