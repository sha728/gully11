"""A draft in progress, held on the server so future spins stay hidden.

The browser only ever sees spins it has revealed. Every pick and move is checked
here against all eleven spins (can the rest of the XI still be filled?), and the
answer is all that goes back: which slots a candidate may take, where a player may
move. No candidate, era or side from an unrevealed spin leaves the server.
"""

from __future__ import annotations

from .service import (FORMATS, FULL_MEMBERS, KEEPER_SLOT, MAX_OVERSEAS_IPL, SLOTS, DraftError, _units)

Board = list  # 11 entries, candidate dict or None, index = slot - 1
OVERSEAS = lambda c: bool(c.get("country")) and c["country"] != "India"  # noqa: E731


def preference(c: dict) -> list[int]:
    """Where a fresh pick goes by default: openers open, keepers keep, bowlers bowl."""
    by_role = {"WK": [6, 3, 4, 5], "BAT": [3, 4, 5, 6], "AR": [7, 8, 3, 4, 5, 6, 9, 10, 11],
               "BOWL": [9, 10, 11, 7, 8] if c.get("spinner") else [9, 10, 11]}
    order = ([1, 2] if c.get("opener") else []) + by_role[c["role"]]
    return [s for s in dict.fromkeys(order) if s in c["slots"]]


def fits(c: dict, slot: int, board: Board) -> bool:
    """Can ``c`` bat at ``slot``? Slot 6 is the keeper's unless a keeper bats higher."""
    if slot not in c["slots"]:
        return False
    if slot != KEEPER_SLOT or c["role"] == "WK":
        return True
    return any(p and p["role"] == "WK" and i + 1 < KEEPER_SLOT and p["id"] != c["id"]
               for i, p in enumerate(board))


def completable(board: Board, pending: list[dict], used: set[str]) -> bool:
    """Can the spins still without a pick cover every empty slot? Bipartite matching."""
    keeper_above = any(p and p["role"] == "WK" and i + 1 < KEEPER_SLOT for i, p in enumerate(board))
    empty = [i + 1 for i, p in enumerate(board) if p is None]
    if len(empty) < len(pending):
        return False
    options = [[s for s in empty if any(
        c["person"] not in used and s in c["slots"]
        and (s != KEEPER_SLOT or c["role"] == "WK" or keeper_above) for c in spin["candidates"])]
        for spin in pending]
    owner: dict[int, int] = {}

    def place(i: int, seen: set[int]) -> bool:
        for s in options[i]:
            if s not in seen:
                seen.add(s)
                if s not in owner or place(owner[s], seen):
                    owner[s] = i
                    return True
        return False

    return all(place(i, set()) for i in range(len(pending)))


