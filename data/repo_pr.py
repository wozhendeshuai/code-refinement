import requests
import pandas as pd
import time
import random
from datetime import datetime
import os
from urllib.parse import quote  # For URL encoding

# --- Configuration ---
INPUT_EXCEL_FILENAME = "openharmony_repos_streaming_20250929.xlsx"
OUTPUT_EXCEL_FILENAME = f"openharmony_repos_with_pr_stats_api_20250929.xlsx"

# 请求头 - 至关重要! 必须使用从浏览器抓包得到的真实 Headers
# 请务必从浏览器开发者工具中复制有效的 Cookie 和其他必要 Header
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36 Edg/140.0.0.0',
    'Authorization': 'Bearer eyJhbGciOiJIUzUxMiJ9.eyJqdGkiOiI2NjM0Yjc1Y2UzYWI4YTJiMDE4ODdhM2IiLCJzdWIiOiJqankxOTk3MTAyMyIsImF1dGhvcml0aWVzIjpbXSwib2JqZWN0SWQiOiI2OGQ5NTI5NTRiNWI4ODY0ODIxMmQzNzEiLCJpYXQiOjE3NTkwNzI5MTcsImV4cCI6MTc1OTE1OTMxN30.t2vyRpkKffjc6X6ceZBAX2rWabCv0RdF-iCnbICDr3_agETTfDTDAo8TSMoeJEWNUkvu6McsKTtpkEaGN9-uWw',
    # 如果 Authorization 失效，可以取消注释下面这行并使用 Cookie
    # 'Cookie': 'uuid_tt_dd=10_20292352760-1738236575016-789853; _frid=9e769ac4450846e8a83200e4fe18080b; gitcode_first_time=2025-05-11%2004:41:02; Gitcode_Wx_Auto_Login=1; c_gitcode_um=-; c_gitcode_fref=https://www.bing.com/; c_gitcode_rid=1757573388534_565552; Hm_lvt_62047c952451105d57bab2c4af9ce85b=1759072572; HMACCOUNT=48ECBD88F427A72E; HWWAFSESTIME=1759072570804; BENSESSCC_TAG=10_20292352760-1738236575016-789853; HWWAFSESID=9c45ca0f0b7dd9ddd5; pageSize={%22global-pager%22:10}; c_gitcode_callback=1759072881.177; GITCODE_ACCESS_TOKEN=eyJhbGciOiJIUzUxMiJ9.eyJqdGkiOiI2NjM0Yjc1Y2UzYWI4YTJiMDE4ODdhM2IiLCJzdWIiOiJqankxOTk3MTAyMyIsImF1dGhvcml0aWVzIjpbXSwib2JqZWN0SWQiOiI2OGQ5NTI5NTRiNWI4ODY0ODIxMmQzNzEiLCJpYXQiOjE3NTkwNzI5MTcsImV4cCI6MTc1OTE1OTMxN30.t2vyRpkKffjc6X6ceZBAX2rWabCv0RdF-iCnbICDr3_agETTfDTDAo8TSMoeJEWNUkvu6McsKTtpkEaGN9-uWw; GITCODE_REFRESH_TOKEN=eyJhbGciOiJIUzUxMiJ9.eyJqdGkiOiI2NjM0Yjc1Y2UzYWI4YTJiMDE4ODdhM2IiLCJzdWIiOiJqankxOTk3MTAyMyIsImF1dGhvcml0aWVzIjpbXSwib2JqZWN0SWQiOiI2OGQ5NTI5NTRiNWI4ODY0ODIxMmQzNzEiLCJpYXQiOjE3NTkwNzI5MTcsImV4cCI6MTc2MTY2NDkxN30.3ZjRwYHCgZnJh3X0SvetRa9ZlB2Kyl1pjAoCLKdfZ2FIllKfw7b0elmMAG-mZkIka9s-wD_kPfxnLXG5wrXTFg; GitCodeUserName=jjy19971023; _fr_ssid=e5b633adda0f4b988e8e8d969c95b37c; gitcode_wechat_from=; last-repo-id=4399986; Hm_lpvt_62047c952451105d57bab2c4af9ce85b=1759079684',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Encoding': 'gzip, deflate, br, zstd',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6',
    'Connection': 'keep-alive',
    'Host': 'web-api.gitcode.com',
    'Origin': 'https://gitcode.com',
    'Referer': 'https://gitcode.com/',
    'Sec-Fetch-Dest': 'empty',
    'Sec-Fetch-Mode': 'cors',
    'Sec-Fetch-Site': 'same-site',
    'X-App-Channel': 'gitcode-fe',
    'X-App-Version': '0',
    'X-Device-ID': 'unknown',
    'X-Device-Type': 'MacOS',
    'X-Network-Type': '4g',
    'X-OS-Version': 'Unknown',
    'X-Platform': 'web',
    'gitcode-utm-source': '',
    'page-ref': 'https%3A%2F%2Fgitcode.com%2Fopenharmony%2Farkcompiler_ets_runtime%2Fpulls',
    'page-repo-id': '4399986',
    'page-title': '%E9%A1%B9%E7%9B%AE%E5%90%88%E5%B9%B6%E8%AF%B7%E6%B1%82%E9%A1%B5',
    'page-uri': 'https%3A%2F%2Fgitcode.com%2Fopenharmony%2Farkcompiler_ets_runtime%2Fpulls',
    'sec-ch-ua': '"Chromium";v="140", "Not=A?Brand";v="24", "Microsoft Edge";v="140"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"macOS"'
}
# GitCode 内部 API Base URL (获取PR统计)
INTERNAL_API_BASE_URL = "https://web-api.gitcode.com/issuepr/api/v1/projects"
# API 端点路径 (相对于项目路径)
API_ENDPOINT_PATH = "isource/merge_requests/count"
# 公共查询参数
COMMON_PARAMS = {
    "scope": "all",
    "state": "opened",
    "per_page": "10",
    "view": "basic",
    "only_count": "true"  # 关键：设置为 false 以获取完整计数对象
}

