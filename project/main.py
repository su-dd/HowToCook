import parse_dishes
import uuid_create
import os
import json

BasePath = 'd:/workspace/HowToCook'
RecipesPath = BasePath + '/recipes'
DishesPath = BasePath + '/dishes'
TipsPath = BasePath + '/tips'
UuidPath = RecipesPath + '/uuid'
RecipesUuidFile = UuidPath + '/uuid.json'

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


if __name__ == '__main__':

    # 刷新UUid
    UUID_MAPPING = uuid_create.generate_uuid_for_md_files(BasePath, [DishesPath, TipsPath], RecipesUuidFile)

    # 调整路径以正确指向项目根目录下的dishes文件夹
    dishes_directory = DishesPath
    recipes_directory = RecipesPath
    
    # 确保recipes目录存在
    os.makedirs(RecipesPath, exist_ok=True)
    
    print("开始解析菜谱文件...")
    recipes_by_category = parse_dishes.scan_dishes_directory(DishesPath, UUID_MAPPING, BasePath)

    recipesCount = 0
    # 为每个分类创建单独的JSON文件
    for category, recipes in recipes_by_category.items():
        output_file = os.path.join(RecipesPath, f"{category}_recipes.json")
        recipesCount += len(recipes)

        print(f"正在生成 {category} 分类的菜谱数据，共 {len(recipes)} 个菜谱...")
        
        # 写入JSON文件
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(recipes, f, ensure_ascii=False, indent=2)
        
        print(f"{category} 分类的菜谱数据已保存到 {output_file}")

    count = count_md_files(DishesPath)
    print(f"总共有 {count} 个菜谱文件")
    print(f"共生成 {recipesCount} 个菜谱文件")

