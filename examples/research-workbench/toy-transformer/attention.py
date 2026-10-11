"""Original scalar-attention teaching example, NOT a Transformer reproduction."""
from math import exp


def scalar_attention(query, keys, values, temperature=1.0):
    if not keys or len(keys) != len(values) or temperature <= 0:
        raise ValueError("Nonempty matching keys/values and positive temperature required")
    scores = [query * key / temperature for key in keys]
    maximum = max(scores)
    weights = [exp(score - maximum) for score in scores]
    total = sum(weights)
    weights = [weight / total for weight in weights]
    return {"weights": weights, "output": sum(w * v for w, v in zip(weights, values))}
