from calculator import calculate_average

def test_calculate_average():
    assert calculate_average([10, 20, 30]) == 20.0
    assert calculate_average([]) == 0.0
