import json
import os
import time

import requests


def fetch_commit_compare_data(base, head):
    api_url = f"https://gitcode.com/api/v5/repos/{OWNER}/{REPO}/compare/{base}...{head}"
    headers = {
        'Accept': 'application/json',
        'PRIVATE-TOKEN': 'r34uS2yEqhNMTBwmAN5ZkQTa'
    }
    try:
        response = requests.get(api_url, headers=headers)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        if hasattr(e, 'response') and e.response is not None:
            print(f"  响应内容: {e.response.text}")
        return None


def save_code_refinement_data_to_file(pr_number, diff_comment, before_file, after_file):
    """保存PR的详细数据，包括文件内容和提交信息，确保每行可JSON化"""
    # 构建完整的PR详细数据
    detailed_pr_data = {
        'pr_number': pr_number,
        'diff_comment': diff_comment,
        'before_file': before_file,
        'after_file': after_file
    }

    # 删除所有以"url"结尾且值为"http"开头的键值对，递归处理嵌套结构
    def remove_url_fields(obj):
        if isinstance(obj, dict):
            keys_to_remove = []
            for key, value in obj.items():
                if isinstance(key, str) and key.endswith('url') and isinstance(value, str) and value.startswith('http'):
                    keys_to_remove.append(key)
                else:
                    remove_url_fields(value)
            for key in keys_to_remove:
                del obj[key]
        elif isinstance(obj, list):
            for item in obj:
                remove_url_fields(item)

    remove_url_fields(detailed_pr_data)
    # 线程安全地写入JSONL
    try:
        # 确保目录存在
        os.makedirs(os.path.dirname(OUTPUT_JSONL_FILE), exist_ok=True)
        # 序列化为JSON字符串，验证是否可JSON化
        json_str = json.dumps(detailed_pr_data, ensure_ascii=False)
        # 写入JSONL文件
        with open(OUTPUT_JSONL_FILE, 'a', encoding='utf-8') as f:
            f.write(json_str + '\n')
        print(f"    diff comment  #{pr_number} 详细信息已保存到JSONL。")
        return True
    except json.JSONEncodeError as e:
        print(f"    PR #{pr_number} 数据无法JSON化: {e}")
        return False
    except Exception as e:
        print(f"    保存PR #{pr_number} 到JSONL文件时出错: {e}")
        return False


# 判断文件是否是一个代码文件
def is_code_file(file_path):
    # 常见的代码文件扩展名
    code_extensions = {
        '.cpp', '.c', '.cc', '.h', '.hpp',
        '.xml', '.ets', '.js', '.ts', '.mjs', '.rs', '.css', '.html',
        '.py',
        '.gn', '.gni',
        '.rc', '.idl',
        '.java',
        '.go', '.rb', '.php', '.sql', '.swift',
        '.kt', '.kts', '.scala', '.cs', '.cxx', '.hxx', '.m', '.mm'
    }

    # 常见的配置文件扩展名
    config_extensions = {
        '.conf', '.config', '.ini', '.properties', '.cfg', '.toml', '.env', '.yaml', '.yml'
    }

    # 常见的非代码文件扩展名（文档、资源、二进制等）
    non_code_extensions = {
        '.txt', '.log', '.md', '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
        '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.ico', '.svg', '.webp',
        '.zip', '.tar', '.gz', '.rar', '.7z',
        '.exe', '.dll', '.so', '.dylib', '.bin',
        '.cer', '.crt', '.pem', '.key', '.p12', '.pfx',
        '.gitignore', '.gitattributes', '.lock', '.sum',
        '.license', '.LICENSE', '.notice', '.NOTICE'
    }

    # 获取文件扩展名
    _, ext = os.path.splitext(file_path.lower())

    # 移除扩展名中的点号（如果有）
    ext = ext.lstrip('.')

    # 特殊处理没有扩展名的文件
    if not ext:
        # 检查是否为特定的配置文件名（无扩展名）
        return False

    # 如果是明确的代码扩展名
    if '.' + ext in code_extensions:
        return True

    # 如果是明确的配置扩展名
    if '.' + ext in config_extensions:
        return False

    # 如果是明确的非代码扩展名
    if '.' + ext in non_code_extensions:
        return False

    # 对于未知扩展名，默认认为不是代码文件
    return False


