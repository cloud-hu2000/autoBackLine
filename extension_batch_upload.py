import argparse
import base64
import json
import os
import shutil
import sys
import time
from datetime import date
from pathlib import Path
from urllib.parse import quote, urlparse

import requests
import websocket
from dotenv import load_dotenv


load_dotenv()

DEFAULT_EXTENSION_ID = os.getenv("PLUGIN_EXTENSION_ID", "eckpehelplpholpddkpmihfigodplkdp")
DEFAULT_OPTIONS_URL = os.getenv(
    "PLUGIN_OPTIONS_URL",
    f"chrome-extension://{DEFAULT_EXTENSION_ID}/options.html",
)
DEFAULT_BATCH_URL = os.getenv(
    "PLUGIN_URL",
    f"chrome-extension://{DEFAULT_EXTENSION_ID}/batch.html",
)

for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")


class CdpError(RuntimeError):
    pass


class CdpPage:
    def __init__(self, ws_url, timeout_seconds):
        self.ws = websocket.create_connection(
            ws_url,
            timeout=timeout_seconds,
            suppress_origin=True,
        )
        self.next_id = 1

    def close(self):
        try:
            self.ws.close()
        except Exception:
            pass

    def send(self, method, params=None):
        message_id = self.next_id
        self.next_id += 1
        payload = {"id": message_id, "method": method}
        if params:
            payload["params"] = params
        self.ws.send(json.dumps(payload))

        while True:
            raw = self.ws.recv()
            response = json.loads(raw)
            if response.get("id") != message_id:
                continue
            if "error" in response:
                raise CdpError(f"{method} failed: {response['error']}")
            return response.get("result", {})

    def eval(self, expression, await_promise=False):
        result = self.send(
            "Runtime.evaluate",
            {
                "expression": expression,
                "awaitPromise": await_promise,
                "returnByValue": True,
            },
        )
        if "exceptionDetails" in result:
            raise CdpError(f"JavaScript evaluation failed: {result['exceptionDetails']}")
        return result.get("result", {}).get("value")


def write_event(message, **extra):
    event = {"message": message}
    event.update(extra)
    print(json.dumps(event, ensure_ascii=False), flush=True)


def http_base(port):
    return f"http://127.0.0.1:{port}"


def request_json(method, url, timeout_seconds):
    response = requests.request(method, url, timeout=timeout_seconds)
    response.raise_for_status()
    return response.json()


def list_targets(port, timeout_seconds):
    return request_json("GET", f"{http_base(port)}/json/list", timeout_seconds)


def new_target(port, url, timeout_seconds):
    encoded_url = quote(url, safe="")
    endpoint = f"{http_base(port)}/json/new?{encoded_url}"
    try:
        return request_json("PUT", endpoint, timeout_seconds)
    except requests.RequestException:
        return request_json("GET", endpoint, timeout_seconds)


def attach_target(target, timeout_seconds):
    ws_url = target.get("webSocketDebuggerUrl")
    if not ws_url:
        raise CdpError(f"Target has no websocket URL: {target}")
    page = CdpPage(ws_url, timeout_seconds)
    page.send("Page.enable")
    page.send("Runtime.enable")
    page.send("DOM.enable")
    return page


def wait_until(deadline, func, interval=0.25):
    last_error = None
    while time.monotonic() < deadline:
        try:
            value = func()
            if value:
                return value
        except Exception as exc:
            last_error = exc
        time.sleep(interval)
    if last_error:
        raise last_error
    return None


def wait_ready(page, deadline):
    wait_until(
        deadline,
        lambda: page.eval("document.readyState !== 'loading'"),
    )


def page_info(page):
    return page.eval(
        """(() => ({
          href: location.href,
          title: document.title,
          body: document.body ? document.body.innerText.slice(0, 1000) : ''
        }))()"""
    ) or {}


def ensure_extension_page(page, expected_url, description):
    info = page_info(page)
    href = info.get("href", "")
    body = info.get("body", "")
    if href.startswith("chrome-error://") or "ERR_BLOCKED_BY_CLIENT" in body:
        raise CdpError(f"{description} is unavailable or blocked: {href}")
    if expected_url and not href.startswith(expected_url):
        write_event(f"{description} loaded with unexpected URL", expected=expected_url, actual=href)
    return info


