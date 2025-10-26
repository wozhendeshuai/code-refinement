import os

# 读取一个文件夹下所有的PDF文件，并逐一打印出其文件名
def print_pdf_filenames(folder_path):
    count=1
    for filename in os.listdir(folder_path):
        if filename.lower().endswith('.pdf'):
            print(f"{count}. {filename}")
            count+=1

# 示例用法
print_pdf_filenames('/Users/jiajunyu/paper/API document')