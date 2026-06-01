"""
主程序入口
整合所有模块，实现自动化流程
"""

from typing import Optional
import time
import argparse

from browser.browser_manager import BrowserManager
from core.login import LoginHandler
from core.node_selector import NodeSelector
from core.semrush_scraper import SemrushScraper
from core.backlinks_merger import run_merger
from data.excel_handler import ExcelHandler
import config


class AutomationRunner:
    """自动化流程运行器"""

    def __init__(self):
        self.browser = None
        self.login_handler = None
        self.node_selector = None
        self.semrush_scraper = None
        self.excel_handler = ExcelHandler()
        self._cleanup_done = False  # 标记是否已经执行过清理
        self.gmitm: Optional[str] = None  # 登录后从URL提取的追踪参数
        self.scrape_date: Optional[str] = None  # 记录本次抓取的日期字符串
        self.current_node: Optional[str] = None  # 当前使用的节点名称

    def initialize(self):
        """初始化浏览器和处理器"""
        print("=" * 50)
        print("初始化浏览器...")
        self.browser = BrowserManager().start()
        self.login_handler = LoginHandler(self.browser)
        self.node_selector = NodeSelector(self.browser)
        self.semrush_scraper = SemrushScraper(self.browser)
        print("初始化完成")
        print("=" * 50)

    def cleanup(self, keep_browser_open: bool = False):
        """清理资源"""
        # 避免重复清理
        if self._cleanup_done:
            return
        self._cleanup_done = True

        if self.browser:
            if keep_browser_open:
                print("\n" + "=" * 50)
                print("浏览器保持打开状态，请手动关闭浏览器窗口")
                print("按回车键关闭浏览器并退出程序...")
                print("=" * 50)
                try:
                    input()
                except:
                    pass
            print("关闭浏览器...")
            self.browser.close()
            print("清理完成")

    def run_login(self) -> bool:
        """执行登录"""
        print("\n" + "=" * 50)
        print("步骤1: 执行登录")
        print("=" * 50)
        success = self.login_handler.login()
        if success:
            self.gmitm = self.login_handler.gmitm
            if self.gmitm:
                print(f"已获取追踪参数: {self.gmitm}")
            else:
                print("警告: 未能获取追踪参数，步骤2可能失败")
            print("登录成功!")
        else:
            print("登录失败!")
        return success

    def run_select_node(self, node_text: str = None) -> bool:
        """选择节点并打开"""
        if not self._recover_login_before_node():
            return False

        result = self.node_selector.select_node_and_open(node_text)
        if not result and self.login_handler.is_on_login_page():
            print("选择节点失败后检测到页面回到登录页，重新登录后重试步骤2...")
            if not self.login_handler.login(force=True):
                print("重新登录失败，无法继续选择节点")
                return False
            result = self.node_selector.select_node_and_open(node_text)

        if result:
            # 记录当前使用的节点
            self.current_node = node_text or config.NODE_CONFIG.get("default_node")

            # 节点打开后，等待URL稳定后再提取 __gmitm
            time.sleep(3)
            current_url = self.browser.page.url
            print(f"节点页面URL: {current_url}")
            self.gmitm = self.login_handler._extract_gmitm_from_url(current_url)
            if self.gmitm:
                print(f"已从节点URL获取 __gmitm: {self.gmitm}")
            else:
                print("警告: 未能从节点URL中获取 __gmitm，将从config读取")
                # 备选：从配置读取
                params = config.SEMRUSH_CONFIG.get("params", {})
                self.gmitm = params.get("__gmitm", "")
                if self.gmitm:
                    print(f"从配置获取 __gmitm: {self.gmitm}")
        return result

    def _recover_login_before_node(self) -> bool:
        """步骤2前等待前端校验 token；如被踢回登录页则强制重登。"""
        print("步骤2前检查登录状态，等待前端校验 token...")
        time.sleep(5)
        try:
            current_url = self.browser.page.url
            print(f"步骤2前当前URL: {current_url}")
        except Exception:
            current_url = ""

        if self.login_handler.is_on_login_page():
            print("检测到 token 可能已过期，当前仍在登录页，开始重新登录...")
            if not self.login_handler.login(force=True):
                print("重新登录失败，无法继续选择节点")
                return False
            time.sleep(3)

            if self.login_handler.is_on_login_page():
                print("重新登录后仍在登录页，停止步骤2")
                return False

        return True

    def run_scrape(self) -> bool:
        """执行 Semrush 反向链接抓取（从 Excel 读取所有域名，逐一抓取）"""
        print("\n" + "=" * 50)
        print("步骤2: Semrush 反向链接抓取")
        print("=" * 50)

        try:
            df = self.excel_handler.read_all_data()
            domain_col = config.EXCEL_CONFIG.get("input_domain_column", "域名")
            if domain_col not in df.columns:
                print(f"Excel中未找到 '{domain_col}' 列，可用列: {list(df.columns)}")
                return False

            domains = df[domain_col].dropna().tolist()
            domains = [str(d) for d in domains if str(d).strip()]
            if not domains:
                print("Excel中没有可抓取的域名")
                return False

            print(f"从 Excel 读取到 {len(domains)} 个域名")

            # 记录抓取日期（用于后续合并）
            from datetime import date
            self.scrape_date = date.today().strftime("%Y-%m-%d")

            success_count = 0
            for idx, domain in enumerate(domains, 1):
                try:
                    result = self.semrush_scraper.scrape_domain(domain, self.gmitm)
                except Exception as e:
                    print(f"域名 {domain} 抓取时发生未预料的异常: {e}")
                    import traceback
                    traceback.print_exc()
                    self.browser.save_screenshot(f"scrape_exception_{idx}")
                    result = False  # 当作失败，继续下一个

                # None = 检测到升级弹窗，需要切换到下一个节点
                if result is None:
                    print(f"域名 {domain} 抓取遇到升级弹窗，尝试切换节点...")
                    self.semrush_scraper.return_to_dashboard()

                    next_node = self.node_selector.get_next_node(self.current_node)
                    if not next_node:
                        print("无法获取下一个节点名称，停止抓取")
                        break

                    if not self.node_selector.select_node_and_open(next_node):
                        print("切换节点失败，停止抓取")
                        break

                    self.current_node = next_node
                    # 重新获取新节点的 gmitm
                    time.sleep(3)
                    new_url = self.browser.page.url
                    self.gmitm = self.login_handler._extract_gmitm_from_url(new_url)
                    if self.gmitm:
                        print(f"已从新节点URL获取 __gmitm: {self.gmitm}")
                    else:
                        params = config.SEMRUSH_CONFIG.get("params", {})
                        self.gmitm = params.get("__gmitm", "")

                    # 重试当前域名
                    time.sleep(2)
                    retry_result = self.semrush_scraper.scrape_domain(domain, self.gmitm)
                    if retry_result:
                        success_count += 1
                    continue

                if result:
                    success_count += 1

                if idx < len(domains):
                    import random
                    delay = random.uniform(3, 7)
                    print(f"等待 {delay:.1f} 秒后继续...")
                    time.sleep(delay)

            print(f"\n批量抓取完成: {success_count}/{len(domains)} 成功")
            return success_count > 0

        except Exception as e:
            print(f"数据抓取出错: {e}")
            import traceback
            traceback.print_exc()
            return False

    def run_merge(self, target_date: str = None, use_blacklist: bool = True) -> bool:
        """执行反向链接数据整合分析"""
        print("\n" + "=" * 50)
        print("步骤3: 反向链接数据整合分析")
        print("=" * 50)
        if target_date is None:
            target_date = self.scrape_date
        if target_date is None:
            from datetime import date
            target_date = date.today().strftime("%Y-%m-%d")
        return run_merger(target_date=target_date, use_blacklist=use_blacklist)

    def run_full_workflow(self, loop: bool = False, max_loops: int = 1, node_text: str = None, target_date: str = None, use_blacklist: bool = True):
        """
        运行完整工作流程

        Args:
            loop: 是否循环执行
            max_loops: 最大循环次数
            node_text: 要选择的节点名称
            target_date: 整合分析的目标日期（YYYY-MM-DD格式）
            use_blacklist: 是否启用黑名单过滤
        """
        loop_count = 0
        while loop_count < max_loops:
            loop_count += 1
            if loop:
                print(f"\n{'='*50}")
                print(f"第 {loop_count}/{max_loops} 轮执行")
                print(f"{'='*50}\n")

            try:
                # 1. 登录
                if not self.run_login():
                    print("登录失败，停止执行")
                    break

                # 2. 选择节点并打开
                if not self.run_select_node(node_text):
                    print("选择节点失败，停止执行")
                    break

                # 3. Semrush 反向链接抓取
                self.run_scrape()

                # 4. 整合分析
                self.run_merge(target_date=target_date, use_blacklist=use_blacklist)

                if loop and loop_count < max_loops:
                    print("\n等待 10 秒后开始下一轮...")
                    time.sleep(10)

            except Exception as e:
                print(f"执行过程中出错: {e}")
                import traceback
                print("错误堆栈:")
                print(traceback.format_exc())
                # 保存截图
                if self.browser:
                    self.browser.save_screenshot("error")
                print("\n" + "=" * 50)
                print("出错啦！浏览器将保持打开状态供你调试")
                print("请检查错误原因后，按回车键关闭浏览器")
                print("=" * 50)
                # 等待用户确认后再关闭浏览器 (传入True会等待用户按回车)
                self.cleanup(keep_browser_open=True)
                return  # 退出方法

        print("\n" + "=" * 50)
        print("所有任务执行完成!")
        print("=" * 50)


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="网站自动化工具")
    parser.add_argument(
        "--mode",
        choices=["login", "node", "scrape", "full", "merge"],
        default="full",
        help="运行模式: login(仅登录), node(选择节点), scrape(仅抓取), full(完整流程), merge(仅整合分析)"
    )
    parser.add_argument(
        "--node",
        type=str,
        default=None,
        help="要选择的节点名称，如: 节点3"
    )
    parser.add_argument(
        "--loop",
        action="store_true",
        help="是否循环执行"
    )
    parser.add_argument(
        "--max-loops",
        type=int,
        default=1,
        help="最大循环次数"
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="无头模式运行浏览器"
    )
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="整合分析的目标日期（YYYY-MM-DD格式），用于 merge 模式或完整流程"
    )
    parser.add_argument(
        "--no-blacklist",
        action="store_true",
        help="merge 阶段禁用黑名单过滤",
    )
    args = parser.parse_args()

    if args.headless:
        config.BROWSER_CONFIG["headless"] = True

    runner = AutomationRunner()

    try:
        runner.initialize()

        if args.mode == "login":
            runner.run_login()
        elif args.mode == "node":
            if not runner.run_login():
                print("需要先登录")
            else:
                runner.run_select_node(args.node)
        elif args.mode == "scrape":
            if not runner.run_login():
                print("需要先登录")
            else:
                runner.run_scrape()
        elif args.mode == "full":
            runner.run_full_workflow(loop=args.loop, max_loops=args.max_loops, node_text=args.node, target_date=args.date, use_blacklist=not args.no_blacklist)
        elif args.mode == "merge":
            runner.run_merge(target_date=args.date, use_blacklist=not args.no_blacklist)

    except KeyboardInterrupt:
        print("\n用户中断执行")
        print("\n" + "=" * 50)
        print("浏览器将保持打开状态")
        print("按回车键关闭浏览器...")
        print("=" * 50)
        runner.cleanup(keep_browser_open=True)
    except Exception as e:
        print(f"程序异常: {e}")
        import traceback
        print("错误堆栈:")
        print(traceback.format_exc())
        print("\n" + "=" * 50)
        print("出错啦！浏览器将保持打开状态供你调试")
        print("请检查错误原因后，按回车键关闭浏览器")
        print("=" * 50)
        runner.cleanup(keep_browser_open=True)
    finally:
        # 如果还没执行过清理，才执行
        runner.cleanup(keep_browser_open=False)


if __name__ == "__main__":
    main()
