from opentelemetry.propagate import inject

def inject_trace():
    carrier = {}
    inject(carrier)
    return carrier