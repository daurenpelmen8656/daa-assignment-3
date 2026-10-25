# Assignment 3 — Graph Algorithms: Analysis

Language: **Java 17** (`submission.json` → `{"language": "Java"}`, compiled with `--release 17`). Algorithms: `src/Java/Algorithms.java`.
All graph algorithms are written by hand. Only `java.util.Arrays` (sorting of primitive `long[]`, `copyOf`, `fill`) and `LinkedHashMap` (result container) are used; the priority queue (binary heap) and the hash set for the condensation are small primitive-array classes written in the same file.

## 0. Build, run and test commands

```sh
python tools/run.py --setup                        # compiles (javac --release 17) and checks ping -> {"status":"ready"}
python tools/run.py --check                        # 36 public cases + repeated-batch state-reset check
python tools/run.py --input tests/my_cases.jsonl   # actual output of my 32 hand-made requests
python tests/test_my_cases.py > tests/RESULTS.txt  # my own test-suite (80 checks); report saved
mkdir -p .build/bench && javac --release 17 -d .build/bench src/Java/*.java tests/Benchmark.java \
  && java -Xmx384m -cp .build/bench Benchmark > tests/BENCHMARK.txt     # Kruskal vs Prim benchmark
```

Manual build/run of the solution itself: `javac --release 17 -d .build/Java src/Java/*.java` and `java -Xmx384m -cp .build/Java Main < input.jsonl`.
Requirements: JDK 17+ and Python 3.12+ (Python only runs the supplied checker and my test driver).

Results actually obtained: `--setup` PASS; `--check` all 36 public cases PASS and the state-reset batch PASS; `tests/test_my_cases.py`: **80 passed, 0 failed** (`tests/RESULTS.txt`). The tests run with the same JVM flag as the checker, `-Xmx384m`, also at the full limits.

## 1. Shared design

**Adjacency (CSR).** `buildCsr(n, edges, mode)` builds compressed adjacency arrays `start` (n+1 offsets), `to` (head of each arc) and `eid` (**original edge ID** of each arc) by counting sort in `O(n + m)` time and memory. Modes: forward, transpose (for Kosaraju pass 2), and undirected without self-loops (for Prim). IDs therefore survive every restructuring.

**Deep graphs: no recursion anywhere.** Every DFS uses an explicit `int[]` stack plus a per-vertex pointer array `ptr[u]` (next unread arc of `u`). A suspended vertex keeps its progress in `ptr`, so each arc is read exactly once → `O(n+m)`; nothing is rescanned. The Java call stack has constant depth, so a 100 000-vertex chain works (tested for topo, scc, dag, route helper). DSU `find` is also iterative (find root, then compress). The supplied JSON parser recurses only over JSON nesting depth (≤ 3 here), not over the graph size.

**State reset.** There is no static mutable state. Every method allocates its own arrays from the request (`Input.*` converts the request to fresh `int` arrays), so requests cannot influence each other. Tested by running three identical mixed batches (including `ping`) in one JVM process, and tiny requests after a 50 000-vertex request.

**Integers and memory.** Costs and distances are `long` (sums up to 2.5·10¹⁴ are far from overflow); weights are offset by 10⁹ (`w + 10⁹` ∈ [0, 2·10⁹], computed in `long`) when packed into sort keys. Distances are returned as `Long[]` with `null` for unreachable vertices. Everything is stored in primitive arrays, so the full-limit requests (n = 100 000, m = 250 000) run inside `-Xmx384m`.

## 2. DSU (`dsu`)

