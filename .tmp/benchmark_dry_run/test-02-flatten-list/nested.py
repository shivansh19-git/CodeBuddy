def flatten_nested_list(nested):
    out = []
    for item in nested:
        if isinstance(item, list):
            out.extend(flatten_nested_list(item))
        else:
            out.append(item)
    return out
