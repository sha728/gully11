"""Shared helper for XI tests: a legal draft from a set of spins."""


def auto_draft(spins: list[dict], max_overseas: int | None = None) -> list[str]:
    """Pick one candidate per spin, highest value first, while reserving slots so
    the XI ends with a keeper and five bowling options (and at most
    ``max_overseas`` non-Indians when given)."""
    picks: list[dict | None] = [None] * len(spins)
    used: set[str] = set()

    def take(i, pred):
        for c in spins[i]["candidates"]:
            if c["person"] not in used and pred(c) and overseas_ok(c):
                picks[i] = c
                used.add(c["person"])
                return True
        return False

    def overseas_ok(c):
        if max_overseas is None or not c.get("country") or c["country"] == "India":
            return True
        return sum(1 for p in picks if p and p.get("country") and p["country"] != "India") < max_overseas

    # keeper first, then five bowling options, then best available everywhere else
    for i in range(len(spins)):
        if take(i, lambda c: c["role"] == "WK"):
            break
    need = 5
    for i in range(len(spins)):
        if need and picks[i] is None and take(i, lambda c: c["role"] in ("BOWL", "AR")):
            need -= 1
    for i in range(len(spins)):
        if picks[i] is None:
            take(i, lambda c: True)
    return [p["id"] for p in picks]
