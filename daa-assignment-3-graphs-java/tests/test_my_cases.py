"""Own tests for Assignment 3 (Java solution).  Run from the repository root:

    python tests/test_my_cases.py            # all tests, prints a report
    python tests/test_my_cases.py > tests/RESULTS.txt

Hand-made cases carry an expected answer that was derived by hand (reason printed next to it).
Random cases are checked against independent brute-force oracles (not the code under test).
Every request is sent to the REAL program (src/Java, class Main) as JSON Lines, in batches, so the
adapter, state reset and output format are tested as well; the Java route helper is called through tests/RouteHelperTest.java.
"""
import itertools
import json
import pathlib
import random
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import run as launcher  # noqa: E402  (tools/run.py: builds the selected language, 60 s compile limit)

MAIN = launcher.build("Java")          # javac --release 17 ... ; java -Xmx384m -cp .build/Java Main
ROUTE_DIR = ROOT / ".build" / "route_test"


def build_route_driver():
    ROUTE_DIR.mkdir(parents=True, exist_ok=True)
    sources = sorted(str(p) for p in (ROOT / "src" / "Java").glob("*.java"))
    subprocess.run(["javac", "--release", "17", "-encoding", "UTF-8", "-d", str(ROUTE_DIR), *sources,
                    str(ROOT / "tests" / "RouteHelperTest.java")], check=True, timeout=60)


