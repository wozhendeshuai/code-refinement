import json
import os
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


# --- 配置结束 ---


class GitCodePRAnalyzer:
    def __init__(self):
        self.session = self._create_session()
        self.lock = threading.Lock()  # 用于线程安全的文件写入
        self.processed_pr_numbers = set()

    def _create_session(self):
        """创建带重试机制的requests会话"""
        session = requests.Session()
        retry_strategy = Retry(
            total=MAX_RETRIES,
            backoff_factor=BACKOFF_FACTOR,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        return session

    def load_pr_numbers_from_jsonl(self, filename):
        """从JSONL文件中读取PR编号列表"""
        pr_numbers = []
        if os.path.exists(filename):
            try:
                with open(filename, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            try:
                                pr_data = json.loads(line)
                                pr_number = pr_data.get('number')
                                if pr_number:
                                    pr_numbers.append(pr_number)
                            except json.JSONDecodeError:
                                print(f"跳过无法解析的JSONL行: {line[:100]}...")
            except Exception as e:
                print(f"读取JSONL文件 {filename} 时出错: {e}")
        return pr_numbers

    def load_processed_pr_numbers(self, filename):
        """从文件中读取已处理的PR编号集合"""
        id_set = set()
        if os.path.exists(filename):
            try:
                with open(filename, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line.isdigit():
                            id_set.add(int(line))
            except Exception as e:
                print(f"读取已处理PR文件 {filename} 时出错: {e}")
        return id_set

    def save_processed_pr_number(self, pr_number, filename):
        """将PR number追加到文件"""
        try:
            with open(filename, 'a', encoding='utf-8') as f:
                f.write(f"{pr_number}\n")
        except Exception as e:
            print(f"写入已处理PR文件 {filename} 时出错: {e}")

    def fetch_pr_files(self, pr_number):
        """调用API获取PR修改的文件列表（支持分页）"""
        all_files = []
        page = 1

        while True:
            url = f"{API_BASE_URL}/repos/{OWNER}/{REPO}/pulls/{pr_number}/files"
            params = {
                'page': page,
                'per_page': PER_PAGE
            }
            # print(f"获取PR #{pr_number} 修改的文件列表第 {page} 页")
            try:
                response = self.session.get(url, headers=HEADERS, params=params, timeout=30)
                response.raise_for_status()
                files = response.json()

                # 如果返回空列表，说明没有更多数据
                if not files:
                    break

                all_files.extend(files)

                # 如果返回的数量少于每页容量，说明是最后一页
                if len(files) < PER_PAGE or len(files)>=PER_PAGE:
                    break

                page += 1

            except requests.exceptions.RequestException as e:
                print(f"获取PR #{pr_number} 修改的文件列表第 {page} 页失败: {e}")
                if hasattr(e, 'response') and e.response is not None:
                    print(f"  响应状态: {e.response.status_code}, 响应内容: {e.response.text[:200]}...")
                return None

        print(f"    PR #{pr_number}: 获取到 {len(all_files)} 个文件")
        return all_files

    def fetch_pr_commits(self, pr_number):
        """调用API获取PR的所有提交列表（支持分页）"""
        all_commits = []
        page = 1

        while True:
            url = f"{API_BASE_URL}/repos/{OWNER}/{REPO}/pulls/{pr_number}/commits"
            params = {
                'page': page,
                'per_page': PER_PAGE
            }
            try:
                response = self.session.get(url, headers=HEADERS, params=params, timeout=30)
                response.raise_for_status()
                commits = response.json()

                # 如果返回空列表，说明没有更多数据
                if not commits:
                    break

                all_commits.extend(commits)

                # 如果返回的数量少于每页容量，说明是最后一页
                if len(commits) < PER_PAGE:
                    break

                page += 1

            except requests.exceptions.RequestException as e:
                print(f"获取PR #{pr_number} 的提交列表第 {page} 页失败: {e}")
                if hasattr(e, 'response') and e.response is not None:
                    print(f"  响应状态: {e.response.status_code}, 响应内容: {e.response.text[:200]}...")
                return None

        print(f"    PR #{pr_number}: 获取到 {len(all_commits)} 个提交")
        return all_commits

    def fetch_pr_diff_comments(self, pr_number):
        """调用API获取单个PR的diff评论列表"""
        url = f"{API_BASE_URL}/repos/{OWNER}/{REPO}/pulls/{pr_number}/comments"
        url_with_file=f"{API_BASE_URL}/repos/{OWNER}/{REPO}/pulls/comments/"
        all_comments = []
        all_comments_with_diff_file=[]
        page = 1

        while True:
            params = {
                'page': page,
                'per_page': PER_PAGE,
                'comment_type':"diff_comment"
            }
            try:
                response = requests.get(url, headers=HEADERS, params=params)
                response.raise_for_status()
                comments = response.json()

                if not comments:  # 如果返回空列表，说明已获取完所有评论
                    break

                all_comments.extend(comments)
                page += 1
                for comment in comments:

                    url_with_file_temp=url_with_file+str(comment.get("id"))
                    response = requests.get(url_with_file_temp, headers=HEADERS)
                    response.raise_for_status()
                    comments_with_file = response.json()
                    # 这个时候将两个comment中所有的key进行合并，取一个并集
                    for key in comment:
                        if key in comments_with_file and comment[key]==comments_with_file[key]:
                            continue
                        elif key not in comments_with_file:
                            comments_with_file[key]=comment[key]
                        else:
                            comments_with_file[key+"_from_comment"]=comment[key]
                    all_comments_with_diff_file.append(comments_with_file)

                # 如果返回的评论数量少于每页数量，说明已到达最后一页
                if len(comments) < PER_PAGE:
                    break


            except requests.exceptions.RequestException as e:
                print(f"获取PR #{pr_number} 的diff评论失败: {e}")
                if hasattr(e, 'response') and e.response is not None:
                    print(f"  响应内容: {e.response.text}")
                return None
        print(f"    PR #{pr_number}: 获取到 {len(all_comments_with_diff_file)} 个diff评论")

        return all_comments_with_diff_file

    def fetch_file_content_at_sha(self, file_path, sha):
        """调用API获取指定SHA的文件内容"""
        url = f"{File_CONTENT_URL}/{OWNER}/{REPO}/raw/{sha}/{file_path}"
        try:
            response = self.session.get(url, headers=HEADERS, timeout=30)
            response.raise_for_status()
            # 直接返回文本内容，不解析JSON
            return response.text
        except requests.exceptions.RequestException as e:
            print(f"获取文件 {file_path} 在SHA {sha} 的内容失败: {e}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"  响应状态: {e.response.status_code}, 响应内容: {e.response.text[:200]}...")
            return None


    def process_pr_files_with_content(self, pr_number, pr_files_data, pr_commits_data):
        """
        结合PR文件列表和提交列表，获取每个文件在PR前后的内容
        """
        if not pr_files_data or not pr_commits_data:
            print(f"    PR #{pr_number}: 文件或提交数据为空，跳过内容获取。")
            return [], 0, []

        # 按提交顺序排序
        sorted_commits = sorted(pr_commits_data, key=lambda x: x.get('commit', {}).get('author', {}).get('date', ''))

        # 获取PR的base sha（PR开始前的基线）
        first_commit = sorted_commits[0] if sorted_commits else None
        base_sha = first_commit.get('parents').get('sha') if first_commit else None

        # 提取提交次数和SHA列表（包括最开始的base sha）
        commit_count = len(sorted_commits)
        commit_shas = [commit.get('sha') for commit in sorted_commits if commit.get('sha')]

        # 如果获取到base sha，则将其作为列表的第一个元素
        if base_sha:
            all_shas = [base_sha] + commit_shas
        else:
            # 如果无法获取base sha，则使用第一个提交作为基线
            first_commit_sha = sorted_commits[0].get('sha') if sorted_commits else None
            all_shas = [first_commit_sha] + commit_shas if first_commit_sha else commit_shas

        processed_files = []
        for file_info in pr_files_data:
            filename = file_info.get('filename')

            # 初始化文件内容
            old_file_content = None
            new_file_content = None

            # 根据文件状态决定获取哪些内容
            status = file_info.get('status', 'modified')  # 默认为modified

            if status == 'added':
                # 新增文件：只有PR后的内容（最新的提交）
                if commit_shas:
                    new_file_content = self.fetch_file_content_at_sha(filename, commit_shas[-1])

            elif status == 'deleted':
                # 删除文件：只有PR前的内容（PR开始前的base）
                if base_sha:
                    old_file_content = self.fetch_file_content_at_sha(filename, base_sha)
                elif sorted_commits:
                    old_file_content = self.fetch_file_content_at_sha(filename, sorted_commits[0].get('sha'))

            elif status == 'renamed':
                # 重命名文件：PR前是旧文件名在base，PR后是新文件名在最新提交
                old_filename = file_info.get('patch').get('old_path')
                new_filename = file_info.get('patch').get('new_path')
                if base_sha:
                    old_file_content = self.fetch_file_content_at_sha(old_filename, base_sha)
                if commit_shas:
                    new_file_content = self.fetch_file_content_at_sha(new_filename, commit_shas[-1])

            else:  # modified, copied, changed
                # 修改文件：PR前是base，PR后是最新提交
                if base_sha:
                    old_file_content = self.fetch_file_content_at_sha(filename, base_sha)
                if commit_shas:
                    new_file_content = self.fetch_file_content_at_sha(filename, commit_shas[-1])

            # 构建包含文件内容的文件信息
            processed_file_info = {
                **file_info,  # 包含原始文件信息
                'old_file_content': old_file_content,
                'new_file_content': new_file_content
            }
            processed_files.append(processed_file_info)
        print(f"    PR 涉及的文件长度为：{len(processed_files)}，提交次数为：{commit_count}")
        return processed_files, commit_count, all_shas

    def save_pr_detailed_data(self, pr_data, processed_files, pr_commits_data, commit_count, commit_shas, diff_comments):
        """保存PR的详细数据，包括文件内容和提交信息，确保每行可JSON化"""
        pr_number = pr_data.get('number')
        pr_id = pr_data.get('id')

        # 构建完整的PR详细数据
        detailed_pr_data = {
            **pr_data,  # 包含原始PR数据
            'pr_files': processed_files,
            'pr_commits': pr_commits_data,
            'commit_count': commit_count,
            'commit_shas': commit_shas,  # 包含base sha和所有提交的完整列表
            'diff_comment_num': len(diff_comments) if diff_comments else 0,
            'diff_comments': diff_comments
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
        # 将数据中所有以url结尾的key并且如果其value为“http开头的内容删除，层级要到这条数据最底层的key



        # 线程安全地写入JSONL
        with self.lock:
            try:
                # 确保目录存在
                os.makedirs(os.path.dirname(OUTPUT_JSONL_FILE), exist_ok=True)

                # 序列化为JSON字符串，验证是否可JSON化
                json_str = json.dumps(detailed_pr_data, ensure_ascii=False)

                # 写入JSONL文件
                with open(OUTPUT_JSONL_FILE, 'a', encoding='utf-8') as f:
                    f.write(json_str + '\n')

                print(f"    PR #{pr_number} 详细信息已保存到JSONL。")
                return True
            except json.JSONEncodeError as e:
                print(f"    PR #{pr_number} 数据无法JSON化: {e}")
                return False
            except Exception as e:
                print(f"    保存PR #{pr_number} 到JSONL文件时出错: {e}")
                return False

    def process_single_pr(self, pr_number):
        """处理单个PR的完整流程"""
        print(f"\n  > 处理 PR #{pr_number} ...")

        # 获取PR修改的文件列表
        pr_files_data = self.fetch_pr_files(pr_number)
        if pr_files_data is None:
            print(f"    获取PR #{pr_number} 修改的文件列表失败，跳过。")
            return False

        # 获取PR的提交列表
        pr_commits_data = self.fetch_pr_commits(pr_number)
        if pr_commits_data is None:
            print(f"    获取PR #{pr_number} 的提交列表失败，跳过。")
            return False

        # 获取每个文件在PR前后的内容
        processed_files, commit_count, commit_shas = self.process_pr_files_with_content(
            pr_number, pr_files_data, pr_commits_data
        )
        # 获取diff评论
        diff_comments = self.fetch_pr_diff_comments(pr_number)

        # 从原始JSONL文件中读取PR基本信息
        pr_data = None
        try:
            with open(INPUT_JSONL_FILE, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            pr_info = json.loads(line)
                            if pr_info.get('number') == pr_number:
                                pr_data = pr_info
                                break
                        except json.JSONDecodeError:
                            continue
        except Exception as e:
            print(f"读取PR #{pr_number} 基本信息时出错: {e}")
            return False

        if not pr_data:
            print(f"    无法找到PR #{pr_number} 的基本信息，跳过。")
            return False

        # 保存PR详细数据
        success = self.save_pr_detailed_data(
            pr_data, processed_files, pr_commits_data, commit_count, commit_shas,diff_comments
        )

        if success:
            # 标记为已处理
            self.save_processed_pr_number(pr_number, PROCESSED_PR_NUMBERS_FILE)
            with self.lock:
                self.processed_pr_numbers.add(pr_number)
            print(f"    PR #{pr_number} 已标记为已处理。")

        return success

    def verify_jsonl_file(self, filename):
        """验证JSONL文件中每行都可以被JSON解析"""
        print(f"\n开始验证JSONL文件 {filename} ...")
        valid_lines = 0
        invalid_lines = 0
        total_lines = 0

        if not os.path.exists(filename):
            print(f"文件 {filename} 不存在。")
            return True  # 认为不存在的文件是"有效的"

        try:
            with open(filename, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue
                    total_lines += 1
                    try:
                        json.loads(line)
                        valid_lines += 1
                    except json.JSONDecodeError:
                        print(f"第 {line_num} 行无法解析为JSON: {line[:100]}...")
                        invalid_lines += 1
        except Exception as e:
            print(f"验证JSONL文件时出错: {e}")
            return False

        print(f"验证完成: 总行数={total_lines}, 有效行数={valid_lines}, 无效行数={invalid_lines}")
        return invalid_lines == 0

    def main(self):
        """主函数"""
        print(f"开始从 {INPUT_JSONL_FILE} 获取PR列表，并获取详细信息...")

        # 1. 从JSONL文件加载PR编号
        all_pr_numbers = self.load_pr_numbers_from_jsonl(INPUT_JSONL_FILE)
        print(f"从JSONL文件中加载了 {len(all_pr_numbers)} 个PR编号。")

        # 2. 加载断点续传状态
        self.processed_pr_numbers = self.load_processed_pr_numbers(PROCESSED_PR_NUMBERS_FILE)
        print(f"已加载 {len(self.processed_pr_numbers)} 个已处理的PR编号。")

        # 过滤出未处理的PR
        unprocessed_pr_numbers = [pr_num for pr_num in all_pr_numbers if pr_num not in self.processed_pr_numbers]
        print(f"待处理的PR数量: {len(unprocessed_pr_numbers)}")

        total_pr_details_fetched = 0  # 成功获取详细信息的PR数
        total_pr_saved_jsonl = 0  # 成功保存到JSONL的PR数

        # 并发处理所有未处理的PR
        try:
            # 串行处理所有未处理的PR（已注释掉多线程部分）
            # for pr_num in unprocessed_pr_numbers:
            #     try:
            #         success = self.process_single_pr(pr_num)
            #         if success:
            #             total_pr_saved_jsonl += 1
            #         total_pr_details_fetched += 1
            #         print(
            #             f"  已处理: {total_pr_details_fetched}/{len(unprocessed_pr_numbers)}, 成功: {total_pr_saved_jsonl}")
            #     except Exception as e:
            #         print(f"  PR #{pr_num} 处理过程中发生异常: {e}")
            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                # 提交所有PR任务
                future_to_pr = {executor.submit(self.process_single_pr, pr_num): pr_num for pr_num in
                                unprocessed_pr_numbers}

                # 等待完成
                for future in as_completed(future_to_pr):
                    pr_number = future_to_pr[future]
                    try:
                        success = future.result()
                        if success:
                            total_pr_saved_jsonl += 1
                        total_pr_details_fetched += 1
                        print(
                            f"  已处理: {total_pr_details_fetched}/{len(unprocessed_pr_numbers)}, 成功: {total_pr_saved_jsonl}")
                    except Exception as e:
                        print(f"  PR #{pr_number} 处理过程中发生异常: {e}")


        except KeyboardInterrupt:
            print("\n\n收到中断信号，正在保存进度并退出...")
        finally:
            print("\n" + "=" * 50)
            print("脚本执行结束。")
            print(f"  - 原始PR总数: {len(all_pr_numbers)}")
            print(f"  - 待处理PR数: {len(unprocessed_pr_numbers)}")
            print(f"  - 成功获取详细信息的PR数: {total_pr_details_fetched}")
            print(f"  - 成功保存到 {OUTPUT_JSONL_FILE} 的PR数: {total_pr_saved_jsonl}")
            print(f"  - 最终已处理的PR数: {len(self.processed_pr_numbers)}")

            # 验证最终的JSONL文件
            print("\n开始验证最终的JSONL输出文件...")
            is_valid = self.verify_jsonl_file(OUTPUT_JSONL_FILE)
            if is_valid:
                print("✓ JSONL文件验证通过，所有行都可JSON化。")
            else:
                print("✗ JSONL文件验证失败，存在无法JSON化的行。")
            print("=" * 50)


if __name__ == "__main__":
    REPO_List=[
        "account_os_account",
        "arkui_ace_engine",
        "build",
        "communication_wifi",
        "developtools_ace_ets2bundle",
        "multimedia_audio_framework",
        "web_webview",
        "xts_acts"
    ]
    for repo in REPO_List:
        print("======================================================")
        print(repo)
        # --- 配置 ---
        print("======================================================")
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

        # 输入文件：已有的PR信息JSONL文件
        INPUT_JSONL_FILE = f"{REPO}/{OWNER}_{REPO}_prs.jsonl"

        # 输出文件名
        OUTPUT_JSONL_FILE = f"{REPO}/{OWNER}_{REPO}_pr_commit_comment_details_with_files.jsonl"

        # 断点续传记录文件名
        PROCESSED_PR_NUMBERS_FILE = f"{REPO}/{OWNER}_{REPO}_processed_pr_commit_comment_numbers.txt"

        # API请求参数
        PER_PAGE = 100  # 每页数量，最大100 (根据文档)

        # 并发设置
        MAX_WORKERS = 3  # 并发线程数，避免触发速率限制
        MAX_RETRIES = 3  # API请求重试次数
        BACKOFF_FACTOR = 1  # 退避因子

        analyzer = GitCodePRAnalyzer()
        analyzer.main()



