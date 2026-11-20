# Season (Milestone 6)

After an auction, every franchise's squad plays an IPL season on the match engine.

## Flow

1. The auction ends → **Play the season** → `/auction/{code}/season`.
2. **Setup:** each person who ran a franchise sets their XI (batting order) and an
   Impact sub, starting from the engine's pick; bots use the engine's pick. Seats are
   recognised by the token from the auction (stored as a sha256 hash in
   `auction_rooms.seats`). The host starts the season; auctions saved before seats
   were kept can be started by anyone.
3. **Play:** the whole season is simulated at once (74 matches for ten teams, about
   five seconds) and saved: `seasons.result` plus every full match in `sim_results`
   (`context = 'season'`).
4. **Reveal:** each viewer goes through it match by match; the points table is built
   from the matches they have seen (progress kept in their browser). Their own
   matches can be watched live, ball by ball, with the result hidden until the end.

## Rules

- **XI:** eleven players, at most four overseas on the field, a wicketkeeper, five
  bowling options (Impact sub included). The keeper and bowling rules apply only as
  far as the squad allows; a squad with no keeper gives the gloves to a batter, and
  one with fewer than eleven players fields replacements (role-prior profiles).
- **Impact sub:** one bench bowler per team who bowls but doesn't bat; overseas only
  if the XI has three or fewer overseas players.
- **Engine's XI:** best players by role (batting and bowling strength from each
  player's simulator profile, ranked within the squad), never leaving a rule
  unmeetable; batting order: openers (tagged T20 openers first, a bowler who opens
  included), then batters and keepers, all-rounders, bowlers, each by batting strength.
- **Format:** ten teams play the IPL format (two groups of five; each team plays its
  group twice, its counterpart in the other group twice, the rest once: 14 matches,
  70 in all). Smaller rooms play a double round robin. Matches are ordered so teams
  get rest between games.
- **Points:** 2 for a win, 1 each for a tie (no super over yet); table by points then
  net run rate (all-out innings count as 20 overs).
- **Playoffs:** Qualifier 1 (1v2), Eliminator (3v4), Qualifier 2, Final; two or three
  teams play a final. A tied playoff goes to the team higher in the table.
- **Caps:** Orange (runs) and Purple (wickets), shown once the season is over.
