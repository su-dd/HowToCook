import os
import json
import uuid

def generate_uuid_for_md_files(directories : list, uuid_file_path : str) -> dict:

    """
    为指定路径下的所有.md文件生成UUID，并将映射关系写入uuid.json文件。
    如果文件已存在，会读取现有映射并更新。
    """    
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
    

    # 如果文件存在，将数据更新回去，如果文件不存在，创建一个文件
    if os.path.exists(uuid_file_path):
        with open(uuid_file_path, 'w', encoding='utf-8') as f:
            json.dump(uuid_mapping, f, ensure_ascii=False, indent=2)
    else:
        os.makedirs(os.path.dirname(uuid_file_path), exist_ok=True)
        with open(uuid_file_path, 'w', encoding='utf-8') as f:
            json.dump(uuid_mapping, f, ensure_ascii=False, indent=2)

    return uuid_mapping
