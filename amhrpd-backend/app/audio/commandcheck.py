import re
import difflib

GRAMMAR_WORDS = {"is","am","are","the","a","an"}
POLITE_WORDS = {"please","kindly","can","you"}

COMMAND_KEYWORDS = {
    "forward": "MOVE_FORWARD",
    "backward": "MOVE_BACKWARD",
    "left": "TURN_LEFT",
    "right": "TURN_RIGHT",
    "stop": "STOP",
    "resetposition": "resetposition",
    "handsup": "handsup",
    "headleft": "headleft",
    "headright": "headright",
    "headup": "headup",
    "headdown": "headdown",
}

MIN_CONFIDENCE = 0.78
MAX_FUZZY_TOKEN_LEN = 10

def normalize(text: str) -> str:
    return re.sub(r"[^a-zA-Z0-9 ]+", " ", text).lower().strip()

def filter_tokens(text: str) -> list[str]:
    tokens = normalize(text).split()
    filtered = [t for t in tokens if t not in GRAMMAR_WORDS and t not in POLITE_WORDS]
    if len(filtered) >= 2:
        for i in range(len(filtered) - 1):
            filtered.append(f"{filtered[i]}{filtered[i + 1]}")
    return filtered

def match_command(text: str) -> tuple[str | None, float]:
    tokens = filter_tokens(text)
    if not tokens:
        return None, 0.0
    indexed = list(enumerate(tokens))
    bigrams = [(i, tokens[i] + tokens[i + 1]) for i in range(len(tokens) - 1)]
    for idx, t in indexed:
        if idx <= 1 and t in COMMAND_KEYWORDS:
            return COMMAND_KEYWORDS[t], 1.0
    for idx, t in bigrams:
        if idx <= 1 and t in COMMAND_KEYWORDS:
            return COMMAND_KEYWORDS[t], 1.0
    candidates = [(idx, t) for idx, t in indexed if idx <= 1] + [(idx, t) for idx, t in bigrams if idx <= 1]
    best = None
    score = 0.0
    for _, t in candidates:
        if len(t) > MAX_FUZZY_TOKEN_LEN:
            continue
        for k, cmd in COMMAND_KEYWORDS.items():
            s = difflib.SequenceMatcher(None, t, k).ratio()
            if s > score:
                score = s
                best = cmd
    if score < MIN_CONFIDENCE:
        return None, score
    return best, score
