#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re
import sys
from typing import List, Tuple, Optional, Dict, Any

import pandas as pd

OUTPUT_XLSX = "OpenHarmony_cve_extra_output.xlsx"

# Markdown 链接: [text](url)
RE_MD_LINK = re.compile(r'\[([^\]]+)\]\((https?://[^\s\)]+)\)')
# 纯 URL
RE_URL = re.compile(r'(https?://[^\s\),;]+)')


def find_md_files(root_dir: str) -> List[str]:
    md_files: List[str] = []
    for dirpath, _, filenames in os.walk(root_dir):
        for fn in filenames:
            if fn.lower().endswith(".md"):
                md_files.append(os.path.join(dirpath, fn))
    return sorted(md_files)


def extract_tables_from_lines(lines: List[str]) -> List[List[str]]:
    """从 Markdown 中提取所有表格块"""
    tables: List[List[str]] = []
    i = 0
    n = len(lines)
    while i < n:
        if '|' in lines[i]:
            j = i
            block: List[str] = []
            while j < n and '|' in lines[j]:
                block.append(lines[j].rstrip('\n'))
                j += 1
            has_sep = any(
                re.search(r'-{3,}', ln) or re.search(r':?-{3,}:?', ln)
                for ln in block
            )
            if has_sep and len(block) >= 2:
                tables.append(block)
                i = j
                continue
        i += 1
    return tables


def split_md_table_row(row: str) -> List[str]:
    text = row.strip().strip('|')
    return [c.strip() for c in text.split('|')]


def parse_table(table_lines: List[str]) -> Tuple[List[str], List[List[str]]]:
    """拆成表头 + 数据行"""
    if len(table_lines) < 2:
        return [], []
    header_cells = split_md_table_row(table_lines[0])
    # 找分隔行
    sep_idx = next(
        (i for i, line in enumerate(table_lines[1:], start=1) if re.search(r'-{3,}', line)),
        1
    )
    data_lines = table_lines[sep_idx + 1:]
    data_rows = [
        split_md_table_row(line)
        for line in data_lines
        if '|' in line and line.strip()
    ]
    return header_cells, data_rows


def get_time_from_path(path: str) -> str:
    base = os.path.basename(path)
    return base[:-3] if base.lower().endswith(".md") else base


def extract_links_from_text(text: str) -> List[str]:
    """从单元格里提取所有链接"""
    urls = [m[1] for m in RE_MD_LINK.findall(text)]
    urls += [u for u in RE_URL.findall(text) if u not in urls]
    return list(dict.fromkeys(urls))


def extract_repo_from_url(url: str) -> str:
    """
    从 url 中提取 openharmony 后面的仓库名
    规则：找到 'openharmony/' 然后取到下一个 '/'
    """
    key = "openharmony/"
    idx = url.find(key)
    if idx == -1:
        return ""
    start = idx + len(key)
    # 找下一个 /
    end = url.find('/', start)
    if end == -1:
        # 没有 / 了，就取到末尾
        return url[start:]
    return url[start:end]


def is_main_table(headers: List[str]) -> bool:
    """
    这是你原来那个“主表”的识别逻辑（受影响的仓库 + 修复链接 且相邻）；
    这里我们要的是“另一个表”，所以后面会跳过它。
    """
    header_str = ''.join(headers)
    if ('受影响的仓库' not in header_str) or ('修复链接' not in header_str):
        return False
    for i in range(len(headers) - 1):
        h1 = headers[i]
        h2 = headers[i + 1]
        if ('受影响的仓库' in h1 and '修复链接' in h2) or ('修复链接' in h1 and '受影响的仓库' in h2):
            return True
    return False


def find_cols_for_extra_table(headers: List[str]) -> Dict[str, Optional[int]]:
    """
    这个函数是给“第二张表”用的，我们只想抓：
    - CVE / 漏洞编号 / 编号
    - 修复链接
    受影响的仓库我们是从链接里拆，不一定有列
    """
    hdr_low = [h.lower() for h in headers]
    mapping: Dict[str, Optional[int]] = {
        "vuln_id": None,
        "fix": None,
    }
    for i, h in enumerate(hdr_low):
        if any(k in h for k in ("cve", "漏洞编号", "编号", "vulnerability")):
            mapping["vuln_id"] = i
        elif any(k in h for k in ("修复", "修复链接", "fix", "patch")):
            mapping["fix"] = i
    return mapping


def process_md_file(path: str) -> Tuple[Optional[List[Dict[str, Any]]], Optional[str]]:
    """
    处理单个 md：
    - 跳过第一个“主表”（受影响的仓库 + 修复链接 且相邻）
    - 尝试处理其它表，按“只有 CVE 和 修复链接”的规则解析
    """
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    lines = content.splitlines()
    tables = extract_tables_from_lines(lines)

    if not tables:
        return None, path

    results: List[Dict[str, Any]] = []
    time_str = get_time_from_path(path)

    # 标记一下有没有看到主表
    main_table_seen = False

    for idx, t in enumerate(tables):
        header_cells, data_rows = parse_table(t)
        if not header_cells:
            continue

        # 先跳过主表
        if is_main_table(header_cells):
            main_table_seen = True
            continue

        # 其它表就按“CVE + 修复链接”来解析
        col_map = find_cols_for_extra_table(header_cells)
        if col_map["vuln_id"] is None or col_map["fix"] is None:
            # 这张表也不是我们要的，继续看下一张
            continue

        for row in data_rows:
            # 防御：行长度不够就补空
            if len(row) < len(header_cells):
                row = row + [""] * (len(header_cells) - len(row))

            vuln_id = row[col_map["vuln_id"]] if col_map["vuln_id"] is not None else ""
            fix_raw = row[col_map["fix"]] if col_map["fix"] is not None else ""

            links = extract_links_from_text(fix_raw)
            if not links:
                # 没链接也给一行，方便人工看
                results.append({
                    "time": time_str,
                    "source_file": path,
                    "vuln_id": vuln_id,
                    "vul_description": "",
                    "vul_impact": "",
                    "impact_repo": "",
                    "fix_link": "",
                })
            else:
                for link in links:
                    repo = extract_repo_from_url(link)
                    results.append({
                        "time": time_str,
                        "source_file": path,
                        "vuln_id": vuln_id,
                        "vul_description": "",
                        "vul_impact": "",
                        "impact_repo": repo,
                        "fix_link": link,
                    })

    if results:
        return results, None
    else:
        return None, path


