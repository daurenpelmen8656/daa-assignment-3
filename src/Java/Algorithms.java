import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.Map;

/**
 * Graph algorithms for Assignment 3: DSU, Kruskal, Prim, Kosaraju SCC, DFS topological order,
 * DAG shortest paths and a route-reconstruction helper.
 *
 * Design rules:
 *  - every DFS is iterative (explicit int stack + per-vertex pointer array), so deep graphs
 *    cannot overflow the call stack;
 *  - graphs are stored in compressed adjacency arrays (CSR) that keep the ORIGINAL edge ID;
 *  - no static mutable state: everything lives in local variables of the current request;
 *  - totals and distances use long.
 */
public final class Algorithms {
    private static final long W_OFFSET = 1_000_000_000L; // makes weights non-negative: 0..2e9

    private Algorithms() {
    }

    // ------------------------------------------------------------------------------------
    // Shared helpers
    // ------------------------------------------------------------------------------------

    /** Compressed adjacency lists. Arc p of vertex u lies in start[u]..start[u+1]-1. */
    static final class Csr {
        final int[] start;  // n + 1 offsets
        final int[] to;     // head of every arc
        final int[] eid;    // original edge ID of every arc

        Csr(int[] start, int[] to, int[] eid) {
            this.start = start;
            this.to = to;
            this.eid = eid;
        }
    }

    /**
     * Builds CSR by counting sort in O(n + m).
     * mode 0: u -> v;  mode 1: transpose (v -> u);  mode 2: undirected, both arcs, self-loops skipped.
     */
    static Csr buildCsr(int n, int[][] edges, int mode) {
        int[] start = new int[n + 1];
        for (int[] e : edges) {
            if (mode == 2) {
                if (e[0] != e[1]) {
                    start[e[0] + 1]++;
                    start[e[1] + 1]++;
                }
            } else {
                start[(mode == 0 ? e[0] : e[1]) + 1]++;
            }
        }
        for (int i = 0; i < n; i++) {
            start[i + 1] += start[i];
        }
        int arcs = start[n];
        int[] fill = Arrays.copyOf(start, n);
        int[] to = new int[arcs];
        int[] eid = new int[arcs];
        for (int i = 0; i < edges.length; i++) {
            int u = edges[i][0];
            int v = edges[i][1];
            if (mode == 2) {
                if (u != v) {
                    int p = fill[u]++;
                    to[p] = v;
                    eid[p] = i;
                    int q = fill[v]++;
                    to[q] = u;
                    eid[q] = i;
                }
            } else {
                int from = mode == 0 ? u : v;
                int head = mode == 0 ? v : u;
                int p = fill[from]++;
                to[p] = head;
                eid[p] = i;
            }
        }
        return new Csr(start, to, eid);
    }

    /**
     * Three-state iterative DFS over every component (0 unvisited, 1 active, 2 finished).
     * Returns a topological order, or null when a directed cycle exists.
     * ptr[u] stores how far the adjacency of a suspended vertex has been read: O(n + m).
     */
    static int[] topologicalOrder(int n, Csr g) {
        byte[] state = new byte[n];
        int[] ptr = Arrays.copyOf(g.start, n);
        int[] stack = new int[n];
        int[] order = new int[n];
        int filled = 0;                       // finish order is written backwards
        for (int root = 0; root < n; root++) {
            if (state[root] != 0) {
                continue;
            }
            int top = 0;
            stack[top++] = root;
            state[root] = 1;
            while (top > 0) {
                int u = stack[top - 1];
                int p = ptr[u];
                if (p < g.start[u + 1]) {
                    ptr[u] = p + 1;
                    int v = g.to[p];
                    if (state[v] == 1) {
                        return null;          // edge to an active vertex: directed cycle
                    }
                    if (state[v] == 0) {
                        state[v] = 1;
                        stack[top++] = v;
                    }                          // state 2: finished vertex, not a cycle
                } else {
                    state[u] = 2;
                    order[n - 1 - filled++] = u; // reverse finish order
                    top--;
                }
            }
        }
        return order;
    }

    private static int find(int[] parent, int x) {
        int root = x;
        while (parent[root] != root) {
            root = parent[root];
        }
        while (parent[x] != root) {           // path compression
            int next = parent[x];
            parent[x] = root;
            x = next;
        }
        return root;
    }