def find_batch_target(port, batch_url, timeout_seconds, deadline):
    def find():
        targets = list_targets(port, timeout_seconds)
        for target in targets:
            if target.get("type") == "page" and target.get("url", "").startswith(batch_url):
                return target
        return None

    return wait_until(deadline, find)


def open_batch_from_options(port, options_url, batch_url, timeout_seconds, deadline):
    write_event("Opening extension options page", url=options_url)
    options_target = new_target(port, options_url, timeout_seconds)
    options_page = attach_target(options_target, timeout_seconds)

    try:
        wait_ready(options_page, deadline)
        info = ensure_extension_page(options_page, options_url, "Options page")
        write_event("Options page ready", url=info.get("href"))

        click_result = options_page.eval(
            """(() => {
              const button = document.querySelector('#openBatchBtn');
              if (!button) {
                return { ok: false, reason: 'openBatchBtn not found' };
              }
              button.click();
              return { ok: true, text: button.innerText || button.textContent || '' };
            })()"""
        )
        if not click_result or not click_result.get("ok"):
            raise CdpError(f"Could not click open batch button: {click_result}")

        write_event("Clicked open batch button", text=click_result.get("text", "").strip())
        batch_target = find_batch_target(port, batch_url, timeout_seconds, deadline)
        if not batch_target:
            raise CdpError(f"Batch page did not open from options page: {batch_url}")
        return batch_target
    finally:
        options_page.close()


def open_batch_direct(port, batch_url, timeout_seconds):
    write_event("Opening extension batch page directly", url=batch_url)
    return new_target(port, batch_url, timeout_seconds)


def query_node(page, selector):
    document = page.send("DOM.getDocument", {"depth": 1, "pierce": True})
    root_id = document.get("root", {}).get("nodeId")
    if not root_id:
        return 0
    result = page.send("DOM.querySelector", {"nodeId": root_id, "selector": selector})
    return result.get("nodeId", 0)


def set_file_input(page, csv_path, selectors):
    for selector in selectors:
        node_id = query_node(page, selector)
        if node_id:
            page.send("DOM.setFileInputFiles", {"nodeId": node_id, "files": [csv_path]})
            dispatch_result = page.eval(
                f"""(() => {{
                  const input = document.querySelector({json.dumps(selector)});
                  if (!input) return {{ ok: false, reason: 'input not found after upload' }};
                  input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                  input.dispatchEvent(new Event('change', {{ bubbles: true }}));
                  let directHandler = 'none';
                  if (typeof handleFileSelect === 'function') {{
                    handleFileSelect({{ target: input }});
                    directHandler = 'handleFileSelect';
                  }} else if (typeof processFile === 'function' && input.files && input.files[0]) {{
                    processFile(input.files[0]);
                    directHandler = 'processFile';
                  }}
                  return {{
                    ok: true,
                    fileCount: input.files ? input.files.length : 0,
                    fileName: input.files && input.files[0] ? input.files[0].name : '',
                    directHandler
                  }};
                }})()"""
            )
            write_event("File input events dispatched", selector=selector, result=dispatch_result)
            return selector
    return None


def wait_start_ready(page, start_selectors, deadline):
    selector_list = json.dumps(start_selectors, ensure_ascii=False)
    expression = f"""(() => {{
      const selectors = {selector_list};
      for (const selector of selectors) {{
        const button = document.querySelector(selector);
        if (button) {{
          return {{
            found: true,
            selector,
            text: button.innerText || button.textContent || '',
            disabled: !!button.disabled || button.getAttribute('aria-disabled') === 'true'
          }};
        }}
      }}
      return {{ found: false }};
    }})()"""

    def check():
        state = page.eval(expression)
        if state and state.get("found") and not state.get("disabled"):
            return state
        return None

    return wait_until(deadline, check)


def click_start(page, start_selectors):
    selector_list = json.dumps(start_selectors, ensure_ascii=False)
    return page.eval(
        f"""(async () => {{
          const selectors = {selector_list};
          for (const selector of selectors) {{
            const button = document.querySelector(selector);
            if (button) {{
              let method = 'button.click';
              if (typeof startBatch === 'function') {{
                await startBatch();
                method = 'startBatch';
              }} else {{
                button.click();
              }}
              return {{
                ok: true,
                method,
                selector,
                text: button.innerText || button.textContent || '',
                status: typeof status !== 'undefined' ? status : '',
                statusText: document.querySelector('#statusBadge')?.innerText || '',
                progress: document.querySelector('#progressText')?.innerText || ''
              }};
            }}
          }}
          return {{ ok: false, reason: 'start button not found' }};
        }})()""",
        await_promise=True,
    )