def main(root_dir: str):
    md_files = find_md_files(root_dir)
    print(f"找到 {len(md_files)} 个 md 文件，开始处理(主表+额外表格)...")

    main_results: List[Dict[str, Any]] = []
    extra_results: List[Dict[str, Any]] = []
    need_manual: List[str] = []
    extra_need_manual: List[str] = []

    # 先处理主表
    for md in md_files:
        try:
            with open(md, "r", encoding="utf-8") as f:
                content = f.read()
            lines = content.splitlines()
            tables = extract_tables_from_lines(lines)
            time_str = get_time_from_path(md)
            found_main = False
            for t in tables:
                header_cells, data_rows = parse_table(t)
                if not header_cells:
                    continue
                if is_main_table(header_cells):
                    # 主表处理逻辑
                    col_map = {}
                    for idx, h in enumerate(header_cells):
                        if "编号" in h or "CVE" in h or "vulnerability" in h.lower():
                            col_map["vuln_id"] = idx
                        elif "漏洞描述" in h:
                            col_map["vul_description"] = idx
                        elif "漏洞影响" in h:
                            col_map["vul_impact"] = idx
                        elif "受影响的仓库" in h:
                            col_map["impact_repo"] = idx
                        elif "修复" in h:
                            col_map["fix_link"] = idx
                    for row in data_rows:
                        if len(row) < len(header_cells):
                            row = row + [""] * (len(header_cells) - len(row))
                        main_results.append({
                            "time": time_str,
                            "source_file": md,
                            "vuln_id": row[col_map.get("vuln_id", -1)] if col_map.get("vuln_id", -1) != -1 else "",
                            "vul_description": row[col_map.get("vul_description", -1)] if col_map.get("vul_description", -1) != -1 else "",
                            "vul_impact": row[col_map.get("vul_impact", -1)] if col_map.get("vul_impact", -1) != -1 else "",
                            "impact_repo": row[col_map.get("impact_repo", -1)] if col_map.get("impact_repo", -1) != -1 else "",
                            "fix_link": row[col_map.get("fix_link", -1)] if col_map.get("fix_link", -1) != -1 else "",
                        })
                    found_main = True
                    print(f"[已解析主表] {md} -> {len(data_rows)} 条记录")
                    break  # 只取第一个主表
            if not found_main:
                need_manual.append(md)
                print(f"[主表待人工复查] {md}")
        except Exception as e:
            print(f"[主表错误] 处理 {md} 时异常: {e}")
            need_manual.append(md)

    # 再处理额外表格
    for md in md_files:
        try:
            parsed, manual = process_md_file(md)
            if parsed:
                extra_results.extend(parsed)
                print(f"[已解析额外表格] {md} -> {len(parsed)} 条记录")
            else:
                extra_need_manual.append(manual)
                print(f"[额外表格待人工复查] {manual}")
        except Exception as e:
            print(f"[额外表格错误] 处理 {md} 时异常: {e}")
            extra_need_manual.append(md)

    # 合并主表和额外表格结果，保持列顺序一致
    all_rows = main_results + extra_results
    if all_rows:
        cols = [
            "time",          # 时间（文件名）
            "source_file",   # 来源文件
            "vuln_id",       # 编号/CVE
            "vul_description",  # 漏洞描述
            "vul_impact",       # 漏洞影响
            "impact_repo",      # 受影响的仓库
            "fix_link",         # 修复链接
        ]
        df_all = pd.DataFrame(all_rows)
        df_all = df_all[cols]
        df_all.to_excel(OUTPUT_XLSX, index=False)
        print(f"✅ 已写入 {len(df_all)} 条记录到 {OUTPUT_XLSX}")
        repo_static = {}
        for vul_row in all_rows:
            temp_repo_name = vul_row['impact_repo']
            if temp_repo_name not in repo_static:
                repo_static[temp_repo_name] = 0
            repo_static[temp_repo_name] += 1

        total_count = sum(repo_static.values())
        print("各受影响仓库统计（按数量从高到低）：")
        for repo_name, count in sorted(repo_static.items(), key=lambda x: x[1], reverse=True):
            percentage = (count / total_count) * 100
            print(f"  {repo_name}: {count} ({percentage:.2f}%)")

    if need_manual:
        with open("need_manual_list.txt", "w", encoding="utf-8") as f:
            for p in need_manual:
                if p:
                    f.write(p + "\n")
        print(f"⚠️ {len(need_manual)} 个文件主表需要人工复查，已写入 need_manual_list.txt")

    if extra_need_manual:
        with open("extra_need_manual_list.txt", "w", encoding="utf-8") as f:
            for p in extra_need_manual:
                if p:
                    f.write(p + "\n")
        print(f"⚠️ {len(extra_need_manual)} 个文件中额外表格需要人工复查，已写入 extra_need_manual_list.txt")


if __name__ == "__main__":
    root = "./security-disclosure"
    if len(sys.argv) > 1:
        root = sys.argv[1]
    main(root)