import os


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
