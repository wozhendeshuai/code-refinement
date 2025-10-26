import json
import os
import time

import pandas as pd
import requests

# --- 配置 ---
# 替换为你要查询的仓库所有者和仓库名
OWNER = "openharmony"
REPO = "xts_acts"

# GitCode API基础URL (根据文档)
API_BASE_URL = "https://gitcode.com/api/v5"

HEADERS = {
    'Accept': 'application/json',
    'PRIVATE-TOKEN': 'r34uS2yEqhNMTBwmAN5ZkQTa'
}

# 输出文件名
OUTPUT_JSONL_FILE = f"{REPO}/{OWNER}_{REPO}_prs.jsonl"
OUTPUT_PR_EXCEL_FILE = f"{REPO}/{OWNER}_{REPO}_prs_summary.xlsx"
OUTPUT_ISSUE_EXCEL_FILE = f"{REPO}/{OWNER}_{REPO}_issues_linked_to_prs.xlsx"

# 断点续传记录文件名
FULLY_PROCESSED_IDS_FILE = f"{REPO}/{OWNER}_{REPO}_fully_processed_pr_ids.txt"  # 所有步骤完成的PR ID
PARTIALLY_PROCESSED_IDS_FILE = f"{REPO}/{OWNER}_{REPO}_partially_processed_pr_ids.txt"  # PR数据已处理，Issues待处理的PR ID

# API请求参数
PER_PAGE = 100  # 每页数量，最大100 (根据文档)


# --- 配置结束 ---


def load_id_set_from_file(filename):
    """从文件中读取ID集合"""
    id_set = set()
    if os.path.exists(filename):
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        # 假设ID是整数
                        id_set.add(int(line))
        except Exception as e:
            print(f"读取ID文件 {filename} 时出错: {e}")
    return id_set


def save_id_to_file(pr_id, filename):
    """将ID追加到文件"""
    try:
        with open(filename, 'a', encoding='utf-8') as f:
            f.write(f"{pr_id}\n")
    except Exception as e:
        print(f"写入ID文件 {filename} 时出错: {e}")


def remove_id_from_file(pr_id, filename):
    """从文件中移除特定ID (注意：这需要重写文件)"""
    if not os.path.exists(filename):
        return
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        with open(filename, 'w', encoding='utf-8') as f:
            for line in lines:
                if line.strip() != str(pr_id):
                    f.write(line)
    except Exception as e:
        print(f"从文件 {filename} 移除ID {pr_id} 时出错: {e}")


def fetch_pr_list(page, per_page, state='merged'):
    """调用API获取一页PR列表"""
    url = f"{API_BASE_URL}/repos/{OWNER}/{REPO}/pulls"
    params = {
        'state': state,  # 获取已合并的PR
        'page': page,
        'per_page': per_page
    }
    try:
        response = requests.get(url, headers=HEADERS, params=params)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"获取PR列表失败 (页 {page}): {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"  响应内容: {e.response.text}")
        return None


def fetch_single_pr(pr_number):
    """调用API获取单个PR的详细信息"""
    url = f"{API_BASE_URL}/repos/{OWNER}/{REPO}/pulls/{pr_number}"

    try:
        response = requests.get(url, headers=HEADERS)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"获取单个PR #{pr_number} 详细信息失败: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"  响应内容: {e.response.text}")
        return None


def fetch_issues_linked_to_pr(pr_number):
    """调用API获取与指定PR关联的Issues列表"""
    url = f"{API_BASE_URL}/repos/{OWNER}/{REPO}/pulls/{pr_number}/issues"
    # 根据文档，这个接口可能不支持分页或参数较少

    try:
        response = requests.get(url, headers=HEADERS)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"获取PR #{pr_number} 关联的Issues失败: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"  响应内容: {e.response.text}")
        return None


