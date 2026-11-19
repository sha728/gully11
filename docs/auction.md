# Auction (Milestone 5, first cut)

Mega-auction rooms with live bidding over a WebSocket, AI franchises, and a player
pool built from our own data. Mini mode (the real IPL 2026 auction from Wikipedia,
with retained squads) is the next PR; the season simulation is Milestone 6.

## Rules (`api/src/gully_api/auction/rules.json`)

| Rule | Value | Source |
| --- | --- | --- |
| Purse | ₹120 cr | IPL Player Regulations 2025–27 (2025 figure) |
| Squad | 18–25 | Regulations |
| Overseas | 8 at most | Regulations |
| Bid steps | ₹5 L under ₹1 cr, ₹10 L to ₹2 cr, ₹20 L to ₹5 cr, ₹25 L above | Published increment slabs (Sportstar, 2025 mega auction) |
| Base prices | ₹30 L–₹2 cr slabs; uncapped at most ₹50 L, capped at least ₹75 L | Slabs from the regulations; assignment is ours |

Every bid is checked on the server: not already leading, squad not full, overseas
cap, and enough purse left to fill the rest of the 18 at ₹30 L each.

## Pool and fair prices (`pool.py`)

Everyone who played the IPL in 2024–2026. Value = batting and bowling from the last
three seasons of T20s plus a third of the career, each scored against specialists in
that skill and shrunk toward an ordinary player on small samples, plus IPL and T20I
experience. Fair price = value rank on a curve from ₹20 cr, calibrated so a full set
of 21-man squads is worth about 92% of the room's money. Pool size scales with the
number of franchises (25 per team + 20). Afghanistan's players (no Cricsheet
country) are filled in by hand in `nationality.csv`.

This is a stats estimate, not trained on auction history; the planned price model
replaces `values()` once a licensed price history exists.

## Room flow (`room.py`, `live.py`)

Lobby (host plus friends with the code; empty seats become bots) → marquee sets,
then capped batters, all-rounders, keepers, fast bowlers, spinners in turn, then
uncapped → accelerated round (unsold players again, shorter clock) → summary.

- The server owns the clock (`ends_at` plus `server_now` in every state message).
- **Pass:** once every connected human has passed or can't bid, bots settle the lot at
  once. A friend who has closed the tab counts as passed.
- **Bots** bid up to fair price × role need × richness (purse per open slot) ×
  personality × noise, capped at 1.4× fair plus richness, never breaking the reserve.
  In all-bot runs on the real pool: top prices about ₹25–27 cr, most teams spend
  ₹95–120 cr, squads 18–25.

Rooms live in the API process (a restart ends them); finished auctions are saved to
`auction_rooms`. Several API processes would need the room state in Redis.
