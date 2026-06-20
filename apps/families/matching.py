from difflib import SequenceMatcher


def similarity(left, right):
    left = (left or "").strip().lower()
    right = (right or "").strip().lower()
    if not left or not right:
        return 0
    return SequenceMatcher(None, left, right).ratio()
