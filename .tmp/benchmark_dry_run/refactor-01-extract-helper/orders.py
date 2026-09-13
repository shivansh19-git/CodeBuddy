def calculate_order_total(items, discount_pct=0.0, tax_rate=0.05):
    subtotal = sum(i['price'] * i['qty'] for i in items)
    discounted = subtotal * (1.0 - discount_pct)
    total = discounted * (1.0 + tax_rate)
    return round(total, 2)
