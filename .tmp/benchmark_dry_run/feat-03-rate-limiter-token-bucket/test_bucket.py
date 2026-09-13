from bucket import TokenBucket

def test_token_bucket():
    tb = TokenBucket(5)
    assert tb.consume(3) is True
    assert tb.consume(3) is False
    assert tb.consume(2) is True
    assert tb.consume(1) is False
