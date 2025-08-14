import re
import parse_dishes
import uuid_create
import os
import json
import config


def count_md_files(directory : str) -> int:
    """
    统计目录下所有子目录中的Markdown文件数量
    """
    count = 0
    for root, _, files in os.walk(directory):
        for file in files:
            if file.endswith('.md'):
                count += 1
    return count

def generate_image_mapping() -> dict:
    """
    生成图片路径映射关系
    """
    # 读取现有的映射文件（如果存在）
    if os.path.exists(config.ImageUuidFile):
        with open(config.ImageUuidFile, 'r', encoding='utf-8') as f:
            image_mapping = json.load(f)
    else:
        image_mapping = {}
    return image_mapping


if __name__ == '__main__':

    # 刷新UUid
    dishes_uuid_mapping = uuid_create.generate_uuid_for_md_files(config.BasePath, [config.DishesPath], config.DischessUuidFile)
    tips_uuid_mapping = uuid_create.generate_uuid_for_md_files(config.BasePath, [config.TipsPath], config.TipsUuidFile)

    image_mapping = generate_image_mapping()
    
    # 确保dishes目录存在
    os.makedirs(config.StaticDishesPath, exist_ok=True)
    
    print("开始解析菜谱文件...")
    dishes_by_category = parse_dishes.scan_dishes_directory(config.DishesPath, dishes_uuid_mapping, image_mapping, config.BasePath)

    dishesCount = 0
    # 为每个分类创建单独的JSON文件
    for category, dishes in dishes_by_category.items():
        output_file = os.path.join(config.StaticDishesPath, f"{category}_dishes.json")

        dishesCount += len(dishes)

        print(f"正在生成 {category} 分类的菜谱数据，共 {len(dishes)} 个菜谱...")
        
        # 写入JSON文件
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(dishes, f, ensure_ascii=False, indent=2)
        
        print(f"{category} 分类的菜谱数据已保存到 {output_file}")

    # 写入图片映射文件
    with open(config.ImageUuidFile, 'w', encoding='utf-8') as f:
        json.dump(image_mapping, f, ensure_ascii=False, indent=2)

    count = count_md_files(config.DishesPath)
    print(f"总共有 {count} 个菜谱文件")
    print(f"共生成 {dishesCount} 个菜谱文件")

