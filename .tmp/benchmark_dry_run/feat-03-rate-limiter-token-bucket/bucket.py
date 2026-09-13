class TokenBucket:
    def __init__(self, capacity: int):
        self.capacity = capacity
        self.tokens = capacity

    def consume(self, count: int = 1) -> bool:
        if self.tokens >= count:
            self.tokens -= count
            return True
        return False