def extract_pr_info_for_excel(pr_data):
    """从PR详细数据中提取需要保存到Excel的信息"""
    assignees_name_list = [assignee.get('name', '') for assignee in pr_data.get('assignees', [])]
    testers_name_list = [tester.get('name', '') for tester in pr_data.get('testers', [])]
    approval_reviewers_list = []
    for reviewer in pr_data.get('approval_reviewers', []):
        if isinstance(reviewer, str):
            approval_reviewers_list.append(reviewer)
        elif isinstance(reviewer, dict):
            approval_reviewers_list.append(reviewer.get('name', ''))
    labels_name_list = [label.get('name', '') for label in pr_data.get('labels', [])]

    row_data = {
        'id': pr_data.get('id'),
        'number': pr_data.get('number'),
        'html_url': pr_data.get('html_url'),
        'state': pr_data.get('state'),
        'title': pr_data.get('title'),
        'url': pr_data.get('url'),
        'issue_url': pr_data.get('issue_url'),
        'body': pr_data.get('body'),
        'assignees_number': pr_data.get('assignees_number'),
        'assignees_name_list': ', '.join(assignees_name_list),
        'testers_name_list': ', '.join(testers_name_list),
        'approval_reviewers': ', '.join(approval_reviewers_list),
        'labels_name_list': ', '.join(labels_name_list),
        'created_at': pr_data.get('created_at'),
        'updated_at': pr_data.get('updated_at'),
        'closed_at': pr_data.get('closed_at'),
        'merged_at': pr_data.get('merged_at'),
        'draft': pr_data.get('draft'),
        'can_merge_check': pr_data.get('can_merge_check'),
        'prune_branch': pr_data.get('prune_branch'),
        'mergeable': pr_data.get('mergeable'),
        'user': pr_data.get('user', {}).get('name', pr_data.get('user', {}).get('login', ''))
    }
    return row_data


def extract_issue_info_for_excel(issue_data, belong_pr_number):
    """从Issue数据中提取需要保存到Excel的信息"""
    labels_name_list = [label.get('name', '') for label in issue_data.get('labels', [])]

    row_data = {
        'belong_pr_number': belong_pr_number,  # 关联的PR号
        'issue_number': issue_data.get('number'),
        'title': issue_data.get('title'),
        'state': issue_data.get('state'),
        'url': issue_data.get('url'),
        'html_url': issue_data.get('html_url'),
        'id': issue_data.get('id'),
        'body': issue_data.get('body'),
        'user_login': issue_data.get('user', {}).get('login', ''),  # 通常用login标识用户
        'labels_name_list': ', '.join(labels_name_list),
    }
    return row_data


def append_df_to_excel(df_new_data, excel_filename):
    """将DataFrame追加到Excel文件"""
    if os.path.exists(excel_filename):
        try:
            df_existing = pd.read_excel(excel_filename)
            df_combined = pd.concat([df_existing, df_new_data], ignore_index=True)
        except Exception as e:
            print(f"读取或合并Excel文件 {excel_filename} 时出错: {e}. 将覆盖原文件或创建新文件.")
            df_combined = df_new_data
    else:
        df_combined = df_new_data

    try:
        df_combined.to_excel(excel_filename, index=False)
        # print(f"数据已追加到Excel文件 {excel_filename}。")
    except Exception as e:
        print(f"保存数据到Excel文件 {excel_filename} 时出错: {e}")


def save_pr_data(detailed_pr, pr_info_for_excel):
    """保存PR的JSONL和摘要Excel"""
    pr_id = detailed_pr.get('id')
    pr_number = detailed_pr.get('number')
    jsonl_success = False
    excel_success = False

    # 保存到JSONL
    try:
        # 确保目录存在
        os.makedirs(os.path.dirname(OUTPUT_JSONL_FILE), exist_ok=True)
        with open(OUTPUT_JSONL_FILE, 'a', encoding='utf-8') as f:
            f.write(json.dumps(detailed_pr, ensure_ascii=False) + '\n')
        jsonl_success = True
        print(f"    PR #{pr_number} 详细信息已保存到JSONL。")
    except Exception as e:
        print(f"    保存PR #{pr_number} 到JSONL文件时出错: {e}")

    # 保存到PR摘要Excel
    if jsonl_success:
        try:
            # 确保目录存在
            os.makedirs(os.path.dirname(OUTPUT_PR_EXCEL_FILE), exist_ok=True)
            df_pr_row = pd.DataFrame([pr_info_for_excel])
            append_df_to_excel(df_pr_row, OUTPUT_PR_EXCEL_FILE)
            excel_success = True
            print(f"    PR #{pr_number} 摘要信息已保存到Excel。")
        except Exception as e:
            print(f"    保存PR #{pr_number} 摘要信息到Excel时出错: {e}")

    return jsonl_success, excel_success