def task_state(page):
    return page.eval(
        """(() => ({
          status: typeof status !== 'undefined' ? status : '',
          statusText: document.querySelector('#statusBadge')?.innerText || '',
          statusClass: document.querySelector('#statusBadge')?.className || '',
          progress: document.querySelector('#progressText')?.innerText || '',
          pending: document.querySelector('#pendingCount')?.innerText || '',
          success: document.querySelector('#successCount')?.innerText || '',
          fail: document.querySelector('#failCount')?.innerText || '',
          skipped: document.querySelector('#skippedCount')?.innerText || '',
          manual: document.querySelector('#manualRequiredCount')?.innerText || '',
          resultsLen: typeof localResults !== 'undefined' ? localResults.length : null,
          batchId: typeof batchId !== 'undefined' ? batchId : null,
          startDisabled: document.querySelector('#startBtn')?.disabled
        }))()"""
    )


def successful_batch_urls(page):
    return page.eval(
        """(() => {
          const okResults = new Set(['success', 'skipped']);
          if (!Array.isArray(localResults)) return [];
          return localResults
            .filter((item) => okResults.has(item.result))
            .map((item) => item.url)
            .filter(Boolean);
        })()"""
    ) or []


def wait_task_completed(page, timeout_seconds):
    deadline = time.monotonic() + timeout_seconds if timeout_seconds > 0 else None
    last_state = None

    def check():
        nonlocal last_state
        last_state = task_state(page)
        status = last_state.get("status") if last_state else ""
        if status == "completed":
            return last_state
        if status == "terminated":
            raise CdpError(f"Batch task was terminated: {last_state}")
        return None

    if deadline is None:
      while True:
          completed_state = check()
          if completed_state:
              write_event("Batch task completed", state=completed_state)
              return completed_state
          time.sleep(2)
    else:
      completed_state = wait_until(deadline, check, interval=2)
      if completed_state:
          write_event("Batch task completed", state=completed_state)
          return completed_state
      raise CdpError(f"Timed out waiting for batch task completion. Last state: {last_state}")


def click_export(page):
    return page.eval(
        """(() => {
          const button = document.querySelector('#exportBtn');
          if (!button) {
            return { ok: false, reason: 'exportBtn not found' };
          }
          if (button.disabled) {
            return {
              ok: false,
              reason: 'exportBtn disabled',
              resultsLen: typeof localResults !== 'undefined' ? localResults.length : null
            };
          }
          button.click();
          return {
            ok: true,
            text: button.innerText || button.textContent || '',
            batchId: typeof batchId !== 'undefined' ? batchId : null,
            resultsLen: typeof localResults !== 'undefined' ? localResults.length : null
          };
        })()"""
    )


def existing_downloads(download_dir):
    if not download_dir or not os.path.isdir(download_dir):
        return {}
    files = {}
    for path in Path(download_dir).glob("*.csv"):
        try:
            stat = path.stat()
        except OSError:
            continue
        files[str(path.resolve())] = (stat.st_size, stat.st_mtime_ns)
    return files


def wait_export_file(download_dir, before, timeout_seconds):
    deadline = time.monotonic() + timeout_seconds
    output = Path(download_dir)
    last_candidate = None

    while time.monotonic() < deadline:
        current = existing_downloads(download_dir)
        changed = []
        for path, signature in current.items():
            name = Path(path).name.lower()
            if not name.endswith(".csv"):
                continue
            if path not in before or before[path] != signature:
                changed.append(Path(path))

        if changed:
            changed.sort(key=lambda item: item.stat().st_mtime, reverse=True)
            candidate = changed[0]
            stat1 = candidate.stat()
            time.sleep(0.5)
            stat2 = candidate.stat()
            if stat1.st_size == stat2.st_size and stat1.st_mtime_ns == stat2.st_mtime_ns:
                return str(candidate.resolve())
            last_candidate = str(candidate.resolve())

        time.sleep(0.5)

    raise CdpError(f"Timed out waiting for exported CSV in {download_dir}. Last candidate: {last_candidate}")


def unique_path(path):
    candidate = Path(path)
    if not candidate.exists():
        return candidate

    stem = candidate.stem
    suffix = candidate.suffix
    parent = candidate.parent
    index = 1
    while True:
        next_candidate = parent / f"{stem}_{index}{suffix}"
        if not next_candidate.exists():
            return next_candidate
        index += 1