class Draft:
    """Board logic over (spins, picks). ``picks[i]`` is {"id", "slot"} or None."""

    def __init__(self, fmt: str, spins: list[dict], picks: list[dict | None], revealed: int):
        self.fmt, self.spins, self.revealed = fmt, spins, revealed
        # A pick whose player is no longer on the list (data reloaded) is dropped.
        self.rows = [next((c for c in spins[i]["candidates"] if c["id"] == p["id"]), None) if p else None
                     for i, p in enumerate(picks)]
        self.picks = [p if r else None for p, r in zip(picks, self.rows)]

    def board(self) -> Board:
        out: Board = [None] * 11
        for i, p in enumerate(self.picks):
            if p:
                out[p["slot"] - 1] = self.rows[i]
        return out

    def _pending(self, picks: list[dict | None]) -> list[dict]:
        return [s for s, p in zip(self.spins, picks) if p is None]

    @property
    def waiting(self) -> bool:
        """A revealed spin still needs a pick before the next spin."""
        return any(p is None for p in self.picks[: self.revealed])

    # -------------------------------------------------------------- picking

    def options(self, i: int, c: dict) -> tuple[list[int], str | None]:
        """Slots ``c`` (from spin ``i``) could take now, in preference order, or why none."""
        others = [p for j, p in enumerate(self.picks) if j != i and p]
        others_rows = [r for j, r in enumerate(self.rows) if j != i and r]
        if any(r["person"] == c["person"] for r in others_rows):
            return [], "Already in your XI"
        if (self.fmt == "IPL" and OVERSEAS(c)
                and sum(map(OVERSEAS, others_rows)) >= MAX_OVERSEAS_IPL):
            return [], "Overseas limit reached"
        taken = {p["slot"] for p in others}
        used = {r["person"] for r in others_rows} | {c["person"]}
        current = self.picks[i]["slot"] if self.picks[i] else None
        order = ([current] if current else []) + preference(c) + c["slots"]
        out = []
        for slot in dict.fromkeys(order):
            if slot in taken:
                continue
            trial = list(self.picks)
            trial[i] = {"id": c["id"], "slot": slot}
            board = self._trial_board(trial, i, c)
            if fits(c, slot, board) and completable(board, self._pending(trial), used):
                out.append(slot)
        if not out:
            return [], "No room for this role in your XI" if c["slots"] else "Can't bat anywhere"
        return out, None

    def _trial_board(self, picks: list[dict | None], i: int, c: dict) -> Board:
        out: Board = [None] * 11
        for j, p in enumerate(picks):
            if p:
                out[p["slot"] - 1] = c if j == i else self.rows[j]
        return out

    def pick(self, i: int, pid: str, slot: int | None) -> list[dict | None]:
        if not 0 <= i < self.revealed:
            raise DraftError("That spin hasn't been revealed yet.")
        c = next((x for x in self.spins[i]["candidates"] if x["id"] == pid), None)
        if c is None:
            raise DraftError("That player isn't on this spin's list.")
        options, why = self.options(i, c)
        if why:
            raise DraftError(why)
        if slot is not None and slot not in options:
            raise DraftError(f"{c['name']} can't bat at {slot} without leaving your XI impossible to finish.")
        out = list(self.picks)
        out[i] = {"id": pid, "slot": slot or options[0]}
        return out

    def remove(self, i: int) -> list[dict | None]:
        if not 0 <= i < len(self.picks) or self.picks[i] is None:
            raise DraftError("Nothing picked from that spin.")
        out = list(self.picks)
        out[i] = None
        return out

    # -------------------------------------------------------------- moving

    def moved(self, src: int, dst: int) -> list[dict | None] | None:
        """Picks after moving the player at slot ``src`` to ``dst`` (swapping if
        occupied), or None if that breaks a rule or strands the remaining spins."""
        if src == dst:
            return None
        a = next((i for i, p in enumerate(self.picks) if p and p["slot"] == src), None)
        if a is None:
            return None
        b = next((i for i, p in enumerate(self.picks) if p and p["slot"] == dst), None)
        out = list(self.picks)
        out[a] = {**out[a], "slot": dst}
        if b is not None:
            out[b] = {**out[b], "slot": src}
        board: Board = [None] * 11
        for j, p in enumerate(out):
            if p:
                board[p["slot"] - 1] = self.rows[j]
        if not all(p is None or fits(p, k + 1, board) for k, p in enumerate(board)):
            return None
        used = {r["person"] for r in self.rows if r}
        return out if completable(board, self._pending(out), used) else None

    def move(self, src: int, dst: int) -> list[dict | None]:
        out = self.moved(src, dst)
        if out is None:
            raise DraftError("That move would break the batting-order rules.")
        return out

    # -------------------------------------------------------------- status

    def status(self) -> dict:
        board = self.board()
        chosen = [r for r in self.rows if r]
        overseas = sum(map(OVERSEAS, chosen))
        keeper_top6 = any(p and p["role"] == "WK" for p in board[:KEEPER_SLOT])
        all_fit = all(p is None or fits(p, k + 1, board) for k, p in enumerate(board))
        ready = (len(chosen) == 11 and keeper_top6 and all_fit
                 and (self.fmt != "IPL" or overseas <= MAX_OVERSEAS_IPL))
        return {"picked": len(chosen), "openers": sum(1 for p in board[:2] if p),
                "keeper_top6": keeper_top6, "overseas": overseas if self.fmt == "IPL" else None,
                "ready": ready}

    def view(self) -> dict:
        """What the browser may see: revealed spins (candidates with their legal
        slots), the batting order with legal move targets, and the rules."""
        board = self.board()
        spins = []
        for i, s in enumerate(self.spins[: self.revealed]):
            cands = []
            for c in s["candidates"]:
                options, why = self.options(i, c)
                cands.append({**{k: v for k, v in c.items() if k != "value"}, "options": options, "why": why})
            spins.append({"spin": s["spin"], "era": s["era"], "side": s["side"], "candidates": cands,
                          "pick": self.picks[i]})
        lineup = []
        for pos in SLOTS:
            p = board[pos["slot"] - 1]
            i = next((j for j, x in enumerate(self.picks) if x and x["slot"] == pos["slot"]), None)
            lineup.append({**pos, "spin": i + 1 if i is not None else None,
                           "player": {k: v for k, v in p.items() if k != "value"} if p else None,
                           "targets": [t for t in range(1, 12) if p and self.moved(pos["slot"], t)]})
        return {"revealed": self.revealed, "total": len(self.spins), "spins": spins, "lineup": lineup,
                "can_spin": self.revealed < len(self.spins) and not self.waiting,
                "waiting": self.waiting, "status": self.status()}


def reel(conn, fmt: str) -> dict:
    """Labels the spin animation cycles through: every era and side in the format,
    nothing about the draw itself."""
    sides = FULL_MEMBERS if FORMATS[fmt].unit == "nation" else _units(conn, fmt)
    return {"eras": list(FORMATS[fmt].eras), "sides": sides}
