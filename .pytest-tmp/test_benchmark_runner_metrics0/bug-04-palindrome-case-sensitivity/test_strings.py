from strings import is_palindrome

def test_palindrome():
    assert is_palindrome('Racecar') is True
    assert is_palindrome('A man, a plan, a canal: Panama') is True
    assert is_palindrome('hello') is False
