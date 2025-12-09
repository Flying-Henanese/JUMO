from abc import ABC, abstractmethod
from typing import List, Dict, Any, Union, Optional
import numpy as np

class EmbeddingClient(ABC):
    """
    Abstract base class for Embedding clients.
    Can be implemented by local models (SentenceTransformer) or remote services (Infinity/TEI).
    """
    
    @abstractmethod
    def encode(self, sentences: Union[str, List[str]], **kwargs) -> Union[List[float], List[List[float]], np.ndarray]:
        """
        Encode sentences into embeddings.
        
        Args:
            sentences: A single sentence or a list of sentences.
            **kwargs: Additional arguments for the underlying model.
            
        Returns:
            Embeddings as a list of floats, list of list of floats, or numpy array.
        """
        pass

class NERClient(ABC):
    """
    Abstract base class for Named Entity Recognition clients.
    Can be implemented by local models (Transformers Pipeline) or remote services (Triton/FastAPI).
    """
    
    @abstractmethod
    def extract_entities(self, 
                        text: str, 
                        confidence_threshold: float = 0.7, 
                        return_objects: bool = False, 
                        entity_num: int = 5) -> List[Union[Dict[str, Any], Any]]:
        """
        Extract entities from text.
        
        Args:
            text: Input text.
            confidence_threshold: Confidence threshold for filtering entities.
            return_objects: Whether to return Entity objects (if supported) or dictionaries.
            entity_num: Maximum number of entities to return.
            
        Returns:
            List of entities (dicts or objects).
        """
        pass