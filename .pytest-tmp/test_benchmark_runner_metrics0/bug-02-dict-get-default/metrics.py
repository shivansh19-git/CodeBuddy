def summarize_metrics(data):
    return {
        'total': data['count'],
        'errors': data['errors'],
        'rate': data['errors'] / data['count'] if data['count'] > 0 else 0.0
    }