REQUEST_DELAY_MIN = 0.5  # 减少延迟，因为请求更少了
REQUEST_DELAY_MAX = 1.5


# --- Configuration End ---

def get_project_path_from_html_url(html_url):
    """
    从 html_url 提取项目路径 (owner/repo_name)。
    E.g., https://gitcode.com/OpenHarmony/applications_sample_camera ->
          OpenHarmony/applications_sample_camera
    """
    if not html_url or not isinstance(html_url, str):
        return None
    try:
        parts = html_url.rstrip('/').split('/')
        if len(parts) >= 2:
            owner = parts[-2]
            repo_name = parts[-1]
            return f"{owner}/{repo_name}"
        else:
            print(f"  错误：无法从 URL '{html_url}' 提取项目路径")
            return None
    except Exception as e:
        print(f"  错误：处理 URL '{html_url}' 时异常: {e}")
        return None


def fetch_all_pr_counts(project_path_encoded, headers={}, common_params={}):
    """
    通过一次API调用获取所有PR状态的计数。
    Returns a dictionary with counts or None on failure.
    """
    # 构造完整URL
    # 注意：project_path_encoded 中的 '/' 需要被编码为 %2F
    url = f"{INTERNAL_API_BASE_URL}/{project_path_encoded}/{API_ENDPOINT_PATH}"

    # 合并参数
    params = common_params.copy()

    try:
        print(f"  正在请求: {url}")
        response = requests.get(url, headers=headers, params=params, timeout=15)

        if response.status_code != 200:
            print(f"  API 请求失败 (状态码: {response.status_code}, URL: {response.url})")
            print(f"    响应内容 (前200字符): {response.text[:200]}...")
            return None

        # 解析 JSON 响应
        data = response.json()

        # 验证返回的数据结构
        expected_keys = {'all', 'opened', 'closed', 'merged'}
        if not isinstance(data, dict) or not expected_keys.issubset(data.keys()):
            print(
                f"  API 返回的数据结构不符合预期。期望包含键 {expected_keys}, 实际收到: {list(data.keys()) if isinstance(data, dict) else type(data)}")
            print(f"    响应内容: {data}")
            return None

        print(f"  成功获取 PR 统计: {data}")
        return data  # 返回包含所有计数的字典

    except requests.exceptions.RequestException as e:
        print(f"  请求异常 (URL: {url}): {e}")
    except ValueError as e:  # JSON 解码错误
        print(f"  响应不是有效的 JSON (URL: {url}): {e}")
        print(f"    响应内容 (前200字符): {response.text[:200]}...")
    except Exception as e:
        print(f"  处理响应时发生未预期错误 (URL: {url}): {e}")
    return None
# 定义新的列名
PR_COLUMNS_NEW = ['PR_全部数量', 'PR_已开启数量', 'PR_已关闭数量', 'PR_已合并数量']

def is_row_processed(row):
    """
    判断某一行数据是否已经被处理过（即PR相关字段是否有有效值）。
    如果任何一个新列有非None的有效数值，则认为已处理。
    """
    for col in PR_COLUMNS_NEW:
        value = row.get(col)
        # 检查值是否存在且不为 None 或 NaN (对于数字类型)
        # pd.isna() 可以同时处理 None 和 np.nan
        if value is not None and not pd.isna(value):
             # 进一步检查是否为有意义的数字 (例如，不是 -1 之类的占位符，如果有的话)
             # 这里假设 0 是有效值 (仓库可能真的没有PR)，只要不是空就行
             return True
    return False



