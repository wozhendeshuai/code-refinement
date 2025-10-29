# 通过
import json
from collections import Counter

import pandas as pd

from utils.code_file_check import is_code_file


def analyze_pr_and_issue_data(jsonl_file, issue_excel_file):
    """
    分析PR和Issue数据，统计相关信息
    """
    # 读取PR数据
    pr_data = []
    try:
        with open(jsonl_file, 'r', encoding='utf-8') as f:
            for line in f:
                pr_data.append(json.loads(line.strip()))
        print(f"成功读取 {len(pr_data)} 个PR数据")
    except Exception as e:
        print(f"读取PR数据失败: {e}")
        return

    # 读取Issue数据
    issue_data = []
    try:
        df_issues = pd.read_excel(issue_excel_file)
        issue_data = df_issues.to_dict('records')
        print(f"成功读取 {len(issue_data)} 个Issue数据")
    except Exception as e:
        print(f"读取Issue数据失败: {e}")
        return

    # 1. PR数量统计
    total_prs = len(pr_data)
    print(f"\n1. PR数量统计:")
    print(f"   总PR数量: {total_prs}")

    # 2. 关联Issue数量统计
    total_issues = len(issue_data)
    prs_with_issues = len(set(record['belong_pr_number'] for record in issue_data))
    print(f"\n2. 关联Issue统计:")
    print(f"   总Issue数量: {total_issues}")
    print(f"   关联Issue的PR数量: {prs_with_issues}")
    print(
        f"   平均每个PR关联Issue数: {total_issues / total_prs:.2f}" if total_prs > 0 else "   平均每个PR关联Issue数: 0")

    # 3. PR状态比例分析
    pr_states = [pr.get('state', 'unknown') for pr in pr_data]
    state_counter = Counter(pr_states)
    print(f"\n3. PR状态比例分析:")
    for state, count in state_counter.items():
        percentage = (count / total_prs) * 100 if total_prs > 0 else 0
        print(f"   {state}: {count} 个 ({percentage:.2f}%)")

    # 4. Issue作者与PR作者相同的比例
    same_author_count = 0
    comparison_count = 0

    # 创建PR数据索引以便快速查找
    pr_dict = {pr.get('number'): pr for pr in pr_data}

    for issue in issue_data:
        pr_number = issue.get('belong_pr_number')
        issue_author = issue.get('user_login')

        if pr_number and issue_author:
            pr = pr_dict.get(pr_number)
            if pr:
                pr_author_name = pr.get('user', {}).get('name')
                pr_author_login = pr.get('user', {}).get('login')
                if pr_author_name or pr_author_login:
                    comparison_count += 1
                    if pr_author_name and pr_author_name == issue_author:
                        same_author_count += 1
                    elif pr_author_login and pr_author_login == issue_author:
                        same_author_count += 1


    print(f"\n4. Issue作者与PR作者相同的比例:")
    if comparison_count > 0:
        same_author_percentage = (same_author_count / comparison_count) * 100
        print(f"   相同作者的Issue数量: {same_author_count}")
        print(f"   可比较的Issue数量: {comparison_count}")
        print(f"   相同作者比例: {same_author_percentage:.2f}%")
    else:
        print("   无法计算，没有可比较的数据")


def analyze_pr_refinement_data(jsonl_file, refinement_jsonl_file):
    """
    分析PR和PRRefinement数据，统计相关信息
    """
    # 读取所有PR数据
    all_pr_data = []
    try:
        with open(jsonl_file, 'r', encoding='utf-8') as f:
            for line in f:
                all_pr_data.append(json.loads(line.strip()))
        print(f"成功读取 {len(all_pr_data)} 个PR数据")
    except Exception as e:
        print(f"读取PR数据失败: {e}")
        return

    # 读取PRRefinement数据
    refinement_data = []
    try:
        with open(refinement_jsonl_file, 'r', encoding='utf-8') as f:
            for line in f:
                refinement_data.append(json.loads(line.strip()))
        print(f"成功读取 {len(refinement_data)} 个PRRefinement数据")
    except Exception as e:
        print(f"读取PRRefinement数据失败: {e}")
        return

    # 统计PR数量
    total_pr_count = len(all_pr_data)

    # 统计PRRefinement涉及的PR数量（去重）
    pr_numbers_in_refinement = set()
    for refinement in refinement_data:
        pr_number = refinement.get('pr_number')
        if pr_number:
            pr_numbers_in_refinement.add(pr_number)

    pr_refinement_count = len(pr_numbers_in_refinement)

    # 统计PR Refinement的总量
    refinement_gate_count = len(refinement_data)

    print(f"\nPR和PR Refinement统计分析:")
    print(f"  总PR数量: {total_pr_count}")
    print(f"  PR Refinement涉及的PR数量: {pr_refinement_count}")
    print(f"  PR Refinement的总量: {refinement_gate_count}")

    # 计算比例
    if total_pr_count > 0:
        pr_refinement_percentage = (pr_refinement_count / total_pr_count) * 100
        print(f"  涉及PR Refinement的PR占总PR比例: {pr_refinement_percentage:.2f}%")

    if pr_refinement_count > 0:
        avg_refinement_per_pr = refinement_gate_count / pr_refinement_count
        print(f"  平均每个涉及Refinement的PR有 {avg_refinement_per_pr:.2f} 个Refinement")


