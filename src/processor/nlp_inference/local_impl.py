from typing import List, Union, Dict, Any
import numpy as np
import os
import threading
from sentence_transformers import SentenceTransformer
from .interfaces import EmbeddingClient, NERClient

DEVICE_MODE = os.getenv("DEFAULT_CUDA_DEVICE", "mps")

# 预设好NER模型的名称
MODEL_NAME = "uer/roberta-base-finetuned-cluener2020-chinese"
ENGLISH_MODEL_NAME = "elastic/distilbert-base-cased-finetuned-conll03-english"

def _is_chinese_text(text: str) -> bool:
    """
    简单的中文文本检测
    """
    if not text:
        return False
    for char in text:
        if '\u4e00' <= char <= '\u9fff':
            return True
    return False

def _reconstruct_entity_text_and_bounds(original_text: str, entity_data: Dict[str, Any]):
    """
    基于原文和 NER 输出的起止位置，重建更友好的实体文本
    """
    n = len(original_text)
    try:
        start = max(0, int(entity_data.get('start', 0)))
        end = min(n, int(entity_data.get('end', 0)))
    except Exception:
        start, end = 0, 0
    if start >= end:
        start, end = 0, 0

    def is_letter(ch: str) -> bool:
        allowed = "-_.&'’"
        return ch.isascii() and (ch.isalnum() or ch in allowed)

    left, right = start, end
    while left > 0 and is_letter(original_text[left - 1]):
        left -= 1
    while right < n and is_letter(original_text[right]):
        right += 1

    full_text = original_text[left:right].strip() if left < right else ""
    if not full_text:
        fallback = entity_data.get('raw_entity') or entity_data.get('entity') or entity_data.get('word') or ""
        full_text = str(fallback)

    full_text = full_text.replace("##", "")
    if _is_chinese_text(full_text):
        full_text = full_text.replace(" ", "")

    return full_text, left, right

@parameterized_singleton(lambda model_name: model_name)
class SingletonNERModel:
    """
    使用单例模式的命名实体识别模型
    """
    def __init__(self, model_name: str = MODEL_NAME, device: Optional[str] = None):
        self.model_name: str = model_name
        self.device: str = self._get_optimal_device(device)
        self.tokenizer: Optional[PreTrainedTokenizerBase] = None
        self.model: Optional[PreTrainedModel] = None
        self.ner_pipeline: Optional[Pipeline] = None
        self._load_model()
    
    def _get_optimal_device(self, device: Optional[str] = None) -> str:
        if device:
            return device
        device_mode = os.getenv("DEVICE_MODE", "auto").split(":")[0].lower()
        if device_mode == "auto":
            if hasattr(torch, 'cuda') and torch.cuda.is_available(): # robust check
                device = "cuda"
            elif hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
                device = "mps"
            elif hasattr(torch, 'npu') and torch.npu.is_available():
                device = "npu"
            else:
                device = "cpu"
        else:
            device = device_mode if device_mode in ["mps", "cuda", "npu", "cpu"] else "cpu"
        return device
    
    def _load_model(self):
        try:
            logger.info(f"正在加载NER模型: {self.model_name}")
            self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
            self.model = AutoModelForTokenClassification.from_pretrained(self.model_name)
            if self.device != "cpu":
                try:
                    self.model = self.model.to(self.device)
                except Exception as e:
                    logger.warning(f"无法将模型移动到 {self.device}，回退到CPU: {e}")
                    self.device = "cpu"
            self.ner_pipeline = pipeline(
                "ner", model=self.model, tokenizer=self.tokenizer, 
                device=0 if self.device == "cuda" else -1, 
                aggregation_strategy="simple"
            )
            logger.info("NER模型加载完成")
        except Exception as e:
            logger.error(f"加载NER模型失败: {e}")
            raise
    
    def extract_entities(self, text: str, confidence_threshold: float = 0.7, 
                        return_objects: bool = False, entity_num: int = 5) -> List[Dict[str, Any]]:
        if not text or not text.strip():
            return []
        original_text = text.strip()
        text = original_text[:500] # Truncate for safety
        
        try:
            raw_entities = self.ner_pipeline(text)
            filtered_entities = [e for e in raw_entities if e.get('score', 0) >= confidence_threshold]
            
            entities = []
            for entity_data in filtered_entities:
                clean_text, left, right = _reconstruct_entity_text_and_bounds(original_text, entity_data)
                
                entity_dict = {
                    'entity_group': entity_data.get('entity_group', 'UNKNOWN'),
                    'entity': clean_text,
                    'score': round(entity_data.get('score', 0), 4),
                    'start': left,
                    'end': right
                }

                if return_objects:
                    # Use Entity.from_dict logic or constructor
                    entities.append(Entity(
                        entity_group=entity_dict['entity_group'],
                        entity_text=entity_dict['entity'],
                        score=entity_dict['score'],
                        start=entity_dict['start'],
                        end=entity_dict['end']
                    ))
                else:
                    entities.append(entity_dict)
            
            # Sort and deduplicate
            key_func = lambda x: x.score if return_objects else x['score']
            entities.sort(key=key_func, reverse=True)
            
            unique_entities = OrderedDict()
            for entity in entities:
                key = (entity.entity_group, entity.entity_text) if return_objects else (entity['entity_group'], entity['entity'])
                if key not in unique_entities:
                    unique_entities[key] = entity
                if len(unique_entities) >= entity_num:
                    break
            return list(unique_entities.values())
            
        except Exception as e:
            logger.error(f"实体识别失败: {e}")
            return []
        

class SingletonSentenceTransformer:
    """
    使用单例模式确保全程只创建一个 SentenceTransformer 实例。
    """
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, model_id='BAAI/bge-small-zh-v1.5', mirror=True, device=DEVICE_MODE):
        if cls._instance is None:
            with cls._lock:
                print(f"正在通过{os.getenv('HF_ENDPOINT')}加载模型：{model_id}（mirror={mirror}）,device={device}")
                cls._instance = SentenceTransformer(model_id, device=f'{DEVICE_MODE}')
                print("模型加载完成。")
        return cls._instance


class LocalNERClient(NERClient):
    """
    Local implementation of NERClient using Transformers Pipeline.
    自动选择中英文模型
    """
    def __init__(self):
        # Initialize both models
        self.chinese_model = SingletonNERModel(MODEL_NAME)
        self.english_model = SingletonNERModel(ENGLISH_MODEL_NAME)

    def extract_entities(self, 
                        text: str, 
                        confidence_threshold: float = 0.7, 
                        return_objects: bool = False, 
                        entity_num: int = 5) -> List[Union[Dict[str, Any], Any]]:
        # Detect language
        if _is_chinese_text(text):
            model = self.chinese_model
        else:
            model = self.english_model
            
        return model.extract_entities(
            text=text,
            confidence_threshold=confidence_threshold,
            return_objects=return_objects,
            entity_num=entity_num
        )