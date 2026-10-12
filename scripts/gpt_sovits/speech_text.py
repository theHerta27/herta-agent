"""Bound decoder input without losing sentence punctuation or trailing text."""
import re


def speech_chunks(text):
    chunks, start = [], 0
    while start < len(text):
        end = min(start + 120, len(text))
        if end < len(text):
            boundaries = list(re.finditer(r"[。？！!?；;\n]", text[start:end]))
            if boundaries and boundaries[-1].start() >= 40:
                end = start + boundaries[-1].end()
        chunks.append(text[start:end])
        start = end
    return chunks