def main():

    """主函数，协调读取、API调用和写入。"""
    # 优先使用固定名称的输出文件（如果存在），否则使用原始输入文件
    if os.path.exists(OUTPUT_EXCEL_FILENAME):
        input_source = OUTPUT_EXCEL_FILENAME
        print(f"发现现有进度文件 '{OUTPUT_EXCEL_FILENAME}'，将从此文件继续处理。")
    else:
        input_source = INPUT_EXCEL_FILENAME
        print(f"未发现进度文件，将使用原始输入文件 '{INPUT_EXCEL_FILENAME}'。")

    if not os.path.exists(input_source):
        print(f"错误：找不到输入文件 '{input_source}'")
        return

    try:
        print(f"正在读取文件: {input_source}")
        df = pd.read_excel(input_source)
        print(f"成功读取 {len(df)} 行数据。")
    except Exception as e:
        print(f"读取Excel文件失败: {e}")
        return

    if 'html_url' not in df.columns:
        print("错误：输入文件中未找到 'html_url' 列。")
        return

    print("\n开始遍历仓库并通过API获取PR统计信息...")
    # 定义新的列名
    pr_columns_new = ['PR_全部数量', 'PR_已开启数量', 'PR_已关闭数量', 'PR_已合并数量']
    for col in pr_columns_new:
        if col not in df.columns:
            df[col] = None

    total_rows = len(df)
    already_processed_count = 0

    successful_fetches = 0
    failed_fetches = 0

    # 检查必要 Headers
    if 'Cookie' not in HEADERS or not HEADERS['Cookie'].strip() or 'your_actual_cookie_here' in HEADERS['Cookie']:
        print("\n*** 警告 ***")
        print("检测到 Cookie 可能未正确设置。API 请求很可能失败。")
        print("请从浏览器开发者工具 Network 面板的真实请求中复制有效的 Cookie 到 HEADERS 中。")
        print("*** 警告 ***\n")
        # 可以选择在这里退出: return

    for index, row in df.iterrows():
        original_html_url = row['html_url']
        print(f"\n--- 正在处理第 {index + 1}/{len(df)} 个仓库 ---")
        print(f"原始 URL: {original_html_url}")
        # --- 核心断点续传逻辑 ---
        if is_row_processed(row):
            print(f"  检测到已有数据，跳过。")
            already_processed_count += 1
            continue

        project_path = get_project_path_from_html_url(original_html_url)
        if not project_path:
            failed_fetches += 1
            continue

        # 对项目路径进行 URL 编码，确保 '/' 被编码为 %2F
        project_path_encoded = quote(project_path, safe='')

        # 只发送一次请求获取所有计数
        pr_stats = fetch_all_pr_counts(project_path_encoded, headers=HEADERS, common_params=COMMON_PARAMS)

        if pr_stats:
            # 更新 DataFrame
            df.at[index, 'PR_全部数量'] = pr_stats.get('all')
            df.at[index, 'PR_已开启数量'] = pr_stats.get('opened')
            df.at[index, 'PR_已关闭数量'] = pr_stats.get('closed')
            df.at[index, 'PR_已合并数量'] = pr_stats.get('merged')
            successful_fetches += 1
        else:
            failed_fetches += 1

        # 添加延迟，避免请求过于频繁
        delay = random.uniform(REQUEST_DELAY_MIN, REQUEST_DELAY_MAX)
        print(f"  等待 {delay:.2f} 秒...")
        time.sleep(delay)

        # 每处理一个仓库就保存一次
        try:
            df.to_excel(OUTPUT_EXCEL_FILENAME, index=False)
            print(f"\n[即时保存] 已处理 {index + 1} 行，数据已保存到 '{OUTPUT_EXCEL_FILENAME}'\n")
        except Exception as e:
            print(f"[即时保存失败] {e}\n")

    print("\n--- 数据获取完成 ---")
    print(f"成功获取: {successful_fetches} 个仓库")
    print(f"获取失败: {failed_fetches} 个仓库")

    try:
        # 最终保存
        df.to_excel(OUTPUT_EXCEL_FILENAME, index=False)
        print(f"\n最终数据已保存到 '{OUTPUT_EXCEL_FILENAME}'")
    except Exception as e:
        print(f"保存最终Excel文件失败: {e}")


if __name__ == "__main__":
    main()







