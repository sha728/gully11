# Season (Milestone 6)

After an auction, every franchise's squad plays an IPL season on the match engine.

## Flow

1. The auction ends → **Play the season** → `/auction/{code}/season`.
2. **Setup:** each person who ran a franchise sets their XI (batting order) and an
   Impact sub, starting from the engine's pick; bots use the engine's pick. Seats are
   recognised by the token from the auction (stored as a sha256 hash in
   `auction_rooms.seats`). The host starts the season (draws the fixtures); auctions
   saved before seats were kept can be started by anyone.
3. **One shared timeline, moved on by the host:** *Next match*, *To my next match*
   (plays everything before the host's next match, so it's up next) or *Skip to the
   end*. A match is simulated only when the season reaches it, with the XIs set at
   that moment, so anyone can change their XI between matches; each result records
   the XIs used. Everyone else's page follows along (polls every few seconds).
4. **Watching:** the host's *Play my match* opens it live, ball by ball, with the result
   hidden until the end; anyone whose match has just been played gets *Watch it live*.
   Any played match can be replayed from the results list.

State: `seasons.result` holds the fixtures, results, playoff outcomes and running
cap tallies (plain JSON, updated each step); full matches are in `sim_results`
(`context = 'season'`).

## Rules

- **XI:** eleven players, at most four overseas on the field, a wicketkeeper, five
  bowling options (Impact sub included). The keeper and bowling rules apply only as
  far as the squad allows; a squad with no keeper gives the gloves to a batter, and
  one with fewer than eleven players fields replacements (role-prior profiles).
- **Impact Player:** each team names up to five substitutes from its bench; one of
  them may come on for one of the XI, who takes no further part. He can bat and bowl
  a full four overs, and only eleven players bat (IPL rule). You choose which sub
  (or let the engine pick after the toss: a bowler when batting first, a batter
  when chasing), who he replaces (or let the engine pick) and when: from the first
  ball, at the innings break, or "when he's needed" (see docs/simulator.md). Bots
  name their best three bench bowlers and two batters and let the engine choose. Overseas only if the XI has three or fewer overseas
  players. Scorecards mark him "impact · in" and the replaced player "out".
- **Engine's XI:** best players by role (batting and bowling strength from each
  player's simulator profile, ranked within the squad), never leaving a rule
  unmeetable; batting order: openers (tagged T20 openers first, a bowler who opens
  included), then batters and keepers, all-rounders, bowlers, each by batting strength.
- **Format:** ten teams play the IPL format (two groups of five; each team plays its
  group twice, its counterpart in the other group twice, the rest once: 14 matches,
  70 in all). Smaller rooms play a double round robin. Matches are ordered so teams
  get rest between games.
- **Points:** 2 for a win; a tie goes to a super over (see simulator.md), whose
  winner takes the points. Table by points then
  net run rate (all-out innings count as 20 overs).
- **Playoffs:** Qualifier 1 (1v2), Eliminator (3v4), Qualifier 2, Final; two or three
  teams play a final. Playoff ties also go to a super over.
- **Caps:** Orange (runs) and Purple (wickets), shown once the season is over.
