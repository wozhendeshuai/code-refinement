import json
import os


def get_all_keys_recursive(data, parent_key=''):
    """
    递归获取数据结构中所有的key，包括嵌套对象中的key
    """
    keys = set()

    if isinstance(data, dict):
        for key, value in data.items():
            full_key = f"{parent_key}.{key}" if parent_key else key
            if key == 'pr_files':
                continue
            keys.add(full_key)

            # 如果值是字典或列表，递归处理
            if isinstance(value, dict):
                keys.update(get_all_keys_recursive(value, full_key))
            elif isinstance(value, list):
                for i, item in enumerate(value):
                    if isinstance(item, dict):
                        keys.update(get_all_keys_recursive(item, f"{full_key}[{i}]"))

    elif isinstance(data, list):
        for i, item in enumerate(data):
            if isinstance(item, dict):
                keys.update(get_all_keys_recursive(item, f"[{i}]"))

    return keys


def print_all_jsonl_keys(jsonl_file_path):
    """
    读取JSONL文件并打印每行数据的所有嵌套key
    """
    if not os.path.exists(jsonl_file_path):
        print(f"文件 {jsonl_file_path} 不存在")
        return

    all_keys = set()
    line_count = 0

    print(f"正在读取文件: {jsonl_file_path}")
    print("-" * 50)

    with open(jsonl_file_path, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue

            try:
                data = json.loads(line)

                # 获取当前行的所有key（包括嵌套的）
                line_keys = get_all_keys_recursive(data)
                all_keys.update(line_keys)

                print(f"第 {line_num} 行的所有 keys: {sorted(list(line_keys))}")
                line_count += 1

            except json.JSONDecodeError as e:
                print(f"第 {line_num} 行 JSON 解析错误: {e}")

    print("-" * 50)
    print(f"总共处理了 {line_count} 行数据")
    print(f"所有出现的嵌套 keys: {sorted(list(all_keys))}")
    print(f"keys 总数: {len(all_keys)}")


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


# 使用示例 - 替换为你实际的文件路径
# 注意：根据原始代码，输出文件路径为 f"{REPO}/{OWNER}_{REPO}_pr_commit_comment_details_with_files.jsonl"
# 即 "xts_acts/openharmony_xts_acts_pr_commit_comment_details_with_files.jsonl"

def count_records_need_issue_detection(jsonl_file_path):
    """
    分别统计diff_comment_num>=threshold、commit_count>=threshold的数量，以及两者都>=threshold的数量
    """
    if not os.path.exists(jsonl_file_path):
        print(f"文件 {jsonl_file_path} 不存在")
        return 0, 0, 0
    # 情况1： 在diff_comments中，有评论时间早于最后一次提交时间
    early_comment_time_earlier_than_last_commit_time_count = 0
    diff_comment_threshold = 1
    commit_count_threshold = 2
    diff_comment_ge_threshold = 0
    commit_count_ge_threshold = 0
    both_ge_threshold = 0
    total_lines = 0
    file_type_set = set()

    print(f"正在读取文件: {jsonl_file_path}")
    print(
        f"统计 diff_comment_num >= {diff_comment_threshold}、commit_count >= {commit_count_threshold} 以及两者都满足的数据条数...")
    print("-" * 70)

    with open(jsonl_file_path, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue

            try:
                data = json.loads(line)
                pr_file_list = data.get('pr_files', [])
                for pr_file in pr_file_list:
                    # 统计文件类型提取.后的文件名后缀名
                    file_type = pr_file.get('filename').split('.')[-1]
                    # 如果file_tupe包含/
                    if '/' in file_type:
                        file_type_set.add("no_extension")
                    else:
                        file_type_set.add(file_type)
                # 获取diff_comment_num和commit_count的值
                diff_comment_num = data.get('diff_comment_num', 0)
                commit_count = data.get('commit_count', 0)
                pr_file_len = len(data.get('pr_files', []))
                pr_number = data.get('number')
                pr_create_time = data.get('created_at')

                # 从pr_commits中获取最晚的提交时间
                pr_all_commits = data.get('pr_commits', [])
                last_commit_times = None
                for commit in pr_all_commits:
                    if commit.get('commit') is None:
                        continue
                    if commit.get('commit').get('author') is None:
                        continue
                    if commit.get('commit').get('author').get('date') is None:
                        continue
                    commit_time = commit.get('commit').get('author').get('date')
                    if last_commit_times is None:
                        last_commit_times = commit_time
                    elif commit_time > last_commit_times:
                        last_commit_times = commit_time

                # 获取diff_comments中最早的评论时间
                diff_comments = data.get('diff_comments')
                early_comment_time = None
                if diff_comments:
                    for comment in diff_comments:
                        comment_time = comment.get('created_at')
                        if early_comment_time is None:
                            early_comment_time = comment_time
                        elif comment_time < early_comment_time:
                            early_comment_time = comment_time

                # 如果user已注销，那么就用Commit中的user_id
                if data.get('user') is None:
                    user_id = None
                else:
                    user_id = data.get('user').get('id')
                # 1.检测是否有评论时间早于最后一次提交时间的情况，也即在评论后还更新了代码
                if early_comment_time and last_commit_times and early_comment_time < last_commit_times:
                    early_comment_time_earlier_than_last_commit_time_count += 1
                    print(
                        f"第 {line_num} 行的 PR {pr_number} 满足条件：early_comment_time = {early_comment_time} < last_commit_times = {last_commit_times} (评论时间早于最后一次提交时间)"
                        f"diff_comment_num = {diff_comment_num}, commit_count = {commit_count}  pr_files_len={pr_file_len}")
                # 2. 统计diff_comment_num和commit_count的情况 如果这两者都大于threashold则纳入总数中
                else:
                    # 检查各个条件
                    is_diff_ge_threshold = diff_comment_num >= diff_comment_threshold
                    is_commit_ge_threshold = commit_count >= commit_count_threshold

                    if is_diff_ge_threshold:
                        diff_comment_ge_threshold += 1
                        if is_commit_ge_threshold:
                            # 看一下有多少是作者自己评论自己的PR的情况
                            diff_comment = data.get('diff_comments')
                            user_comment_num = 0
                            for comment in diff_comment:
                                if comment.get('user') is None:
                                    if user_id is None:
                                        user_comment_num += 1
                                elif comment.get('user').get('id') == user_id:
                                    user_comment_num += 1
                            both_ge_threshold += 1
                            print(
                                f"第 {line_num} 行的 PR {pr_number} 满足条件 : diff_comment_num = {diff_comment_num}, user_comment_num = {user_comment_num}, commit_count = {commit_count} (两者都满足) pr_files_len={pr_file_len}")
                        # else:
                        # print(
                        # f"第 {line_num} 行: diff_comment_num = {diff_comment_num}, commit_count = {commit_count} (仅diff_comment_num >= {diff_comment_threshold})")
                    elif is_commit_ge_threshold:
                        commit_count_ge_threshold += 1
                        # print(
                        #     f"第 {line_num} 行: diff_comment_num = {diff_comment_num}, commit_count = {commit_count} (仅commit_count >= {commit_count_threshold})")

                    total_lines += 1

            except json.JSONDecodeError as e:
                print(f"第 {line_num} 行 JSON 解析错误: {e}")

    print("-" * 70)
    print(f"总共处理了 {total_lines} 行数据")
    print(
        f"其中 early_comment_time_earlier_than_last_commit_time_count 的数据条数: {early_comment_time_earlier_than_last_commit_time_count}")
    print(f"其中 diff_comment_num >= {diff_comment_threshold} 的数据条数: {diff_comment_ge_threshold}")
    print(f"其中 commit_count >= {commit_count_threshold} 的数据条数: {commit_count_ge_threshold}")
    print(
        f"其中 diff_comment_num >= {diff_comment_threshold} 且 commit_count >= {commit_count_threshold} 的数据条数: {both_ge_threshold}")
    print(f"总共的需要评审的记录数: {early_comment_time_earlier_than_last_commit_time_count + both_ge_threshold}")
    print(f"file_type_set: {file_type_set}")

    return diff_comment_ge_threshold, commit_count_ge_threshold, both_ge_threshold

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
            if len(parts)<2 or header_parts.startswith('-') is False:
                i += 1
                continue
            old_part, new_part = header_parts.split()
            
            # 提取 old_start 和 old_count
            old_info = old_part[1:].split(',')

            old_start = int(old_info[0])
            old_count = int(old_info[1]) if len(old_info) > 1 else 1
            
            # 提取 new_start 和 new_count
            new_info = new_part[1:].split(',')
            new_start = int(new_info[0])
            new_count = int(new_info[1]) if len(new_info) > 1 else 1
            
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


def count_diff_need_check(jsonl_file_path):
    """
    分别统计diff_comment_num>=threshold、commit_count>=threshold的数量，以及两者都>=threshold的数量
    """
    if not os.path.exists(jsonl_file_path):
        print(f"文件 {jsonl_file_path} 不存在")
        return 0, 0, 0
    # 情况1： 在diff_comments中，有评论时间早于最后一次提交时间
    comment_in_diff_count = 0
    comment_in_new_file_count = 0
    comment_in_old_file_count = 0
    total_lines = 0

    pr_number_set = set()

    print(f"正在读取文件: {jsonl_file_path}")

    with open(jsonl_file_path, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                # 获取diff_comment_num和commit_count的值
                diff_comment_num = data.get('diff_comment_num', 0)
                commit_count = data.get('commit_count', 0)
                # 如果user已注销，那么就用Commit中的user_id
                if data.get('user') is None:
                    pr_user_id = None
                else:
                    pr_user_id = data.get('user').get('id')
                pr_files = data.get('pr_files')

                pr_file_len = len(pr_files)
                pr_number = data.get('number')
                # 获取diff_comments中最早的评论时间
                diff_comments = data.get('diff_comments')
                # 从pr_commits中获取最晚的提交时间
                pr_all_commits = data.get('pr_commits', [])
                # 这里统计一下每个file对应的diff段
                file_path_segments = []
                for pr_file in pr_files:
                    pr_file_patch=pr_file.get('patch')
                    pr_file_patch_diff=get_diff_segments(pr_file_patch.get('diff'))
                    file_temp={}
                    file_temp['old_path']=pr_file_patch.get('old_path')
                    file_temp['new_path']=pr_file_patch.get('new_path')
                    file_temp['diff_segments']=pr_file_patch_diff
                    file_path_segments.append(file_temp)
                if diff_comments:
                    # 这里逐一去核对如下内容，1. 评论的位置是哪里？如果是代码文件,且old_path 和 new_path都存在那说明这个PR的这段提交需要被评审
                    for diff_comment in diff_comments:
                        comment_position = diff_comment.get('position')
                        old_path = comment_position.get('old_path')
                        new_path = comment_position.get('new_path')
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
                                            if file_diff_segment.get('new_start') <= start_new_line <= file_diff_segment.get(
                                                'new_end') and file_diff_segment.get('new_start') <= end_new_line <= file_diff_segment.get(
                                                'new_end'):
                                                if file_diff_segment.get('is_commented') is False:
                                                    file_diff_segment['is_commented'] = True
                                                    comment_in_diff_count += 1
                                                    pr_number_set.add(pr_number)
                                                    comment_in_new_file_count+=1
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
                                            if file_diff_segment.get('old_start') <= start_old_line <= file_diff_segment.get(
                                                'old_end') and file_diff_segment.get('old_start') <= end_old_line <= file_diff_segment.get(
                                                'old_end'):
                                                if file_diff_segment.get('is_commented') is False:
                                                    file_diff_segment['is_commented'] = True
                                                    comment_in_diff_count += 1
                                                    pr_number_set.add(pr_number)
                                                    comment_in_old_file_count+=1
                                                    break
                                                else:
                                                    continue

                total_lines += 1

            except json.JSONDecodeError as e:
                print(f"第 {line_num} 行 JSON 解析错误: {e}")

    print("-" * 70)
    print(f"总共处理了 {total_lines} 行数据")
    print(f"其中comment_in_diff_count 的数据条数: {comment_in_diff_count} 涉及的pr_number数量: {len(pr_number_set)},comment_in_new_file_count:{comment_in_new_file_count},comment_in_old_file_count:{comment_in_old_file_count}")


# 根据原始代码中的变量定义
OWNER = "openharmony"
REPO = "web_webview"
OUTPUT_JSONL_FILE = f"{REPO}/{OWNER}_{REPO}_pr_commit_comment_details_with_files.jsonl"

# 执行函数
# print_all_jsonl_keys(OUTPUT_JSONL_FILE)

# result = count_records_need_issue_detection(OUTPUT_JSONL_FILE)
count_diff_need_check(OUTPUT_JSONL_FILE)
