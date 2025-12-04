"""
Sentence-BERT Embedding Wrapper with Caching

Uses the all-MiniLM-L6-v2 model for fast, high-quality sentence embeddings.
Embeddings are cached to disk for training efficiency.
"""

import os
import hashlib
import pickle
from pathlib import Path
from typing import List, Union, Optional

import numpy as np
from sentence_transformers import SentenceTransformer


class EmbeddingModel:
    """
    Wrapper for Sentence-BERT embeddings with optional caching.
    
    Uses all-MiniLM-L6-v2 which produces 384-dimensional embeddings.
    This model offers a good balance of speed and quality for command classification.
    """
    
    MODEL_NAME = "all-MiniLM-L6-v2"
    EMBEDDING_DIM = 384
    
    def __init__(
        self,
        cache_dir: Optional[str] = None,
        use_cache: bool = True,
        device: Optional[str] = None
    ):
        """
        Initialize the embedding model.
        
        Args:
            cache_dir: Directory to store cached embeddings. Defaults to ./cache/embeddings
            use_cache: Whether to use caching for embeddings
            device: Device to run model on ('cpu', 'cuda', or None for auto)
        """
        self.model = SentenceTransformer(self.MODEL_NAME, device=device)
        self.use_cache = use_cache
        
        if cache_dir is None:
            cache_dir = Path(__file__).parent.parent / "cache" / "embeddings"
        self.cache_dir = Path(cache_dir)
        
        if self.use_cache:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            self._cache = self._load_cache()
        else:
            self._cache = {}
    
    def _get_cache_path(self) -> Path:
        """Get the path to the cache file."""
        return self.cache_dir / f"{self.MODEL_NAME.replace('/', '_')}_cache.pkl"
    
    def _load_cache(self) -> dict:
        """Load the embedding cache from disk."""
        cache_path = self._get_cache_path()
        if cache_path.exists():
            try:
                with open(cache_path, "rb") as f:
                    return pickle.load(f)
            except Exception as e:
                print(f"Warning: Could not load cache: {e}")
                return {}
        return {}
    
    def _save_cache(self):
        """Save the embedding cache to disk."""
        if not self.use_cache:
            return
        cache_path = self._get_cache_path()
        try:
            with open(cache_path, "wb") as f:
                pickle.dump(self._cache, f)
        except Exception as e:
            print(f"Warning: Could not save cache: {e}")
    
    def _get_text_hash(self, text: str) -> str:
        """Generate a hash key for a text string."""
        return hashlib.md5(text.encode()).hexdigest()
    
    def encode(
        self,
        texts: Union[str, List[str]],
        batch_size: int = 32,
        show_progress: bool = False
    ) -> np.ndarray:
        """
        Encode text(s) into embeddings.
        
        Args:
            texts: Single text string or list of texts to encode
            batch_size: Batch size for encoding multiple texts
            show_progress: Whether to show a progress bar
            
        Returns:
            numpy array of shape (n_texts, 384) containing embeddings
        """
        # Handle single text input
        if isinstance(texts, str):
            texts = [texts]
            single_input = True
        else:
            single_input = False
        
        embeddings = []
        texts_to_encode = []
        text_indices = []
        
        # Check cache for each text
        for i, text in enumerate(texts):
            text_hash = self._get_text_hash(text)
            if self.use_cache and text_hash in self._cache:
                embeddings.append((i, self._cache[text_hash]))
            else:
                texts_to_encode.append(text)
                text_indices.append(i)
        
        # Encode uncached texts
        if texts_to_encode:
            new_embeddings = self.model.encode(
                texts_to_encode,
                batch_size=batch_size,
                show_progress_bar=show_progress,
                convert_to_numpy=True
            )
            
            # Cache and collect new embeddings
            for text, embedding, idx in zip(texts_to_encode, new_embeddings, text_indices):
                text_hash = self._get_text_hash(text)
                self._cache[text_hash] = embedding
                embeddings.append((idx, embedding))
            
            # Save updated cache
            self._save_cache()
        
        # Sort embeddings by original index and stack
        embeddings.sort(key=lambda x: x[0])
        result = np.stack([emb for _, emb in embeddings])
        
        if single_input:
            return result[0]
        return result
    
    def clear_cache(self):
        """Clear the embedding cache."""
        self._cache = {}
        cache_path = self._get_cache_path()
        if cache_path.exists():
            cache_path.unlink()
    
    @property
    def embedding_dim(self) -> int:
        """Return the embedding dimension."""
        return self.EMBEDDING_DIM


# Convenience function for quick embedding
_default_model = None

def get_embeddings(
    texts: Union[str, List[str]],
    use_cache: bool = True
) -> np.ndarray:
    """
    Convenience function to get embeddings using a shared model instance.
    
    Args:
        texts: Text or list of texts to encode
        use_cache: Whether to use caching
        
    Returns:
        numpy array of embeddings
    """
    global _default_model
    if _default_model is None:
        _default_model = EmbeddingModel(use_cache=use_cache)
    return _default_model.encode(texts)

