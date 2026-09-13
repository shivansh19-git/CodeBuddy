from lru import SimpleLRUCache

def test_lru_cache():
    cache = SimpleLRUCache(2)
    cache.put(1, 'A')
    cache.put(2, 'B')
    assert cache.get(1) == 'A'
    cache.put(3, 'C')
    assert cache.get(2) == -1
    assert cache.get(3) == 'C'