def save_linked_issues(pr_number, linked_issues_data):
    """保存关联的Issues到Excel"""
    issues_success = True  # 默认成功，除非有错误发生
    if linked_issues_data is None:
        print(f"    PR #{pr_number} 无关联Issues数据或获取失败。")
        return issues_success  # 即使是None(无数据或失败)，也视为“处理完毕”

    if not linked_issues_data:  # 空列表
        print(f"    PR #{pr_number} 未关联任何Issues。")
        return issues_success

    print(f"    PR #{pr_number} 关联了 {len(linked_issues_data)} 个Issue。")
    list_issue_rows = []
    for issue_data in linked_issues_data:
        try:
            issue_row = extract_issue_info_for_excel(issue_data, pr_number)
            list_issue_rows.append(issue_row)
        except Exception as e:
            print(f"    提取PR #{pr_number} 关联的Issue {issue_data.get('number')} 信息时出错: {e}")
            issues_success = False  # 标记为不完全成功

    if list_issue_rows:
        try:
            df_issues = pd.DataFrame(list_issue_rows)
            append_df_to_excel(df_issues, OUTPUT_ISSUE_EXCEL_FILE)
            print(f"    PR #{pr_number} 的关联Issues信息已保存到Excel。")
        except Exception as e:
            print(f"    保存PR #{pr_number} 的关联Issues信息到Excel时出错: {e}")
            issues_success = False

    return issues_success


def mark_pr_as_fully_processed(pr_id, partially_processed_ids):
    """标记PR为完全处理完毕"""
    # 从部分处理列表中移除（如果存在）
    if pr_id in partially_processed_ids:
        remove_id_from_file(pr_id, PARTIALLY_PROCESSED_IDS_FILE)
        partially_processed_ids.discard(pr_id)
    # 添加到完全处理列表
    save_id_to_file(pr_id, FULLY_PROCESSED_IDS_FILE)


def mark_pr_as_partially_processed(pr_id):
    """标记PR为部分处理（PR数据已保存）"""
    # 确保不重复添加
    # 注意：在主循环中调用此函数前应已检查是否在 fully_processed_ids 中
    save_id_to_file(pr_id, PARTIALLY_PROCESSED_IDS_FILE)


