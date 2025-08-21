import os
import json
import re
from typing import List, Dict, Any, Tuple
from pathlib import Path

from image_handler import copy_image_to_recipes
from langchain_unstructured import UnstructuredLoader


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
        elif in_description:
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


def _build_source_path(file_path: str, base_path: str) -> str:
    """
    构建源路径
    """
    return os.path.relpath(file_path, base_path).replace('\\', '/')


def _extract_with_unstructured(file_path: str) -> Dict[str, Any]:
    """
    使用正则表达式解析 Markdown 文件并提取结构化数据
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 初始化提取的数据
    extracted_data = {
        "title": "",
        "description": "",
        "difficulty": 0,
        "ingredients": [],
        "steps": [],
        "prep_time": None,
        "cook_time": None,
        "total_time": None,
        "images": [],
        "additional_notes": []
    }
    
    # 提取标题
    title_match = re.search(r'^#\s+([^\n]+)', content)
    if title_match:
        title = title_match.group(1).replace('的做法', '').strip()
        extracted_data["title"] = title
    else:
        # 如果没有找到标题，使用文件名
        extracted_data["title"] = os.path.basename(file_path).replace('.md', '')
    
    # 提取难度
    difficulty_match = re.search(r'预估烹饪难度：([★]+)', content)
    if difficulty_match:
        extracted_data["difficulty"] = len(difficulty_match.group(1))
    
    # 提取时间信息
    prep_time, cook_time, total_time = _extract_times(content)
    extracted_data["prep_time"] = prep_time
    extracted_data["cook_time"] = cook_time
    extracted_data["total_time"] = total_time
    
    # 提取图片
    image_matches = re.findall(r'!\[([^\]]*)\]\(([^)]+)\)', content)
    images_with_positions = []
    for i, (alt, path) in enumerate(image_matches):
        if not path.startswith('http'):
            abs_path = os.path.join(os.path.dirname(file_path), path).replace('\\', '/')
            extracted_data["images"].append(abs_path)
            images_with_positions.append({"path": abs_path, "alt": alt})
        else:
            extracted_data["images"].append(path)
            images_with_positions.append({"path": path, "alt": alt})
    
    # 提取原料
    ingredients_section = re.search(r'##\s+必备原料和工具\s+([\s\S]*?)(?=##|$)', content)
    if ingredients_section:
        ingredients_text = ingredients_section.group(1)
        # 提取列表项
        ingredients = re.findall(r'^\s*-\s+(.+)$', ingredients_text, re.MULTILINE)
        for ingredient in ingredients:
            ingredient_name, quantity, unit = parse_ingredient_text(ingredient)
            extracted_data["ingredients"].append({
                "name": ingredient_name,
                "quantity": quantity,
                "unit": unit,
                "text_quantity": ingredient,
                "notes": "量未指定" if quantity is None else ""
            })
    
    # 提取计算部分的原料
    calculation_section = re.search(r'##\s+计算\s+([\s\S]*?)(?=##|$)', content)
    if calculation_section:
        calculation_text = calculation_section.group(1)
        # 提取列表项
        calculated_ingredients = re.findall(r'^\s*-\s+(.+)$', calculation_text, re.MULTILINE)
        for ingredient in calculated_ingredients:
            ingredient_name, quantity, unit = parse_ingredient_text(ingredient)
            extracted_data["ingredients"].append({
                "name": ingredient_name,
                "quantity": quantity,
                "unit": unit,
                "text_quantity": ingredient,
                "notes": "量未指定" if quantity is None else ""
            })
    
    # 提取步骤
    # 首先尝试查找"## 操作"或"## 步骤"部分
    steps_section = re.search(r'##\s+(操作|步骤)\s+([\s\S]*?)(?=##|$)', content)
    if steps_section:
        steps_text = steps_section.group(2)  # 使用group(2)获取步骤内容
    else:
        # 如果没有找到明确的步骤部分，使用整个文档内容
        steps_text = content
    
    # 提取标题格式的步骤 (### 标题)
    step_titles = re.findall(r'^\s*###\s+(.+)$', steps_text, re.MULTILINE)
    # 提取列表格式的步骤 (- 或 * 开头)
    list_steps = re.findall(r'^\s*[-*]\s*(.+)$', steps_text, re.MULTILINE)
    
    # 根据找到的步骤格式进行处理
    if step_titles:
        for i, step in enumerate(step_titles, 1):
            # 检查步骤中是否包含图片
            step_images = []
            for img in images_with_positions:
                # 检查图片是否在当前步骤描述中被引用
                if img["alt"] in step or img["path"].split('/')[-1] in step:
                    step_images.append(img["path"])
            
            extracted_data["steps"].append({
                "step": i,
                "description": step.strip(),
                "images": step_images
            })
    elif list_steps:
        for i, step in enumerate(list_steps, 1):
            # 检查步骤中是否包含图片
            step_images = []
            for img in images_with_positions:
                # 检查图片是否在当前步骤描述中被引用
                if img["alt"] in step or img["path"].split('/')[-1] in step:
                    step_images.append(img["path"])
            
            extracted_data["steps"].append({
                "step": i,
                "description": step.strip(),
                "images": step_images
            })
    else:
        # 如果没有找到标题格式或列表格式的步骤，再次尝试从整个文档中提取标题格式的步骤
        full_content_step_titles = re.findall(r'^\s*###\s+(.+)$', content, re.MULTILINE)
        for i, step in enumerate(full_content_step_titles, 1):
            # 检查步骤中是否包含图片
            step_images = []
            for img in images_with_positions:
                # 检查图片是否在当前步骤描述中被引用
                if img["alt"] in step or img["path"].split('/')[-1] in step:
                    step_images.append(img["path"])
            
            extracted_data["steps"].append({
                "step": i,
                "description": step.strip(),
                "images": step_images
            })
    
    # 提取附加内容
    additional_section = re.search(r'##\s+附加内容\s+([\s\S]*?)(?=##|$)', content)
    if additional_section:
        additional_text = additional_section.group(1)
        # 提取段落和图片
        paragraphs = re.findall(r'^[^-\n].*$', additional_text, re.MULTILINE)
        for paragraph in paragraphs:
            if paragraph.strip():
                # 检查段落是否包含图片
                if paragraph.strip().startswith('![') and '](' in paragraph.strip():
                    # 这是一个图片
                    extracted_data["additional_notes"].append({
                        "type": "image",
                        "content": paragraph.strip()
                    })
                else:
                    # 这是普通文本
                    extracted_data["additional_notes"].append({
                        "type": "text",
                        "content": paragraph.strip()
                    })
    
    # 提取参考资料
    references_section = re.search(r'##\s+参考资料\s+([\s\S]*?)(?=##|$)', content)
    if references_section:
        references_text = references_section.group(1)
        # 提取段落
        references = re.findall(r'^[^-\n].*$', references_text, re.MULTILINE)
        for reference in references:
            if reference.strip():
                # 检查段落是否包含图片
                if reference.strip().startswith('![') and '](' in reference.strip():
                    # 这是一个图片
                    extracted_data["additional_notes"].append({
                        "type": "image",
                        "content": reference.strip()
                    })
                else:
                    # 这是普通文本
                    extracted_data["additional_notes"].append({
                        "type": "text",
                        "content": reference.strip()
                    })
    
    # 去重图片
    extracted_data["images"] = list(dict.fromkeys(extracted_data["images"]))
    
    return extracted_data

def _process_images(images: List[str], image_mapping: dict) -> List[str]:
    """
    处理图片路径
    """
    # 处理其他图片
    processed_images = []
    for img in images:
        processed_img = copy_image_to_recipes(img, image_mapping)
        if processed_img:
            processed_images.append(processed_img)
    
    return processed_images


def parse_markdown_file(file_path: str, category: str, uuid_mapping: dict, image_mapping: dict, base_path: str) -> Dict[str, Any]:
    """
    解析菜谱Markdown文件并提取信息
    """
    # 使用 LangChain-Unstructured 库解析文件
    extracted_data = _extract_with_unstructured(file_path)
    
    # 提取图片链接
    images = extracted_data["images"]
    
    # 处理图片
    images = _process_images(images, image_mapping)
    
    # 处理步骤中的图片
    processed_steps = []
    
    # 收集所有可用的图片（主图、步骤中引用的图片、附加内容中的图片）
    all_available_images = []
    
    # 添加主图
    if image_path:
        all_available_images.append(image_path)
    
    # 添加步骤中引用的图片
    for step in extracted_data["steps"]:
        for img in step.get("images", []):
            if img not in all_available_images:
                all_available_images.append(img)
    
    # 提取附加内容中的图片路径
    additional_images = []
    for note in extracted_data["additional_notes"]:
        if note["type"] == "image":
            # 从markdown格式提取图片路径
            import re
            img_match = re.search(r'\(([^)]+)\)', note["content"])
            if img_match:
                img_path = img_match.group(1)
                additional_images.append(img_path)
                if img_path not in all_available_images:
                    all_available_images.append(img_path)
    
    # 处理步骤图片
    step_image_index = 0  # 用于跟踪分配给步骤的图片索引
    for i, step in enumerate(extracted_data["steps"]):
        # 处理步骤图片
        processed_step_images = []
        for img in step.get("images", []):
            processed_img = copy_image_to_recipes(img, image_mapping)
            if processed_img:
                processed_step_images.append(processed_img)
        
        # 如果步骤中没有明确引用图片，尝试从所有可用图片中分配图片
        if not processed_step_images and all_available_images:
            # 分配图片给步骤，优先使用主图和附加内容中的图片
            while step_image_index < len(all_available_images) and len(processed_step_images) < 1:  # 每个步骤最多分配一张图片
                img_to_assign = all_available_images[step_image_index]
                processed_img = copy_image_to_recipes(img_to_assign, image_mapping)
                if processed_img:
                    processed_step_images.append(processed_img)
                step_image_index += 1
        
        processed_steps.append({
            "step": step["step"],
            "description": step["description"],
            "images": processed_step_images
        })
    
    # 处理附加内容中的图片
    processed_additional_notes = []
    for note in extracted_data["additional_notes"]:
        if note["type"] == "image":
            # 处理图片
            # 从markdown格式提取图片路径
            import re
            img_match = re.search(r'\(([^)]+)\)', note["content"])
            if img_match:
                img_path = img_match.group(1)
                processed_img = copy_image_to_recipes(img_path, image_mapping)
                if processed_img:
                    processed_additional_notes.append({
                        "type": "image",
                        "content": processed_img
                    })
        else:
            # 保留文本内容
            processed_additional_notes.append(note)
    
    return {
        "id": _extract_dish_id(file_path, uuid_mapping),
        "name": extracted_data["title"],
        "description": extracted_data["description"],
        "source_path": _build_source_path(file_path, base_path),
        "image_path": image_path,
        "images": images,
        "category": category,
        "difficulty": extracted_data["difficulty"],
        "tags": [category],
        "servings": 1,
        "ingredients": extracted_data["ingredients"],
        "steps": processed_steps,
        "prep_time_minutes": extracted_data["prep_time"],
        "cook_time_minutes": extracted_data["cook_time"],
        "total_time_minutes": extracted_data["total_time"],
        "additional_notes": processed_additional_notes
    }


def scan_dishes_directory(directory: str, uuid_mapping: dict, image_mapping: dict, base_path: str) -> Dict[str, List[Dict[str, Any]]]:
    """
    扫描菜谱目录并按分类解析所有.md文件
    """
    dishes_by_category = {}
    
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
        dishes_by_category[category_dir] = []
    
    for root, dirs, files in os.walk(directory):
        # 获取当前目录的分类名称
        relative_root = os.path.relpath(root, directory)
        # 统一使用正斜杠处理路径
        relative_root = relative_root.replace('\\', '/')
        path_parts = relative_root.split('/')
        category = path_parts[0] if path_parts and path_parts[0] else 'unknown'
        
        # 如果分类不在预定义列表中，则跳过
        if category not in dishes_by_category:
            continue
        
        for file in files:
            if file.endswith('.md'):
                file_path = os.path.join(root, file).replace('\\', '/')
                try:
                    dishe_data = parse_markdown_file(file_path, category_map[category], uuid_mapping, image_mapping, base_path)
                    dishes_by_category[category].append(dishe_data)
                except Exception as e:
                    print(f"解析文件 {file_path} 时出错: {e}")
    
    return dishes_by_category