def java_routes(requests):
    """Calls Algorithms.reconstructRoute (Java) through tests/RouteHelperTest.java."""
    data = "".join(json.dumps(r, separators=(",", ":")) + "\n" for r in requests)
    res = subprocess.run(["java", "-Xmx384m", "-cp", str(ROUTE_DIR), "RouteHelperTest"], input=data,
                         capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert res.returncode == 0, res.stderr
    return [json.loads(x) for x in res.stdout.splitlines()]
PASSED = 0
FAILED = 0


def run_program(requests):
    data = "".join(json.dumps(r, separators=(",", ":")) + "\n" for r in requests)
    res = subprocess.run(MAIN, input=data, capture_output=True, text=True, encoding="utf-8", timeout=120)
    assert res.returncode == 0, res.stderr
    lines = res.stdout.splitlines()
    assert len(lines) == len(requests), (len(lines), len(requests))
    return [json.loads(x) for x in lines]


def report(name, ok, detail=""):
    global PASSED, FAILED
    if ok:
        PASSED += 1
        print(f"PASS  {name}")
    else:
        FAILED += 1
        print(f"FAIL  {name}  {detail}")


# ---------------------------------------------------------------------------------------------
# Independent oracles (brute force, deliberately different from the implementation)
# ---------------------------------------------------------------------------------------------

def oracle_dsu(n, ops):
    label = list(range(n))
    out = []
    for u, v in ops:
        a, b = label[u], label[v]
        if a != b:
            label = [a if x == b else x for x in label]
        cnt = {}
        for x in label:
            cnt[x] = cnt.get(x, 0) + 1
        out.append([len(cnt), max(cnt.values()) if cnt else 0])
    return out


def components_by_closure(n, edges):
    reach = [[i == j for j in range(n)] for i in range(n)]
    for e in edges:
        reach[e[0]][e[1]] = reach[e[1]][e[0]] = True
    for k in range(n):
        for i in range(n):
            if reach[i][k]:
                for j in range(n):
                    if reach[k][j]:
                        reach[i][j] = True
    return len({tuple(r) for r in reach})


def oracle_mst(n, edges):
    """Brute force over ALL edge subsets (tiny m): min cost spanning forest."""
    c = components_by_closure(n, edges)
    best = None
    for mask in range(1 << len(edges)):
        ids = [i for i in range(len(edges)) if mask >> i & 1]
        if len(ids) != n - c:
            continue
        sub = [edges[i] for i in ids]
        if components_by_closure(n, sub) != c:
            continue                         # n-c edges that keep c components must be acyclic
        cost = sum(e[2] for e in sub)
        if best is None or cost < best:
            best = cost
    return (0 if best is None else best), c


def closure_directed(n, edges):
    reach = [[i == j for j in range(n)] for i in range(n)]
    for e in edges:
        reach[e[0]][e[1]] = True
    for k in range(n):
        for i in range(n):
            if reach[i][k]:
                for j in range(n):
                    if reach[k][j]:
                        reach[i][j] = True
    return reach


def oracle_bellman(n, edges, source):
    INF = None
    dist = [INF] * n
    dist[source] = 0
    for _ in range(n):
        for u, v, w in edges:
            if dist[u] is not None and (dist[v] is None or dist[u] + w < dist[v]):
                dist[v] = dist[u] + w
    return dist


# ---------------------------------------------------------------------------------------------
# Semantic validators (accept any valid answer, reject invalid witnesses)
# ---------------------------------------------------------------------------------------------

def valid_forest(n, edges, ans, cost, comps):
    ids = ans.get("edge_ids")
    if ans.get("cost") != cost or ans.get("components") != comps:
        return False
    if len(set(ids)) != len(ids) or len(ids) != n - comps:
        return False
    parent = list(range(n))

    def f(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    total = 0
    for i in ids:
        u, v, w = edges[i]
        a, b = f(u), f(v)
        if a == b:
            return False
        parent[a] = b
        total += w
    return total == cost


def valid_scc(n, edges, ans, reach=None):
    reach = reach or closure_directed(n, edges)
    lab = ans["component"]
    if len(lab) != n:
        return False
    for i in range(n):
        for j in range(n):
            if (lab[i] == lab[j]) != (reach[i][j] and reach[j][i]):
                return False
    want = {(lab[u], lab[v]) for u, v in edges if lab[u] != lab[v]}
    got = [tuple(p) for p in ans["condensation"]]
    return len(got) == len(set(got)) and set(got) == want


def valid_topo(n, edges, ans, has_cycle):
    if has_cycle:
        return ans["acyclic"] is False and ans["order"] == []
    order = ans["order"]
    if ans["acyclic"] is not True or sorted(order) != list(range(n)):
        return False
    pos = {v: i for i, v in enumerate(order)}
    return all(pos[u] < pos[v] for u, v in edges)


def valid_dag(n, edges, source, ans, has_cycle):
    if has_cycle:
        return ans == {"acyclic": False, "distance": [], "parent_edge": []}
    exp = oracle_bellman(n, edges, source)
    if ans["acyclic"] is not True or ans["distance"] != exp or len(ans["parent_edge"]) != n:
        return False
    for v in range(n):
        pe = ans["parent_edge"][v]
        if v == source or exp[v] is None:
            if pe != -1:
                return False
            continue
        if not 0 <= pe < len(edges) or edges[pe][1] != v:
            return False
        u = edges[pe][0]
        if exp[u] is None or exp[u] + edges[pe][2] != exp[v]:
            return False
    for v in range(n):                        # every parent chain must end at the source
        x, steps = v, 0
        while x != source and exp[x] is not None:
            x = edges[ans["parent_edge"][x]][0]
            steps += 1
            if steps > n:
                return False
    return True


# ---------------------------------------------------------------------------------------------
# 1. Hand-made cases with hand-derived answers
# ---------------------------------------------------------------------------------------------
HAND = [
    ("dsu README example", {"task": "dsu", "n": 4, "operations": [[0, 1], [1, 2], [0, 2], [3, 3]]},
     {"states": [[3, 2], [2, 3], [2, 3], [2, 3]]}, "0-1 merges (3 comps, size 2); 1-2 -> size 3; repeat and self-union change nothing"),
    ("dsu n=0", {"task": "dsu", "n": 0, "operations": []}, {"states": []}, "empty graph: no operations, no states"),
    ("dsu n=1 self-union", {"task": "dsu", "n": 1, "operations": [[0, 0]]}, {"states": [[1, 1]]}, "single vertex, largest stays 1"),
    ("dsu n=3 no operations", {"task": "dsu", "n": 3, "operations": []}, {"states": []}, "no initial state is reported"),
    ("dsu chain of unions", {"task": "dsu", "n": 5, "operations": [[0, 1], [2, 3], [1, 3], [4, 4], [0, 4]]},
     {"states": [[4, 2], [3, 2], [2, 4], [2, 4], [1, 5]]}, "{0,1},{2,3} -> {0,1,2,3} -> add 4"),
    ("kruskal README example", {"task": "kruskal", "n": 4, "edges": [[0, 1, 4], [1, 2, 2], [0, 2, 3]]},
     {"cost": 5, "components": 2, "ids_any_of": [[1, 2]]}, "take 2 and 3, drop 4 (cycle); vertex 3 isolated -> 2 components"),
    ("prim README example", {"task": "prim", "n": 4, "edges": [[0, 1, 4], [1, 2, 2], [0, 2, 3]]},
     {"cost": 5, "components": 2, "ids_any_of": [[1, 2]]}, "same graph; Prim must restart for isolate 3"),
    ("kruskal n=0", {"task": "kruskal", "n": 0, "edges": []}, {"cost": 0, "components": 0, "ids_any_of": [[]]}, "empty graph"),
    ("prim n=0", {"task": "prim", "n": 0, "edges": []}, {"cost": 0, "components": 0, "ids_any_of": [[]]}, "empty graph"),
    ("kruskal only isolates", {"task": "kruskal", "n": 3, "edges": []}, {"cost": 0, "components": 3, "ids_any_of": [[]]}, "3 isolates"),
    ("prim only self-loops", {"task": "prim", "n": 2, "edges": [[0, 0, -5], [1, 1, -7]]},
     {"cost": 0, "components": 2, "ids_any_of": [[]]}, "negative self-loops must never be chosen"),
    ("kruskal negative loop + edge", {"task": "kruskal", "n": 2, "edges": [[0, 0, -5], [0, 1, 3]]},
     {"cost": 3, "components": 1, "ids_any_of": [[1]]}, "loop skipped even though cheaper; only edge 1 connects"),
    ("prim parallel ties", {"task": "prim", "n": 2, "edges": [[0, 1, 5], [0, 1, 2], [0, 1, 2]]},
     {"cost": 2, "components": 1, "ids_any_of": [[1], [2]]}, "parallel edges 1 and 2 tie at 2; either is optimal"),
    ("kruskal total > 32 bit", {"task": "kruskal", "n": 4, "edges": [[0, 1, 10**9], [1, 2, 10**9], [2, 3, 10**9], [0, 3, 10**9]]},
     {"cost": 3 * 10**9, "components": 1, "ids_any_of": [[0, 1, 2], [0, 1, 3], [0, 2, 3], [1, 2, 3]]}, "3 edges of 1e9 = 3e9 > 2^31"),
    ("prim negative total beyond 32 bit", {"task": "prim", "n": 3, "edges": [[0, 1, -10**9], [1, 2, -10**9], [0, 2, 7]]},
     {"cost": -2 * 10**9, "components": 1, "ids_any_of": [[0, 1]]}, "-1e9 + -1e9; edge of weight 7 is worse"),
    ("scc README example", {"task": "scc", "n": 4, "edges": [[0, 1], [1, 0], [1, 2], [0, 2], [2, 3]]},
     {"groups": [[0, 1], [2], [3]], "cond": [[0, 1], [1, 2]]}, "0<->1 form one SCC; 2 and 3 are singletons; chain {01}->{2}->{3}"),
    ("scc n=0", {"task": "scc", "n": 0, "edges": []}, {"groups": [], "cond": []}, "empty graph"),
    ("scc isolate + self-loop + duplicates", {"task": "scc", "n": 3, "edges": [[0, 0], [0, 1], [0, 1], [0, 1]]},
     {"groups": [[0], [1], [2]], "cond": [[0, 1]]}, "self-loop internal; three parallel 0->1 give ONE condensation pair"),
    ("scc one big cycle", {"task": "scc", "n": 4, "edges": [[0, 1], [1, 2], [2, 3], [3, 0]]},
     {"groups": [[0, 1, 2, 3]], "cond": []}, "a single 4-cycle is one SCC with no cross edges"),
    ("topo README example", {"task": "topo", "n": 4, "edges": [[0, 2], [1, 2], [2, 3]]}, {"acyclic": True}, "any order with 0,1 before 2 before 3"),
    ("topo n=0", {"task": "topo", "n": 0, "edges": []}, {"acyclic": True, "order": []}, "empty graph"),
    ("topo self-loop", {"task": "topo", "n": 2, "edges": [[1, 1]]}, {"acyclic": False, "order": []}, "self-loop is a cycle"),
    ("topo diamond (finished vertex is not a cycle)", {"task": "topo", "n": 4, "edges": [[0, 1], [0, 2], [1, 3], [2, 3]]}, {"acyclic": True},
     "3 is reached twice; second visit hits a FINISHED vertex -> no cycle"),
    ("topo cycle in 2nd component", {"task": "topo", "n": 5, "edges": [[0, 1], [3, 4], [4, 3]]}, {"acyclic": False, "order": []}, "cycle 3<->4 away from vertex 0"),
    ("dag README example", {"task": "dag", "n": 5, "source": 0, "edges": [[0, 1, 3], [0, 2, 8], [1, 2, -7], [2, 3, 4]]},
     {"acyclic": True, "distance": [0, 3, -4, 0, None], "parent_edge": [-1, 0, 2, 3, -1]}, "0->1->2 costs 3-7=-4 (beats 8); then +4 = 0; vertex 4 unreachable"),
    ("dag n=1", {"task": "dag", "n": 1, "source": 0, "edges": []}, {"acyclic": True, "distance": [0], "parent_edge": [-1]}, "only the source"),
    ("dag cycle unreachable from source", {"task": "dag", "n": 4, "source": 0, "edges": [[0, 1, 1], [2, 3, 1], [3, 2, 1]]},
     {"acyclic": False, "distance": [], "parent_edge": []}, "cycle 2<->3 unreachable from 0 still makes the answer false"),
    ("dag self-loop", {"task": "dag", "n": 2, "source": 0, "edges": [[1, 1, 4]]}, {"acyclic": False, "distance": [], "parent_edge": []}, "self-loop = cycle"),
    ("dag distance -1 is finite, not 'unreachable'", {"task": "dag", "n": 3, "source": 0, "edges": [[0, 1, -1]]},
     {"acyclic": True, "distance": [0, -1, None], "parent_edge": [-1, 0, -1]}, "vertex 1 has cost -1; vertex 2 null"),
    ("dag unreachable vertex has negative edge", {"task": "dag", "n": 4, "source": 0, "edges": [[2, 3, -100], [0, 1, 5]]},
     {"acyclic": True, "distance": [0, 5, None, None], "parent_edge": [-1, 1, -1, -1]}, "must NOT relax out of unreachable 2: vertex 3 stays null"),
    ("dag 64-bit distance", {"task": "dag", "n": 4, "source": 0, "edges": [[0, 1, 10**9], [1, 2, 10**9], [2, 3, 10**9]]},
     {"acyclic": True, "distance": [0, 10**9, 2 * 10**9, 3 * 10**9], "parent_edge": [-1, 0, 1, 2]}, "3e9 exceeds 32 bits"),
    ("dag tied/parallel edges", {"task": "dag", "n": 3, "source": 0, "edges": [[0, 1, 2], [0, 1, 2], [0, 2, 4], [1, 2, 2]]},
     {"acyclic": True, "distance": [0, 2, 4], "parent_alts": {"1": [0, 1], "2": [2, 3]}}, "edges 0,1 tie to vertex 1; edge 2 and path 0-1-2 tie at 4"),
]


def check_hand(req, exp, ans):
    t = req["task"]
    if t == "dsu":
        return ans == exp
    if t in ("kruskal", "prim"):
        return (valid_forest(req["n"], req["edges"], ans, exp["cost"], exp["components"])
                and sorted(ans["edge_ids"]) in [sorted(x) for x in exp["ids_any_of"]])
    if t == "scc":
        lab = ans["component"]
        groups = sorted(sorted(i for i in range(req["n"]) if lab[i] == c) for c in set(lab))
        want = sorted(sorted(g) for g in exp["groups"])
        if groups != want:
            return False
        rep = {tuple(g): lab[g[0]] for g in groups}
        cond = {(rep[tuple(sorted(a))], rep[tuple(sorted(b))]) for a, b in
                [(g1, g2) for g1 in exp["groups"] for g2 in exp["groups"]]
                if any(u in a and v in b for u, v in req["edges"]) and a != b}
        return {tuple(p) for p in ans["condensation"]} == cond and len(ans["condensation"]) == len(cond)
    if t == "topo":
        return valid_topo(req["n"], req["edges"], ans, exp["acyclic"] is False)
    if t == "dag":
        if "parent_alts" in exp:
            return (ans["acyclic"] and ans["distance"] == exp["distance"]
                    and all(ans["parent_edge"][int(k)] in v for k, v in exp["parent_alts"].items())
                    and ans["parent_edge"][0] == -1)
        return ans == exp
    raise AssertionError(t)


def test_hand():
    print("\n== Hand-made cases (expected answers derived by hand), sent to the real program ==")
    answers = run_program([h[1] for h in HAND])
    for (name, req, exp, why), ans in zip(HAND, answers):
        report(f"{name}", check_hand(req, exp, ans), f"got {ans}")
        print(f"      why: {why}")
    return answers


# ---------------------------------------------------------------------------------------------
# 2. Random small cases against independent brute-force oracles
# ---------------------------------------------------------------------------------------------

def test_random(seed=2026, rounds=250):
    print(f"\n== Random small graphs vs brute-force oracles (seed={seed}, {rounds} per task) ==")
    rnd = random.Random(seed)
    reqs, meta = [], []
    for _ in range(rounds):
        n = rnd.randint(0, 7)
        # dsu
        ops = [[rnd.randrange(n), rnd.randrange(n)] for _ in range(rnd.randint(0, 9))] if n else []
        reqs.append({"task": "dsu", "n": n, "operations": ops}); meta.append(("dsu", oracle_dsu(n, ops)))
        # undirected weighted (also feeds prim); keep m <= 9 for subset brute force
        m = rnd.randint(0, 9) if n else 0
        ed = [[rnd.randrange(n), rnd.randrange(n), rnd.randint(-5, 5)] for _ in range(m)]
        o = oracle_mst(n, ed)
        for t in ("kruskal", "prim"):
            reqs.append({"task": t, "n": n, "edges": ed}); meta.append((t, o))
        # directed unweighted
        m2 = rnd.randint(0, 12) if n else 0
        de = [[rnd.randrange(n), rnd.randrange(n)] for _ in range(m2)]
        reach = closure_directed(n, de)
        cyc = (any([i, i] in de for i in range(n))
               or any(reach[i][j] and reach[j][i] for i in range(n) for j in range(n) if i != j))
        reqs.append({"task": "scc", "n": n, "edges": de}); meta.append(("scc", reach))
        reqs.append({"task": "topo", "n": n, "edges": de}); meta.append(("topo", cyc))
        if n:
            dw = [[u, v, rnd.randint(-6, 6)] for u, v in de]
            s = rnd.randrange(n)
            reqs.append({"task": "dag", "n": n, "source": s, "edges": dw}); meta.append(("dag", cyc))
    answers = run_program(reqs)
    bad = {}
    for req, (kind, ref), ans in zip(reqs, meta, answers):
        t = req["task"]
        if t == "dsu":
            ok = ans["states"] == ref
        elif t in ("kruskal", "prim"):
            ok = valid_forest(req["n"], req["edges"], ans, ref[0], ref[1])
        elif t == "scc":
            ok = valid_scc(req["n"], req["edges"], ans, ref)
        elif t == "topo":
            ok = valid_topo(req["n"], req["edges"], ans, ref)
        else:
            ok = valid_dag(req["n"], req["edges"], req["source"], ans, ref)
        if not ok:
            bad.setdefault(t, []).append(req)
    for t in ("dsu", "kruskal", "prim", "scc", "topo", "dag"):
        total = sum(1 for r in reqs if r["task"] == t)
        report(f"random {t}: {total} cases", t not in bad, f"{len(bad.get(t, []))} failures, first: {bad.get(t, [None])[0]}")
    return reqs


# ---------------------------------------------------------------------------------------------
# 3. Validator self-tests: accept alternative valid answers, reject invalid witnesses
# ---------------------------------------------------------------------------------------------

def test_validators():
    print("\n== Validator self-tests (alternative valid answer accepted, invalid witness rejected) ==")
    ed = [[0, 1, 2], [0, 1, 2], [1, 2, 5]]
    report("forest: alternative tied edge accepted",
           valid_forest(3, ed, {"cost": 7, "edge_ids": [1, 2], "components": 1}, 7, 1))
    report("forest: wrong cost rejected",
           not valid_forest(3, ed, {"cost": 6, "edge_ids": [1, 2], "components": 1}, 7, 1))
    report("forest: cycle (both parallel edges) rejected",
           not valid_forest(3, ed, {"cost": 4, "edge_ids": [0, 1], "components": 1}, 7, 1))
    report("forest: duplicate id rejected",
           not valid_forest(3, ed, {"cost": 14, "edge_ids": [1, 1, 2], "components": 1}, 7, 1))
    e = [[0, 1], [1, 0], [1, 2]]
    report("scc: shifted labels accepted", valid_scc(3, e, {"component": [9, 9, 4], "condensation": [[9, 4]]}))
    report("scc: merged SCCs rejected", not valid_scc(3, e, {"component": [1, 1, 1], "condensation": []}))
    report("scc: duplicate condensation pair rejected", not valid_scc(3, e, {"component": [9, 9, 4], "condensation": [[9, 4], [9, 4]]}))
    report("scc: reversed condensation pair rejected", not valid_scc(3, e, {"component": [9, 9, 4], "condensation": [[4, 9]]}))
    te = [[0, 2], [1, 2]]
    report("topo: second valid order accepted", valid_topo(3, te, {"acyclic": True, "order": [0, 1, 2]}, False)
           and valid_topo(3, te, {"acyclic": True, "order": [1, 0, 2]}, False))
    report("topo: order violating an edge rejected", not valid_topo(3, te, {"acyclic": True, "order": [2, 0, 1]}, False))
    report("topo: missing vertex rejected", not valid_topo(3, te, {"acyclic": True, "order": [0, 2]}, False))
    de = [[0, 1, 2], [0, 1, 2], [1, 2, 2], [0, 2, 4]]
    good = {"acyclic": True, "distance": [0, 2, 4], "parent_edge": [-1, 1, 3]}
    alt = {"acyclic": True, "distance": [0, 2, 4], "parent_edge": [-1, 0, 2]}
    report("dag: alternative tied parents accepted", valid_dag(3, de, 0, good, False) and valid_dag(3, de, 0, alt, False))
    report("dag: parent edge ending elsewhere rejected",
           not valid_dag(3, de, 0, {"acyclic": True, "distance": [0, 2, 4], "parent_edge": [-1, 3, 3]}, False))
    report("dag: parent edge that is not tight rejected",
           not valid_dag(3, de, 0, {"acyclic": True, "distance": [0, 2, 4], "parent_edge": [-1, 0, 0]}, False))
    report("dag: wrong distance rejected",
           not valid_dag(3, de, 0, {"acyclic": True, "distance": [0, 2, 5], "parent_edge": [-1, 0, 2]}, False))


# ---------------------------------------------------------------------------------------------
# 4. Route helper
# ---------------------------------------------------------------------------------------------

def test_route_helper():
    print("\n== Route helper calls: Algorithms.reconstructRoute (reachable, source, unreachable, tied/parallel) ==")
    ed = [[0, 1, 3], [0, 2, 8], [1, 2, -7], [2, 3, 4]]
    base = {"n": 5, "source": 0, "edges": ed}
    r_reach, r_src, r_unr = java_routes([dict(base, target=3), dict(base, target=0), dict(base, target=4)])
    pe, r = r_reach["parent_edge"], r_reach["route"]
    cost = sum(next(w for u, v, w in ed if (u, v) == (a, b)) for a, b in zip(r, r[1:]))
    print(f"      reconstructRoute(0, 3) -> {r}, parent_edge={pe}, edge IDs used={[pe[v] for v in r[1:]]}, cost={cost}")
    report("route to reachable target 3", r == [0, 1, 2, 3] and cost == 0)
    print(f"      reconstructRoute(0, 0) -> {r_src['route']}")
    report("route to the source itself is [source]", r_src["route"] == [0])
    print(f"      reconstructRoute(0, 4) -> {r_unr['route']}  (documented: unreachable target -> empty array)")
    report("route to unreachable target is []", r_unr["route"] == [])
    ed2 = [[0, 1, 2], [0, 1, 2], [0, 2, 4], [1, 2, 2]]
    tied = {"n": 3, "source": 0, "edges": ed2, "target": 2}
    t0, a1, a2, bad = java_routes([tied,
                                   dict(tied, parent_edge=[-1, 0, 2]),
                                   dict(tied, parent_edge=[-1, 1, 3]),
                                   dict(tied, parent_edge=[-1, 0, 0])])
    pe2, r = t0["parent_edge"], t0["route"]
    ids = [pe2[v] for v in r[1:]]
    cost = sum(ed2[i][2] for i in ids)
    dir_ok = all(ed2[i][0] == x and ed2[i][1] == y for i, x, y in zip(ids, r, r[1:]))
    print(f"      tied graph: parent_edge={pe2}, reconstructRoute(0, 2) -> {r}, edge IDs={ids}, cost={cost}")
    report("tied/parallel route: direction and total weight verified", dir_ok and r[0] == 0 and r[-1] == 2 and cost == 4)
    for alt in (a1, a2):
        rr = alt["route"]
        ids = [alt["parent_edge"][v] for v in rr[1:]]
        ok = rr[0] == 0 and rr[-1] == 2 and sum(ed2[i][2] for i in ids) == 4
        print(f"      witness parent_edge={alt['parent_edge']} -> route {rr}, edge IDs={ids}, cost={sum(ed2[i][2] for i in ids)}")
        report(f"helper accepts alternative valid witness {alt['parent_edge']}", ok)
    report("helper rejects invalid witness (edge 0 ends at vertex 1, not 2) -> []", bad["route"] == [])


# ---------------------------------------------------------------------------------------------
# 5. Full limits, deep chains, mixed repeated requests
# ---------------------------------------------------------------------------------------------

def timed_run(requests):
    t = time.perf_counter()
    ans = run_program(requests)
    return ans, time.perf_counter() - t


def test_limits():
    print("\n== Full published limits (n=100000, m/q=250000) and deep chains, through the real program ==")
    N, M = 100000, 250000
    rnd = random.Random(7)

    ops = [[rnd.randrange(N), rnd.randrange(N)] for _ in range(M)]
    (ans,), sec = timed_run([{"task": "dsu", "n": N, "operations": ops}])
    st = ans["states"]
    report(f"dsu full limit ({sec:.2f}s)", len(st) == M and st[-1][0] >= 1 and all(st[i][0] >= st[i + 1][0] for i in range(M - 1)))
    chain_ops = [[i, i + 1] for i in range(N - 1)]
    (ans,), sec = timed_run([{"task": "dsu", "n": N, "operations": chain_ops}])
    report(f"dsu chain of 99999 unions -> [1,100000] ({sec:.2f}s)", ans["states"][-1] == [1, N] and ans["states"][0] == [N - 1, 2])

    wedges = [[rnd.randrange(N), rnd.randrange(N), rnd.randint(-10**9, 10**9)] for _ in range(M)]
    ans_k, sec_k = timed_run([{"task": "kruskal", "n": N, "edges": wedges}])
    ans_p, sec_p = timed_run([{"task": "prim", "n": N, "edges": wedges}])
    k, p = ans_k[0], ans_p[0]
    report(f"kruskal vs prim full limit agree: cost={k['cost']}, comps={k['components']} ({sec_k:.2f}s / {sec_p:.2f}s)",
           k["cost"] == p["cost"] and k["components"] == p["components"])
    report("kruskal and prim forests are valid", valid_forest(N, wedges, k, k["cost"], k["components"]) and valid_forest(N, wedges, p, k["cost"], k["components"]))

    dedges = [[rnd.randrange(N), rnd.randrange(N)] for _ in range(M)]
    (a,), sec = timed_run([{"task": "scc", "n": N, "edges": dedges}])
    lab = a["component"]
    pairs = [tuple(x) for x in a["condensation"]]
    pairset = set(pairs)
    good = len(lab) == N and len(pairs) == len(pairset) and all(x != y for x, y in pairs)
    good = good and all(lab[u] == lab[v] or (lab[u], lab[v]) in pairset for u, v in dedges)
    good = good and {(lab[u], lab[v]) for u, v in dedges if lab[u] != lab[v]} == pairset
    good = good and scc_independent_check(N, dedges, lab, pairs)
    report(f"scc full limit random digraph: {len(set(lab))} SCCs, {len(pairs)} cross pairs ({sec:.2f}s)", good)

    # random DAG with full limits (edges oriented low -> high index)
    dag_edges = []
    for _ in range(M):
        u, v = rnd.randrange(N), rnd.randrange(N)
        if u == v:
            v = (u + 1) % N
            if v < u:
                u, v = v, u
        elif u > v:
            u, v = v, u
        dag_edges.append([u, v, rnd.randint(-10**9, 10**9)])
    (a_t,), sec_t = timed_run([{"task": "topo", "n": N, "edges": [[u, v] for u, v, _ in dag_edges]}])
    pos = {v: i for i, v in enumerate(a_t["order"])}
    report(f"topo full limit random DAG ({sec_t:.2f}s)", a_t["acyclic"] and len(pos) == N and all(pos[u] < pos[v] for u, v, _ in dag_edges))
    (a_d,), sec_d = timed_run([{"task": "dag", "n": N, "source": 0, "edges": dag_edges}])
    # independent check: DP in index order (edges go low -> high, so index order is topological)
    best = [None] * N
    best[0] = 0
    by_src = {}
    for u, v, w in dag_edges:
        by_src.setdefault(u, []).append((v, w))
    for u in range(N):
        if best[u] is None:
            continue
        for v, w in by_src.get(u, ()):
            if best[v] is None or best[u] + w < best[v]:
                best[v] = best[u] + w
    report(f"dag full limit random DAG matches independent DP ({sec_d:.2f}s)",
           a_d["acyclic"] and a_d["distance"] == best and valid_dag_fast(N, dag_edges, 0, a_d, best))

    # Deep chains, N vertices (would overflow a recursive DFS)
    chain = [[i, i + 1] for i in range(N - 1)]
    (a,), sec = timed_run([{"task": "topo", "n": N, "edges": chain}])
    report(f"topo deep chain 100000 ({sec:.2f}s)", a["acyclic"] and a["order"] == list(range(N)))
    (a,), sec = timed_run([{"task": "topo", "n": N, "edges": chain + [[N - 1, 0]]}])
    report(f"topo deep chain closed into one cycle -> false ({sec:.2f}s)", a == {"acyclic": False, "order": []})
    (a,), sec = timed_run([{"task": "scc", "n": N, "edges": chain + [[N - 1, 0]]}])
    report(f"scc one cycle of 100000 vertices -> single SCC ({sec:.2f}s)", len(set(a["component"])) == 1 and a["condensation"] == [])
    (a,), sec = timed_run([{"task": "scc", "n": N, "edges": chain}])
    report(f"scc deep chain: 100000 SCCs, 99999 condensation pairs ({sec:.2f}s)", len(set(a["component"])) == N and len(a["condensation"]) == N - 1)
    wchain = [[i, i + 1, -1] for i in range(N - 1)]
    (a,), sec = timed_run([{"task": "dag", "n": N, "source": 0, "edges": wchain}])
    report(f"dag deep chain with weight -1: distance[-1] == -99999 ({sec:.2f}s)", a["distance"][-1] == -(N - 1) and a["parent_edge"][-1] == N - 2)
    (rr,) = java_routes([{"n": N, "source": 0, "target": N - 1, "edges": wchain}])
    report("route helper on a 100000-vertex chain (iterative, no recursion)", rr["route"] == list(range(N)))
    uchain = [[i, i + 1, 1] for i in range(N - 1)]
    (a,), sec = timed_run([{"task": "kruskal", "n": N, "edges": uchain}])
    (b,), sec2 = timed_run([{"task": "prim", "n": N, "edges": uchain}])
    report(f"kruskal/prim on path of 100000 vertices ({sec:.2f}s / {sec2:.2f}s)", a["cost"] == b["cost"] == N - 1 and a["components"] == b["components"] == 1)
    big = 10**9
    heavy = [[i, i + 1, big] for i in range(N - 1)]
    (a,), _ = timed_run([{"task": "kruskal", "n": N, "edges": heavy}])
    report("total beyond 32 bit at scale: cost == 99999 * 1e9", a["cost"] == (N - 1) * big)


def scc_independent_check(n, edges, lab, pairs):
    """Large-scale SCC proof without a closure matrix: (1) every label class is strongly connected
    (forward and backward BFS from one member, inside the class); (2) the condensation is acyclic
    (Kahn).  Strongly connected classes + acyclic quotient = exactly the SCC partition."""
    members = {}
    for v, c in enumerate(lab):
        members.setdefault(c, []).append(v)
    fwd = [[] for _ in range(n)]
    bwd = [[] for _ in range(n)]
    for u, v in edges:
        if lab[u] == lab[v]:
            fwd[u].append(v)
            bwd[v].append(u)
    for c, vs in members.items():
        for g in (fwd, bwd):
            seen = {vs[0]}
            todo = [vs[0]]
            while todo:
                x = todo.pop()
                for y in g[x]:
                    if y not in seen:
                        seen.add(y)
                        todo.append(y)
            if len(seen) != len(vs):
                return False
    indeg = {c: 0 for c in members}
    out = {c: [] for c in members}
    for a, b in pairs:
        indeg[b] += 1
        out[a].append(b)
    queue = [c for c, d in indeg.items() if d == 0]
    done = 0
    while queue:
        c = queue.pop()
        done += 1
        for d in out[c]:
            indeg[d] -= 1
            if indeg[d] == 0:
                queue.append(d)
    return done == len(members)


def valid_dag_fast(n, edges, source, ans, exp):
    pe = ans["parent_edge"]
    for v in range(n):
        if v == source or exp[v] is None:
            if pe[v] != -1:
                return False
        else:
            u, w2, w = edges[pe[v]]
            if w2 != v or exp[u] + w != exp[v]:
                return False
    return True


def test_mixed_repeat():
    print("\n== State reset: mixed tasks, repeated in one process (ping included) ==")
    batch = [{"task": "ping"},
             {"task": "dsu", "n": 3, "operations": [[0, 1]]},
             {"task": "kruskal", "n": 3, "edges": [[0, 1, 1]]},
             {"task": "scc", "n": 3, "edges": [[0, 1], [1, 0]]},
             {"task": "dag", "n": 3, "source": 2, "edges": [[0, 1, 1]]},
             {"task": "topo", "n": 2, "edges": [[0, 1]]},
             {"task": "prim", "n": 3, "edges": [[0, 1, 1]]},
             {"task": "dsu", "n": 3, "operations": [[1, 2]]}]
    first = run_program(batch * 3)
    report("ping preserved", first[0] == {"status": "ready"})
    same = all(first[i] == first[i + len(batch)] == first[i + 2 * len(batch)] for i in range(len(batch)))
    report("three identical batches in one process give identical answers", same)
    report("second dsu request does not see the first one's unions", first[7] == {"states": [[2, 2]]} and first[1] == {"states": [[2, 2]]})
    report("dag after a bigger graph: n=3 arrays only", first[4]["distance"] == [None, None, 0] and len(first[4]["parent_edge"]) == 3)
    # big request followed by tiny ones: stale arrays would corrupt them
    seq = run_program([{"task": "dsu", "n": 50000, "operations": [[i, i + 1] for i in range(49999)]},
                       {"task": "dsu", "n": 2, "operations": [[0, 0]]},
                       {"task": "scc", "n": 1, "edges": []}])
    report("tiny requests after a huge one are unaffected", seq[1] == {"states": [[2, 1]]} and seq[2] == {"component": [seq[2]["component"][0]], "condensation": []})


def write_jsonl(random_reqs):
    path = ROOT / "tests" / "my_cases.jsonl"
    with path.open("w", encoding="utf-8") as f:
        for h in HAND:
            f.write(json.dumps(h[1], separators=(",", ":")) + "\n")
    print(f"\nWrote {len(HAND)} hand-made requests to {path.relative_to(ROOT)} "
          "(run: python tools/run.py --input tests/my_cases.jsonl)")


if __name__ == "__main__":
    build_route_driver()
    test_hand()
    rr = test_random()
    test_validators()
    test_route_helper()
    test_mixed_repeat()
    test_limits()
    write_jsonl(rr)
    print(f"\nSUMMARY: {PASSED} passed, {FAILED} failed")
    sys.exit(1 if FAILED else 0)
