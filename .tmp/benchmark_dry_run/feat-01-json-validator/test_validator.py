from validator import validate_user_payload

def test_validate_user_payload():
    assert validate_user_payload({'id': 1, 'username': 'alice', 'email': 'a@example.com'}) is True
    assert validate_user_payload({'id': 1, 'username': 'alice'}) is False
    assert validate_user_payload({}) is False