def main():
    """主函数"""
    print(f"开始获取仓库 {OWNER}/{REPO} 的已合并PR及其关联的Issues...")

    # 1. 加载断点续传状态
    fully_processed_ids = load_id_set_from_file(FULLY_PROCESSED_IDS_FILE)
    partially_processed_ids = load_id_set_from_file(PARTIALLY_PROCESSED_IDS_FILE)

    print(f"已加载 {len(fully_processed_ids)} 个完全处理完毕的PR ID。")
    print(f"已加载 {len(partially_processed_ids)} 个部分处理的PR ID (需检查Issues)。")

    page = 1
    total_api_fetched = 0  # 从API获取的PR摘要数
    total_pr_details_fetched = 0  # 成功获取详细信息的PR数
    total_pr_saved_jsonl = 0  # 成功保存到JSONL的PR数
    total_pr_saved_excel = 0  # 成功保存到PR Excel的PR数
    total_issues_saved_excel = 0  # 成功保存到Issue Excel的Issue记录数 (估算)

    try:
        while True:
            print(f"\n--- 正在获取第 {page} 页merged的PR列表 ---")
            pr_list_merged = fetch_pr_list(page, PER_PAGE, state='merged')
            print(f"\n--- 正在获取第 {page} 页closed的PR列表 ---")
            pr_list_closed = fetch_pr_list(page, PER_PAGE, state='closed')
            if pr_list_closed and pr_list_merged:
                pr_list= pr_list_merged + pr_list_closed
            elif pr_list_closed:
                pr_list = pr_list_closed
            elif pr_list_merged:
                pr_list = pr_list_merged
            else:
                pr_list = None

            if pr_list is None:
                print("由于API错误，无法继续获取PR列表。")
                break

            if not pr_list:
                print("没有更多PR数据，获取完成。")
                break

            total_api_fetched += len(pr_list)
            print(f"  获取到 {len(pr_list)} 个PR摘要信息。")
            pr_index_in_page=1
            for pr_summary in pr_list:
                pr_id = pr_summary.get('id')
                pr_number = pr_summary.get('number')

                if not pr_id or not pr_number:
                    print(f"  警告：PR摘要缺少ID或Number: {pr_summary}")
                    continue

                # --- 断点续传逻辑 ---
                if pr_id in fully_processed_ids:
                    print(f"  PR ID {pr_id} (#{pr_number}) 已完全处理，跳过。")
                    continue

                # --- 处理PR数据 ---
                # 获取当前PR在本页中的索引（第几个）
                pr_index_in_page = pr_list.index(pr_summary) + 1
                print(f"\n  > 处理第 {page} 页的第 {pr_index_in_page} 个 PR #{pr_number} (ID: {pr_id}) ...")
                total_pr_details_fetched += 1

                # 获取PR详细信息
                detailed_pr = fetch_single_pr(pr_number)
                if detailed_pr is None:
                    print(f"    获取PR #{pr_number} 详细信息失败，跳过。")
                    # 注意：这里不记录ID，因为详细信息获取失败，下次会重试。
                    # 如果想避免重试失败的PR，可以在这里记录到一个失败列表文件。
                    continue

                # 提取PR摘要信息
                pr_info_for_excel = extract_pr_info_for_excel(detailed_pr)

                # 保存PR数据 (JSONL & Excel)
                jsonl_ok, excel_ok = save_pr_data(detailed_pr, pr_info_for_excel)
                if jsonl_ok:
                    total_pr_saved_jsonl += 1
                if excel_ok:
                    total_pr_saved_excel += 1

                # --- 处理关联的Issues ---
                issues_ok = False
                linked_issues_data = None
                # 无论PR数据是否完全保存成功，都尝试获取Issues
                # （但只有PR数据成功保存，才值得保存Issues）
                if jsonl_ok or excel_ok:
                    print(f"    正在获取PR #{pr_number} 关联的Issues...")
                    linked_issues_data = fetch_issues_linked_to_pr(pr_number)

                # 保存Issues信息 (Excel)
                # 只有当PR数据至少有一项保存成功时，才处理Issues
                if jsonl_ok or excel_ok:
                    issues_ok = save_linked_issues(pr_number, linked_issues_data)
                    # 粗略估算保存的Issue数量
                    if linked_issues_data and isinstance(linked_issues_data, list):
                        total_issues_saved_excel += len(linked_issues_data)

                # --- 更新断点续传状态 ---
                # 策略：只要PR的JSONL或Excel保存成功，就认为PR部分处理完成
                # 只有当PR数据和Issues都处理完毕（或确认无Issues）时，才标记为完全处理
                if jsonl_ok or excel_ok:
                    # 1. 标记为部分处理（PR数据已保存）
                    if pr_id not in partially_processed_ids and pr_id not in fully_processed_ids:
                        mark_pr_as_partially_processed(pr_id)
                        partially_processed_ids.add(pr_id)

                    # 2. 如果Issues也处理完毕（或无），则标记为完全处理
                    #    （这里简化处理：只要尝试了保存Issues，就认为处理完毕）
                    #    （更严谨的做法是检查 save_linked_issues 的返回值和 linked_issues_data 的状态）
                    #    （当前逻辑下，即使Issues API失败，也会标记为完全处理，因为PR数据已存）
                    #    （如果希望Issues失败也重试，则需要更复杂的逻辑来区分“无Issues”和“获取失败”）
                    #    （此处按“处理了Issues环节”来判断）
                    if True:  # issues环节已处理
                        mark_pr_as_fully_processed(pr_id, partially_processed_ids)
                        fully_processed_ids.add(pr_id)
                        print(f"    PR #{pr_number} 已标记为完全处理完毕。")

            page += 1
            # 可选：在处理完每页后添加延迟
            time.sleep(20)  # 避免触发速率限制

    except KeyboardInterrupt:
        print("\n\n收到中断信号，正在保存进度并退出...")
    finally:
        print("\n" + "=" * 50)
        print("脚本执行结束。")
        print(f"  - 从API获取的PR摘要总数: {total_api_fetched}")
        print(f"  - 成功获取详细信息的PR数: {total_pr_details_fetched}")
        print(f"  - 成功保存到 {OUTPUT_JSONL_FILE} 的PR数: {total_pr_saved_jsonl}")
        print(f"  - 成功保存到 {OUTPUT_PR_EXCEL_FILE} 的PR数: {total_pr_saved_excel}")
        print(f"  - 成功保存到 {OUTPUT_ISSUE_EXCEL_FILE} 的Issue记录数 (估算): {total_issues_saved_excel}")
        print(f"  - 完全处理完毕的PR数: {len(fully_processed_ids)}")
        print(f"  - 部分处理的PR数: {len(partially_processed_ids)}")
        print("=" * 50)


if __name__ == "__main__":
    main()
