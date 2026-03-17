import re

def has_valid_prefix(text: str) -> bool:
    t = re.sub(r"[^a-zA-Z0-9 ]+", " ", text).lower().strip()
    tokens = t.split()
    head = " ".join(tokens[:3])
    if "hi chetan" in head:
        return True
    return False
