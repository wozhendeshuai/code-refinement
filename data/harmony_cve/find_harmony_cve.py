#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re
import sys
from typing import List, Tuple, Optional, Dict, Any

import pandas as pd

OUTPUT_XLSX = "OpenHarmony_cve_output.xlsx"

# Markdown 链接: [text](url)
RE_MD_LINK = re.compile(r'\[([^\]]+)\]\((https?://[^\s\)]+)\)')
# 纯 URL
RE_URL = re.compile(r'(https?://[^\s\),;]+)')


def find_md_files(root_dir: str) -> List[str]:
    """递归查找所有 Markdown 文件"""
    md_files: List[str] = []
    for dirpath, _, filenames in os.walk(root_dir):
        for fn in filenames:
            if fn.lower().endswith(".md"):
                md_files.append(os.path.join(dirpath, fn))
    return sorted(md_files)


def extract_tables_from_lines(lines: List[str]) -> List[List[str]]:
    """
    从 Markdown 文件中提取所有形如：

    | col1 | col2 |
    | ---- | ---- |
    | ...  | ...  |

    的表格块。这里的策略比较朴素：
    1) 连续出现含有 '|' 的行视为一个表格候选块
    2) 如果块里出现分隔行（--- 或 :---: 这种），就认为是表格
    """
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
            # 判断这个块是不是表格：必须有分隔行
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
    """把一行 markdown 表格行拆成单元格"""
    text = row.strip().strip('|')
    return [c.strip() for c in text.split('|')]


def parse_table(table_lines: List[str]) -> Tuple[List[str], List[List[str]]]:
    """
    解析一个 markdown 表格块，返回 (表头, 数据行列表)
    表头是 List[str]
    数据行是 List[List[str]]
    """
    if len(table_lines) < 2:
        return [], []
    # 第一行一定是表头
    header_cells = split_md_table_row(table_lines[0])

    # 找出分隔行位置（通常第二行）
    sep_idx = next(
        (i for i, line in enumerate(table_lines[1:], start=1)
         if re.search(r'-{3,}', line)),
        1
    )

    # 分隔行之后的都当成数据行
    data_lines = table_lines[sep_idx + 1:]
    data_rows = [
        split_md_table_row(line)
        for line in data_lines
        if '|' in line and line.strip()
    ]
    return header_cells, data_rows


def extract_links_from_text(text: str) -> List[str]:
    """从一个单元格文本里尽可能多地提取 URL（支持 [text](url) 和裸 URL）"""
    urls = [m[1] for m in RE_MD_LINK.findall(text)]
    urls += [u for u in RE_URL.findall(text) if u not in urls]
    # 去重保持顺序
    return list(dict.fromkeys(urls))


def get_time_from_path(path: str) -> str:
    """从文件名中提取时间（去掉 .md），比如 2024-06.md -> 2024-06"""
    base = os.path.basename(path)
    return base[:-3] if base.lower().endswith(".md") else base


def should_process_table(headers: List[str]) -> bool:
    """判断是不是我们要的表：要求表头里既有“受影响的仓库”又有“修复链接”，并且这两列相邻"""
    header_str = ''.join(headers)
    if ('受影响的仓库' not in header_str) or ('修复链接' not in header_str):
        return False

    # 再检查是否相邻
    for i in range(len(headers) - 1):
        h1 = headers[i]
        h2 = headers[i + 1]
        if ('受影响的仓库' in h1 and '修复链接' in h2) or ('修复链接' in h1 and '受影响的仓库' in h2):
            return True

    return False


def find_column_indices(headers: List[str]) -> Dict[str, Optional[int]]:
    """
    根据表头的大概含义推断各列索引。
    当前支持的字段：
      - vuln_id: 漏洞编号 / 编号 / CVE / vulnerability
      - description: 描述
      - impact: 影响 / 受影响
      - fix: 修复 / 修复链接 / patch
    没有就留 None
    """
    hdr_low = [h.lower() for h in headers]
    mapping: Dict[str, Optional[int]] = {
        'vuln_id': None,
        'vul_description': None,
        'vul_impact': None,
        'impact_repo': None,
        'fix': None,
    }
    for i, h in enumerate(hdr_low):
        if any(k in h for k in ('漏洞编号', '编号', 'cve', 'vuln', 'vulnerability')):
            mapping['vuln_id'] = i
        elif any(k in h for k in ('漏洞描述', '描述', 'description')):
            mapping['vul_description'] = i
        elif h =="漏洞影响":
            mapping['vul_impact'] = i
        elif any(k in h for k in ('受影响的仓库')):
            mapping['impact_repo'] = i
        elif any(k in h for k in ('修复', '修复链接', 'fix', 'patch')):
            mapping['fix'] = i
    return mapping