def get_diff_segments(diff_text):
    """
    根据diff的具体内容，将其拆分成不同的段落，给出段落的起始和结束行号，包括old_start，old_end，new_start，new_end
    """
    if not diff_text:
        return []

    segments = []
    lines = diff_text.split('\n')

    i = 0
    while i < len(lines):
        line = lines[i]
        # 查找 @@ -old_start,old_count +new_start,new_count @@ 格式的行
        if line.startswith('@@'):
            # 解析 hunk 头部信息
            header_parts = line.split('@@')[1].strip()
            parts = header_parts.split()
            if len(parts) < 2 or header_parts.startswith('-') is False:
                i += 1
                continue
            elif len(parts) > 2:
                header_parts = parts[0] + ' ' + parts[1]
            else:
                old_part, new_part = header_parts.split()

            # 提取 old_start 和 old_count
            old_info = old_part[1:].split(',')

            old_start = int(old_info[0])
            old_count = int(old_info[1]) if len(old_info) > 1 and old_info[1] != '' else 1

            # 提取 new_start 和 new_count
            new_info = new_part[1:].split(',')
            new_start = int(new_info[0]) if new_info[0] else -1
            new_count = int(new_info[1]) if len(new_info) > 1 and new_info[1] != '' else -1

            # 计算结束行号
            old_end = old_start + old_count - 1 if old_count > 0 else old_start
            new_end = new_start + new_count - 1 if new_count > 0 else new_start

            # 添加段落信息
            segments.append({
                'old_start': old_start,
                'old_end': old_end,
                'new_start': new_start,
                'new_end': new_end,
                'is_commented': False  # 初始时假设没有评论
            })

        i += 1

    return segments


