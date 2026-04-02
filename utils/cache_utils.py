import hashlib
import json
import diskcache
from pathlib import Path
from utils.config import CACHE_DIR

class PersistentCache:
    """A simple disk-based cache for expensive LLM/Embedding calls."""
    
    def __init__(self, namespace: str):
        cache_path = CACHE_DIR / namespace
        cache_path.mkdir(parents=True, exist_ok=True)
        self.cache = diskcache.Cache(str(cache_path))
        
    def _make_key(self, data: any) -> str:
        """Create a stable hash key for any JSON-serializable data."""
        s = json.dumps(data, sort_keys=True)
        return hashlib.sha256(s.encode()).hexdigest()
        
    def get(self, key_data: any):
        key = self._make_key(key_data)
        return self.cache.get(key)
        
    def set(self, key_data: any, value: any, expire: int = 86400 * 7):
        """Default expiry: 7 days."""
        key = self._make_key(key_data)
        self.cache.set(key, value, expire=expire)
        
    def close(self):
        self.cache.close()

# Shared instances
embedding_cache = PersistentCache("embeddings")
expansion_cache = PersistentCache("expansions")
