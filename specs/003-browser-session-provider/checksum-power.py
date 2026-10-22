"""How small a roster-composition error can a 3-decimal FG% detect?"""
import random
random.seed(7)

def displayed(m, a):
    return None if a == 0 else round(m / a, 3)

# Realistic 9-cat team week: ~10 active players.
def team_week():
    players = []
    for _ in range(10):
        fga = random.randint(5, 50)
        fgm = round(fga * random.uniform(0.35, 0.60))
        players.append((fgm, fga))
    return players

misses_ratio = 0
misses_both = 0
trials = 20000
for _ in range(trials):
    ps = team_week()
    M, A = sum(p[0] for p in ps), sum(p[1] for p in ps)
    truth = displayed(M, A)
    # Error: wrongly include/exclude ONE player (a slot misattribution).
    m, a = random.choice(ps)
    wrong = displayed(M - m, A - a)
    if wrong == truth:
        misses_ratio += 1
        # Counting categories are read DIRECTLY as team totals and summed as
        # integers -- exact, no rounding. Only a player with zero in all seven
        # evades that check.
        if m == 0 and a > 0:          # all-miss cameo: no counting stats
            misses_both += 1

print(f"single-player slot errors evading the 3dp FG% check: {misses_ratio/trials:.1%}")
print(f"  ... AND evading an exact integer counting-category sum: {misses_both/trials:.4%}")

# The pathological case the ratio check cannot see: a player shooting exactly
# the team rate.
print()
M, A = 180, 300
print(f"team {M}/{A} -> {displayed(M,A)}")
for m, a in [(3, 5), (6, 10), (4, 7), (0, 5), (1, 2)]:
    print(f"  adding {m}/{a}: -> {displayed(M+m, A+a)}"
          f"{'   UNDETECTED' if displayed(M+m,A+a)==displayed(M,A) else ''}")