def count_diff_need_refinement(jsonl_file_path):
    """
    分别统计diff_comment_num>=threshold、commit_count>=threshold的数量，以及两者都>=threshold的数量
    """
    pr_number_set = set()
    # 打开OUTPUT_JSONL_FILE文件，然后看一下当前处理到哪里了，保存最后一行的pr_number，以便继续处理
    with open(OUTPUT_JSONL_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            last_pr_number = json.loads(line).get('pr_number')
            pr_number_set.add(last_pr_number)
    print(f"上次处理到的pr_number是: {last_pr_number}")
    if not os.path.exists(jsonl_file_path):
        print(f"文件 {jsonl_file_path} 不存在")
        return 0, 0, 0
    # 情况1： 在diff_comments中，有评论时间早于最后一次提交时间

    total_lines = 0

    refinement_count = 0

    print(f"正在读取文件: {jsonl_file_path}")
    has_attach_last_pr_number = False
    # 获取文件总行数用于进度显示
    total_lines_in_file = sum(1 for _ in open(jsonl_file_path, 'r', encoding='utf-8'))
    print(f"文件 {jsonl_file_path} 总共有 {total_lines_in_file} 行数据")

    with open(jsonl_file_path, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):

            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                pr_files = data.get('pr_files')
                pr_number = data.get('number')
                # 如果当前没到处理过的最后一个pr_number，那么就跳过
                if pr_number == last_pr_number:
                    print(f"到达上次处理中断点，第 {line_num} 行，总共 {total_lines_in_file} 行，"
                          f"pr_number是:{pr_number},进度: {line_num / total_lines_in_file}%")
                    has_attach_last_pr_number = True
                    continue
                if not has_attach_last_pr_number:
                    continue
                print(f"正在处理第 {line_num} 行，总共 {total_lines_in_file} 行，pr_number是:{pr_number},进度: {line_num / total_lines_in_file}%")
                # 获取diff_comments中最早的评论时间
                diff_comments = data.get('diff_comments')
                commit_shas = data.get('commit_shas')
                # 从pr_commits中获取最晚的提交时间
                pr_all_commits = data.get('pr_commits', [])
                # 这里统计一下每个file对应的diff段
                file_path_segments = []
                for pr_file in pr_files:
                    pr_file_patch = pr_file.get('patch')
                    pr_file_patch_diff = get_diff_segments(pr_file_patch.get('diff'))
                    file_temp = {}
                    file_temp['old_path'] = pr_file_patch.get('old_path')
                    file_temp['new_path'] = pr_file_patch.get('new_path')
                    file_temp['diff_segments'] = pr_file_patch_diff
                    file_path_segments.append(file_temp)

                if diff_comments:
                    # 这里逐一去核对如下内容，1. 评论的位置是哪里？如果是代码文件,且old_path 和 new_path都存在那说明这个PR的这段提交需要被评审
                    for diff_comment in diff_comments:
                        comment_position = diff_comment.get('position')
                        old_path = comment_position.get('old_path')
                        new_path = comment_position.get('new_path')

                        diff_comment_created_at = diff_comment.get('created_at')

                        if is_code_file(old_path) and is_code_file(new_path):
                            # 在判断一下这个comment所处的diff是否已经被评论过了
                            start_new_line = diff_comment.get('diff_position').get('start_new_line')
                            end_new_line = diff_comment.get('diff_position').get('end_new_line')
                            if start_new_line is not None and end_new_line is not None:
                                for file_path_segment in file_path_segments:
                                    file_old_path = file_path_segment.get('old_path')
                                    file_new_path = file_path_segment.get('new_path')
                                    diff_segments = file_path_segment.get('diff_segments')
                                    if file_old_path == old_path and file_new_path == new_path:
                                        for file_diff_segment in diff_segments:
                                            if file_diff_segment.get(
                                                    'new_start') <= start_new_line <= file_diff_segment.get(
                                                'new_end') and file_diff_segment.get(
                                                'new_start') <= end_new_line <= file_diff_segment.get(
                                                'new_end'):
                                                if file_diff_segment.get('is_commented') is False:
                                                    file_diff_segment['is_commented'] = True
                                                    commit_base_sha = commit_shas[0]
                                                    commit_before_comment_time_sha = None
                                                    commit_after_comment_time_sha = commit_shas[-1]
                                                    commit_before_time = None
                                                    # 获取这个comment对应的创建前的最后一次提交的commit_sha
                                                    for pr_commit in pr_all_commits:
                                                        commit_date = pr_commit.get('commit').get('author').get('date')
                                                        if commit_before_time is None and commit_date <= diff_comment_created_at:
                                                            commit_before_comment_time_sha = pr_commit.get('sha')
                                                            commit_before_time = commit_date
                                                        elif commit_before_time and commit_date <= diff_comment_created_at and commit_date > commit_before_time:
                                                            commit_before_comment_time_sha = pr_commit.get('sha')
                                                            commit_before_time = commit_date
                                                    # 判断如果这几个sha有两个是相同的那么继续找下一个，这个不符合
                                                    if commit_before_comment_time_sha is None or commit_before_comment_time_sha == commit_after_comment_time_sha or commit_before_comment_time_sha == commit_base_sha:
                                                        continue
                                                    else:
                                                        before_diff = fetch_commit_compare_data(commit_base_sha,
                                                                                                commit_before_comment_time_sha)
                                                        if before_diff is None:
                                                            continue
                                                        before_files = before_diff.get('files')
                                                        before_file = None
                                                        has_before_file_comment_position = False
                                                        for temp_file in before_files:
                                                            if temp_file.get('filename') == old_path or temp_file.get(
                                                                    'filename') == new_path:
                                                                # 针对before_file应该确保这个文件中包含讨论所在的位置
                                                                before_file = temp_file
                                                                temp_file_patch = get_diff_segments(
                                                                    temp_file.get('patch'))
                                                                for temp_patch_segement in temp_file_patch:
                                                                    if temp_patch_segement.get(
                                                                            'new_start') <= start_new_line <= temp_patch_segement.get(
                                                                        'new_end') and temp_patch_segement.get(
                                                                        'new_start') <= end_new_line <= temp_patch_segement.get(
                                                                        'new_end'):
                                                                        has_before_file_comment_position = True
                                                                        break
                                                                time.sleep(4)
                                                                break

                                                        after_diff = fetch_commit_compare_data(
                                                            commit_before_comment_time_sha,
                                                            commit_after_comment_time_sha)
                                                        if after_diff is None:
                                                            continue
                                                        after_files = after_diff.get('files')
                                                        after_file = None
                                                        has_after_file_comment_position = False
                                                        for temp_file in after_files:
                                                            if temp_file.get('filename') == old_path or temp_file.get(
                                                                    'filename') == new_path:
                                                                after_file = temp_file
                                                                # 对于after_file应该确保这个文件中包含讨论所在位置
                                                                temp_file_patch = get_diff_segments(
                                                                    temp_file.get('patch'))
                                                                for temp_patch_segement in temp_file_patch:
                                                                    if temp_patch_segement.get(
                                                                            'new_start') <= start_new_line <= temp_patch_segement.get(
                                                                        'new_end') and temp_patch_segement.get(
                                                                        'new_start') <= end_new_line <= temp_patch_segement.get(
                                                                        'new_end'):
                                                                        has_after_file_comment_position = True
                                                                        break
                                                                time.sleep(4)
                                                                break
                                                        # 如果都满足，那么就说明这个是一个有效数据，接下来就统计并保存一下
                                                        if has_after_file_comment_position and has_before_file_comment_position:
                                                            print(
                                                                f'line {line_num},pr_number:{pr_number}，找到一个有效数据')
                                                            save_code_refinement_data_to_file(pr_number, diff_comment,
                                                                                              before_file,
                                                                                              after_file)
                                                            pr_number_set.add(pr_number)
                                                            refinement_count += 1
                                                    break
                                                else:
                                                    continue

                            start_old_line = diff_comment.get('diff_position').get('start_old_line')
                            end_old_line = diff_comment.get('diff_position').get('end_old_line')
                            if start_old_line is not None and end_old_line is not None:
                                for file_path_segment in file_path_segments:
                                    file_old_path = file_path_segment.get('old_path')
                                    file_new_path = file_path_segment.get('new_path')
                                    diff_segments = file_path_segment.get('diff_segments')
                                    if file_old_path == old_path and file_new_path == new_path:
                                        for file_diff_segment in diff_segments:
                                            if file_diff_segment.get(
                                                    'old_start') <= start_old_line <= file_diff_segment.get(
                                                'old_end') and file_diff_segment.get(
                                                'old_start') <= end_old_line <= file_diff_segment.get(
                                                'old_end'):
                                                if file_diff_segment.get('is_commented') is False:
                                                    file_diff_segment['is_commented'] = True
                                                    commit_base_sha = commit_shas[0]
                                                    commit_before_comment_time_sha = None
                                                    commit_after_comment_time_sha = commit_shas[-1]
                                                    commit_before_time = None
                                                    # 获取这个comment对应的创建前的最后一次提交的commit_sha
                                                    for pr_commit in pr_all_commits:
                                                        commit_date = pr_commit.get('commit').get('author').get('date')
                                                        if commit_before_time is None and commit_date <= diff_comment_created_at:
                                                            commit_before_comment_time_sha = pr_commit.get('sha')
                                                            commit_before_time = commit_date
                                                        elif commit_before_time and commit_date <= diff_comment_created_at and commit_date > commit_before_time:
                                                            commit_before_comment_time_sha = pr_commit.get('sha')
                                                            commit_before_time = commit_date
                                                    # 判断如果这几个sha有两个是相同的那么继续找下一个，这个不符合
                                                    if commit_before_comment_time_sha is None or commit_before_comment_time_sha == commit_after_comment_time_sha or commit_before_comment_time_sha == commit_base_sha:
                                                        continue
                                                    else:
                                                        before_diff = fetch_commit_compare_data(commit_base_sha,
                                                                                                commit_before_comment_time_sha)
                                                        before_files = before_diff.get('files')
                                                        before_file = None
                                                        has_before_file_comment_position = False
                                                        for temp_file in before_files:
                                                            if temp_file.get('filename') == old_path or temp_file.get(
                                                                    'filename') == new_path:
                                                                # 针对before_file应该确保这个文件中包含讨论所在的位置
                                                                before_file = temp_file
                                                                temp_file_patch = get_diff_segments(
                                                                    temp_file.get('patch'))
                                                                for temp_patch_segement in temp_file_patch:
                                                                    if temp_patch_segement.get(
                                                                            'new_start') <= start_new_line <= temp_patch_segement.get(
                                                                        'new_end') and temp_patch_segement.get(
                                                                        'new_start') <= end_new_line <= temp_patch_segement.get(
                                                                        'new_end'):
                                                                        has_before_file_comment_position = True
                                                                        break
                                                                time.sleep(4)
                                                                break

                                                        after_diff = fetch_commit_compare_data(
                                                            commit_before_comment_time_sha,
                                                            commit_after_comment_time_sha)
                                                        after_files = after_diff.get('files')
                                                        after_file = None
                                                        has_after_file_comment_position = False
                                                        for temp_file in after_files:
                                                            if temp_file.get('filename') == old_path or temp_file.get(
                                                                    'filename') == new_path:
                                                                after_file = temp_file
                                                                # 对于after_file应该确保这个文件中包含讨论所在位置
                                                                temp_file_patch = get_diff_segments(
                                                                    temp_file.get('patch'))
                                                                for temp_patch_segement in temp_file_patch:
                                                                    if temp_patch_segement.get(
                                                                            'new_start') <= start_new_line <= temp_patch_segement.get(
                                                                        'new_end') and temp_patch_segement.get(
                                                                        'new_start') <= end_new_line <= temp_patch_segement.get(
                                                                        'new_end'):
                                                                        has_after_file_comment_position = True
                                                                        break
                                                                time.sleep(4)
                                                                break
                                                        # 如果都满足，那么就说明这个是一个有效数据，接下来就统计并保存一下
                                                        if has_after_file_comment_position and has_before_file_comment_position:
                                                            print(
                                                                f'line {line_num},pr_number:{pr_number}，找到一个有效数据')
                                                            save_code_refinement_data_to_file(pr_number, diff_comment,
                                                                                              before_file,
                                                                                              after_file)
                                                            pr_number_set.add(pr_number)
                                                            refinement_count += 1
                                                    break
                                                else:
                                                    continue

                total_lines += 1

            except json.JSONDecodeError as e:
                print(f"第 {line_num} 行 JSON 解析错误: {e}")

    print("-" * 70)
    # 获取文件总行数用于进度显示
    total_output_lines_in_file = sum(1 for _ in open(OUTPUT_JSONL_FILE, 'r', encoding='utf-8'))
    print( f"其中涉及的pr_number数量: {total_lines_in_file},涉及的PR数量：{len(pr_number_set)}，有效的refinement_count:{total_output_lines_in_file}")


# 根据原始代码中的变量定义
OWNER = "openharmony"
REPO = "account_os_account"
PR_JSONL_FILE = f"{REPO}/{OWNER}_{REPO}_pr_commit_comment_details_with_files.jsonl"
OUTPUT_JSONL_FILE = f"{REPO}/{OWNER}_{REPO}_pr_refinement_code.jsonl"
count_diff_need_refinement(PR_JSONL_FILE)
