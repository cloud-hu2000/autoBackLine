"""
独立运行：读取 data/downloads 下指定日期的 CSV，合并去重后写入输出文件。
绕过 main.py 的流程，可避免 Excel 占用输出文件导致的 PermissionError。
支持两次去重：
  第一次：每个（源域名 + 目标域名）组合保留 AS 最高
  第二次：每个（URL对应域名）只保留 AS 最高
"""
from pathlib import Path
import csv
import time
from datetime import date
from typing import Dict, List
from core.backlinks_merger import (
    parse_single_csv,
    extract_domain_from_filename,
    merge_and_filter,
    OUTPUT_DIR,
    load_all_blacklists,
    apply_blacklist_filter,
)


def safe_write_csv(records: List[Dict], output_path: Path) -> bool:
    """写入 CSV，被占用时等待后重试一次"""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # 先尝试直接写入
    try:
        with open(output_path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["页面AS", "原URL", "URL对应域名", "目标域名", "类型", "外部链接数量"])
            for r in records:
                writer.writerow([
                    r["as"], r["source_url"], r["domain"],
                    r["target_domain"], r["type"], r["external_links"],
                ])
        return True
    except PermissionError:
        pass

    # 被占用则等待 2 秒后重试
    print(f"  [!] 文件被占用，等待 2 秒后重试...")
    time.sleep(2)
    try:
        with open(output_path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["页面AS", "原URL", "URL对应域名", "目标域名", "类型", "外部链接数量"])
            for r in records:
                writer.writerow([
                    r["as"], r["source_url"], r["domain"],
                    r["target_domain"], r["type"], r["external_links"],
                ])
        return True
    except PermissionError:
        print(f"  [!] 重试后仍被占用，跳过写入。请关闭 Excel 后手动运行。")
        return False


def main():
    import argparse
    parser = argparse.ArgumentParser(description="合并并去重 Semrush 导出的 CSV（两次去重）")
    parser.add_argument("--date", type=str, default=date.today().strftime("%Y-%m-%d"),
                        help="日期（默认: 今天）")
    parser.add_argument(
        "--no-blacklist",
        action="store_true",
        help="禁用黑名单过滤",
    )
    args = parser.parse_args()

    target_date = args.date

    DOWNLOAD_DIR = Path("data/downloads")
    pattern = f"backlinks_export_{target_date}_*.csv"
    files = list(DOWNLOAD_DIR.glob(pattern))
    files.sort(key=lambda f: f.stat().st_mtime)

    if not files:
        print(f"[!] 未找到日期 {target_date} 对应的 CSV 文件")
        return

    print(f"=" * 50)
    print(f"合并去重 - 日期: {target_date}")
    print(f"=" * 50)

    all_records = []
    for fpath in files:
        print(f"解析: {fpath.name}")
        recs = parse_single_csv(str(fpath), target_domain=extract_domain_from_filename(fpath.name))
        print(f"  读取到 {len(recs)} 条记录")
        all_records.extend(recs)

    if not all_records:
        print("[!] 未读取到任何数据")
        return

    blog_count = sum(1 for r in all_records if r["type"] == "博客")
    print(f"\n总计读取: {len(all_records)} 条记录")
    if args.no_blacklist:
        print("[*] 黑名单已禁用（--no-blacklist）")
    else:
        url_bl, domain_bl = load_all_blacklists()
        if url_bl or domain_bl:
            all_records = apply_blacklist_filter(all_records, url_bl, domain_bl)
            print(f"黑名单过滤后剩余: {len(all_records)} 条")

    merged = merge_and_filter(all_records)
    print(f"第一次去重（源域名+目标域名）: {len(merged)} 条")
    print(f"其中【博客】类型: {blog_count} 条")

    # 第二次去重：按 URL 对应域名去重，同一外链只保留 AS 最高
    domain_best: Dict[str, Dict] = {}
    for r in merged:
        if r["domain"] not in domain_best or r["as"] > domain_best[r["domain"]]["as"]:
            domain_best[r["domain"]] = r
    merged = sorted(domain_best.values(), key=lambda x: x["as"], reverse=True)
    print(f"第二次去重（URL对应域名，仅保留AS最高）: {len(merged)} 条")

    output_file = OUTPUT_DIR / f"backlinks_merged_{target_date}.csv"
    if safe_write_csv(merged, output_file):
        print(f"已写入: {output_file}  ({len(merged)} 条记录)")

    print("\n完成!")


if __name__ == "__main__":
    main()
