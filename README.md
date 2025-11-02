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
## OpenHarmony 自动化评审结构定义

### PRReviewSample 结构
- `repo`: 仓库名称
- `pr_number`: PR 编号
- `metadata`: {`title`, `body`, `state`, `created_at`, `merged_at`, `user`, `labels_name_list`, `assignees_name_list`}
- `diff_files`: 数组，元素结构：
  - `file_path`
  - `hunks`: 数组，元素结构：
    - `header`
    - `old_start`/`old_end`/`new_start`/`new_end`
    - `has_comment`
    - `lines`: 数组，元素结构：`status`(`added`|`removed`|`context`)、`content`、`old_line_no`、`new_line_no`
  - `historical_comments`: 来自 PR 历史的评论摘要
- `comments`: 当前 PR 的全部评论
- `commit_history`: 键为 `file_path`，值为该文件相关的历史提交列表

### 四个核心问题对应输入/输出文件
1. **问题一：代码片段评审必要性判断**
   - 输入模块：`data/pr_data/processing/question_one.py`
   - 输出文件：`data/processed/question_01_outputs.jsonl`
2. **问题二：评审意见生成**
   - 输入模块：`data/pr_data/processing/question_two.py`
   - 输出文件：`data/processed/question_02_outputs.jsonl`
3. **问题三：问题行定位**
   - 输入模块：`data/pr_data/processing/question_three.py`
   - 输出文件：`data/processed/question_03_outputs.jsonl`
4. **问题四：修复版本生成**
   - 输入模块：`data/pr_data/processing/question_four.py`
   - 输出文件：`data/processed/question_04_outputs.jsonl`

`QuestionOutputPaths` 位于 `data/pr_data/processing/outputs.py`，可将各问题的推理结果统一写入对应文件。

### 多智能体角色
- `ProjectContextAgent`：预取项目级上下文
- `ContextAgent`：提炼 PR 元信息与文件列表
- `NeedReviewAgent`：判断 Hunk 是否需要评审
- `ReviewCommentAgent`：生成评审意见
- `LineLocatorAgent`：行级问题定位
- `FixGeneratorAgent`：生成修复建议
- `ReflectorAgent`：总结历史经验并刷新规则
- `OpenHarmonyReviewOrchestrator`：负责流水线编排与黑板管理

上述 Agent 均在 `utils/agents/openharmony/` 目录内按角色拆分为独立文件，基础设施由 `utils/agents/openharmony/base.py` 提供，编排逻辑见 `utils/agents/openharmony/orchestrator.py`。

#### 云端 API 版（`CloudOpenHarmonyPipeline`）
- 模型调用：通过 `CloudLLMClient` 将 prompt 转发至通义千问/百炼等 RESTful API，若失败自动回落启发式结果。
- 入口模块：`utils/agents/openharmony/cloud_runtime.py`
- 使用示例：
  ```python
  from utils.agents.openharmony import CloudLLMClient, CloudOpenHarmonyPipeline
  from data.pr_data.processing.dataset_builder import PRReviewDatasetBuilder

  builder = PRReviewDatasetBuilder.from_disk(repo="OpenHarmony", data_root="data/pr_data")
  sample = builder.samples[0]
  client = CloudLLMClient(endpoint="https://dashscope.aliyuncs.com/api/v1/services/invoke", model="qwen-turbo", api_key="<key>")
  pipeline = CloudOpenHarmonyPipeline(llm_client=client)
  outputs = pipeline.run(sample)
  ```

#### 本地多 GPU 版（`LocalOpenHarmonyPipeline`）
- 模型调度：`LocalModelRegistry` 负责记录/分配任务至不同 GPU 并在结果中附带 `scheduler_log`。
- 默认映射：
  | 任务 | 默认模型 | GPU | 上下文长度 |
  | --- | --- | --- | --- |
  | need_review | qwen2-7b | cuda:1 | 16384 |
  | review_comment | qwen2-72b | cuda:0 | 32768 |
  | line_locator | qwen2-32b | cuda:2 | 12288 |
  | fix_generator | codeqwen-7b | cuda:0 | 16384 |
- 使用示例：
  ```python
  from utils.agents.openharmony import LocalOpenHarmonyPipeline
  from data.pr_data.processing.dataset_builder import PRReviewDatasetBuilder

  builder = PRReviewDatasetBuilder.from_disk(repo="OpenHarmony", data_root="data/pr_data")
  sample = builder.samples[0]
  pipeline = LocalOpenHarmonyPipeline()
  outputs = pipeline.run(sample)
  print(outputs["scheduler_log"])
  ```


数据处理骨架已迁移至 `data/pr_data/processing/` 包，可通过以下命令验证数据构建流程：

```bash
python -m data.pr_data.processing --repo OpenHarmony \
  --data-root data/pr_data \
  --pr-issue path/to/get_pr\&issue_output.jsonl \
  --pr-commit path/to/get_pr\&commit_output.jsonl \
  --code-refinement path/to/get_code_refinement_data_output.jsonl
```