**Steps.** `parent[i]=i`, `size[i]=1`, `components=n`, `largest=1` (0 when `n=0`). For each pair: `a=find(u)`, `b=find(v)`; if different, attach the smaller-size root under the larger (union by size), add sizes, `components--`, update `largest`; append `[components, largest]`.
**Invariant.** `parent` is a forest whose trees are exactly the current components; `size[root]` is the tree's vertex count; `components` is the number of roots; `largest` is the maximum root size (sizes only grow, so a running maximum is exact).
**Correctness.** Merging two different roots merges exactly two components; equal roots (repeated union, self-union) change nothing, so the previous state is repeated. Path compression re-points nodes to their root and never changes the partition. Size is stored separately and used directly, so `largest` is correct.
**Boundary cases.** `n=0` → `states=[]`; no operations → `states=[]` (no initial state); `n=1`, `[0,0]` → `[[1,1]]`; repeated and self unions.
**Complexity.** `O(n + q·α(n))` amortised time, `O(n+q)` memory including the `q` output states.

## 3. Kruskal (`kruskal`, core `kruskalCore`)

**Steps.** Pack every edge as the `long` key `((w + 10⁹) << 18) | id` (`id < 2¹⁸` because `m ≤ 250 000`) and sort the keys with `Arrays.sort(long[])`; the edge array itself is not reordered, so the ID is the original position. Scan the keys in order with a DSU and accept an edge iff `find(u) != find(v)`; sum weights in a `long`; `components = n − accepted`.
**Invariant.** After a prefix of the sorted order, the accepted edges form a minimum spanning forest of the graph made of that prefix, and DSU components equal the components of the accepted edges.
**Correctness.** Cycle property: an edge joining two vertices that are already connected closes a cycle and cannot be needed in an MSF built in nondecreasing order. A self-loop always has `find(u)==find(v)`, so it is never accepted even with a negative weight. Every accepted edge joins two components, so the result is acyclic with `n − c` edges. Negative weights need no special treatment because only the order matters (the offset preserves it).
**Boundary cases.** `n=0` → `cost=0, edge_ids=[], components=0`; isolates counted; parallel and equal-weight edges; negative self-loops; totals above 32 bit.
**Complexity.** `O(n + m log(m+1))` time, `O(n+m)` memory.

## 4. Prim (`prim`, core `primCore`)

**Steps.** Build the undirected CSR (both arcs of every non-loop edge, original ID kept). For every unvisited `root`: `components++`, mark it, push all its arcs; then loop: pop the minimum arc; if its head is already visited, skip it (lazy deletion); otherwise mark the head, add the weight, record the edge ID and push the head's arcs that lead to unvisited vertices. The heap is a hand-written binary min-heap on a `long[]` whose key is `((w + 10⁹) << 20) | arcIndex` (arc indices `< 2·250 000 < 2²⁰`); each arc is pushed at most once, so capacity `2m` suffices.
**Invariant.** The visited vertices `S` of the current component are spanned by the accepted edges, which form a tree contained in some minimum spanning tree of the component; the heap contains every arc crossing the cut `(S, rest)` (plus stale ones), so the first non-stale pop is a minimum crossing edge.
**Correctness.** Cut property: a minimum-weight edge across a cut belongs to some MST, so every accepted edge keeps the invariant; when only stale entries remain the component is spanned. The outer loop restarts at every unvisited vertex, so the result is a minimum spanning **forest**, and isolated vertices are single-vertex components counted by the restart.
**Boundary cases.** As for Kruskal, plus restarts for disconnected graphs and isolates (README example: vertex 3).
**Complexity.** Lazy heap: `O(n + m log(m+1))` time, `O(n+m)` memory.

## 5. Kosaraju SCC (`scc`)

