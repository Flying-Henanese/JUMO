"""
Image RAG (Retrieval-Augmented Generation) Module
=================================================

This module provides a framework for processing images extracted from documents
to support text-based retrieval. It implements image captioning and tagging
capabilities, similar to how mobile photo galleries allow searching images by text.

Key Components:
1.  `ImageRAGMetadata`: Data structure for storing image metadata (caption, tags, etc.).
2.  `ImageDescriptionInterface`: Abstract interface for captioning models.
3.  `LocalBLIPCaptioner`: Concrete implementation using the BLIP model via HuggingFace Transformers.
4.  `ImageRAGProcessor`: Main processor that orchestrates the image analysis.
"""

import os
# os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any, Union
from dataclasses import dataclass, asdict
from PIL import Image

from loguru import logger
import torch
from transformers import pipeline, AutoProcessor, AutoModelForCausalLM

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

    def to_markdown(self, include_image: bool = True) -> str:
        """
        Format metadata as a Markdown block suitable for RAG ingestion.
        """
        md_lines = []
        if include_image:
            md_lines.append(f"![Image]({self.image_path})")
        
        # Use blockquote to group metadata semantically with the image
        md_lines.append(f"> **Image Description**: {self.caption}")
        if self.tags:
            md_lines.append(f"> **Tags**: {', '.join(self.tags)}")
        
        return "\n".join(md_lines)

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

