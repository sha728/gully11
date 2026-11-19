"""Shared helper for XI tests: a legal draft from a set of spins."""

from gully_api.xi.service import _fills


def auto_draft(spins: list[dict], max_overseas: int | None = None) -> tuple[list[str], list[int]]:
    """A legal XI: match spins to batting positions (keeper at 6), then take the
    best unused candidate who fits each spin's position (at most ``max_overseas``
    non-Indians when given). Returns (picks in spin order, slot of each pick)."""
    spin_in: dict[int, int] = {}

    def place(i: int, seen: set[int]) -> bool:
        options = set().union(*(_fills(c) for c in spins[i]["candidates"]))
        for slot in sorted(options):
            if slot not in seen:
                seen.add(slot)
                if slot not in spin_in or place(spin_in[slot], seen):
                    spin_in[slot] = i
                    return True
        return False

    assert all(place(i, set()) for i in range(len(spins))), "spins can't fill every slot"
    slot_of = {i: slot for slot, i in spin_in.items()}

    picks: list[dict] = []
    used: set[str] = set()
    overseas = 0
    for i, spin in enumerate(spins):
        for c in spin["candidates"]:
            foreign = bool(c.get("country")) and c["country"] != "India"
            if (c["person"] in used or slot_of[i] not in _fills(c)
                    or (max_overseas is not None and foreign and overseas >= max_overseas)):
                continue
            picks.append(c)
            used.add(c["person"])
            overseas += foreign
            break
        else:
            raise AssertionError(f"no candidate for spin {i + 1} at slot {slot_of[i]}")
    return [p["id"] for p in picks], [slot_of[i] for i in range(len(spins))]
