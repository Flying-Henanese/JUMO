"""
图像 RAG (检索增强生成) 模块
=================================================

本模块提供了一个处理从文档中提取的图像的框架，以支持基于文本的检索。
它实现了图像描述（Captioning）和标签（Tagging）功能，
类似于手机相册允许通过文本搜索图片的功能。

主要组件:
1.  `ImageRAGMetadata`: 用于存储图像元数据（描述、标签等）的数据结构。
2.  `ImageDescriptionInterface`: 图像描述模型的抽象接口。
3.  `LocalBLIPCaptioner`: 使用 HuggingFace Transformers 的 BLIP 模型的具体实现。
4.  `ImageRAGProcessor`: 协调图像分析的主处理器。
"""

import os
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any, Union
from dataclasses import dataclass, asdict
from PIL import Image

from loguru import logger
import torch
from transformers import pipeline

from utils.auto_device_selector import get_device

@dataclass
class ImageRAGMetadata:
    """
    Metadata for an image to support RAG retrieval.
    """
    image_path: str
    caption: str = ""
    tags: List[str] = None
    confidence: float = 0.0
    model_name: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

class ImageDescriptionInterface(ABC):
    """
    Abstract base class for image description/captioning models.
    """
    
    @abstractmethod
    def generate_description(self, image: Union[str, Image.Image]) -> str:
        """
        Generate a natural language description for the image.
        
        Args:
            image: File path or PIL Image object.
            
        Returns:
            A string description of the image.
        """
        pass

    @abstractmethod
    def generate_tags(self, image: Union[str, Image.Image], top_k: int = 5) -> List[str]:
        """
        Generate keywords/tags for the image.
        
        Args:
            image: File path or PIL Image object.
            top_k: Number of tags to return.
            
        Returns:
            List of tag strings.
        """
        pass

class LocalBLIPCaptioner(ImageDescriptionInterface):
    """
    Local implementation using the BLIP model (Salesforce/blip-image-captioning-base).
    Good balance between speed and accuracy for general image captioning.
    """
    
    DEFAULT_MODEL = "Salesforce/blip-image-captioning-base"

    def __init__(self, model_name: str = None):
        self.model_name = model_name or self.DEFAULT_MODEL
        self.device_str = get_device()
        self.device_id = 0 if "cuda" in self.device_str else -1
        self.pipeline = None
        self._load_model()

    def _load_model(self):
        try:
            logger.info(f"Loading Image Captioning model: {self.model_name} on {self.device_str}...")
            # 'image-to-text' pipeline automatically handles image preprocessing and generation
            self.pipeline = pipeline(
                "image-to-text", 
                model=self.model_name, 
                device=self.device_id
            )
            logger.info("Image Captioning model loaded successfully.")
        except Exception as e:
            logger.error(f"Failed to load model {self.model_name}: {e}")
            logger.warning("Image captioning will be unavailable.")
            self.pipeline = None

    def _load_image(self, image: Union[str, Image.Image]) -> Optional[Image.Image]:
        if isinstance(image, str):
            if not os.path.exists(image):
                logger.error(f"Image file not found: {image}")
                return None
            try:
                return Image.open(image).convert("RGB")
            except Exception as e:
                logger.error(f"Failed to open image {image}: {e}")
                return None
        elif isinstance(image, Image.Image):
            return image.convert("RGB")
        return None

    def generate_description(self, image: Union[str, Image.Image]) -> str:
        if not self.pipeline:
            return ""
        
        img_obj = self._load_image(image)
        if not img_obj:
            return ""

        try:
            # BLIP generation
            results = self.pipeline(img_obj, max_new_tokens=50)
            if results and len(results) > 0:
                text = results[0].get("generated_text", "").strip()
                return text
            return ""
        except Exception as e:
            logger.error(f"Error during caption generation: {e}")
            return ""

    def extract_tags_from_text(self, text: str, top_k: int = 5) -> List[str]:
        """
        Helper method to extract tags from text without re-running the model.
        """
        if not text:
            return []
            
        # Basic stopword list for filtering
        stopwords = {"a", "an", "the", "in", "on", "at", "of", "with", "by", "is", "are", 
                     "image", "picture", "photo", "showing", "shows", "features", "contains"}
        words = text.lower().replace(".", "").replace(",", "").split()
        
        tags = []
        seen = set()
        for w in words:
            if w not in stopwords and len(w) > 2 and w not in seen:
                tags.append(w)
                seen.add(w)
                
        return tags[:top_k]

    def generate_tags(self, image: Union[str, Image.Image], top_k: int = 5) -> List[str]:
        """
        Generates tags by extracting significant words from the caption.
        """
        description = self.generate_description(image)
        return self.extract_tags_from_text(description, top_k)

class ImageRAGProcessor:
    """
    Main processor for Image RAG tasks.
    """
    
    def __init__(self, model_backend: Optional[ImageDescriptionInterface] = None):
        """
        Initialize the processor.
        
        Args:
            model_backend: Custom backend instance. If None, loads LocalBLIPCaptioner.
        """
        if model_backend:
            self.backend = model_backend
        else:
            # Default to local BLIP model
            self.backend = LocalBLIPCaptioner()

    def process_image(self, image_path: str) -> ImageRAGMetadata:
        """
        Process a single image and return metadata.
        """
        logger.info(f"Processing image for RAG: {image_path}")
        
        caption = self.backend.generate_description(image_path)
        
        # Optimization: If backend is LocalBLIPCaptioner, use the caption directly
        # to extract tags, avoiding a second inference pass.
        if isinstance(self.backend, LocalBLIPCaptioner):
            tags = self.backend.extract_tags_from_text(caption)
        else:
            tags = self.backend.generate_tags(image_path)
        
        metadata = ImageRAGMetadata(
            image_path=image_path,
            caption=caption,
            tags=tags,
            model_name=getattr(self.backend, "model_name", "custom")
        )
        
        logger.debug(f"Generated metadata: {metadata}")
        return metadata