**Steps.** (1) Iterative DFS on `G` from every vertex; a vertex is appended to `finish` when its adjacency is exhausted. (2) Build the transpose with `buildCsr(..., mode 1)`. (3) Take vertices in decreasing finish order; each still unlabelled one starts an iterative DFS on the transpose that labels everything newly reached with the next label `0,1,2,…`. (4) For every edge `(u,v)` with `component[u] != component[v]` insert the key `a·k + b` (`k` = number of labels) into a primitive open-addressing hash set (`LongSet`, capacity ≥ 2·number of cross edges); the set is decoded into `[a,b]` pairs. Keys are always positive because `a != b`, so `0` can mark an empty slot.
**Invariant.** When a root `r` is taken in pass 2, the labelled vertices are exactly those reachable in the transpose from earlier roots; `r` has the largest finish time among unlabelled vertices, so it is in a source SCC of the remaining condensation, and its transpose-reachable unlabelled set is exactly its SCC.
**Correctness.** Standard Kosaraju argument: for an edge `C → C'` between SCCs the maximum finish time in `C` exceeds that in `C'`. Labels are unique per SCC, isolates are singleton SCCs, internal edges and self-loops give `a == b` and are skipped, the hash set removes duplicate pairs.
**Boundary cases.** `n=0` → both arrays empty; duplicate edges; self-loops; one big cycle (one label, empty condensation); chain (n SCCs, n−1 pairs).
**Complexity.** `O(n+m)` expected time (hash-based deduplication), `O(n+m)` memory.

## 6. DFS topological order (`topo`)

**Steps.** `topologicalOrder`: three-state iterative DFS (0 unvisited, 1 active, 2 finished) from every unvisited vertex. For arc `u→v`: state 1 → directed cycle, return `null`; state 0 → push `v`; state 2 → ignore. When the adjacency of a vertex is exhausted it is marked finished and written into `order` from the back (`order[n-1-filled]`), i.e. the array already holds the reverse finish order. `topo` returns `acyclic=false, order=[]` for `null`.
**Invariant.** The stack contains exactly the active vertices and is a path of the DFS forest; a finished vertex has all out-neighbours finished.
**Correctness.** A directed cycle exists iff DFS meets an arc to an active vertex (back edge); a self-loop `u→u` hits `u` while active. An arc to a finished vertex (cross/forward edge, e.g. in a diamond) is not a cycle. Without back edges, `v` finishes before `u` for every arc `u→v`, so reverse finish order puts `u` before `v`.
**Boundary cases.** `n=0` → `acyclic=true, order=[]`; self-loop; a cycle in a later component (every component is started); diamond; duplicate edges; isolates (each appears once).
**Complexity.** `O(n+m)` time and memory (the `ptr` array prevents rescanning).

## 7. DAG shortest paths (`dag`) and the route helper

**Steps.** `topologicalOrder` over the **whole** graph; on a cycle return `acyclic=false, distance=[], parent_edge=[]`. Otherwise `reached[source]=true, dist[source]=0` and walk the topological order; skip a vertex that is not `reached` (**never relax from an unreachable vertex**); for every outgoing arc compute `dist[u] + w` (in `long`) and if `v` is not reached or the candidate is smaller, update `dist[v]` and `parentEdge[v]` with the **original edge ID**. Output: `distance` as `Long[]` with `null` for unreachable vertices, `parent_edge` as `int[]` (−1 for the source and unreachable vertices).
**Invariant.** When `u` is taken, all its predecessors in the order are processed, so `dist[u]` is final; `parentEdge[v]` is an edge ending at `v` with `dist[tail] + w = dist[v]` at the time of the update.
**Correctness.** In a DAG one relaxation of every arc in topological order suffices (negative weights allowed). Following parent edges moves strictly backwards in the topological order and therefore ends at the source. A separate `reached` flag is used instead of a sentinel, because `-1` (or any value) can be a real distance.
**Boundary cases.** `n=1`; cycle unreachable from the source (still `false`); self-loop; negative edge hanging off an unreachable vertex (vertex stays `null`); parallel/tied edges; sums above 32 bit (3·10⁹).
**Complexity.** `O(n+m)` time and memory.

### Route helper: `Algorithms.reconstructRoute(int source, int target, int[] parentEdge, int[][] edges)`

Returns the vertex array `source → … → target`. **No-route convention (my documented choice): an unreachable target returns an empty array (`new int[0]`).** The route to the source is `{source}`. The helper walks `parentEdge` backwards (`v ← edges[parentEdge[v]][0]`), verifies that every parent edge really ends at the current vertex and is a valid ID (otherwise it returns the empty array: invalid witness), then reverses: `O(L)` time and space for `L` vertices, iterative. JSON `distance` still uses `null` for unreachable vertices; the empty array is only the helper's convention.

