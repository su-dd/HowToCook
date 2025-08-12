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
    if os.path.exists(config.ImageMappingFile):
        with open(config.ImageMappingFile, 'r', encoding='utf-8') as f:
            image_mapping = json.load(f)
    else:
        image_mapping = {}
    return image_mapping


if __name__ == '__main__':

    # 刷新UUid
    UUID_MAPPING = uuid_create.generate_uuid_for_md_files(config.BasePath, [config.DishesPath, config.TipsPath], config.RecipesUuidFile)

    image_mapping = generate_image_mapping()

    # 调整路径以正确指向项目根目录下的dishes文件夹
    dishes_directory = config.DishesPath
    recipes_directory = config.RecipesPath
    
    # 确保recipes目录存在
    os.makedirs(config.RecipesPath, exist_ok=True)
    
    print("开始解析菜谱文件...")
    recipes_by_category = parse_dishes.scan_dishes_directory(config.DishesPath, UUID_MAPPING, image_mapping, config.BasePath)

    recipesCount = 0
    # 为每个分类创建单独的JSON文件
    for category, recipes in recipes_by_category.items():
        output_file = os.path.join(config.RecipesPath, f"{category}_recipes.json")

        recipesCount += len(recipes)

        print(f"正在生成 {category} 分类的菜谱数据，共 {len(recipes)} 个菜谱...")
        
        # 写入JSON文件
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(recipes, f, ensure_ascii=False, indent=2)
        
        print(f"{category} 分类的菜谱数据已保存到 {output_file}")

    count = count_md_files(DishesPath)
    print(f"总共有 {count} 个菜谱文件")
    print(f"共生成 {recipesCount} 个菜谱文件")