class Florence2Backend(ImageDescriptionInterface):
    """
    Backend using Microsoft Florence-2 model.
    Superior for detailed captioning, OCR, and object detection.
    """
    DEFAULT_MODEL = "microsoft/Florence-2-base"

    def __init__(self, model_name: str = None):
        self.model_name = model_name or self.DEFAULT_MODEL
        self.device_str = get_device()
        # Florence-2 works best with fp16 on CUDA, float32 on CPU/MPS
        self.torch_dtype = torch.float16 if "cuda" in self.device_str else torch.float32
        self.model = None
        self.processor = None
        self._load_model()

    def _load_model(self):
        try:
            logger.info(f"Loading Florence-2 model: {self.model_name} on {self.device_str}...")
            self.model = AutoModelForCausalLM.from_pretrained(
                self.model_name, 
                torch_dtype=self.torch_dtype, 
                trust_remote_code=True,
                attn_implementation="eager"
            ).to(self.device_str)
            self.processor = AutoProcessor.from_pretrained(self.model_name, trust_remote_code=True)
            logger.info("Florence-2 model loaded successfully.")
        except Exception as e:
            logger.error(f"Failed to load Florence-2 model {self.model_name}: {e}")
            self.model = None

    def _load_image(self, image: Union[str, Image.Image]) -> Optional[Image.Image]:
        if isinstance(image, str):
            if not os.path.exists(image):
                return None
            try:
                return Image.open(image).convert("RGB")
            except Exception:
                return None
        elif isinstance(image, Image.Image):
            return image.convert("RGB")
        return None

    def generate_description(self, image: Union[str, Image.Image]) -> str:
        if not self.model or not self.processor:
            return ""
        
        img_obj = self._load_image(image)
        if not img_obj:
            return ""

        try:
            # Use MORE_DETAILED_CAPTION for rich context suitable for RAG
            prompt = "<CAPTION>"
            inputs = self.processor(text=prompt, images=img_obj, return_tensors="pt")
            inputs = {k: v.to(self.device_str, self.torch_dtype) if v.dtype == torch.float else v.to(self.device_str) for k, v in inputs.items()}

            generated_ids = self.model.generate(
                input_ids=inputs["input_ids"],
                pixel_values=inputs["pixel_values"],
                max_new_tokens=1024,
                do_sample=False,
                num_beams=3,
                use_cache=False,  # Fix for 'Cache only has 0 layers' error with newer transformers
            )
            generated_text = self.processor.batch_decode(generated_ids, skip_special_tokens=False)[0]
            
            parsed_answer = self.processor.post_process_generation(
                generated_text, 
                task=prompt, 
                image_size=(img_obj.width, img_obj.height)
            )
            return parsed_answer.get(prompt, "")
        except Exception as e:
            logger.error(f"Error in Florence-2 generation: {e}")
            return ""

    def generate_tags(self, image: Union[str, Image.Image], top_k: int = 5) -> List[str]:
        """
        Generate tags using a hybrid approach:
        1. Phrase Grounding: Extract key entities from the caption.
        2. Object Detection: Identify specific objects in the image.
        """
        if not self.model or not self.processor:
            return []

        img_obj = self._load_image(image)
        if not img_obj:
            return []

        tags = set()
        
        try:
            # 1. Generate Caption first
            description = self.generate_description(image)
            
            # 2. Use Caption to Phrase Grounding to extract entities
            # This task finds the bounding boxes for phrases in the caption, effectively acting as an entity extractor
            prompt_grounding = "<CAPTION_TO_PHRASE_GROUNDING>"
            # Combine task prompt with the description for grounding
            full_prompt = prompt_grounding + description
            
            inputs = self.processor(text=full_prompt, images=img_obj, return_tensors="pt")
            inputs = {k: v.to(self.device_str, self.torch_dtype) if v.dtype == torch.float else v.to(self.device_str) for k, v in inputs.items()}
            
            generated_ids = self.model.generate(
                input_ids=inputs["input_ids"],
                pixel_values=inputs["pixel_values"],
                max_new_tokens=1024,
                do_sample=False,
                num_beams=3,
                use_cache=False,
            )
            generated_text = self.processor.batch_decode(generated_ids, skip_special_tokens=False)[0]
            parsed_grounding = self.processor.post_process_generation(
                generated_text, 
                task=prompt_grounding, 
                image_size=(img_obj.width, img_obj.height)
            )
            
            # Extract labels from grounding result: {'<CAPTION_TO_PHRASE_GROUNDING>': {'bboxes': [...], 'labels': ['General Consultant', 'table']}}
            grounding_result = parsed_grounding.get(prompt_grounding, {})
            if grounding_result and 'labels' in grounding_result:
                for label in grounding_result['labels']:
                    # Clean label
                    clean_label = label.lower().strip()
                    if len(clean_label) > 2:
                        tags.add(clean_label)

            # 3. Object Detection (OD) for concrete objects
            prompt_od = "<OD>"
            inputs_od = self.processor(text=prompt_od, images=img_obj, return_tensors="pt")
            inputs_od = {k: v.to(self.device_str, self.torch_dtype) if v.dtype == torch.float else v.to(self.device_str) for k, v in inputs_od.items()}
            
            generated_ids_od = self.model.generate(
                input_ids=inputs_od["input_ids"],
                pixel_values=inputs_od["pixel_values"],
                max_new_tokens=1024,
                do_sample=False,
                num_beams=3,
                use_cache=False,
            )
            generated_text_od = self.processor.batch_decode(generated_ids_od, skip_special_tokens=False)[0]
            parsed_od = self.processor.post_process_generation(
                generated_text_od, 
                task=prompt_od, 
                image_size=(img_obj.width, img_obj.height)
            )
            
            od_result = parsed_od.get(prompt_od, {})
            if od_result and 'labels' in od_result:
                for label in od_result['labels']:
                    tags.add(label.lower().strip())
                    
        except Exception as e:
            logger.error(f"Error generating tags with Florence-2: {e}")
            # Fallback to simple text extraction if complex tasks fail
            return self.extract_tags_from_text(description, top_k)

        # 4. Filter and Rank
        # Convert to list and filter generic stop words again just in case
        valid_tags = list(tags)
        # Sort by length (longer phrases often more specific) or keep as is
        valid_tags.sort(key=len, reverse=True)
        
        return valid_tags[:top_k]

    def extract_tags_from_text(self, text: str, top_k: int = 5) -> List[str]:
        # Use the same logic as LocalBLIPCaptioner (could be refactored to a mixin)
        if not text: return []
        stopwords = {
            "a", "an", "the", "in", "on", "at", "of", "with", "by", "is", "are", "was", "were",
            "image", "picture", "photo", "showing", "shows", "features", "contains", "depicts",
            "background", "foreground", "view", "seen", "visible", "located", "placed",
            "left", "right", "top", "bottom", "center", "corner", "side",
            "and", "or", "but", "for", "to", "from", "up", "down"
        }
        import string
        translator = str.maketrans('', '', string.punctuation)
        clean_text = text.lower().translate(translator)
        words = clean_text.split()
        tags = []
        seen = set()
        for w in words:
            if w not in stopwords and len(w) > 2 and w not in seen:
                tags.append(w)
                seen.add(w)
        return tags[:top_k]

