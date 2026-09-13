from nested import flatten_nested_list

def test_flatten_nested_list():
    assert flatten_nested_list([1, [2, [3, 4]], 5]) == [1, 2, 3, 4, 5]
