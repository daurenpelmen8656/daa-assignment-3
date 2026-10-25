import java.io.BufferedReader;
import java.io.FileReader;
import java.io.IOException;
import java.util.Arrays;
import java.util.Map;
import java.util.Random;

/**
 * Kruskal vs Prim on IDENTICAL graphs at three sizes.
 *
 * Build and run (repository root; compilation is NOT timed):
 *   javac --release 17 -d .build/bench src/Java/*.java tests/Benchmark.java
 *   java -Xmx384m -cp .build/bench Benchmark > tests/BENCHMARK.txt
 *
 * Timing boundary: only Algorithms.kruskalCore(n, edges) / Algorithms.primCore(n, edges) on an
 * already converted int[][] edge list, measured with System.nanoTime(). Graph generation, JSON
 * parsing, Map -> int[][] conversion and JSON output are excluded for BOTH methods; CSR/adjacency
 * construction (Prim) and sorting + DSU (Kruskal) are part of each algorithm and included.
 * 3 untimed warm-up calls per method and size (JIT), then 5 timed calls; System.gc() runs before
 * every timed call, outside the timer. Both forests are validated before timing.
 */
public final class Benchmark {
    private static final long SEED = 20261025L;
    private static final int[][] SIZES = {{1_000, 5_000}, {10_000, 50_000}, {100_000, 250_000}};
    private static final int WARMUPS = 3;
    private static final int RUNS = 5;

    public static void main(String[] args) throws IOException {
        System.out.println("Environment");
        System.out.println("  java     : " + System.getProperty("java.version") + " (" + System.getProperty("java.vm.name") + ")");
        System.out.println("  os       : " + System.getProperty("os.name") + " " + System.getProperty("os.version") + " " + System.getProperty("os.arch"));
        System.out.println("  cpu      : " + cpuName() + " (logical cores: " + Runtime.getRuntime().availableProcessors() + ")");
        System.out.println("  heap     : max " + Runtime.getRuntime().maxMemory() / (1024 * 1024) + " MiB (run with -Xmx384m like tools/run.py)");
        System.out.println("  timer    : System.nanoTime(); " + WARMUPS + " untimed warm-ups + " + RUNS + " timed runs per method per size; System.gc() before each timed run (outside the timer)");
        System.out.println("  seed     : new Random(" + SEED + "L) generates the three graphs in order; weights uniform in [-1e9, 1e9]");
        System.out.println("  boundary : only Algorithms.kruskalCore / primCore on a ready int[][] (no generation, JSON, conversion); compilation excluded");
        System.out.println("  command  : javac --release 17 -d .build/bench src/Java/*.java tests/Benchmark.java && java -Xmx384m -cp .build/bench Benchmark");
        System.out.println();
        System.out.printf("%8s %8s | %-8s %-46s %10s | cost / components%n", "n", "m", "method", "runs (ms)", "median ms");

        Random random = new Random(SEED);
        for (int[] size : SIZES) {
            int n = size[0];
            int m = size[1];
            int[][] edges = new int[m][];
            for (int i = 0; i < m; i++) {
                edges[i] = new int[] {random.nextInt(n), random.nextInt(n), random.nextInt(2_000_000_001) - 1_000_000_000};
            }
            Map<String, Object> k = Algorithms.kruskalCore(n, edges);
            Map<String, Object> p = Algorithms.primCore(n, edges);
            long cost = (Long) k.get("cost");
            int components = (Integer) k.get("components");
            if (cost != (Long) p.get("cost") || components != (Integer) p.get("components")) {
                throw new AssertionError("Kruskal and Prim disagree");
            }
            validate(n, edges, k, cost, components);
            validate(n, edges, p, cost, components);
            for (String method : new String[] {"kruskal", "prim"}) {
                for (int i = 0; i < WARMUPS; i++) {
                    run(method, n, edges);
                }
                double[] ms = new double[RUNS];
                for (int i = 0; i < RUNS; i++) {
                    System.gc();
                    long t = System.nanoTime();
                    run(method, n, edges);
                    ms[i] = (System.nanoTime() - t) / 1e6;
                }
                double[] sorted = ms.clone();
                Arrays.sort(sorted);
                StringBuilder runs = new StringBuilder();
                for (int i = 0; i < RUNS; i++) {
                    runs.append(i == 0 ? "" : ", ").append(String.format("%.1f", ms[i]));
                }
                System.out.printf("%8d %8d | %-8s %-46s %10.1f | %d / %d%n", n, m, method, runs, sorted[RUNS / 2], cost, components);
            }
        }
        System.out.println();
        System.out.println("Both methods returned the same cost and component count on every graph, and both forests were valid.");
    }

    private static Map<String, Object> run(String method, int n, int[][] edges) {
        return method.equals("kruskal") ? Algorithms.kruskalCore(n, edges) : Algorithms.primCore(n, edges);
    }

    /** Independent check: n - c edges, no cycle, spanning every component, sum equals cost. */
    private static void validate(int n, int[][] edges, Map<String, Object> result, long cost, int components) {
        int[] ids = (int[]) result.get("edge_ids");
        if (ids.length != n - components) {
            throw new AssertionError("wrong edge count");
        }
        int[] parent = new int[n];
        for (int i = 0; i < n; i++) {
            parent[i] = i;
        }
        long sum = 0;
        boolean[] used = new boolean[edges.length];
        for (int id : ids) {
            if (used[id]) {
                throw new AssertionError("repeated edge ID");
            }
            used[id] = true;
            int a = root(parent, edges[id][0]);
            int b = root(parent, edges[id][1]);
            if (a == b) {
                throw new AssertionError("cycle in forest");
            }
            parent[a] = b;
            sum += edges[id][2];
        }
        if (sum != cost) {
            throw new AssertionError("cost mismatch");
        }
        for (int[] e : edges) {
            if (root(parent, e[0]) != root(parent, e[1])) {
                throw new AssertionError("forest does not span a component");
            }
        }
    }

    private static int root(int[] parent, int x) {
        while (parent[x] != x) {
            parent[x] = parent[parent[x]];
            x = parent[x];
        }
        return x;
    }

    private static String cpuName() {
        try (BufferedReader in = new BufferedReader(new FileReader("/proc/cpuinfo"))) {
            String line;
            while ((line = in.readLine()) != null) {
                if (line.startsWith("model name")) {
                    return line.substring(line.indexOf(':') + 1).trim();
                }
            }
        } catch (IOException ignored) {
            // fall through
        }
        return "unknown";
    }
}
