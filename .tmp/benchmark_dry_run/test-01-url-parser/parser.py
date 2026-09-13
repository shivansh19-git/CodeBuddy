def parse_query_params(query_string: str) -> dict[str, str]:
    if not query_string:
        return {}
    if query_string.startswith('?'):
        query_string = query_string[1:]
    res = {}
    for pair in query_string.split('&'):
        if '=' in pair:
            k, v = pair.split('=', 1)
            res[k] = v
    return res
