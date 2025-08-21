import os
import shutil
import requests
from urllib.parse import urlparse
import config
import uuid
from PIL import Image


def copy_image_to_recipes(image_path: str, image_mapping: dict) -> str:
    """
    将图片复制到recipes文件夹下，并返回新路径
    支持本地图片和网络图片
    """
    if not image_path:
        return None
    
    new_path = get_new_image(image_path, image_mapping)
    
    # 返回相对于项目根目录的路径
    return config.CDNPath + os.path.relpath(new_path, os.getcwd()).replace('\\', '/')


def get_new_image(image_path: str, image_mapping: dict) -> str:
    """
    获取转移、压缩图片的到StaticImagesPath目录下
    """
    new_path = ""
    if image_path in image_mapping:
        new_path = image_mapping[image_path]
    else:
        # 从旧路径提取文件名
        filename = os.path.basename(image_path)
        # 提取扩展名
        ext = os.path.splitext(image_path)[1]
        # 如果是网络图片且没有扩展名，尝试从URL获取扩展名
        if not ext and image_path.startswith(('http://', 'https://')):
            # 尝试从URL获取扩展名
            parsed_url = urlparse(image_path)
            path = parsed_url.path
            ext = os.path.splitext(path)[1]
        
        # 如果仍然没有扩展名，使用默认的.webp
        if not ext:
            ext = '.webp'
        # 生成新文件名
        new_filename = f"{uuid.uuid4()}{ext}"
        new_path = os.path.join(config.StaticImagesPath, new_filename).replace('\\', '/')
    
    # 判断是本地图片还是网络图片
    if image_path.startswith(('http://', 'https://')):
        # 下载网络图片
        try:
            response = requests.get(image_path, timeout=30)
            response.raise_for_status()
            # 确保目标目录存在
            os.makedirs(os.path.dirname(new_path), exist_ok=True)
            with open(new_path, 'wb') as f:
                f.write(response.content)
        except Exception as e:
            print(f"下载图片 {image_path} 时出错: {e}")
            return image_path  # 如果下载失败，返回原路径
    else:
        # 复制本地文件
        try:
            # 确保目标目录存在
            os.makedirs(os.path.dirname(new_path), exist_ok=True)
            shutil.copy2(image_path, new_path)
        except Exception as e:
            print(f"复制图片 {image_path} 时出错: {e}")
            return image_path  # 如果复制失败，返回原路径
    
    # 压缩图片
    try:
        with Image.open(new_path) as img:
            # 如果图片模式是RGBA且要保存为JPEG，需要转换为RGB
            if img.mode == 'RGBA' and new_path.lower().endswith('.jpg'):
                img = img.convert('RGB')
            
            # 获取文件名和扩展名
            filename, ext = os.path.splitext(new_path)
            
            # 如果是JPEG或PNG格式，转换为WebP格式以减小文件大小
            if ext.lower() in ['.jpg', '.jpeg', '.png']:
                webp_path = filename + '.webp'
                img.save(webp_path, 'webp', optimize=True, quality=85)
                # 删除原文件
                os.remove(new_path)
                # 更新new_path为WebP文件路径
                new_path = webp_path
            else:
                # 对于其他格式，使用原有的压缩方式
                img.save(new_path, optimize=True, quality=85)
    except Exception as e:
        print(f"压缩图片 {new_path} 时出错: {e}")
    
    image_mapping[image_path] = new_path
    return new_path