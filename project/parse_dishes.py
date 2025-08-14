import os
import json
import re
from typing import List, Dict, Any, Tuple
from pathlib import Path

from image_handler import copy_image_to_dishes
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
    复制图片到dishes文件夹并更新路径
    """
    if image_path:
        image_path = copy_image_to_dishes(image_path, image_mapping)
    
    if images:
        images = [copy_image_to_dishes(img, image_mapping) for img in images]
    
    return image_path, images


def _build_source_path(file_path: str, base_path: str) -> str:
    """
    构建源路径
    """
    return os.path.relpath(file_path, base_path).replace('\\', '/')


def _extract_with_unstructured(file_path: str) -> Dict[str, Any]:
    """
    使用 LangChain-Unstructured 库解析 Markdown 文件并提取结构化数据
    """
    # 加载文档
    loader = UnstructuredLoader(file_path, mode="elements", post_processors=[])
    docs = loader.load()
    
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
    
    # 处理提取的元素
    current_section = None
    step_counter = 1
    
    for doc in docs:
        # 提取标题
        if doc.metadata.get("category") == "Title":
            title = doc.page_content.replace('的做法', '')
            # 如果标题为空，则使用文件名作为标题
            if not title.strip():
                title = os.path.basename(file_path).replace('.md', '')
            extracted_data["title"] = title
        
        # 提取难度
        elif "预估烹饪难度" in doc.page_content and doc.metadata.get("category") == "NarrativeText":
            difficulty_match = re.search(r'预估烹饪难度：(★+)', doc.page_content)
            if difficulty_match:
                extracted_data["difficulty"] = len(difficulty_match.group(1))
        
        # 提取时间信息
        elif ("预估准备时间" in doc.page_content or "预估烹饪时间" in doc.page_content or 
              "预估总时间" in doc.page_content) and doc.metadata.get("category") == "NarrativeText":
            prep_time, cook_time, total_time = _extract_times(doc.page_content)
            extracted_data["prep_time"] = prep_time
            extracted_data["cook_time"] = cook_time
            extracted_data["total_time"] = total_time
        
        # 识别章节标题
        elif doc.metadata.get("category") == "Header":
            if "必备原料和工具" in doc.page_content:
                current_section = "ingredients"
            elif "操作" in doc.page_content:
                current_section = "steps"
            elif "计算" in doc.page_content:
                current_section = "ingredients"  # 计算部分也属于原料
            elif "参考资料" in doc.page_content or "附加内容" in doc.page_content:
                current_section = "additional_notes"
            else:
                current_section = None
        
        # 提取原料
        elif current_section == "ingredients" and doc.metadata.get("category") == "ListItem":
            # 解析原料文本，提取名称、数量和单位
            ingredient_name, quantity, unit = parse_ingredient_text(doc.page_content)
            extracted_data["ingredients"].append({
                "name": ingredient_name,
                "quantity": quantity,
                "unit": unit,
                "text_quantity": doc.page_content,
                "notes": "量未指定" if quantity is None else ""
            })
        
        # 提取步骤
        elif current_section == "steps" and doc.metadata.get("category") == "ListItem":
            extracted_data["steps"].append({
                "step": step_counter,
                "description": doc.page_content
            })
            step_counter += 1
        
        # 提取图片
        elif doc.metadata.get("category") == "Image":
            image_path = doc.metadata.get("image_path")
            if image_path:
                # 转换为绝对路径
                if not image_path.startswith('http'):
                    abs_path = os.path.join(os.path.dirname(file_path), image_path).replace('\\', '/')
                    extracted_data["images"].append(abs_path)
                else:
                    extracted_data["images"].append(image_path)
        
        # 提取参考资料
        elif current_section == "additional_notes" and doc.metadata.get("category") in ["NarrativeText", "ListItem"]:
            extracted_data["additional_notes"].append(doc.page_content)
    
    # 去重图片
    extracted_data["images"] = list(dict.fromkeys(extracted_data["images"]))
    
    return extracted_data


def parse_markdown_file(file_path: str, category: str, uuid_mapping: dict, image_mapping: dict, base_path: str) -> Dict[str, Any]:
    """
    解析菜谱Markdown文件并提取信息
    """
    # 使用 LangChain-Unstructured 库解析文件
    extracted_data = _extract_with_unstructured(file_path)
    
    # 提取描述
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    description = _extract_description(content, extracted_data["title"])
    
    # 提取图片链接
    images = extracted_data["images"]
    
    # 设置主图路径
    image_path = _extract_main_image(content, description, images, file_path)
    
    # 处理图片
    image_path, images = _process_images(image_path, images, image_mapping)
    
    return {
        "id": _extract_dish_id(file_path, uuid_mapping),
        "name": extracted_data["title"],
        "description": description,
        "source_path": _build_source_path(file_path, base_path),
        "image_path": image_path,
        "images": images,
        "category": category,
        "difficulty": extracted_data["difficulty"],
        "tags": [category],
        "servings": 1,
        "ingredients": extracted_data["ingredients"],
        "steps": extracted_data["steps"],
        "prep_time_minutes": extracted_data["prep_time"],
        "cook_time_minutes": extracted_data["cook_time"],
        "total_time_minutes": extracted_data["total_time"],
        "additional_notes": extracted_data["additional_notes"]
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
