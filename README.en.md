# Code Refinement Data Analysis Toolkit

This project is a comprehensive code review data analysis toolkit designed primarily to retrieve PR (Pull Request) and associated code modification data from the GitCode platform, and perform statistical analysis and quality assessment.

## Main Features

- PR Data Collection: Retrieve PR information, commit records, file modification contents, etc., from GitCode
- Code Modification Analysis: Compare code changes to identify code segments requiring optimization
- Data Statistics Processing: Generate Excel reports to summarize PRs, Issues, and code improvement points
- Quality Detection: Identify code modifications requiring further inspection

## Directory Structure

- `data/` - Core data processing modules
  - `pr_data/` - PR data retrieval and analysis
  - `repo_pr.py` - Repository PR statistics tool
- `utils/` - Utility functions
  - `code_file_check.py` - Code file inspection
  - `diff_utils.py` - Diff text processing
  - `json_utils.py` - JSON data processing
- `test/` - Test scripts

## Usage Instructions

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Configure API authentication (if needed):
Modify the authentication settings in `pr_data/get_pr&commit.py`

3. Run data collection:
```bash
python data/pr_data/get_pr&commit.py
```

4. Run data analysis:
```bash
python data/pr_data/PR_static_analysis.py
```

## Dependencies

- requests
- pandas
- openpyxl
- gitpython

## Notes

- GitCode API access permissions must be configured
- Python 3.8+ environment is recommended
- Be mindful of memory usage when processing large datasets

## License

This project is licensed under the Apache-2.0 License.