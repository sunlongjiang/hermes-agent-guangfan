# evolution/sdk/runtime.py — temporary stub for Task 4; Task 5 implements full trace capture.
"""Runtime module — invokes wrapped agent methods. Task 5 will add trace capture + optimized loading."""


def invoke(instance, method_name, original_fn, args, kwargs):
    """Stub: call the original method untouched. Task 5 replaces this with trace capture."""
    return original_fn(instance, *args, **kwargs)