class CLIPTaggingBackend(ImageDescriptionInterface):
    """
    Backend using OpenAI CLIP for Zero-Shot Image Classification.
    This mimics 'Gallery Search' behavior by matching images against a fixed set of concepts.
    """
    DEFAULT_MODEL = "openai/clip-vit-base-patch32"
    
    # Comprehensive list of tags relevant for Documents + General Photos
    DEFAULT_CANDIDATES = [
        # Document Types
        "chart", "diagram", "flowchart", "table", "spreadsheet", "invoice", "receipt", 
        "report", "document", "screenshot", "user interface", "webpage", "code snippet",
        "handwriting", "signature", "logo", "infographic", "presentation slide",
        # General Content
        "person", "people", "crowd", "man", "woman", "face",
        "computer", "laptop", "phone", "keyboard", "screen",
        "scenery", "landscape", "building", "office", "meeting room",
        "cat", "dog", "animal", "plant", "flower", "food",
        "vehicle", "car", "train", "plane"
    ]

    def __init__(self, model_name: str = None, candidate_labels: List[str] = None):
        self.model_name = model_name or self.DEFAULT_MODEL
        self.device_str = get_device()
        self.device_id = 0 if "cuda" in self.device_str else -1
        self.candidate_labels = candidate_labels or self.DEFAULT_CANDIDATES
        self.pipeline = None
        self._load_model()

    def _load_model(self):
        try:
            logger.info(f"Loading CLIP model: {self.model_name}...")
            self.pipeline = pipeline(
                "zero-shot-image-classification", 
                model=self.model_name, 
                device=self.device_id
            )
            logger.info("CLIP model loaded successfully.")
        except Exception as e:
            logger.error(f"Failed to load CLIP model: {e}")

    def generate_description(self, image: Union[str, Image.Image]) -> str:
        # CLIP isn't a captioner, but we can fake it by joining top tags
        tags = self.generate_tags(image, top_k=3)
        if tags:
            return f"Image classified as: {', '.join(tags)}"
        return "Image classification failed."

    def generate_tags(self, image: Union[str, Image.Image], top_k: int = 5) -> List[str]:
        if not self.pipeline:
            return []
        
        # Load image if string
        if isinstance(image, str):
            try:
                image = Image.open(image).convert("RGB")
            except Exception:
                return []
        
        try:
            results = self.pipeline(images=image, candidate_labels=self.candidate_labels)
            # Results format: [{'score': 0.99, 'label': 'cat'}, ...]
            # Sort by score just in case, though pipeline usually sorts
            sorted_res = sorted(results, key=lambda x: x['score'], reverse=True)
            
            # Filter by confidence threshold (e.g., > 0.05) to avoid noise
            tags = [res['label'] for res in sorted_res if res['score'] > 0.05]
            return tags[:top_k]
        except Exception as e:
            logger.error(f"CLIP tagging failed: {e}")
            return []

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
            
        # Expanded stopword list
        stopwords = {
            "a", "an", "the", "in", "on", "at", "of", "with", "by", "is", "are", "was", "were",
            "image", "picture", "photo", "showing", "shows", "features", "contains", "depicts",
            "background", "foreground", "view", "seen", "visible", "located", "placed",
            "left", "right", "top", "bottom", "center", "corner", "side",
            "and", "or", "but", "for", "to", "from", "up", "down"
        }
        
        # Clean and tokenize
        import string
        translator = str.maketrans('', '', string.punctuation)
        clean_text = text.lower().translate(translator)
        words = clean_text.split()
        
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

if __name__ == "__main__":
    import sys
    
    # Configure logging for standalone execution
    logger.remove()
    logger.add(sys.stderr, level="INFO")
    
    # Hardcoded test image path
    test_image_path = "tests/test_resource/test_image.jpg"
    
    if os.path.exists(test_image_path):
        print(f"Processing test image: {test_image_path}")
        # Use Florence-2 backend
        processor = ImageRAGProcessor(model_backend=Florence2Backend())
        try:
            result = processor.process_image(test_image_path)
            print("\n=== Result ===")
            print(f"Caption: {result.caption}")
            print(f"Tags: {result.tags}")
            print(f"Model: {result.model_name}")
            print("==============")
        except Exception as e:
            logger.error(f"Processing failed: {e}")
    else:
        print(f"Test image not found at: {test_image_path}")
        print("\nRunning a mock test instead...")
        
        # Mock test if no image provided
        class MockBackend(ImageDescriptionInterface):
            def generate_description(self, image: Union[str, Image.Image]) -> str:
                return "A mock description of a test image showing a cat."
            
            def generate_tags(self, image: Union[str, Image.Image], top_k: int = 5) -> List[str]:
                return ["cat", "test", "mock"]
                
        mock_processor = ImageRAGProcessor(model_backend=MockBackend())
        mock_result = mock_processor.process_image("dummy_path.jpg")
        
        print("\n=== Mock Result ===")
        print(f"Caption: {mock_result.caption}")
        print(f"Tags: {mock_result.tags}")
        print("===================")