def wait_export_file_to_output(output_dir, before_output, fallback_dir, before_fallback, timeout_seconds):
    deadline = time.monotonic() + timeout_seconds
    output_path = Path(output_dir)
    fallback_path = Path(fallback_dir) if fallback_dir else None
    last_candidate = None

    while time.monotonic() < deadline:
        scan_dirs = [(output_path, before_output, False)]
        if fallback_path and fallback_path.exists() and fallback_path.resolve() != output_path.resolve():
            scan_dirs.append((fallback_path, before_fallback, True))

        for directory, before, should_move in scan_dirs:
            current = existing_downloads(str(directory))
            changed = []
            for path, signature in current.items():
                name = Path(path).name.lower()
                if name.endswith(".csv") and (path not in before or before[path] != signature):
                    changed.append(Path(path))

            if changed:
                changed.sort(key=lambda item: item.stat().st_mtime, reverse=True)
                candidate = changed[0]
                stat1 = candidate.stat()
                time.sleep(0.5)
                stat2 = candidate.stat()
                if stat1.st_size == stat2.st_size and stat1.st_mtime_ns == stat2.st_mtime_ns:
                    if should_move:
                        target = unique_path(output_path / candidate.name)
                        shutil.move(str(candidate), str(target))
                        write_event("Exported CSV moved to output directory", source=str(candidate), path=str(target.resolve()))
                        return str(target.resolve())
                    return str(candidate.resolve())
                last_candidate = str(candidate.resolve())

        time.sleep(0.5)

    raise CdpError(f"Timed out waiting for exported CSV. Output: {output_dir}; fallback: {fallback_dir}; last candidate: {last_candidate}")


def batch_diagnostics(page, start_selectors):
    selector_list = json.dumps(start_selectors, ensure_ascii=False)
    return page.eval(
        f"""(() => {{
          const selectors = {selector_list};
          const buttons = selectors.map((selector) => {{
            const button = document.querySelector(selector);
            return button ? {{
              selector,
              text: button.innerText || button.textContent || '',
              disabled: !!button.disabled,
              ariaDisabled: button.getAttribute('aria-disabled')
            }} : {{ selector, found: false }};
          }});
          return {{
            href: location.href,
            readyState: document.readyState,
            fileCount: document.querySelector('#fileInput')?.files?.length || 0,
            parsedUrlCount: Array.isArray(window.parsedUrls) ? window.parsedUrls.length : null,
            fileInfoText: document.querySelector('#fileInfo')?.innerText || '',
            fileCountText: document.querySelector('#fileCount')?.innerText || '',
            startButtons: buttons,
            bodyText: document.body ? document.body.innerText.slice(0, 600) : ''
          }};
        }})()"""
    )


def save_screenshot(page, screenshot_dir):
    if not screenshot_dir:
        return
    Path(screenshot_dir).mkdir(parents=True, exist_ok=True)
    result = page.send("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": True})
    data = result.get("data")
    if not data:
        return
    path = Path(screenshot_dir) / f"extension_batch_{int(time.time())}.png"
    path.write_bytes(base64.b64decode(data))
    write_event("Screenshot saved", path=str(path))


def urls_match(expected, actual):
    from blog_backlink_loop import normalize_url

    expected_url = normalize_url(expected)
    actual_url = normalize_url(actual)
    if not expected_url or not actual_url:
        return False

    expected_parts = urlparse(expected_url)
    actual_parts = urlparse(actual_url)
    if expected_parts.netloc != actual_parts.netloc:
        return False

    expected_path = (expected_parts.path or "/").rstrip("/")
    actual_path = (actual_parts.path or "/").rstrip("/")
    return actual_path.startswith(expected_path) or expected_path.startswith(actual_path)


def find_open_blog_target(port, blog_urls, processed_urls, timeout_seconds):
    targets = list_targets(port, timeout_seconds)
    for target in targets:
        target_url = target.get("url", "")
        if not target_url or target_url.startswith("chrome-extension://") or target_url.startswith("chrome://"):
            continue
        for blog_url in blog_urls:
            if blog_url in processed_urls:
                continue
            if urls_match(blog_url, target_url):
                return blog_url, target
    return None, None


