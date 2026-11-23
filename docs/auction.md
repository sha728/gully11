# Auction (Milestone 5, first cut)

Auction rooms with live bidding over a WebSocket and AI franchises, in two modes:
mega (a player pool built from our own data) and mini (a replay of the real IPL
2026 auction). The season simulation is Milestone 6.

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
experience. Fair price = value rank on a curve from ₹15 cr, calibrated so a full set
of 21-man squads is worth about 92% of the room's money. Pool size scales with the
number of franchises (25 per team + 20). Afghanistan's players (no Cricsheet
country) now get one from the pipeline (Wikidata, see README "Nationality");
`nationality.csv` still pins their country and capped status for the auction.

### Is there a price model to learn? (`scripts/price_check.py`)

`gully-pipeline auction-history` reads who was sold for how much at the 2024 and
2025 auctions from Wikipedia (`ipl_auction_history.csv`, 252 sales; with the 2026
sales that is 302 with a known player). Each player is described by what was
known before that auction and a price model is fitted on two years and tested on
the third:

| Features | Share of price variance explained | Typical miss |
| --- | --- | --- |
| rank by `value` (the game today) | 19% | ×3.5 |
| `value` plus role, capped, overseas | 29% | ×3.2 |
| role, capped, overseas and the base price | 36% | ×3.0 |

Two things came out of it. Franchises pay for much that stats don't show (a
bidding war, team needs, age, who they just lost), so about two thirds of
the price stays unexplained whatever we add, and base price, which is itself the
market's guess, adds more than form does. And the fitted model is worse for the
game than the current method: regression flattens the stars (a ₹27 cr player
comes out at ₹2.6 cr), while ranking by `value` and pricing the rank on a curve
orders sold players as well as anything we tried (Spearman 0.44, 0.66 and 0.43
for the three auctions, against 0.35–0.69 for the fitted models). So fair prices
still come from `values()` and the curve, which keeps stars dear and always
adds up to the room's money; the history is here for checking them. It also shows
real auctions are far noisier than the all-bot ones in the game (bots value a
player at 0.65–1.15× fair; real prices scatter by a factor of about three).

## Room flow (`room.py`, `live.py`)

Lobby (host plus friends with the code; anyone can take a franchise held by a bot or an open seat; empty seats become bots; bot personalities stay on the server) → marquee sets,
then capped batters, all-rounders, keepers, fast bowlers, spinners in turn, then
uncapped → accelerated round (unsold players again, shorter clock) → summary.

- The server owns the clock (`ends_at` plus `server_now` in every state message).
- **Pass:** once every connected human has passed or can't bid, bots settle the lot at
  once. A friend who has closed the tab counts as passed.
- **Bots** keep a shortlist: each has its own chance of wanting each player (higher
  when short of that role, higher still when rich or behind on spending), and its own
  valuation (fair price × role need × richness × personality × a 0.65–1.15 rating),
  capped at 1.3× fair plus richness and never breaking the purse reserve. So a lot
  draws a few keen bidders, not the whole room. Personalities never leave the server.
  In all-bot runs on the real pool: marquee players ₹9–19 cr with the odd bargain,
  sales at about 0.9–1.0× fair on average, every bot spending ₹83–116 cr.

Rooms live in the API process (a restart ends them); finished auctions are saved to
`auction_rooms`. Several API processes would need the room state in Redis.

## Mini mode: the IPL 2026 auction (`mini.py`)

`gully-pipeline auction2026` reads "List of 2026 Indian Premier League personnel
changes" on Wikipedia (CC BY-SA 4.0) into `api/src/gully_api/auction/data/`:
`ipl2026_retained.csv` (173 retained players with salaries) and
`ipl2026_auction.csv` (the 77 players sold on 16 December 2025, by registration
number, with set, base price, buyer and price). Each row carries the page revision.
Players are matched to our ids by Wikipedia article, then full name and country,
then a close spelling or Cricsheet initials when exactly one player fits: 170 of
173 retained and 63 of 77 sold; the rest are uncapped domestic players with no
ball-by-ball record.

- All ten franchises, with their retained squads; purse = ₹125 cr minus the retained
  salaries listed on Wikipedia (MI ₹2.75 cr ... KKR ₹70.3 cr). These may differ by a
  few crore from figures reported elsewhere; the page lists no purses itself.
- Lots in real order and sets, at real base prices; the accelerated round as it
  happened, with players unsold earlier added at its end.
- Overseas fee cap ₹18 cr: bidding can go past it, the team pays at most the cap.
- Stats, career numbers and "last IPL team" stop before the 2025/26 season, so the
  replay shows nothing from after the auction.
- Where each player really went, and for how much, stays on the server until the
  end, then appears next to the room's result. Only players who were sold are on
  Wikipedia, so the unsold ones from the real auction aren't in the replay.
