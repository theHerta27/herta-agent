from collections import Counter


def summarize(text):
    words = text.split()
    return {
        "total": len(words),
        "unique": len(set(words)),
        "counts": dict(sorted(Counter(words).items())),
    }
