from collections import defaultdict
import json

_metrics = defaultdict()
_error_dict = json.dumps({"result": 0})

def init():
    _metrics["total_requests"] = 0
    _metrics["period_requests"] = 0
    _metrics["total_error_requests"] = 0
    _metrics["period_error_requests"] = 0

def get(k):
    return _metrics[k]

def reset(k):
    _metrics[k] = 0

def collect(func):
    def wrapper( *a, **k ):
        _metrics["total_requests"] += 1
        _metrics["period_requests"] += 1

        d = func( *a, **k )

        if d == _error_dict:
            _metrics["total_error_requests"] +=1
            _metrics["period_error_requests"] += 1

        return d

    return wrapper
