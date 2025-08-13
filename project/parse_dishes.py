import os
import json
import re
from typing import List, Dict, Any, Tuple

from image_handler import copy_image_to_recipes

def parse_ingredient_text(text: str) -> Tuple[str, float, str]:
    """
    解析原料文本，提取名称、数量和单位
    例如："鸡蛋 2个" -> ("鸡蛋", 2.0, "个")
    """
    # 常见单位列表
    units = ['克', 'g', 'kg', '毫升', 'ml', '升', 'l', '个', '只', '块', '片', '根', '条', '把', '朵', '粒', '颗', '瓣', '滴', '勺', '杯', '碗', '包', '袋', '瓶', '罐', '盒', '斤', '两']
    
    # 移除特殊字符
    text = text.strip().replace('：', '').replace(':', '')
    
    # 尝试匹配范围值，如"70-230g"
    range_pattern = r'(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)\s*(' + '|'.join(units) + ')'
    range_match = re.search(range_pattern, text)
    
    if range_match:
        # 取范围的平均值作为数量
        min_val = float(range_match.group(1))
        max_val = float(range_match.group(2))
        quantity = (min_val + max_val) / 2
        unit = range_match.group(3)
        # 移除范围部分，获取名称
        name = re.sub(range_pattern, '', text).strip()
        return name, quantity, unit
    
    # 尝试匹配数量和单位
    # 匹配模式：数字+单位 或 数字+空格+单位
    pattern = r'^(.*?)(\d+(?:\.\d+)?)\s*(' + '|'.join(units) + ')'
    match = re.search(pattern, text)
    
    if match:
        name = match.group(1).strip()
        quantity = float(match.group(2))
        unit = match.group(3)
        return name, quantity, unit
    
    # 如果没有匹配到，尝试匹配只有数字的情况
    pattern = r'^(.*?)(\d+(?:\.\d+)?)$'
    match = re.search(pattern, text)
    
    if match:
        name = match.group(1).strip()
        quantity = float(match.group(2))
        return name, quantity, None
    
    # 如果都没有匹配到，返回原始文本作为名称
    return text, None, None

def _extract_title(content: str) -> str:
    """
    从Markdown内容中提取标题
    """
    title_match = re.search(r'# (.+)', content)
    title = title_match.group(1) if title_match else ""
    return title.replace('的做法', '')


def _extract_description(content: str, title: str) -> str:
    """
    从Markdown内容中提取描述
    """
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
    
    return '\n'.join(description_parts).strip()

