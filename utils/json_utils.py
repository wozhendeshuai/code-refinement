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