Actual calls (`tests/RouteHelperTest.java`, driven by `tests/test_my_cases.py`; output in `tests/RESULTS.txt`):

| Case | Graph / `parent_edge` | Call | Result | Verification |
|---|---|---|---|---|
| reachable target | README graph, `parent_edge=[-1,0,2,3,-1]` | `reconstructRoute(0,3,…)` | `[0,1,2,3]`, edge IDs `[0,2,3]` | directions `0→1`, `1→2`, `2→3` correct; cost 3 + (−7) + 4 = **0** |
| source | same | `reconstructRoute(0,0,…)` | `[0]` | trivial route |
| unreachable target | same | `reconstructRoute(0,4,…)` | `[]` | `distance[4]=null`, `parent_edge[4]=-1` |
| tied / parallel | edges `[[0,1,2],[0,1,2],[0,2,4],[1,2,2]]`, program answered `parent_edge=[-1,0,2]` | `reconstructRoute(0,2,…)` | `[0,2]`, edge ID `[2]` | edge 2 is `0→2`, cost 4 = `distance[2]` |
| tied, other valid witness | same graph, `parent_edge=[-1,1,3]` | `reconstructRoute(0,2,…)` | `[0,1,2]`, edge IDs `[1,3]` | `0→1` (parallel edge 1, w 2) + `1→2` (w 2) = 4 |
| invalid witness | `parent_edge=[-1,0,0]` | `reconstructRoute(0,2,…)` | `[]` | edge 0 ends at vertex 1, not 2 → rejected |
| deep chain | 100 000-vertex chain | `reconstructRoute(0,99999,…)` | all 100 000 vertices in order | iterative, no stack overflow |

## 8. Tests (`tests/`)

| File | Content |
|---|---|
| `tests/test_my_cases.py` | all own tests; builds the Java solution with the supplied launcher logic, sends JSON lines to the real `Main`, prints `PASS/FAIL` and the reason of every hand-made case |
| `tests/RouteHelperTest.java` | Java driver that calls `Algorithms.reconstructRoute` directly |
| `tests/RESULTS.txt` | actual output of the last run (80 passed, 0 failed) |
| `tests/my_cases.jsonl` | the 32 hand-made requests for `python tools/run.py --input …` |
| `tests/Benchmark.java`, `tests/BENCHMARK.txt` | benchmark source and its output |

Coverage: (a) 32 hand-made requests with hand-derived expectations (a one-line justification is printed for each): empty graphs, no operations, isolates, repeated/self unions, loops, parallel/tied edges, negative weights, totals beyond 32 bit, unreachable vertices, a cycle unreachable from the source, a finished vertex (diamond) that is not a cycle; (b) up to 250 random small requests per task (215 for `dag`, because `n=0` has no source) checked against **independent brute-force oracles** (union relabelling for DSU, subset enumeration for MSF, transitive closure for SCC/topo, Bellman–Ford for DAG; seed 2026); (c) validator self-tests: alternative valid answers are accepted (tied forest edge, shifted SCC labels, another topological order, another tied parent) and invalid witnesses are rejected (wrong cost, cycle in forest, duplicate ID, merged SCCs, duplicate or reversed condensation pair, order violating an edge, parent edge ending elsewhere, non-tight parent, wrong distance); (d) full limits n = 100 000 with 250 000 edges/operations for every task (SCC verified by "every class strongly connected + condensation acyclic", DAG by an independent DP), deep chains of 100 000 vertices for topo/scc/dag/route helper/kruskal/prim, and a total of 99 999·10⁹; (e) state reset with repeated mixed batches including `ping`. At the full limits Kruskal and Prim return the same optimum (−52 825 034 977 141, 658 components) and both forests pass the validator; the same random input gave the same optimum in an earlier Python implementation of mine, which is an extra cross-check.

## 9. Benchmark: Kruskal vs Prim on the same graphs