def _extract_times(content: str) -> tuple:
    """
    从Markdown内容中提取准备时间、烹饪时间和总时间
    返回 (prep_time_minutes, cook_time_minutes, total_time_minutes)
    """
    prep_time = None
    cook_time = None
    total_time = None
    
    # 中文数字到阿拉伯数字的映射
    chinese_numerals = {
        '一': 1, '二': 2, '三': 3, '四': 4, '五': 5, 
        '六': 6, '七': 7, '八': 8, '九': 9, '十': 10,
        '半': 0.5
    }
    
    # 将中文数字转换为阿拉伯数字的函数
    def chinese_to_arabic(chinese_num):
        # 处理简单的中文数字
        if chinese_num in chinese_numerals:
            return chinese_numerals[chinese_num]
        
        # 处理复合中文数字，如"二十"、"二十五"等
        if chinese_num == '二十':
            return 20
        elif chinese_num == '二十五':
            return 25
        elif chinese_num == '三十':
            return 30
        elif chinese_num == '三十五':
            return 35
        elif chinese_num == '四十':
            return 40
        elif chinese_num == '四十五':
            return 45
        elif chinese_num == '五十':
            return 50
        
        return None
    
    # 匹配时间信息的正则表达式（支持阿拉伯数字和中文数字）
    time_pattern = r'(预估准备时间|预估烹饪时间|预估总时间)：(\d+(?:\.\d+)?|[' + ''.join(chinese_numerals.keys()) + r']+)(?:\s*个)?\s*(分钟|小时|天)'
    matches = re.findall(time_pattern, content)
    
    for match in matches:
        time_type, value, unit = match
        
        # 处理中文数字
        if value in chinese_numerals:
            time_value = float(chinese_numerals[value])
        else:
            time_value = float(value)
        
        # 转换为分钟
        if unit == '小时':
            time_value *= 60
        elif unit == '天':
            time_value *= 1440  # 24 * 60
        
        if '准备时间' in time_type:
            prep_time = int(time_value)
        elif '烹饪时间' in time_type:
            cook_time = int(time_value)
        elif '总时间' in time_type:
            total_time = int(time_value)
    
    # 如果没有找到明确的时间标记，尝试从描述中提取时间信息
    if prep_time is None and cook_time is None and total_time is None:
        # 匹配描述中的时间信息，如"需要 2 小时即可完成"或"需要四个小时即可完成"
        desc_time_pattern = r'(\d+(?:\.\d+)?|[' + ''.join(chinese_numerals.keys()) + r']+)\s*(分钟|小时|天).*?(完成|制作)'
        desc_matches = re.findall(desc_time_pattern, content)
        
        if desc_matches:
            value, unit, _ = desc_matches[0]
            
            # 处理中文数字
            if value in chinese_numerals:
                time_value = float(chinese_numerals[value])
            else:
                time_value = float(value)
            
            # 转换为分钟
            if unit == '小时':
                time_value *= 60
            elif unit == '天':
                time_value *= 1440
            
            # 如果只找到一个时间，假设它是总时间
            total_time = int(time_value)
    
    # 如果prep_time或cook_time未找到，尝试从步骤中提取
    if prep_time is None or cook_time is None:
        # 匹配步骤中的时间信息，支持中文数字
        # 定义多个模式以匹配不同格式的时间表达
        step_time_patterns = [
            r'([一二三四五六七八九十半]+)\s*(分钟|小时|天)',  # 中文数字+单位
            r'(\d+(?:\.\d+)?)\s*(分钟|小时|天)',             # 阿拉伯数字+单位
            r'([一二三四五六七八九十半]+)个(分钟|小时|天)',    # 中文数字+"个"+单位
            r'(\d+(?:\.\d+)?)个(分钟|小时|天)',              # 阿拉伯数字+"个"+单位
            r'(二十|二十五|三十|三十五|四十|四十五|五十|六十)\s*(分钟|小时|天)',  # 复合中文数字+单位
            r'(二十|二十五|三十|三十五|四十|四十五|五十|六十)个(分钟|小时|天)'   # 复合中文数字+"个"+单位
        ]
        
        step_time_matches = []
        for pattern in step_time_patterns:
            matches = re.findall(pattern, content)
            if matches:
                step_time_matches.extend(matches)
        
        # 计算步骤中的总时间
        step_total_minutes = 0
        for match in step_time_matches:
            if len(match) == 2:
                value, unit = match
                # 处理中文数字
                if value in chinese_numerals:
                    time_value = float(chinese_numerals[value])
                else:
                    # 处理复合中文数字
                    time_value = chinese_to_arabic(value)
                    if time_value is None:
                        time_value = float(value)
                
                if unit == '小时':
                    time_value *= 60
                elif unit == '天':
                    time_value *= 1440  # 24 * 60
                step_total_minutes += time_value
        
        # 如果从步骤中提取到时间，则更新总时间
        if step_total_minutes > 0 and total_time is None:
            total_time = int(step_total_minutes)
        
        # 如果prep_time或cook_time仍为None，将步骤中的时间分配给cook_time
        if (prep_time is None or cook_time is None) and step_total_minutes > 0:
            if cook_time is None:
                cook_time = int(step_total_minutes)
            # 如果prep_time仍为None，暂时保持为None，因为很难从步骤中准确提取准备时间
    
    return prep_time, cook_time, total_time


def _extract_difficulty(content: str) -> int:
    """
    从Markdown内容中提取难度
    """
    difficulty_match = re.search(r'预估烹饪难度：(★+)', content)
    return len(difficulty_match.group(1)) if difficulty_match else 0


