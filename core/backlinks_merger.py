"""
Semrush 反向链接数据整合分析模块
功能：
  1. 读取 data/downloads/ 下所有当日日期的 CSV 文件
  2. 解析并提取：页面AS、原URL、URL对应域名、类型、外部链接数
  3. 筛选"博客"类型，每个域名仅保留AS最高的记录
  4. 输出到 data/backlinks_merged_YYYY-MM-DD.csv
支持独立运行：python -m core.backlinks_merger
"""

import os
import re
import csv
import argparse
from datetime import date
from pathlib import Path
from typing import Optional, Dict, List, Tuple


# ========== 路径配置 ==========
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DOWNLOAD_DIR = PROJECT_ROOT / "data" / "downloads"
OUTPUT_DIR = PROJECT_ROOT / "data"
URL_BLACKLIST_FILE = PROJECT_ROOT / "data" / "url_blacklist.csv"
DOMAIN_BLACKLIST_FILE = PROJECT_ROOT / "data" / "domain_blacklist.csv"


# ========== 黑名单功能 ==========

def load_blacklist(filepath: Path) -> set:
    """从黑名单CSV文件加载关键词列表（去重、忽略空行和标题行）"""
    if not filepath.exists():
        return set()
    keywords = set()
    try:
        with open(filepath, "r", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            rows = list(reader)
    except (UnicodeError, UnicodeDecodeError):
        try:
            with open(filepath, "r", encoding="gbk") as f:
                reader = csv.reader(f)
                rows = list(reader)
        except Exception as e:
            print(f"  [!] 加载黑名单失败 {filepath}: {e}")
            return set()
    except Exception as e:
        print(f"  [!] 加载黑名单失败 {filepath}: {e}")
        return set()
    if not rows:
        return set()
    # 第一行如果是标题行，跳过
    data_rows = rows[1:] if len(rows) > 1 else rows
    for row in data_rows:
        for cell in row:
            kw = cell.strip()
            if kw:
                keywords.add(kw)
    return keywords


def load_all_blacklists() -> Tuple[set, set]:
    """加载 URL 黑名单和域名黑名单"""
    url_kw = load_blacklist(URL_BLACKLIST_FILE)
    domain_kw = load_blacklist(DOMAIN_BLACKLIST_FILE)
    if url_kw:
        print(f"已加载 URL 黑名单: {len(url_kw)} 条关键词")
    if domain_kw:
        print(f"已加载域名黑名单: {len(domain_kw)} 条关键词")
    return url_kw, domain_kw


def apply_blacklist_filter(records: List[Dict], url_blacklist: set, domain_blacklist: set) -> List[Dict]:
    """
    根据黑名单过滤记录。
    - URL 黑名单：对 source_url 进行子串匹配
    - 域名黑名单：对 domain（URL对应域名）和 target_domain（目标域名）进行子串匹配
    """
    if not url_blacklist and not domain_blacklist:
        return records

    filtered = []
    url_hit_count = 0
    domain_hit_count = 0

    for r in records:
        src_url = r["source_url"]
        src_domain = r["domain"]
        tgt_domain = r["target_domain"]

        url_blocked = False
        if url_blacklist:
            for kw in url_blacklist:
                if kw in src_url:
                    url_hit_count += 1
                    url_blocked = True
                    break

        domain_blocked = False
        if not domain_blocked and domain_blacklist:
            for kw in domain_blacklist:
                if kw in src_domain or kw in tgt_domain:
                    domain_hit_count += 1
                    domain_blocked = True
                    break

        if not url_blocked and not domain_blocked:
            filtered.append(r)

    total_removed = len(records) - len(filtered)
    if url_hit_count:
        print(f"  URL 黑名单过滤掉: {url_hit_count} 条")
    if domain_hit_count:
        print(f"  域名黑名单过滤掉: {domain_hit_count} 条")
    if total_removed:
        print(f"  黑名单共过滤掉: {total_removed} 条")
    return filtered


# ========== 解析工具 ==========

def parse_source_url_field(raw: str) -> Tuple[str, str, str]:
    """
    解析 '源页面标题和 URL' 字段。
    旧格式（用 | 分隔）：
      'https://sologamertest.fr/ | FR | 移动友好'
      'https://www.be-games.be/ | 博客 | FR | 移动友好'
    新格式（用换行符分隔，每行一个字段）：
      第一行：页面标题（可选）
      第二行：源页面 URL
      第三行及之后：标签（博客、Wiki、语言代码等）
    返回: (url, type_label, extra)
    """
    raw = raw.strip().strip('"')

    # 检测新格式：包含换行符，则每行对应一个字段
    if '\n' in raw:
        parts = raw.split('\n')
        # 第二行（index=1）一定是 URL
        url = parts[1].strip() if len(parts) > 1 else parts[0].strip()
        # 第三行及之后（index=2+）是标签
        tag_parts = parts[2:] if len(parts) > 2 else []
    else:
        # 旧格式：用 " | " 分割
        parts = raw.split(" | ")
        url = parts[0].strip()
        tag_parts = parts[1:]

    # 已知语言标签
    known_langs = {
        "FR", "EN", "ZH", "JA", "DE", "ES", "IT", "PT", "RU",
        "PL", "NL", "DA", "FI", "RO", "AR", "KO", "VI", "TH",
        "ID", "MS", "TR", "NO", "SV", "CS", "SK", "HE", "UK",
        "EL", "LT", "LV", "ET", "BG", "HR", "SL", "HU",
    }
    type_parts: List[str] = []
    lang_parts: List[str] = []
    for p in tag_parts:
        p = p.strip()
        if p in known_langs:
            lang_parts.append(p)
        else:
            type_parts.append(p)

    type_label = type_parts[0] if type_parts else ""
    extra = " | ".join(tag_parts)
    return url, type_label, extra


def extract_domain_from_url(raw: str) -> str:
    """从URL中提取域名"""
    raw = raw.strip().strip('"')
    if not raw:
        return ""
    # 去掉协议
    raw = re.sub(r"^https?://(www\.)?", "", raw, flags=re.IGNORECASE)
    # 去掉路径，取第一部分作为域名
    domain = raw.split("/")[0].split("?")[0].split("#")[0]
    return domain.strip()


def extract_domain_from_filename(filename: str) -> str:
    """从CSV文件名中提取目标域名，如 backlinks_export_2026-03-22_thenerdswife.com.csv -> thenerdswife.com"""
    name = os.path.basename(filename)
    # 去掉前缀 backlinks_export_YYYY-MM-DD_
    m = re.match(r"backlinks_export_\d{4}-\d{2}-\d{2}_(.+?)\.csv$", name)
    if m:
        return m.group(1)
    return ""


def parse_as(value: str) -> int:
    """解析页面AS为整数"""
    try:
        return int(str(value).strip().strip('"'))
    except (ValueError, TypeError):
        return 0


def parse_external_links(raw: str) -> int:
    """解析外部链接数"""
    try:
        return int(str(raw).strip().strip('"').split(",")[0])
    except (ValueError, TypeError):
        return 0


def parse_single_csv(filepath: str, target_domain: str = "") -> List[Dict]:
    """
    解析单个Semrush导出的CSV文件。
    原始列：页面 AS, 源页面标题和 URL, 外部链接, 内部链接, 锚链接和目标 URL,
            首次发现日期, 上次发现日期
    Args:
        filepath:       CSV文件路径
        target_domain:  目标域名（从CSV文件名中提取，代表Semrush查询的目标网站）
    返回解析后的记录列表。
    """
    records = []
    try:
        with open(filepath, "r", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            rows = list(reader)
    except UnicodeError:
        try:
            with open(filepath, "r", encoding="gbk") as f:
                reader = csv.reader(f)
                rows = list(reader)
        except Exception:
            print(f"  [!] 无法读取文件（编码问题）: {filepath}")
            return []
    except Exception as e:
        print(f"  [!] 读取文件失败: {filepath}, 错误: {e}")
        return []

    if len(rows) < 2:
        return []

    header = [h.strip() for h in rows[0]]
    # 标准化列名
    header_map: Dict[str, int] = {}
    for idx, h in enumerate(header):
        h_clean = h.strip()
        if "页面 AS" in h_clean or "AS" in h_clean:
            header_map["as"] = idx
        elif "源页面" in h_clean or "来源 URL" in h_clean:
            header_map["source"] = idx
        elif "外部链接" in h_clean:
            header_map["external"] = idx
        elif "内部链接" in h_clean:
            header_map["internal"] = idx
        elif "锚链接" in h_clean or "目标 URL" in h_clean:
            header_map["target"] = idx

    for row_idx, row in enumerate(rows[1:], start=2):
        if len(row) < max(header_map.values(), default=0) + 1:
            continue

        as_val = parse_as(row[header_map.get("as", 0)])
        source_raw = row[header_map.get("source", 1)].strip() if header_map.get("source") is not None else ""
        external_links = parse_external_links(
            row[header_map.get("external", 2)] if header_map.get("external") is not None else "0"
        )

        src_url, src_type, src_extra = parse_source_url_field(source_raw)
        domain = extract_domain_from_url(src_url)

        records.append({
            "as": as_val,
            "source_url": src_url,
            "domain": domain,
            "target_domain": target_domain,
            "type": src_type,
            "external_links": external_links,
        })

    return records


def find_today_csvs(target_date: Optional[str] = None) -> List[Path]:
    """
    在 DOWNLOAD_DIR 中查找文件名包含指定日期（YYYY-MM-DD 格式）的 backlinks_export CSV 文件。
    若 target_date 为 None，则使用今日日期。
    """
    if target_date is None:
        target_date = date.today().strftime("%Y-%m-%d")

    pattern = f"backlinks_export_{target_date}_*.csv"
    files = list(DOWNLOAD_DIR.glob(pattern))
    files.sort(key=lambda f: f.stat().st_mtime)
    return files


# ========== 核心合并逻辑 ==========

def merge_and_filter(records: List[Dict]) -> List[Dict]:
    """
    筛选博客类型 + 域名去重（保留AS最高的记录）。
    输入：所有CSV的所有记录
    输出：筛选并去重后的记录
    """
    # 1. 仅保留类型为"博客"的记录
    blog_records = [r for r in records if r["type"] == "博客"]

    # 2. 按（源域名 + 目标域名）组合分组，每组保留AS最高的记录
    key_best: Dict[str, Dict] = {}
    for r in blog_records:
        # 用 "源域名 | 目标域名" 作为去重键，确保同一来源在每个目标域名下只保留一条
        key = f"{r['domain']} | {r['target_domain']}"
        if key not in key_best or r["as"] > key_best[key]["as"]:
            key_best[key] = r

    # 3. 按AS降序排列
    result = sorted(key_best.values(), key=lambda x: x["as"], reverse=True)
    return result


def write_merged_csv(records: List[Dict], output_path: Path):
    """将合并后的数据写入CSV"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["页面AS", "原URL", "URL对应域名", "目标域名", "类型", "外部链接数量"])
        for r in records:
            writer.writerow([
                r["as"],
                r["source_url"],
                r["domain"],
                r["target_domain"],
                r["type"],
                r["external_links"],
            ])
    print(f"已写入: {output_path}  ({len(records)} 条记录)")


# ========== 主入口 ==========

def run_merger(
    target_date: Optional[str] = None,
    download_dir: Optional[Path] = None,
    use_blacklist: bool = True,
):
    """
    执行合并分析流程。
    Args:
        target_date:    指定日期字符串（如 "2026-03-22"），None则用今天
        download_dir:   下载目录路径，默认用 DOWNLOAD_DIR
        use_blacklist:  是否启用黑名单过滤（默认 True）
    """
    if download_dir:
        global DOWNLOAD_DIR
        DOWNLOAD_DIR = Path(download_dir)

    if target_date is None:
        target_date = date.today().strftime("%Y-%m-%d")

    print("=" * 50)
    print(f"Semrush 反向链接数据整合分析")
    print(f"日期: {target_date}")
    print(f"下载目录: {DOWNLOAD_DIR}")
    print("=" * 50)

    csv_files = find_today_csvs(target_date)
    if not csv_files:
        print(f"\n[!] 在 {DOWNLOAD_DIR} 中未找到日期为 {target_date} 的 CSV 文件")
        print("    提示：文件名格式应为 backlinks_export_YYYY-MM-DD_域名.csv")
        return False

    print(f"\n找到 {len(csv_files)} 个CSV文件:")
    for f in csv_files:
        print(f"  - {f.name}")

    all_records: List[Dict] = []
    for fpath in csv_files:
        print(f"\n解析: {fpath.name}")
        recs = parse_single_csv(str(fpath), target_domain=extract_domain_from_filename(fpath.name))
        print(f"  读取到 {len(recs)} 条记录")
        all_records.extend(recs)

    if not all_records:
        print("\n[!] 未读取到任何数据")
        return False

    print(f"\n总计读取: {len(all_records)} 条记录")

    # 黑名单过滤
    if use_blacklist:
        url_bl, domain_bl = load_all_blacklists()
        if url_bl or domain_bl:
            all_records = apply_blacklist_filter(all_records, url_bl, domain_bl)
            print(f"黑名单过滤后剩余: {len(all_records)} 条")

    blog_count = sum(1 for r in all_records if r["type"] == "博客")
    print(f"其中【博客】类型: {blog_count} 条")

    merged = merge_and_filter(all_records)
    print(f"去重后（每域名保留AS最高）: {len(merged)} 条")

    output_file = OUTPUT_DIR / f"backlinks_merged_{target_date}.csv"
    write_merged_csv(merged, output_file)

    print("\n" + "=" * 50)
    print("整合分析完成!")
    print("=" * 50)
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Semrush反向链接数据整合分析 - 支持独立运行",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python -m core.backlinks_merger                      # 分析今天的CSV
  python -m core.backlinks_merger --date 2026-03-22 # 分析指定日期
  python -m core.backlinks_merger --dir "E:\\data\\downloads" # 指定下载目录
        """,
    )
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="目标日期（YYYY-MM-DD格式），默认为今天",
    )
    parser.add_argument(
        "--dir",
        type=str,
        default=None,
        help="CSV下载目录路径，默认: data/downloads",
    )
    parser.add_argument(
        "--no-blacklist",
        action="store_true",
        help="禁用黑名单过滤",
    )
    args = parser.parse_args()

    run_merger(target_date=args.date, download_dir=args.dir, use_blacklist=not args.no_blacklist)


if __name__ == "__main__":
    main()