Setup (printed by `tests/Benchmark.java`): OpenJDK 21.0.12 (compiled with `--release 17`), Linux x86-64, Intel Xeon @ 2.10 GHz virtual machine, 1 logical core, `-Xmx384m`; timer `System.nanoTime()`; **3 untimed warm-up calls** per method and size (JIT), **5 timed runs** per method per size, median reported; `System.gc()` before each timed run, outside the timer. Graphs: random multigraphs (loops and parallel edges possible), weights uniform in [−10⁹, 10⁹], generated by `new Random(20261025L)` in the order of the sizes below; both methods receive the **identical** `int[][]` edge list. **Timing boundary:** only `Algorithms.kruskalCore(n, edges)` / `Algorithms.primCore(n, edges)`; generation, JSON parsing, `Map → int[][]` conversion and JSON output are excluded for both; undirected CSR construction and the heap (Prim) and key packing, sorting and DSU (Kruskal) are inside each algorithm and included. Compilation is excluded. Before timing, both results were required to have equal cost and component count and both forests were validated (`n − c` edges, no repeated ID, acyclic, spanning, cost equals the sum).

| n | m | components | optimum cost | Kruskal runs (ms) | Kruskal median | Prim runs (ms) | Prim median |
|---:|---:|---:|---:|---|---:|---|---:|
| 1 000 | 5 000 | 1 | −770 758 789 312 | 1.3, 1.8, 0.6, 0.6, 0.5 | **0.6** | 1.5, 3.0, 0.9, 1.4, 1.6 | **1.5** |
| 10 000 | 50 000 | 1 | −7 595 720 050 042 | 17.5, 14.5, 14.6, 16.0, 15.7 | **15.7** | 16.4, 16.5, 17.6, 23.4, 18.7 | **17.6** |
| 100 000 | 250 000 | 643 | −52 957 153 367 008 | 43.2, 38.5, 29.1, 36.1, 30.7 | **36.1** | 74.2, 85.1, 64.6, 74.8, 69.6 | **74.2** |

**Asymptotic argument (separate from the measurements).** Both algorithms are `O(n + m log m)`; the logarithm comes from sorting (Kruskal) and heap operations (Prim). Both need `O(n+m)` memory.

**Observations.** Kruskal had the smaller median at all three sizes: about 2.5× (n = 1 000), 1.1× (n = 10 000) and 2.1× (n = 100 000). The ratio is not monotone in the size, so no trend should be read into three points. Prim's runs are also more spread out at each size (e.g. 64.6–85.1 ms at n = 100 000).

**Limitations.** (1) The measured gap is a constant-factor effect of these two implementations, not a different asymptotic class. A plausible reason is that Kruskal sorts a flat `long[]` and then runs a short DSU loop, while Prim first builds a `2m`-arc CSR and performs up to `2m` heap pushes and pops with many stale entries; I did not profile this, so it is a hypothesis. A dense graph or an indexed heap could change the ratio. (2) Only one graph family (random sparse multigraphs, average degree 10 or 5) and one machine (single-core virtual machine, so JIT and GC compete with the benchmark thread) were measured; the five runs of a size use one graph, so graph-to-graph variance is not captured. (3) The smallest size takes about 1 ms, close to timer/JIT/GC noise (single runs vary by a factor 3), so its medians are the least reliable. (4) Only three sizes; no claim about the exact growth rate is made.

## 10. Sources and AI assistance

* Algorithms follow the standard textbook descriptions (Kruskal, Prim, Kosaraju, DFS topological sort, DAG relaxation, DSU with union by size and path compression) and the assignment text in `README.md`. The JSON adapters (`Json.java`, `Input.java`, `Main.java`) are supplied by the template and unchanged.
* **My own verification:** *(fill in before submission — e.g. "I re-ran all commands of section 0 on my machine, read every algorithm and can explain it; my benchmark timings were: …". If you re-run the benchmark on your computer, replace the table in section 9 and the hardware line with your own numbers.)*