    // ------------------------------------------------------------------------------------
    // 1. DSU
    // ------------------------------------------------------------------------------------

    /** DSU with path compression and union by size/rank; return states. */
    static Map<String, Object> dsu(Map<String, Object> input) {
        int n = Input.vertexCount(input);
        int[][] operations = Input.operations(input);

        int[] parent = new int[n];
        int[] size = new int[n];
        for (int i = 0; i < n; i++) {
            parent[i] = i;
            size[i] = 1;
        }
        int components = n;
        int largest = n > 0 ? 1 : 0;
        int[][] states = new int[operations.length][];
        for (int i = 0; i < operations.length; i++) {
            int a = find(parent, operations[i][0]);
            int b = find(parent, operations[i][1]);
            if (a != b) {
                if (size[a] < size[b]) {       // union by size
                    int t = a;
                    a = b;
                    b = t;
                }
                parent[b] = a;
                size[a] += size[b];
                components--;
                if (size[a] > largest) {
                    largest = size[a];
                }
            }
            states[i] = new int[] {components, largest};
        }
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("states", states);
        return result;
    }

    // ------------------------------------------------------------------------------------
    // 2. Kruskal
    // ------------------------------------------------------------------------------------

    /** Separate Kruskal implementation; return cost, edge_ids, components. */
    static Map<String, Object> kruskal(Map<String, Object> input) {
        return kruskalCore(Input.vertexCount(input), Input.edges(input));
    }

    /** Kruskal on already converted input (also used by the benchmark). */
    static Map<String, Object> kruskalCore(int n, int[][] edges) {
        int m = edges.length;
        // Sort (weight, original id) packed in one long: id < 2^18 because m <= 250000.
        long[] keys = new long[m];
        for (int i = 0; i < m; i++) {
            keys[i] = ((edges[i][2] + W_OFFSET) << 18) | i;
        }
        Arrays.sort(keys);

        int[] parent = new int[n];
        int[] size = new int[n];
        for (int i = 0; i < n; i++) {
            parent[i] = i;
            size[i] = 1;
        }
        int[] chosen = new int[Math.max(0, n - 1)];
        int count = 0;
        long cost = 0;
        for (int k = 0; k < m; k++) {
            int id = (int) (keys[k] & ((1 << 18) - 1));
            int a = find(parent, edges[id][0]);
            int b = find(parent, edges[id][1]);
            if (a != b) {                      // self-loops always have a == b
                if (size[a] < size[b]) {
                    int t = a;
                    a = b;
                    b = t;
                }
                parent[b] = a;
                size[a] += size[b];
                cost += edges[id][2];
                chosen[count++] = id;
            }
        }
        return forest(cost, Arrays.copyOf(chosen, count), n - count);
    }

