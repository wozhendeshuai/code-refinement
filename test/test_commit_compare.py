import requests
import json


def test_gitcode_compare_api(owner, repo, base, head):
    """
    测试 GitCode API 的 /compare 接口
    https://docs.gitcode.com/docs/apis/get-api-v-5-repos-owner-repo-compare-base-head

    参数:
    - owner: 仓库所有者
    - repo: 仓库名称
    - base: 基准分支或提交SHA
    - head: 比较分支或提交SHA
    - token: 私人令牌（可选）
    """

    # API URL
    api_url = f"https://gitcode.com/api/v5/repos/{owner}/{repo}/compare/{base}...{head}"

    # 设置请求头
    headers = {
        'Accept': 'application/json',
        'PRIVATE-TOKEN': 'ZHntmapyoy-tm62QF71DMPkZ'
    }



    print(f"正在调用 API: {api_url}")
    print(f"请求头: {headers}")
    print("-" * 50)

    try:
        # 发送GET请求
        response = requests.get(api_url, headers=headers)

        print(f"响应状态码: {response.status_code}")

        if response.status_code == 200:
            # 解析响应数据
            data = response.json()
            print("API 调用成功！")
            print(f"响应数据类型: {type(data)}")
            print(f"响应数据: {data}")

            print(data['files'][0]['patch'])

    except requests.exceptions.RequestException as e:
        print(f"请求异常: {e}")
    except json.JSONDecodeError as e:
        print(f"JSON 解析错误: {e}")
        print(f"原始响应内容: {response.text}")


def main():
    print("GitCode API /compare 测试工具")
    print("=" * 50)

    # 获取用户输入
    owner = "openharmony"
    repo = "web_webview"
    base = '1309a333b5ac28cd6342799f557b57da509ced56'
    head = 'b187ed5d2c821d06121ac4c7549b65c4bfebaf36'


    print("\n" + "=" * 50)
    test_gitcode_compare_api(owner, repo, base, head)


if __name__ == "__main__":
    main()



