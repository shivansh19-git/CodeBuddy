from parser import parse_query_params

def test_parse_query_params():
    assert parse_query_params('?a=1&b=2') == {'a': '1', 'b': '2'}
    assert parse_query_params('') == {}