def _extract_ingredients(content: str) -> list:
    """
    从Markdown内容中提取原料和工具
    """
    ingredients = []
    processed_ingredients = set()  # 用于跟踪已处理的原料，避免重复
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
                    ingredient_text = stripped_line[2:].strip()
                elif stripped_line.startswith('  - ') or stripped_line.startswith('  * '):
                    ingredient_text = stripped_line[4:].strip()
                
                # 解析原料文本，提取名称、数量和单位
                ingredient_name, quantity, unit = parse_ingredient_text(ingredient_text)
                
                # 特殊处理：如果原料名称包含子列表，则需要提取子列表项
                if ingredient_name and (ingredient_name.endswith("：") or "包含" in ingredient_name):
                    # 这是一个带子列表的项，如"袋装螺蛳粉一包，其中应该包含："
                    if ingredient_name not in processed_ingredients:
                        ingredients.append({
                            "name": ingredient_name,
                            "quantity": quantity,
                            "unit": unit,
                            "text_quantity": stripped_line,
                            "notes": "量未指定" if quantity is None else ""
                        })
                        processed_ingredients.add(ingredient_name)
                    
                    # 查找接下来的子列表项
                    j = i + 1
                    while j < len(lines) and (lines[j].startswith('  - ') or lines[j].startswith('  * ') or 
                                              lines[j].startswith('    - ') or lines[j].startswith('    * ')):
                        sub_line = lines[j].strip()
                        sub_ingredient_text = ""
                        if sub_line.startswith('  - ') or sub_line.startswith('  * '):
                            sub_ingredient_text = sub_line[4:].strip()
                        elif sub_line.startswith('    - ') or sub_line.startswith('    * '):
                            sub_ingredient_text = sub_line[6:].strip()
                        
                        if sub_ingredient_text:
                            sub_ingredient_name, sub_quantity, sub_unit = parse_ingredient_text(sub_ingredient_text)
                            if sub_ingredient_name and sub_ingredient_name not in processed_ingredients:
                                ingredients.append({
                                    "name": sub_ingredient_name,
                                    "quantity": sub_quantity,
                                    "unit": sub_unit,
                                    "text_quantity": sub_line,
                                    "notes": "量未指定" if sub_quantity is None else ""
                                })
                                processed_ingredients.add(sub_ingredient_name)
                        j += 1
                    i = j  # 跳过已处理的子项
                    continue
                elif ingredient_name and ingredient_name not in processed_ingredients:
                    # 普通的原料项
                    ingredients.append({
                        "name": ingredient_name,
                        "quantity": quantity,
                        "unit": unit,
                        "text_quantity": stripped_line,
                        "notes": "量未指定" if quantity is None else ""
                    })
                    processed_ingredients.add(ingredient_name)
            i += 1
    
    # 提取计算部分（支持-和*两种列表标记）
    calculation_section = re.search(r'## 计算\n(.*?)\n##', content, re.DOTALL)
    if calculation_section:
        calculation_text = calculation_section.group(1)
        # 支持-和*两种列表标记
        calculation_lines = [line.strip() for line in calculation_text.split('\n') if line.strip().startswith(('- ', '* '))]
        for line in calculation_lines:
            ingredient_text = line[2:]  # 去掉 "- " 或 "* " 前缀
            # 解析原料文本，提取名称、数量和单位
            name, quantity, unit = parse_ingredient_text(ingredient_text)
            if name and name not in processed_ingredients:
                ingredients.append({
                    "name": name,
                    "quantity": quantity,
                    "unit": unit,
                    "text_quantity": line,
                    "notes": "量未指定" if quantity is None else ""
                })
                processed_ingredients.add(name)
    
    return ingredients


def _extract_steps(content: str) -> list:
    """
    从Markdown内容中提取操作步骤
    """
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
    # 如果没有找到步骤，使用默认值
    if not steps:
        steps = [{"step": 1, "description": "暂无详细步骤说明"}]
    
    return steps


def _extract_additional_notes(content: str) -> list:
    """
    从Markdown内容中提取参考资料作为additional_notes
    """
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
    
    return additional_notes


def _extract_images(content: str, file_path: str) -> list:
    """
    从Markdown内容中提取图片链接
    """
    images = []
    # 匹配Markdown图片语法 ![alt](path)
    image_pattern = r'!\[.*?\]\((.*?)\)'
    matches = re.findall(image_pattern, content)
    
    # 转换为绝对路径
    for match in matches:
        # 如果是相对路径，转换为绝对路径
        if not match.startswith('http'):
            abs_path = os.path.join(os.path.dirname(file_path), match).replace('\\', '/')
            images.append(abs_path)
        else:
            # 如果是网络图片，保持原样
            images.append(match)
    
    # 去重
    images = list(dict.fromkeys(images))
    
    return images

