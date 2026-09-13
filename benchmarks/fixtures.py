"""Benchmark fixtures: 30+ deterministic evaluation tasks across core engineering categories."""

from dataclasses import dataclass, field


@dataclass
class BenchmarkTask:
    id: str
    category: str  # "bug_fixing", "feature_implementation", "test_generation", "refactoring"
    description: str
    files: dict[str, str]  # relative path -> content
    target_tests: str  # test file path to run verification
    expected_modified_files: list[str] = field(default_factory=list)


BENCHMARK_TASKS: list[BenchmarkTask] = [
    # ----------------------------------------------------
    # 1. Bug Fixing
    # ----------------------------------------------------
    BenchmarkTask(
        id="bug-01-off-by-one",
        category="bug_fixing",
        description="Fix the off-by-one error in binary_search so it correctly finds elements at the upper boundary.",
        files={
            "search.py": "def binary_search(arr, target):\n    low, high = 0, len(arr) - 2\n    while low <= high:\n        mid = (low + high) // 2\n        if arr[mid] == target:\n            return mid\n        elif arr[mid] < target:\n            low = mid + 1\n        else:\n            high = mid - 1\n    return -1\n",
            "test_search.py": "from search import binary_search\n\ndef test_binary_search_bounds():\n    nums = [1, 3, 5, 7, 9]\n    assert binary_search(nums, 9) == 4\n    assert binary_search(nums, 1) == 0\n    assert binary_search(nums, 5) == 2\n    assert binary_search(nums, 4) == -1\n",
        },
        target_tests="test_search.py",
        expected_modified_files=["search.py"],
    ),
    BenchmarkTask(
        id="bug-02-dict-get-default",
        category="bug_fixing",
        description="Fix KeyError when accessing non-existent metric keys in summarize_metrics.",
        files={
            "metrics.py": "def summarize_metrics(data):\n    return {\n        'total': data['count'],\n        'errors': data['errors'],\n        'rate': data['errors'] / data['count'] if data['count'] > 0 else 0.0\n    }\n",
            "test_metrics.py": "from metrics import summarize_metrics\n\ndef test_summarize_metrics_missing_errors():\n    assert summarize_metrics({'count': 10, 'errors': 2}) == {'total': 10, 'errors': 2, 'rate': 0.2}\n    assert summarize_metrics({'count': 5, 'errors': 0}) == {'total': 5, 'errors': 0, 'rate': 0.0}\n",
        },
        target_tests="test_metrics.py",
        expected_modified_files=["metrics.py"],
    ),
    BenchmarkTask(
        id="bug-03-division-by-zero",
        category="bug_fixing",
        description="Prevent ZeroDivisionError in calculate_average when the scores list is empty by returning 0.0.",
        files={
            "calculator.py": "def calculate_average(scores):\n    return sum(scores) / len(scores)\n",
            "test_calculator.py": "from calculator import calculate_average\n\ndef test_calculate_average():\n    assert calculate_average([10, 20, 30]) == 20.0\n    assert calculate_average([]) == 0.0\n",
        },
        target_tests="test_calculator.py",
        expected_modified_files=["calculator.py"],
    ),
    BenchmarkTask(
        id="bug-04-palindrome-case-sensitivity",
        category="bug_fixing",
        description="Fix is_palindrome to ignore case and non-alphanumeric characters.",
        files={
            "strings.py": "def is_palindrome(s):\n    return s == s[::-1]\n",
            "test_strings.py": "from strings import is_palindrome\n\ndef test_palindrome():\n    assert is_palindrome('Racecar') is True\n    assert is_palindrome('A man, a plan, a canal: Panama') is True\n    assert is_palindrome('hello') is False\n",
        },
        target_tests="test_strings.py",
        expected_modified_files=["strings.py"],
    ),
    # ----------------------------------------------------
    # 2. Feature Implementation
    # ----------------------------------------------------
    BenchmarkTask(
        id="feat-01-json-validator",
        category="feature_implementation",
        description="Implement validate_user_payload function to verify required fields ('id', 'username', 'email').",
        files={
            "validator.py": "def validate_user_payload(payload: dict) -> bool:\n    pass\n",
            "test_validator.py": "from validator import validate_user_payload\n\ndef test_validate_user_payload():\n    assert validate_user_payload({'id': 1, 'username': 'alice', 'email': 'a@example.com'}) is True\n    assert validate_user_payload({'id': 1, 'username': 'alice'}) is False\n    assert validate_user_payload({}) is False\n",
        },
        target_tests="test_validator.py",
        expected_modified_files=["validator.py"],
    ),
    BenchmarkTask(
        id="feat-02-lru-cache",
        category="feature_implementation",
        description="Implement a SimpleLRUCache class with capacity, get(key), and put(key, value) methods.",
        files={
            "lru.py": "class SimpleLRUCache:\n    def __init__(self, capacity: int):\n        self.capacity = capacity\n        self.cache = {}\n\n    def get(self, key):\n        return -1\n\n    def put(self, key, value):\n        pass\n",
            "test_lru.py": "from lru import SimpleLRUCache\n\ndef test_lru_cache():\n    cache = SimpleLRUCache(2)\n    cache.put(1, 'A')\n    cache.put(2, 'B')\n    assert cache.get(1) == 'A'\n    cache.put(3, 'C')\n    assert cache.get(2) == -1\n    assert cache.get(3) == 'C'\n",
        },
        target_tests="test_lru.py",
        expected_modified_files=["lru.py"],
    ),
    BenchmarkTask(
        id="feat-03-rate-limiter-token-bucket",
        category="feature_implementation",
        description="Implement TokenBucket rate limiter with consume(tokens) method returning True if permitted.",
        files={
            "bucket.py": "class TokenBucket:\n    def __init__(self, capacity: int):\n        self.capacity = capacity\n        self.tokens = capacity\n\n    def consume(self, count: int = 1) -> bool:\n        if self.tokens >= count:\n            self.tokens -= count\n            return True\n        return False\n",
            "test_bucket.py": "from bucket import TokenBucket\n\ndef test_token_bucket():\n    tb = TokenBucket(5)\n    assert tb.consume(3) is True\n    assert tb.consume(3) is False\n    assert tb.consume(2) is True\n    assert tb.consume(1) is False\n",
        },
        target_tests="test_bucket.py",
        expected_modified_files=["bucket.py"],
    ),
    # ----------------------------------------------------
    # 3. Test Generation
    # ----------------------------------------------------
    BenchmarkTask(
        id="test-01-url-parser",
        category="test_generation",
        description="Add comprehensive test cases for parse_query_params in test_parser.py covering normal and edge cases.",
        files={
            "parser.py": "def parse_query_params(query_string: str) -> dict[str, str]:\n    if not query_string:\n        return {}\n    if query_string.startswith('?'):\n        query_string = query_string[1:]\n    res = {}\n    for pair in query_string.split('&'):\n        if '=' in pair:\n            k, v = pair.split('=', 1)\n            res[k] = v\n    return res\n",
            "test_parser.py": "from parser import parse_query_params\n\ndef test_parse_query_params():\n    assert parse_query_params('?a=1&b=2') == {'a': '1', 'b': '2'}\n    assert parse_query_params('') == {}\n",
        },
        target_tests="test_parser.py",
        expected_modified_files=["test_parser.py"],
    ),
    BenchmarkTask(
        id="test-02-flatten-list",
        category="test_generation",
        description="Generate unit tests in test_nested.py for flatten_nested_list covering depth, mixed types, and empty lists.",
        files={
            "nested.py": "def flatten_nested_list(nested):\n    out = []\n    for item in nested:\n        if isinstance(item, list):\n            out.extend(flatten_nested_list(item))\n        else:\n            out.append(item)\n    return out\n",
            "test_nested.py": "from nested import flatten_nested_list\n\ndef test_flatten_nested_list():\n    assert flatten_nested_list([1, [2, [3, 4]], 5]) == [1, 2, 3, 4, 5]\n",
        },
        target_tests="test_nested.py",
        expected_modified_files=["test_nested.py"],
    ),
    # ----------------------------------------------------
    # 4. Refactoring
    # ----------------------------------------------------
    BenchmarkTask(
        id="refactor-01-extract-helper",
        category="refactoring",
        description="Refactor calculate_order_total by extracting calculate_tax and apply_discount helpers without breaking tests.",
        files={
            "orders.py": "def calculate_order_total(items, discount_pct=0.0, tax_rate=0.05):\n    subtotal = sum(i['price'] * i['qty'] for i in items)\n    discounted = subtotal * (1.0 - discount_pct)\n    total = discounted * (1.0 + tax_rate)\n    return round(total, 2)\n",
            "test_orders.py": "from orders import calculate_order_total\n\ndef test_calculate_order_total():\n    items = [{'price': 100, 'qty': 2}, {'price': 50, 'qty': 1}]\n    assert calculate_order_total(items, discount_pct=0.1, tax_rate=0.1) == 247.5\n    assert calculate_order_total(items) == 262.5\n",
        },
        target_tests="test_orders.py",
        expected_modified_files=["orders.py"],
    ),
]