def analyze_pr_commit_and_file_statistics(jsonl_file):
    """
    分析PR的提交次数、文件数量、评论数量等统计信息
    """
    # 读取PR详细数据
    pr_data = []
    try:
        with open(jsonl_file, 'r', encoding='utf-8') as f:
            for line in f:
                pr_data.append(json.loads(line.strip()))
        print(f"成功读取 {len(pr_data)} 个PR详细数据")
    except Exception as e:
        print(f"读取PR详细数据失败: {e}")
        return

    # 统计数据
    commit_count_distribution = Counter()  # 提交次数分布
    file_count_distribution = Counter()  # 文件数量分布
    code_file_count_distribution = Counter()  # 代码文件数量分布
    comment_count_distribution = Counter()  # 评论数量分布

    total_commits = 0
    total_files = 0
    total_code_files = 0
    total_comments = 0

    for pr in pr_data:
        # 提交次数统计
        commit_count = pr.get('commit_count', 0)
        commit_count_distribution[commit_count] += 1
        total_commits += commit_count

        # 文件数量统计
        pr_files = pr.get('pr_files', [])
        file_count = len(pr_files)
        file_count_distribution[file_count] += 1
        total_files += file_count

        # 代码文件数量统计
        code_file_count = 0
        for file_info in pr_files:
            filename = file_info.get('filename', '')
            if is_code_file(filename):
                code_file_count += 1
        code_file_count_distribution[code_file_count] += 1
        total_code_files += code_file_count

        # 评论数量统计
        comment_count = pr.get('diff_comment_num', 0)
        comment_count_distribution[comment_count] += 1
        total_comments += comment_count

    total_prs = len(pr_data)
    print(f"\nPR提交次数分布:")
    if total_prs > 0 and commit_count_distribution:
        items = []
        for commit_count in sorted(commit_count_distribution.keys()):
            count = commit_count_distribution[commit_count]
            percentage = (count / total_prs) * 100
            items.append(f"{commit_count}次:{count} ({percentage:.2f}%)")
        print("  " + " | ".join(items))
    else:
        print("  无数据")

    print(f"\nPR文件数量分布:")
    if total_prs > 0 and file_count_distribution:
        items = []
        for file_count in sorted(file_count_distribution.keys()):
            count = file_count_distribution[file_count]
            percentage = (count / total_prs) * 100
            items.append(f"{file_count}个:{count} ({percentage:.2f}%)")
        print("  " + " | ".join(items))
    else:
        print("  无数据")

    print(f"\nPR代码文件数量分布:")
    if total_prs > 0 and code_file_count_distribution:
        items = []
        for code_file_count in sorted(code_file_count_distribution.keys()):
            count = code_file_count_distribution[code_file_count]
            percentage = (count / total_prs) * 100
            items.append(f"{code_file_count}个:{count} ({percentage:.2f}%)")
        print("  " + " | ".join(items))
    else:
        print("  无数据")

    print(f"\nPR评论数量分布:")
    if total_prs > 0 and comment_count_distribution:
        items = []
        for comment_count in sorted(comment_count_distribution.keys()):
            count = comment_count_distribution[comment_count]
            percentage = (count / total_prs) * 100
            items.append(f"{comment_count}条:{count} ({percentage:.2f}%)")
        print("  " + " | ".join(items))
    else:
        print("  无数据")

    print(f"\n平均值统计:")
    avg_commits = total_commits / total_prs if total_prs > 0 else 0
    avg_files = total_files / total_prs if total_prs > 0 else 0
    avg_code_files = total_code_files / total_prs if total_prs > 0 else 0
    avg_comments = total_comments / total_prs if total_prs > 0 else 0

    print(f"  每个PR平均提交次数: {avg_commits:.2f}")
    print(f"  每个PR平均文件数量: {avg_files:.2f}")
    print(f"  每个PR平均代码文件数量: {avg_code_files:.2f}")
    print(f"  每个PR平均评论数量: {avg_comments:.2f}")

REPO_List = [
    "account_os_account",
    "web_webview"
]
for repo in REPO_List:
    print("========"*20)
    print(repo)
    # --- 配置 ---
    print("========"*20)
    # 替换为你要查询的仓库所有者和仓库名
    OWNER = "openharmony"
    REPO = repo

    # GitCode API基础URL (根据文档)
    API_BASE_URL = "https://gitcode.com/api/v5"
    File_CONTENT_URL = "https://raw.gitcode.com"

    HEADERS = {
        'Accept': 'application/json',
        'PRIVATE-TOKEN': 'ZHntmapyoy-tm62QF71DMPkZ'
    }

    # 输出文件名
    PR_JSONL_FILE = f"{REPO}/{OWNER}_{REPO}_prs.jsonl"
    PR_ISSUE_EXCEL_FILE = f"{REPO}/{OWNER}_{REPO}_issues_linked_to_prs.xlsx"
    analyze_pr_and_issue_data(PR_JSONL_FILE, PR_ISSUE_EXCEL_FILE)

    # 输出文件名
    PR_COMMIT_COMMENT_JSONL_FILE = f"{REPO}/{OWNER}_{REPO}_pr_commit_comment_details_with_files.jsonl"
    analyze_pr_commit_and_file_statistics(PR_COMMIT_COMMENT_JSONL_FILE)


    PR_Refinement_JSONL_FILE = f"{REPO}/{OWNER}_{REPO}_pr_refinement_code.jsonl"
    analyze_pr_refinement_data(PR_JSONL_FILE, PR_Refinement_JSONL_FILE)