def _extract_main_image(content: str, description: str, images: list, file_path: str) -> str:
    """
    从Markdown内容中提取主图路径
    """
    # 设置主图路径
    # 如果有图片，使用第一张图片作为主图
    image_path = images[0] if images else None
    
    return image_path
    
def _extract_dish_id(file_path: str, uuid_mapping: dict) -> str:
    """
    从文件路径和UUID映射中提取dish_id
    """
    relative_path = os.path.relpath(file_path, os.getcwd()).replace('\\', '/')
    dish_id = uuid_mapping.get(relative_path)
    
    # 如果没有找到UUID， 应该报错，终止程序报错
    if not dish_id:
        raise ValueError(f"未找到文件 {relative_path} 的UUID映射")
    
    return dish_id


def _process_images(image_path: str, images: list, image_mapping: dict) -> tuple:
    """
    复制图片到recipes文件夹并更新路径
    """
    if image_path:
        image_path = copy_image_to_recipes(image_path, image_mapping)
    
    if images:
        images = [copy_image_to_recipes(img, image_mapping) for img in images]
    
    return image_path, images


def _build_source_path(file_path: str, base_path: str) -> str:
    """
    构建源路径
    """
    return os.path.relpath(file_path, base_path).replace('\\', '/')


def parse_markdown_file(file_path: str, category: str, uuid_mapping: dict, image_mapping: dict, base_path : str) -> Dict[str, Any]:
    """
    解析菜谱Markdown文件并提取信息
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 提取标题
    title = _extract_title(content)
    
    # 提取描述
    description = _extract_description(content, title)
    
    # 提取难度
    difficulty = _extract_difficulty(content)
    
    # 提取必需原料和工具
    ingredients = _extract_ingredients(content)
    
    # 提取操作步骤
    steps = _extract_steps(content)
    
    # 提取参考资料作为additional_notes
    additional_notes = _extract_additional_notes(content)
    
    # 提取图片链接
    images = _extract_images(content, file_path)
    
    # 设置主图路径
    image_path = _extract_main_image(content, description, images, file_path)
    
    # 提取时间信息
    prep_time, cook_time, total_time = _extract_times(content)
    
    # 提取dish_id
    dish_id = _extract_dish_id(file_path, uuid_mapping)
    
    # 处理图片
    image_path, images = _process_images(image_path, images, image_mapping)
    
    # 构建源路径
    source_path = _build_source_path(file_path, base_path)
    
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
        "prep_time_minutes": prep_time,
        "cook_time_minutes": cook_time,
        "total_time_minutes": total_time,
        "additional_notes": additional_notes
    }

def scan_dishes_directory(directory: str, uuid_mapping: dict, image_mapping: dict, base_path : str) -> Dict[str, List[Dict[str, Any]]]:


    """
    扫描菜谱目录并按分类解析所有.md文件
    """
    recipes_by_category = {}
    
    # 初始化所有分类
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
    
    for category_dir in category_map.keys():
        recipes_by_category[category_dir] = []
    
    for root, dirs, files in os.walk(directory):
        # 获取当前目录的分类名称
        relative_root = os.path.relpath(root, directory)
        # 统一使用正斜杠处理路径
        relative_root = relative_root.replace('\\', '/')
        path_parts = relative_root.split('/')
        category = path_parts[0] if path_parts and path_parts[0] else 'unknown'
        
        # 如果分类不在预定义列表中，则跳过
        if category not in recipes_by_category:
            print(f"跳过分类: {category}")
            continue
        
        for file in files:
            if file.endswith('.md'):
                file_path = os.path.join(root, file).replace('\\', '/')
                try:
                    recipe_data = parse_markdown_file(file_path, category_map[category], uuid_mapping, image_mapping, base_path)
                    recipes_by_category[category].append(recipe_data)
                except Exception as e:
                    print(f"解析文件 {file_path} 时出错: {e}")
    
    return recipes_by_category