def wait_blog_analysis_download(output_dir, fallback_dir, before_output, before_fallback, timeout_seconds):
    from blog_backlink_loop import stable_changed_csv

    scan_dirs = [Path(output_dir)]
    before_maps = {str(Path(output_dir)): before_output}
    fallback_path = Path(fallback_dir) if fallback_dir else None
    if fallback_path and fallback_path.exists() and fallback_path.resolve() != Path(output_dir).resolve():
        scan_dirs.append(fallback_path)
        before_maps[str(fallback_path)] = before_fallback
    return stable_changed_csv(scan_dirs, before_maps, timeout_seconds)


def monitor_blog_pages_during_batch(
    batch_page,
    port,
    blog_urls,
    input_dir,
    input_xlsx,
    button_text,
    button_selectors,
    keyword,
    timeout_seconds,
    download_timeout_seconds,
    completion_timeout_seconds,
):
    from blog_backlink_loop import (
        click_analysis_button,
        merge_analysis_csvs_to_input,
        read_existing_keyword,
        safe_filename,
        set_download_dir,
    )

    output_path = Path(input_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    fallback_download_dir = os.path.join(str(Path.home()), "Downloads")
    processed_urls = set()
    exported_files = []
    started_at = time.monotonic()
    last_state = None

    write_event("Monitoring opened blog pages during batch task", count=len(blog_urls), input_dir=str(output_path.resolve()))
    while completion_timeout_seconds <= 0 or time.monotonic() - started_at < completion_timeout_seconds:
        last_state = task_state(batch_page)
        status = last_state.get("status") if last_state else ""
        if status == "terminated":
            raise CdpError(f"Batch task was terminated: {last_state}")

        blog_url, target = find_open_blog_target(port, blog_urls, processed_urls, timeout_seconds)
        if blog_url and target:
            page = attach_target(target, timeout_seconds)
            try:
                set_download_dir(page, output_path)
                before_output = existing_downloads(str(output_path))
                before_fallback = existing_downloads(fallback_download_dir)
                deadline = time.monotonic() + timeout_seconds
                click_result = click_analysis_button(page, button_text, button_selectors, deadline)
                if click_result:
                    write_event("Clicked opened blog floating button", url=blog_url, page=target.get("url"), result=click_result)
                    downloaded = wait_blog_analysis_download(
                        output_path,
                        fallback_download_dir,
                        before_output,
                        before_fallback,
                        download_timeout_seconds,
                    )
                    target_path = unique_path(
                        output_path / f"blog_analysis_{date.today().strftime('%Y-%m-%d')}_{safe_filename(blog_url)}.csv"
                    )
                    if downloaded.resolve() != target_path.resolve():
                        shutil.move(str(downloaded), str(target_path))
                    exported_files.append({"url": blog_url, "path": str(target_path.resolve())})
                    write_event("Opened blog analysis CSV saved", url=blog_url, path=str(target_path.resolve()))
                else:
                    write_event("Opened blog floating button not found yet", url=blog_url, page=target.get("url"))
            except Exception as exc:
                write_event("Opened blog analysis failed", url=blog_url, page=target.get("url"), error=str(exc))
            finally:
                processed_urls.add(blog_url)
                page.close()
            continue

        if status == "completed":
            write_event("Batch task completed", state=last_state)
            break
        time.sleep(1)
    else:
        raise CdpError(f"Timed out waiting for batch task completion. Last state: {last_state}")

    success_urls = successful_batch_urls(batch_page)
    success_exported_files = [
        item["path"]
        for item in exported_files
        if any(urls_match(success_url, item["url"]) for success_url in success_urls)
    ]
    write_event(
        "Filtered opened blog analysis CSV files by batch success results",
        exported_csv_count=len(exported_files),
        success_url_count=len(success_urls),
        merge_csv_count=len(success_exported_files),
    )

    if success_exported_files:
        xlsx_keyword = keyword or read_existing_keyword(input_xlsx, os.getenv("BLOG_ANALYSIS_KEYWORD", "SEO工具"))
        merge_result = merge_analysis_csvs_to_input(success_exported_files, input_xlsx, xlsx_keyword)
        write_event(
            "input.xlsx overwritten from opened blog analysis CSV files",
            input_xlsx=str(Path(input_xlsx).resolve()),
            csv_count=len(success_exported_files),
            raw_count=merge_result["raw_count"],
            blacklisted_count=merge_result["blacklisted_count"],
            domain_count=len(merge_result["urls"]),
            merged_csv=merge_result["merged_csv"],
        )
    else:
        write_event("No successful opened blog analysis CSV files remained after batch result filtering; input.xlsx was not overwritten")

    return last_state, success_exported_files


def parse_args():
    parser = argparse.ArgumentParser(description="Upload a merged CSV to the Chrome extension batch page.")
    parser.add_argument("--csv", required=True, help="Merged CSV file to upload.")
    parser.add_argument("--url", default=DEFAULT_BATCH_URL, help="Batch page URL.")
    parser.add_argument("--options-url", default=DEFAULT_OPTIONS_URL, help="Options page URL used to open batch page.")
    parser.add_argument("--direct-batch", action="store_true", help="Open the batch page directly instead of via options.")
    parser.add_argument("--port", type=int, default=9222, help="Chrome remote debugging port.")
    parser.add_argument("--file-selector", default="#fileInput", help="Primary file input selector.")
    parser.add_argument("--start-selector", action="append", default=[], help="Additional selector for the start button.")
    parser.add_argument("--no-start", action="store_true", help="Upload the CSV but do not click the start button.")
    parser.add_argument("--no-export", action="store_true", help="Do not export the final batch result CSV after starting.")
    parser.add_argument("--output-dir", default="", help="Directory where exported result CSV should be saved.")
    parser.add_argument("--completion-timeout-minutes", type=int, default=0, help="Maximum wait time for the batch task to complete. Use 0 to wait indefinitely.")
    parser.add_argument("--export-timeout-ms", type=int, default=30000, help="Maximum wait time for the exported CSV download.")
    parser.add_argument("--timeout-ms", type=int, default=30000, help="Timeout for page operations.")
    parser.add_argument("--post-start-wait-ms", type=int, default=3000, help="Wait after clicking start.")
    parser.add_argument("--screenshot-dir", default="", help="Optional directory for a screenshot after upload.")
    parser.add_argument("--analyze-opened-blogs", action="store_true", help="While the batch task is running, click the floating blog backlink button on opened blog pages.")
    parser.add_argument("--blog-analysis-input-dir", default="data/input", help="Directory where per-blog analysis CSV files are saved.")
    parser.add_argument("--blog-analysis-input-xlsx", default="data/input.xlsx", help="Workbook overwritten after per-blog analysis CSV files are collected.")
    parser.add_argument("--blog-analysis-button-text", default=os.getenv("BLOG_ANALYSIS_BUTTON_TEXT", "导出外链"), help="Floating button text to click on opened blog pages.")
    parser.add_argument("--blog-analysis-button-selector", action="append", default=[], help="Additional CSS selector for the floating blog analysis button.")
    parser.add_argument("--blog-analysis-keyword", default=os.getenv("BLOG_ANALYSIS_KEYWORD", "SEO工具"), help="Keyword value written to input.xlsx.")
    parser.add_argument("--blog-analysis-download-timeout-ms", type=int, default=60000, help="CSV download timeout after clicking the floating blog button.")
    parser.add_argument("--blog-analysis-max-pages", type=int, default=0, help="Optional cap for opened blog analysis during debugging.")
    return parser.parse_args()


def main():
    args = parse_args()
    csv_path = os.path.abspath(args.csv)
    if not os.path.isfile(csv_path):
        write_event("CSV file does not exist", csv=csv_path)
        return 2

    timeout_seconds = max(args.timeout_ms / 1000, 1)
    deadline = time.monotonic() + timeout_seconds
    file_selectors = [args.file_selector, "input[type='file']"]
    start_selectors = args.start_selector + ["#startBtn", "button#startBtn", "button"]
    blog_urls = []
    blog_button_selectors = args.blog_analysis_button_selector + [
        "[data-action='analyze-backlinks']",
        "[data-testid='analyze-backlinks']",
        "#analyzeBacklinks",
        ".analyze-backlinks",
    ]

    if args.analyze_opened_blogs:
        from blog_backlink_loop import select_blog_urls

        blog_urls = select_blog_urls(csv_path, "all")
        if args.blog_analysis_max_pages > 0:
            blog_urls = blog_urls[: args.blog_analysis_max_pages]
        write_event("Prepared blog URLs for in-batch analysis", count=len(blog_urls))

    try:
        request_json("GET", f"{http_base(args.port)}/json/version", timeout_seconds)
        output_dir = os.path.abspath(args.output_dir) if args.output_dir else ""
        if output_dir and not args.no_start and not args.no_export:
            Path(output_dir).mkdir(parents=True, exist_ok=True)

        if args.direct_batch:
            batch_target = open_batch_direct(args.port, args.url, timeout_seconds)
        else:
            batch_target = open_batch_from_options(
                args.port,
                args.options_url,
                args.url,
                timeout_seconds,
                deadline,
            )

        batch_page = attach_target(batch_target, timeout_seconds)
        try:
            wait_ready(batch_page, deadline)
            info = ensure_extension_page(batch_page, args.url, "Batch page")
            write_event("Batch page ready", url=info.get("href"))

            used_file_selector = set_file_input(batch_page, csv_path, file_selectors)
            if not used_file_selector:
                write_event("File input not found", selectors=file_selectors)
                return 3
            write_event("CSV uploaded", csv=csv_path, selector=used_file_selector)

            start_state = wait_start_ready(batch_page, start_selectors, deadline)
            if not start_state:
                write_event("Start button did not become ready", selectors=start_selectors, diagnostics=batch_diagnostics(batch_page, start_selectors))
                return 4
            write_event("Start button ready", selector=start_state.get("selector"), text=start_state.get("text", "").strip())

            save_screenshot(batch_page, args.screenshot_dir)

            if args.no_start:
                write_event("No-start mode enabled; task was not started")
                return 0

            click_result = click_start(batch_page, start_selectors)
            if not click_result or not click_result.get("ok"):
                write_event("Could not click start button", result=click_result)
                return 4
            write_event(
                "Started batch task",
                method=click_result.get("method"),
                selector=click_result.get("selector"),
                text=click_result.get("text", "").strip(),
                state=click_result,
            )
            time.sleep(max(args.post_start_wait_ms, 0) / 1000)
            state = task_state(batch_page)
            write_event("Batch task state after start", state=state)
            if state and state.get("status") == "idle" and not state.get("startDisabled"):
                write_event("Batch task did not leave idle state", state=state)
                return 4

            blog_exported_files = []
            if args.analyze_opened_blogs and blog_urls:
                _blog_state, blog_exported_files = monitor_blog_pages_during_batch(
                    batch_page,
                    args.port,
                    blog_urls,
                    os.path.abspath(args.blog_analysis_input_dir),
                    os.path.abspath(args.blog_analysis_input_xlsx),
                    args.blog_analysis_button_text,
                    blog_button_selectors,
                    args.blog_analysis_keyword,
                    timeout_seconds,
                    max(args.blog_analysis_download_timeout_ms / 1000, 1),
                        args.completion_timeout_minutes * 60 if args.completion_timeout_minutes > 0 else 0,
                    )
            elif not args.no_export:
                wait_task_completed(batch_page, args.completion_timeout_minutes * 60 if args.completion_timeout_minutes > 0 else 0)

            if not args.no_export:
                if not output_dir:
                    output_dir = os.path.abspath(os.path.join(os.getcwd(), "data", "output"))
                    Path(output_dir).mkdir(parents=True, exist_ok=True)
                fallback_download_dir = os.path.join(str(Path.home()), "Downloads")
                before_output_downloads = existing_downloads(output_dir)
                before_fallback_downloads = existing_downloads(fallback_download_dir)
                export_result = click_export(batch_page)
                if not export_result or not export_result.get("ok"):
                    write_event("Could not export result CSV", result=export_result)
                    if blog_exported_files:
                        write_event("Skipping final result CSV export because blog analysis CSV files were already collected", csv_count=len(blog_exported_files))
                        return 0
                    return 7
                write_event("Clicked export result CSV button", result=export_result)
                exported_file = wait_export_file_to_output(
                    output_dir,
                    before_output_downloads,
                    fallback_download_dir,
                    before_fallback_downloads,
                    max(args.export_timeout_ms / 1000, 1),
                )
                write_event("Exported result CSV saved", path=exported_file)
            return 0
        finally:
            batch_page.close()
    except requests.RequestException as exc:
        write_event("Chrome debug endpoint is unavailable", port=args.port, error=str(exc))
        return 5
    except CdpError as exc:
        write_event("Chrome extension automation failed", error=str(exc))
        return 5
    except Exception as exc:
        write_event("Unexpected extension automation error", error=repr(exc))
        return 1


if __name__ == "__main__":
    sys.exit(main())
