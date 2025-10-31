# 通过
import json
from collections import Counter

import pandas as pd

from utils.code_file_check import is_code_file

REPO_List = [
    "account_os_account",
    "arkui_ace_engine",
    "build",
    "communication_wifi",
    "developtools_ace_ets2bundle",
    "multimedia_audio_framework",
    "web_webview",
    # "xts_acts"
]
pr_count = 0
refinement_count = 0
refinement_count_dict = {}
# 读取PRRefinement数据
refinement_data = []
for repo in REPO_List:
    print("========" * 20)
    print(repo)
    # --- 配置 ---
    print("========" * 20)
    # 替换为你要查询的仓库所有者和仓库名
    OWNER = "openharmony"
    REPO = repo

    # 输出文件名
    PR_JSONL_FILE = f"../pr_data/{REPO}/{OWNER}_{REPO}_prs.jsonl"

    PR_Refinement_JSONL_FILE = f"../pr_data/{REPO}/{OWNER}_{REPO}_pr_refinement_code.jsonl"

    try:
        with open(PR_Refinement_JSONL_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                temp_json=json.loads(line.strip())
                temp_data=[]
                temp_data.append(REPO)
                temp_data.append(temp_json['pr_number'])
                temp_data.append(temp_json['diff_comment']['body'])
                refinement_data.append(temp_data)

        print(f"成功读取 {len(refinement_data)} 个PRRefinement数据")
    except Exception as e:
        print(f"读取PRRefinement数据失败: {e}")

# 保存到 Excel，并在第一列加入序号
if refinement_data:
    df = pd.DataFrame(refinement_data, columns=['repo', 'pr_number', 'body'])
    df.insert(0, '序号', range(1, len(df) + 1))
    output_file = "../pr_data/all_pr_refinement_comment.xlsx"
    try:
        df.to_excel(output_file, index=False)
        print(f"已保存 {len(df)} 条数据到 `../pr_data/all_pr_refinement_comment.xlsx`")
    except Exception as e:
        print(f"保存 Excel 失败: {e}")
else:
    print("没有可保存的 PRRefinement 数据")

