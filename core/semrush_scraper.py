"""
Semrush反向链接数据抓取模块
简化为：注入导出脚本 → 点击"导出当前页面"按钮 → 等待下载
"""

import os
import time
import re
from datetime import datetime
from pathlib import Path
from typing import Optional, List

from playwright.sync_api import Download

from browser.browser_manager import BrowserManager
import config


class SemrushScraper:
    """Semrush反向链接数据抓取器"""

    EXPORT_SCRIPT = """
(function() {
    if (document.getElementById("export-current-page")) return;

    function exportTableToCSV() {
        const head = document.querySelector('[data-ui-name="DefinitionTable.Head"]');
        const body = document.querySelector('[data-ui-name="DefinitionTable.Body"]');
        if (!head || !body) {
            console.error("未找到表格数据");
            return;
        }

        const rows = [];

        // 表头
        const headers = [];
        head.querySelectorAll('[role="columnheader"]').forEach((cell, i) => {
            if (i === 0) return;
            headers.push(cell.textContent.trim().replace(/Sortable$/i, "").trim());
        });
        rows.push(headers);

        // 数据行
        body.querySelectorAll('[role="row"]').forEach(row => {
            const cells = row.querySelectorAll('[role="gridcell"]');
            const rowData = [];
            cells.forEach((cell, i) => {
                if (i === 0) return;
                const name = cell.getAttribute("name");
                if (name === "source") {
                    const link = cell.querySelector('a[data-path="backlinks.table.source"]');
                    const href = link ? (link.getAttribute("data-test-source-url") || link.textContent.trim()) : "";
                    const tags = Array.from(cell.querySelectorAll('[data-ui-name="Tag.Text"]'))
                        .map(t => t.textContent.trim()).join(" | ");
                    rowData.push(href + (tags ? " | " + tags : ""));
                } else if (name === "target") {
                    const link = cell.querySelector('a[data-path="backlinks.table.target"]');
                    rowData.push(link ? link.textContent.trim() : cell.textContent.trim());
                } else {
                    rowData.push(cell.textContent.trim());
                }
            });
            if (rowData.length) rows.push(rowData);
        });

        const BOM = "\\uFEFF";
        const csvContent = rows.map(r =>
            r.map(v => `"${String(v).replace(/"/g, '""')}"`).join(",")
        ).join("\\n");

        const blob = new Blob([BOM + csvContent], { type: "text/csv;charset=utf-8;" });
        const link = document.createElement("a");
        link.href = URL.createObjectURL(blob);
        link.download = `backlinks_export_${new Date().toISOString().slice(0, 10)}.csv`;
        link.style.visibility = "hidden";
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(link.href);
    }

    function createExportButton() {
        const btn = document.createElement("button");
        btn.id = "export-current-page";
        btn.type = "button";
        btn.style.cssText = `
            margin-left: 16px; color: var(--intergalactic-text-secondary,#6c6e79);
            background-color: rgba(138,142,155,.1); height: 28px;
            border-radius: 6px; font-size: 14px; display: inline-flex;
            align-items: center; border: 1px solid #c4c7cf; cursor: pointer;
            font-weight: 500; min-width: fit-content; padding: 4px 6px;
        `;
        btn.innerHTML = `<span><svg width="16" height="16" viewBox="0 0 16 16">
            <path d="m8 1 3.696 3.7a1 1 0 1 1-1.415 1.413L9 4.83v6.083a1 1 0 1 1-2 0V4.828l-1.289 1.29a1 1 0 1 1-1.414-1.415L8 1Z"/>
            <path d="M3 13v-2a1 1 0 1 0-2 0v3a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-3a1 1 0 1 0-2 0v2H3Z"/>
        </svg></span><span style="margin-left:8px">导出当前页面</span>`;
        btn.addEventListener("click", exportTableToCSV);
        return btn;
    }

    function insertButton() {
        const targetBtn = document.querySelector('button[data-path="backlinks.table.export"]');
        if (targetBtn && !document.getElementById("export-current-page")) {
            targetBtn.parentNode.insertBefore(createExportButton(), targetBtn.nextSibling);
            return true;
        }
        return false;
    }

    if (!insertButton()) {
        const obs = new MutationObserver(() => {
            if (insertButton()) obs.disconnect();
        });
        obs.observe(document.body, { childList: true, subtree: true });
    }
})();
"""

    def __init__(self, browser: BrowserManager):
        self.browser = browser
        self.download_dir = os.path.join(os.path.dirname(__file__), "..", "data", "downloads")
        Path(self.download_dir).mkdir(parents=True, exist_ok=True)

    def inject_export_script(self) -> bool:
        """注入导出按钮脚本"""
        try:
            self.browser.page.evaluate(self.EXPORT_SCRIPT)
            time.sleep(1)
            return True
        except Exception as e:
            print(f"注入导出脚本失败: {e}")
            return False

    def wait_for_export_button(self, timeout: int = 20) -> bool:
        """等待导出按钮出现"""
        print("等待导出按钮...")
        start = time.time()
        while time.time() - start < timeout:
            try:
                btn = self.browser.page.query_selector("#export-current-page")
                if btn and btn.is_visible():
                    print("导出按钮已就绪")
                    return True
            except Exception:
                pass
            time.sleep(0.5)
        print("等待导出按钮超时")
        return False

    def _is_target_csv_download(self, download: Download) -> bool:
        """判断是否为「导出当前页面」生成的 CSV（忽略浏览器/站点产生的无扩展名临时文件）"""
        name = (download.suggested_filename or "").strip().lower()
        if name.endswith(".csv"):
            return True
        if "backlinks_export" in name:
            return True
        # 无扩展名且像 UUID 的通常是无关下载，跳过
        if name and "." not in name and re.match(
            r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
            name,
            re.I,
        ):
            return False
        return False

    def _save_download_to_project(self, download: Download, domain: str) -> str:
        """将 Playwright 捕获的下载保存到项目目录（避免只落到系统「下载」文件夹）"""
        out = Path(self.download_dir)
        out.mkdir(parents=True, exist_ok=True)
        suggested = download.suggested_filename or ""
        date_str = datetime.now().strftime("%Y-%m-%d")
        # 去掉协议前缀和尾部斜杠，保留干净域名
        clean_domain = re.sub(r"^https?://", "", domain.strip()).strip("/").replace("/", "_").replace("\\", "_")
        dest = out / f"backlinks_export_{date_str}_{clean_domain}.csv"
        # save_as 会等待下载完成再写入
        download.save_as(str(dest))
        return str(dest)

    def click_export_and_save_csv(self, domain: str, wait_seconds: float = 20.0) -> Optional[str]:
        """
        点击「导出当前页面」并只接受 CSV 下载。
        说明：Chrome 有时会先产生无扩展名的 UUID 临时下载，轮询文件夹会误判；
        这里用 download 事件，跳过 UUID，直到等到 .csv 或超时。
        """
        page = self.browser.page
        pending: List[Download] = []

        def on_download(d: Download) -> None:
            pending.append(d)
            try:
                print(f"  [下载事件] suggested_filename={d.suggested_filename!r}")
            except Exception:
                pass

        page.on("download", on_download)
        try:
            page.click("#export-current-page", timeout=15000)
            print("已点击导出按钮，等待 CSV 下载事件...")
            deadline = time.time() + wait_seconds
            seen: List[Download] = []

            while time.time() < deadline:
                for d in pending:
                    if d in seen:
                        continue
                    seen.append(d)
                    if self._is_target_csv_download(d):
                        path = self._save_download_to_project(d, domain)
                        print(f"已保存 CSV: {path}")
                        return path
                time.sleep(0.15)

            print("警告: 在超时内未收到有效的 CSV 下载事件（可能被 UUID 等无关下载干扰）")
            return None
        except Exception as e:
            print(f"点击导出或等待下载失败: {e}")
            return None
        finally:
            try:
                page.remove_listener("download", on_download)
            except Exception:
                pass

    def get_latest_csv(self) -> Optional[str]:
        """兼容：获取下载目录中最新的 backlinks_export CSV（仅作兜底）"""
        try:
            files = list(Path(self.download_dir).glob("backlinks_export_*.csv"))
            if not files:
                return None
            return str(max(files, key=lambda f: f.stat().st_mtime))
        except Exception:
            return None

    # 弹窗触发后等待 DOM 就绪的额外时长（秒）
    _POPUP_WAIT_EXTRA = 2

    def is_upgrade_popup_visible(self) -> bool:
        """检测「升级到 Guru」弹窗按钮是否可见"""
        try:
            selector = config.UPGRADE_POPUP_SELECTOR
            btn = self.browser.page.query_selector(selector)
            if btn and btn.is_visible():
                print("检测到「升级到 Guru」弹窗!")
                self.browser.save_screenshot("upgrade_popup_detected")
                return True
        except Exception:
            pass
        return False

    def return_to_dashboard(self):
        """从 Semrush 页面返回到 Dashboard 首页，供节点切换使用"""
        print("返回 Dashboard 首页...")
        self.browser.navigate(config.SITE_CONFIG["home_url"])
        time.sleep(2)

    def scrape_domain(self, domain: str, gmitm: str = None) -> bool:
        """
        抓取单个域名的反向链接数据
        简化为：导航 → 注入脚本 → 等待按钮 → 点击导出 → 等待下载
        """
        print(f"\n{'='*50}")
        print(f"抓取域名: {domain}")
        print(f"{'='*50}")

        params = config.SEMRUSH_CONFIG.get("params", {})
        gmitm = gmitm or params.get("__gmitm", "")

        # 导航到反向链接页面
        base = config.SEMRUSH_CONFIG.get("backlinks_url", "https://sem.3ue.co/analytics/backlinks/backlinks/")
        url = f"{base}?q={domain}&searchType=domain"
        if gmitm:
            url += f"&__gmitm={gmitm}"
        print(f"导航到: {url}")
        self.browser.navigate(url)
        time.sleep(3)

        # 注入导出脚本前，先检测是否弹出升级提示
        if self.is_upgrade_popup_visible():
            return None  # None = 需要切换节点

        # 注入导出脚本
        self.inject_export_script()

        # 等待按钮出现
        if not self.wait_for_export_button():
            # 按钮超时后再次检测是否为升级弹窗
            if self.is_upgrade_popup_visible():
                return None
            self.browser.save_screenshot(f"no_export_{domain}")
            return False

        # 点击导出：用 Playwright download 事件保存 CSV（勿再轮询本地目录误判）
        time.sleep(1)
        saved = self.click_export_and_save_csv(domain, wait_seconds=25.0)
        if saved:
            return True

        # 下载超时后再次检测是否为升级弹窗
        if self.is_upgrade_popup_visible():
            return None

        self.browser.save_screenshot(f"download_failed_{domain}")
        # 兜底：若事件未捕获但文件已进项目目录
        fallback = self.get_latest_csv()
        if fallback:
            print(f"兜底检测到 CSV: {fallback}")
            return True
        return False
