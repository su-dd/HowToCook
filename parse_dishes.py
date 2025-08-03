import os
import json
import re
from typing import List, Dict, Any

def parse_markdown_file(file_path: str) -> Dict[str, Any]:
    """
    解析菜谱Markdown文件并提取信息
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 提取标题
    title_match = re.search(r'# (.+)', content)
    title = title_match.group(1) if title_match else ""
    title = title.replace('的做法', '') 
    
    # 提取描述（标题后的段落直到预估烹饪难度）
    description_parts = []
    lines = content.split('\n')
    in_description = False
    for line in lines:
        if line.startswith('# ') and title in line:
            in_description = True
            continue
        elif line.startswith('预估烹饪难度：'):
            description_parts.append(line)
            break
        elif in_description and not line.startswith('!['):
            description_parts.append(line)
        elif in_description and line.startswith('!['):
            # 处理图片链接
            description_parts.append(line)
    
    description = '\n'.join(description_parts).strip()
    
    # 提取难度
    difficulty_match = re.search(r'预估烹饪难度：(★+)', content)
    difficulty = len(difficulty_match.group(1)) if difficulty_match else 0
    
    # 提取类别（从路径推断）
    category_map = {
        'aquatic': '水产',
        'breakfast': '早餐',
        'condiment': '佐料',
        'dessert': '甜品',
        'drink': '饮品',
        'meat_dish': '肉食',
        'semi-finished': '半成品',
        'soup': '汤类',
        'staple': '主食',
        'vegetable_dish': '素菜'
    }
    
    category = '未知'
    for key, value in category_map.items():
        if key in file_path:
            category = value
            break
    
    # 提取必需原料和工具（支持-和*两种列表标记，包括嵌套列表）
    ingredients = []
    ingredients_section = re.search(r'## 必备原料和工具\n(.*?)\n##', content, re.DOTALL)
    if ingredients_section:
        ingredients_text = ingredients_section.group(1)
        # 查找所有以列表标记开头的行，包括缩进的列表项
        lines = ingredients_text.split('\n')
        i = 0
        while i < len(lines):
            line = lines[i]
            # 检查是否为列表项，但排除引用行（>）和子标题（###）
            if (line.strip().startswith(('- ', '* ', '  - ', '  * ')) and 
                not line.strip().startswith('>') and
                not line.strip().startswith(('###', '##'))):
                # 去掉前缀获取原料名称
                stripped_line = line.strip()
                if stripped_line.startswith('- ') or stripped_line.startswith('* '):
                    ingredient_name = stripped_line[2:].strip()
                elif stripped_line.startswith('  - ') or stripped_line.startswith('  * '):
                    ingredient_name = stripped_line[4:].strip()
                
                # 特殊处理：如果原料名称包含子列表，则需要提取子列表项
                if ingredient_name and (ingredient_name.endswith("：") or "包含" in ingredient_name):
                    # 这是一个带子列表的项，如"袋装螺蛳粉一包，其中应该包含："
                    ingredients.append({
                        "name": ingredient_name,
                        "quantity": None,
                        "unit": None,
                        "text_quantity": stripped_line,
                        "notes": "量未指定"
                    })
                    
                    # 查找接下来的子列表项
                    j = i + 1
                    while j < len(lines) and (lines[j].startswith('  - ') or lines[j].startswith('  * ') or 
                                              lines[j].startswith('    - ') or lines[j].startswith('    * ')):
                        sub_line = lines[j].strip()
                        sub_ingredient = ""
                        if sub_line.startswith('  - ') or sub_line.startswith('  * '):
                            sub_ingredient = sub_line[4:].strip()
                        elif sub_line.startswith('    - ') or sub_line.startswith('    * '):
                            sub_ingredient = sub_line[6:].strip()
                        
                        if sub_ingredient:
                            ingredients.append({
                                "name": sub_ingredient,
                                "quantity": None,
                                "unit": None,
                                "text_quantity": sub_line,
                                "notes": "量未指定"
                            })
                        j += 1
                    i = j  # 跳过已处理的子项
                    continue
                elif ingredient_name:
                    # 普通的原料项
                    ingredients.append({
                        "name": ingredient_name,
                        "quantity": None,
                        "unit": None,
                        "text_quantity": stripped_line,
                        "notes": "量未指定"
                    })
            i += 1
    
    # 提取计算部分（支持-和*两种列表标记）
    calculation_section = re.search(r'## 计算\n(.*?)\n##', content, re.DOTALL)
    if calculation_section:
        calculation_text = calculation_section.group(1)
        # 支持-和*两种列表标记
        calculation_lines = [line.strip() for line in calculation_text.split('\n') if line.strip().startswith(('- ', '* '))]
        for line in calculation_lines:
            ingredient = line[2:]  # 去掉 "- " 或 "* " 前缀
            # 提取原料名称（第一个词）
            name_parts = ingredient.split()
            if name_parts:
                name = name_parts[0]
                ingredients.append({
                    "name": name,
                    "quantity": None,
                    "unit": None,
                    "text_quantity": line,
                    "notes": "量未指定"
                })
    
    # 提取操作步骤（支持-和*两种列表标记）
    steps = []
    steps_section = re.search(r'## 操作\n(.*?)(?:\n## |\Z)', content, re.DOTALL)
    if steps_section:
        steps_text = steps_section.group(1)
        # 查找所有以-或*开头的行，忽略子标题
        step_lines = [line.strip() for line in steps_text.split('\n') if line.strip().startswith(('- ', '* '))]
        for i, line in enumerate(step_lines, 1):
            step_text = line[2:]  # 去掉 "- " 或 "* " 前缀
            steps.append({
                "step": i,
                "description": step_text
            })
    
    # 提取参考资料作为additional_notes
    additional_notes = []
    # 查找参考资料部分（支持不同形式的参考资料标题）
    reference_patterns = [
        r'### 参考资料\n(.*?)(?:\n#|$)',
        r'## 附加内容\n(.*?)(?:\n#|$)',
        r'如果您遵循本指南的制作流程而发现有问题或可以改进的流程，请提出 Issue 或 Pull request 。'
    ]
    
    reference_found = False
    for pattern in reference_patterns[:-1]:  # 除最后一个默认文本外的所有模式
        reference_section = re.search(pattern, content, re.DOTALL)
        if reference_section:
            reference_text = reference_section.group(1).strip()
            # 将参考资料按行分割并添加到列表中
            reference_lines = [line.strip() for line in reference_text.split('\n') if line.strip() and not line.strip().startswith(('##', '###'))]
            additional_notes.extend(reference_lines)
            reference_found = True
            break
    
    # 如果没有找到参考资料部分，检查是否有默认文本
    if not reference_found:
        if "如果您遵循本指南的制作流程而发现有问题或可以改进的流程，请提出 Issue 或 Pull request 。" in content:
            additional_notes.append("如果您遵循本指南的制作流程而发现有问题或可以改进的流程，请提出 Issue 或 Pull request 。")
        else:
            # 如果都没有，使用默认值
            additional_notes.append("如果您遵循本指南的制作流程而发现有问题或可以改进的流程，请提出 Issue 或 Pull request 。")
    
    # 提取图片链接
    images = []
    # 查找描述中的图片
    image_matches = re.findall(r'!\[.*?\]\((.*?)\)', description)
    for match in image_matches:
        if match.startswith('./'):
            # 相对路径转换为完整路径
            image_path = os.path.join(os.path.dirname(file_path), match[2:]).replace('\\', '/')
            images.append(image_path)
        else:
            images.append(match)
    
    # 如果描述中没有图片，查找整个文件中的所有图片
    if not images:
        # 查找整个文件中的所有图片
        all_image_matches = re.findall(r'!\[.*?\]\((.*?)\)', content)
        for match in all_image_matches:
            if match.startswith('./'):
                # 相对路径转换为完整路径
                full_path = os.path.join(os.path.dirname(file_path), match[2:]).replace('\\', '/')
                images.append(full_path)
            else:
                images.append(match)
    
    # 设置主图路径
    image_path = images[0] if images else None
    
    # 构建ID（基于文件路径和标题）
    relative_path = os.path.relpath(file_path, 'e:/HowToCookPython')
    path_parts = relative_path.replace('\\', '/').split('/')
    
    # 移除文件扩展名获取文件名部分
    if path_parts[-1].endswith('.md'):
        path_parts[-1] = path_parts[-1][:-3]  # 移除 .md 扩展名
    
    # 构建完整的ID
    dish_id = '-'.join(path_parts)
    
    # 构建源路径
    source_path = os.path.relpath(file_path, 'e:/HowToCookPython').replace('\\', '/')
    
    return {
        "id": dish_id,
        "name": title,
        "description": description,
        "source_path": source_path,
        "image_path": image_path,
        "images": images,
        "category": category,
        "difficulty": difficulty,
        "tags": [category],
        "servings": 1,
        "ingredients": ingredients,
        "steps": steps,
        "prep_time_minutes": None,
        "cook_time_minutes": None,
        "total_time_minutes": None,
        "additional_notes": additional_notes
    }

def scan_dishes_directory(directory: str) -> List[Dict[str, Any]]:
    """
    扫描菜谱目录并解析所有.md文件
    """
    recipes = []
    
    for root, dirs, files in os.walk(directory):
        for file in files:
            if file.endswith('.md'):
                file_path = os.path.join(root, file)
                try:
                    recipe_data = parse_markdown_file(file_path)
                    recipes.append(recipe_data)
                except Exception as e:
                    print(f"解析文件 {file_path} 时出错: {e}")
    
    return recipes

def main():
    dishes_directory = './dishes'
    output_file = './recipes/all_recipes.json'
    
    print("开始解析菜谱文件...")
    recipes = scan_dishes_directory(dishes_directory)
    
    print(f"共解析 {len(recipes)} 个菜谱")
    
    # 写入JSON文件
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(recipes, f, ensure_ascii=False, indent=2)
    
    print(f"菜谱数据已保存到 {output_file}")

if __name__ == "__main__":
    main()