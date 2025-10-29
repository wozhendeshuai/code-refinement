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
            if len(parts) < 2 or header_parts.startswith('-') is False:
                i += 1
                continue
            elif len(parts) > 2:
                header_parts = parts[0] + ' ' + parts[1]
                old_part, new_part = header_parts.split()
            else:
                old_part, new_part = header_parts.split()

            # 提取 old_start 和 old_count
            old_info = old_part[1:].split(',') if len(old_part) > 1 else ['-1', '-1']

            old_start = int(old_info[0])
            old_count = int(old_info[1]) if len(old_info) > 1 and old_info[1] != '' else 1

            # 提取 new_start 和 new_count
            new_info = new_part[1:].split(',')
            new_start = int(new_info[0]) if new_info[0] else -1
            new_count = int(new_info[1]) if len(new_info) > 1 and new_info[1] != '' else -1

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