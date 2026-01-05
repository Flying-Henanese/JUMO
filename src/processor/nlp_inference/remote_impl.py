from typing import List, Union, Dict, Any, Optional
import os
import requests
from loguru import logger
from .interfaces import EmbeddingClient, NERClient
from ..named_entity_recognition import Entity

class RemoteEmbeddingClient(EmbeddingClient):
    def __init__(self, service_url: Optional[str] = None):
        self.service_url = service_url or os.getenv("EMBEDDING_SERVICE_URL", "http://localhost:8000/encode")
        logger.info(f"Initialized RemoteEmbeddingClient with URL: {self.service_url}")

    def encode(self, sentences: Union[str, List[str]], **kwargs) -> Union[List[float], List[List[float]]]:
        if isinstance(sentences, str):
            sentences = [sentences]
        
        try:
            response = requests.post(
                self.service_url,
                json={"texts": sentences},
                timeout=30
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to call Embedding service at {self.service_url}: {e}")
            raise

class RemoteNERClient(NERClient):
    def __init__(self, service_url: Optional[str] = None):
        self.service_url = service_url or os.getenv("NER_SERVICE_URL", "http://localhost:8000/extract")
        logger.info(f"Initialized RemoteNERClient with URL: {self.service_url}")

    def extract_entities(self, text: str, confidence_threshold: float = 0.7, 
                        return_objects: bool = False, entity_num: int = 5) -> List[Union[Dict[str, Any], Any]]:
        
        payload = {
            "text": text,
            "confidence_threshold": confidence_threshold,
            "return_objects": return_objects,
            "entity_num": entity_num
        }
        
        try:
            response = requests.post(
                self.service_url,
                json=payload,
                timeout=30
            )
            response.raise_for_status()
            result_dicts = response.json()
            
            if return_objects:
                entities = []
                for entity_dict in result_dicts:
                    entities.append(Entity(
                        entity_group=entity_dict.get('entity_group'),
                        entity_text=entity_dict.get('entity'),
                        score=entity_dict.get('score'),
                        start=entity_dict.get('start'),
                        end=entity_dict.get('end')
                    ))
                return entities
            return result_dicts
            
        except Exception as e:
            logger.error(f"Failed to call NER service at {self.service_url}: {e}")
            return []