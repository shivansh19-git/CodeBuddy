from orders import calculate_order_total

def test_calculate_order_total():
    items = [{'price': 100, 'qty': 2}, {'price': 50, 'qty': 1}]
    assert calculate_order_total(items, discount_pct=0.1, tax_rate=0.1) == 247.5
    assert calculate_order_total(items) == 262.5
