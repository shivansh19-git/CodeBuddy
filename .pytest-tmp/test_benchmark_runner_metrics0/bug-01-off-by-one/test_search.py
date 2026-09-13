from search import binary_search

def test_binary_search_bounds():
    nums = [1, 3, 5, 7, 9]
    assert binary_search(nums, 9) == 4
    assert binary_search(nums, 1) == 0
    assert binary_search(nums, 5) == 2
    assert binary_search(nums, 4) == -1