    private static Map<String, Object> forest(long cost, int[] ids, int components) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("cost", cost);
        result.put("edge_ids", ids);
        result.put("components", components);
        return result;
    }

    // ------------------------------------------------------------------------------------
    // 3. Prim (lazy binary heap on primitive longs, restarted in every component)
    // ------------------------------------------------------------------------------------

    /** Separate Prim implementation; restart for every unvisited component. */
    static Map<String, Object> prim(Map<String, Object> input) {
        return primCore(Input.vertexCount(input), Input.edges(input));
    }

    private static final int ARC_BITS = 20;                 // arcs <= 2 * 250000 < 2^20
    private static final long ARC_MASK = (1L << ARC_BITS) - 1;

    /** Prim on already converted input (also used by the benchmark). */
    static Map<String, Object> primCore(int n, int[][] edges) {
        Csr g = buildCsr(n, edges, 2);
        int arcs = g.to.length;
        long[] heap = new long[arcs + 1];     // every arc is pushed at most once
        int size = 0;
        boolean[] visited = new boolean[n];
        int[] chosen = new int[Math.max(0, n - 1)];
        int count = 0;
        long cost = 0;
        int components = 0;

        for (int root = 0; root < n; root++) {
            if (visited[root]) {
                continue;
            }
            components++;                     // restart: a new component begins here
            visited[root] = true;
            size = pushArcs(heap, size, g, edges, visited, root);
            while (size > 0) {
                long top = heap[0];           // pop minimum
                size--;
                if (size > 0) {
                    siftDown(heap, size, heap[size]);
                }
                int arc = (int) (top & ARC_MASK);
                int v = g.to[arc];
                if (visited[v]) {
                    continue;                 // stale entry (lazy deletion)
                }
                visited[v] = true;
                cost += (top >>> ARC_BITS) - W_OFFSET;
                chosen[count++] = g.eid[arc];
                size = pushArcs(heap, size, g, edges, visited, v);
            }
        }
        return forest(cost, Arrays.copyOf(chosen, count), components);
    }

    private static int pushArcs(long[] heap, int size, Csr g, int[][] edges, boolean[] visited, int u) {
        for (int p = g.start[u]; p < g.start[u + 1]; p++) {
            if (!visited[g.to[p]]) {
                long key = ((edges[g.eid[p]][2] + W_OFFSET) << ARC_BITS) | p;
                int i = size++;
                while (i > 0) {               // sift up
                    int parent = (i - 1) >> 1;
                    if (heap[parent] <= key) {
                        break;
                    }
                    heap[i] = heap[parent];
                    i = parent;
                }
                heap[i] = key;
            }
        }
        return size;
    }

    /** Places `key` at the root of a heap of `size` elements and restores heap order. */
    private static void siftDown(long[] heap, int size, long key) {
        int i = 0;
        while (true) {
            int child = 2 * i + 1;
            if (child >= size) {
                break;
            }
            if (child + 1 < size && heap[child + 1] < heap[child]) {
                child++;
            }
            if (heap[child] >= key) {
                break;
            }
            heap[i] = heap[child];
            i = child;
        }
        heap[i] = key;
    }

    // ------------------------------------------------------------------------------------
    // 4. Kosaraju SCC
    // ------------------------------------------------------------------------------------

    /** Kosaraju's two DFS passes; return component and exact condensation. */
    static Map<String, Object> scc(Map<String, Object> input) {
        int n = Input.vertexCount(input);
        int[][] edges = Input.edges(input);

        // Pass 1: finish order on G.
        Csr g = buildCsr(n, edges, 0);
        boolean[] seen = new boolean[n];
        int[] ptr = Arrays.copyOf(g.start, n);
        int[] stack = new int[n];
        int[] finish = new int[n];
        int finished = 0;
        for (int root = 0; root < n; root++) {
            if (seen[root]) {
                continue;
            }
            int top = 0;
            stack[top++] = root;
            seen[root] = true;
            while (top > 0) {
                int u = stack[top - 1];
                int p = ptr[u];
                if (p < g.start[u + 1]) {
                    ptr[u] = p + 1;
                    int v = g.to[p];
                    if (!seen[v]) {
                        seen[v] = true;
                        stack[top++] = v;
                    }
                } else {
                    finish[finished++] = u;
                    top--;
                }
            }
        }

        // Pass 2: DFS on the transpose in decreasing finish order.
        Csr t = buildCsr(n, edges, 1);
        int[] component = new int[n];
        Arrays.fill(component, -1);
        int labels = 0;
        for (int idx = n - 1; idx >= 0; idx--) {
            int root = finish[idx];
            if (component[root] != -1) {
                continue;
            }
            int top = 0;
            stack[top++] = root;
            component[root] = labels;
            while (top > 0) {
                int u = stack[--top];
                for (int p = t.start[u]; p < t.start[u + 1]; p++) {
                    int v = t.to[p];
                    if (component[v] == -1) {
                        component[v] = labels;
                        stack[top++] = v;
                    }
                }
            }
            labels++;
        }

        // Condensation: distinct cross-component pairs through a primitive hash set.
        long k = Math.max(labels, 1);
        int cross = 0;
        for (int[] e : edges) {
            if (component[e[0]] != component[e[1]]) {
                cross++;
            }
        }
        LongSet set = new LongSet(cross);
        for (int[] e : edges) {
            int a = component[e[0]];
            int b = component[e[1]];
            if (a != b) {
                set.add(a * k + b);           // always > 0 because a != b
            }
        }
        int[][] condensation = new int[set.size][];
        int out = 0;
        for (long key : set.table) {
            if (key != 0) {
                condensation[out++] = new int[] {(int) (key / k), (int) (key % k)};
            }
        }
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("component", component);
        result.put("condensation", condensation);
        return result;
    }

    /** Open-addressing hash set of positive longs (0 marks an empty slot). Expected O(1) add. */
    private static final class LongSet {
        final long[] table;
        final int mask;
        int size;

        LongSet(int expected) {
            int capacity = 16;
            while (capacity < 2L * expected) {
                capacity <<= 1;
            }
            table = new long[capacity];
            mask = capacity - 1;
        }

        void add(long key) {
            int i = (int) ((key * 0x9E3779B97F4A7C15L) >>> 40) & mask;
            while (table[i] != 0) {
                if (table[i] == key) {
                    return;
                }
                i = (i + 1) & mask;
            }
            table[i] = key;
            size++;
        }
    }

    // ------------------------------------------------------------------------------------
    // 5. DFS topological order
    // ------------------------------------------------------------------------------------

    /** Three-state DFS and reverse finish order; return acyclic and order. */
    static Map<String, Object> topo(Map<String, Object> input) {
        int n = Input.vertexCount(input);
        int[][] edges = Input.edges(input);

        int[] order = topologicalOrder(n, buildCsr(n, edges, 0));
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("acyclic", order != null);
        result.put("order", order != null ? order : new int[0]);
        return result;
    }

    // ------------------------------------------------------------------------------------
    // 6. DAG shortest paths and route helper
    // ------------------------------------------------------------------------------------

    /** Whole-graph cycle check and DAG relaxation; return acyclic, distance, parent_edge. */
    static Map<String, Object> dag(Map<String, Object> input) {
        int n = Input.vertexCount(input);
        int source = Input.source(input);
        int[][] edges = Input.edges(input);

        Csr g = buildCsr(n, edges, 0);
        int[] order = topologicalOrder(n, g);       // checks EVERY component, not only source's
        Map<String, Object> result = new LinkedHashMap<>();
        if (order == null) {
            result.put("acyclic", false);
            result.put("distance", new Long[0]);
            result.put("parent_edge", new int[0]);
            return result;
        }
        long[] dist = new long[n];
        boolean[] reached = new boolean[n];
        int[] parentEdge = new int[n];
        Arrays.fill(parentEdge, -1);
        reached[source] = true;
        for (int idx = 0; idx < n; idx++) {
            int u = order[idx];
            if (!reached[u]) {
                continue;                           // never relax from an unreachable vertex
            }
            for (int p = g.start[u]; p < g.start[u + 1]; p++) {
                int v = g.to[p];
                long candidate = dist[u] + edges[g.eid[p]][2];
                if (!reached[v] || candidate < dist[v]) {
                    reached[v] = true;
                    dist[v] = candidate;
                    parentEdge[v] = g.eid[p];       // original edge ID, not a vertex
                }
            }
        }
        Long[] distance = new Long[n];
        for (int v = 0; v < n; v++) {
            distance[v] = reached[v] ? Long.valueOf(dist[v]) : null; // unreachable -> JSON null
        }
        result.put("acyclic", true);
        result.put("distance", distance);
        result.put("parent_edge", parentEdge);
        return result;
    }

    /**
     * Route helper: vertex sequence source -> ... -> target built from parent_edge IDs.
     * Route to the source itself is {source}. NO-ROUTE CONVENTION: an unreachable target (or a
     * corrupted witness) returns an EMPTY array. O(L) time and space for L vertices.
     */
    static int[] reconstructRoute(int source, int target, int[] parentEdge, int[][] edges) {
        if (target == source) {
            return new int[] {source};
        }
        if (parentEdge[target] == -1) {
            return new int[0];
        }
        int[] buffer = new int[parentEdge.length + 1];
        int length = 0;
        int v = target;
        buffer[length++] = v;
        while (v != source) {
            int id = parentEdge[v];
            if (id < 0 || id >= edges.length || edges[id][1] != v || length > parentEdge.length) {
                return new int[0];                  // edge does not end at v: invalid witness
            }
            v = edges[id][0];
            buffer[length++] = v;
        }
        int[] route = new int[length];
        for (int i = 0; i < length; i++) {
            route[i] = buffer[length - 1 - i];      // reverse
        }
        return route;
    }
}
