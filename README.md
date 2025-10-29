# Code Refinement 数据分析工具集

本项目是一套完整的代码审查数据分析工具集，主要用于从 GitCode 平台获取 PR（Pull Request）及相关代码修改数据，并进行统计分析和质量评估。

## 主要功能

- PR 数据采集：从 GitCode 获取 PR 信息、提交记录、文件修改内容等
- 代码修改分析：对比代码变更，识别需要优化的代码段
- 数据统计处理：生成 Excel 报表，统计 PR、Issue 及代码改进点
- 质量检测：识别需要进一步检查的代码修改

## 目录结构说明

- `data/` - 核心数据处理模块
  - `pr_data/` - PR 数据获取与分析
  - `repo_pr.py` - 仓库 PR 统计工具
- `utils/` - 工具函数
  - `code_file_check.py` - 代码文件检测
  - `diff_utils.py` - Diff 文本处理
  - `json_utils.py` - JSON 数据处理
- `test/` - 测试代码

## 使用说明

1. 安装依赖：
```bash
pip install -r requirements.txt
```

2. 配置 API 认证信息（如需）：
修改 `pr_data/get_pr&commit.py` 中的认证配置

3. 运行数据采集：
```bash
python data/pr_data/get_pr&commit.py
```

4. 运行数据分析：
```bash
python data/pr_data/PR_static_analysis.py
```

## 依赖库

- requests
- pandas
- openpyxl
- gitpython

## 注意事项

- 需要配置 GitCode API 访问权限
- 建议使用 Python 3.8+ 环境
- 处理大规模数据时注意内存使用

## 许可证

本项目采用 Apache-2.0 许可证。