def parse_vuln_table(path: str,
                     header_cells: List[str],
                     data_rows: List[List[str]]) -> List[Dict[str, Any]]:
    """把一张真正的漏洞表解析成结构化记录"""
    results: List[Dict[str, Any]] = []
    mapping = find_column_indices(header_cells)
    time_str = get_time_from_path(path)

    for row in data_rows:
        vuln_id = (
            row[mapping['vuln_id']]
            if mapping['vuln_id'] is not None and mapping['vuln_id'] < len(row)
            else ''
        )
        desc = (
            row[mapping['vul_description']]
            if mapping['vul_description'] is not None and mapping['vul_description'] < len(row)
            else ''
        )
        impact = (
            row[mapping['vul_impact']]
            if mapping['vul_impact'] is not None and mapping['vul_impact'] < len(row)
            else ''
        )
        impact_repo = (
            row[mapping['impact_repo']]
            if mapping['impact_repo'] is not None and mapping['impact_repo'] < len(row)
            else ''
        )
        fix_raw = (
            row[mapping['fix']]
            if mapping['fix'] is not None and mapping['fix'] < len(row)
            else ''
        )

        links = extract_links_from_text(fix_raw)
        # 如果有多条修复链接，就一行变多行
        if links:
            for link in links:
                results.append({
                    'time': time_str,
                    'source_file': path,
                    'vuln_id': vuln_id,
                    'vul_description': desc,
                    'vul_impact': impact,
                    'impact_repo': impact_repo,
                    'fix_link': link,
                })
        else:
            # 没有链接也留一行，方便后续人工补
            results.append({
                'time': time_str,
                'source_file': path,
                'vuln_id': vuln_id,
                'vul_description': desc,
                'vul_impact': impact,
                'impact_repo': impact_repo,
                'fix_link': '',
            })
    return results


def process_md_file(path: str) -> Tuple[Optional[List[Dict[str, Any]]], Optional[str]]:
    """
    处理单个 markdown：
    - 如果解析到了目标表，就返回 (记录列表, None)
    - 如果没解析到，就返回 (None, 这个文件路径) 方便写入人工复查
    """
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    lines = content.splitlines()
    tables = extract_tables_from_lines(lines)

    for t in tables:
        header_cells, data_rows = parse_table(t)
        if not header_cells:
            continue
        if should_process_table(header_cells):
            return parse_vuln_table(path, header_cells, data_rows), None

    # 所有表都不符合，标记人工复查
    return None, path


def main(root_dir: str):
    md_files = find_md_files(root_dir)
    print(f"找到 {len(md_files)} 个 md 文件，开始处理...")

    all_rows: List[Dict[str, Any]] = []
    need_manual: List[str] = []

    for md in md_files:
        try:
            parsed, manual = process_md_file(md)
            if parsed:
                all_rows.extend(parsed)
                print(f"[已解析] {md} -> {len(parsed)} 条记录")
            else:
                need_manual.append(manual)
                print(f"[待人工复查] {manual}")
        except Exception as e:
            print(f"[错误] 处理 {md} 时异常: {e}")
            need_manual.append(md)

    if all_rows:
        df = pd.DataFrame(all_rows)
        df.to_excel(OUTPUT_XLSX, index=False)
        print(f"✅ 已写入 {len(df)} 条记录到 {OUTPUT_XLSX}")
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
        print(f"⚠️ {len(need_manual)} 个文件需要人工复查，已写入 need_manual_list.txt")


if __name__ == "__main__":
    # 默认目录和你现在的一样
    root = "./security-disclosure"
    if len(sys.argv) > 1:
        root = sys.argv[1]
    main(root)