import os
import json
import uuid

def generate_uuid_for_md_files(path : str):

    # 定义要遍历的目录
    directories = [
        path + '/dishes',
        path + '/tips'
    ]
    
    # UUID 文件路径
    uuid_file_path = './Uuid/Uuid.json'
    
    # 读取现有的 UUID 映射
    if os.path.exists(uuid_file_path):
        with open(uuid_file_path, 'r', encoding='utf-8') as f:
            uuid_mapping = json.load(f)
    else:
        uuid_mapping = {}
    
    # 遍历指定目录及其子目录中的所有 .md 文件
    for directory in directories:
        for root, _, files in os.walk(directory):
            for file in files:
                if file.endswith('.md'):
                    file_path = os.path.join(root, file)
                    relative_path = os.path.relpath(file_path, path).replace('\\', '/')
                    
                    # 如果文件还没有 UUID，则生成一个
                    if relative_path not in uuid_mapping:
                        new_uuid = str(uuid.uuid4())
                        uuid_mapping[new_uuid] = relative_path
    
    # 将更新后的 UUID 映射写回文件
    with open(uuid_file_path, 'w', encoding='utf-8') as f:
        json.dump(uuid_mapping, f, ensure_ascii=False, indent=2)

if __name__ == '__main__':
    generate_uuid_for_md_files('d:/workspace/HowToCook')