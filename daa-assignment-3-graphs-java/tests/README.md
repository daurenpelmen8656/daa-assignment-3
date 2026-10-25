# My tests

| File | Purpose |
|---|---|
| `test_my_cases.py` | 80 checks against the Java solution: 32 hand-made cases with hand-derived answers, up to 250 random cases per task checked against brute-force oracles (seed 2026), validator self-tests (alternative valid answer accepted, invalid witness rejected), route-helper calls, state reset, full limits (n = 100 000, m = 250 000) and deep chains |
| `RouteHelperTest.java` | Java driver calling `Algorithms.reconstructRoute` directly |
| `RESULTS.txt` | actual output of `python tests/test_my_cases.py` |
| `my_cases.jsonl` | the hand-made requests: `python tools/run.py --input tests/my_cases.jsonl` prints the actual results |
| `Benchmark.java` / `BENCHMARK.txt` | Kruskal vs Prim at three sizes and its output |

Commands (repository root):

```sh
python tools/run.py --setup
python tools/run.py --check
python tests/test_my_cases.py
mkdir -p .build/bench && javac --release 17 -d .build/bench src/Java/*.java tests/Benchmark.java && java -Xmx384m -cp .build/bench Benchmark
```

Full explanation, expected answers and justifications: `ANALYSIS.md` (sections 7–9) and the `why:` lines in `RESULTS.txt`.
