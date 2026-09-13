from metrics import summarize_metrics

def test_summarize_metrics_missing_errors():
    assert summarize_metrics({'count': 10, 'errors': 2}) == {'total': 10, 'errors': 2, 'rate': 0.2}
    assert summarize_metrics({'count': 5, 'errors': 0}) == {'total': 5, 'errors': 0, 'rate': 0.0}
