import java.util.List;
import java.util.Map;
import java.util.StringJoiner;
import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;

/**
 * Test driver for Algorithms.reconstructRoute (the route helper is not a JSON task).
 * Reads JSON lines {"n","source","target","edges":[[u,v,w]...], optional "parent_edge":[...]}.
 * Without "parent_edge" the program first runs Algorithms.dag; with it, the given witness is used
 * (to show that other valid witnesses give valid routes and invalid ones are rejected).
 * Writes {"parent_edge":[...],"route":[...]} per line.   Used by tests/test_my_cases.py.
 */
public final class RouteHelperTest {
    public static void main(String[] args) throws IOException {
        BufferedReader in = new BufferedReader(new InputStreamReader(System.in, StandardCharsets.UTF_8));
        String line;
        while ((line = in.readLine()) != null) {
            Map<String, Object> request = Json.parseRequest(line);
            int source = Input.source(request);
            int target = ((Number) request.get("target")).intValue();
            int[][] edges = Input.edges(request);
            int[] parentEdge;
            if (request.containsKey("parent_edge")) {
                List<?> given = (List<?>) request.get("parent_edge");
                parentEdge = new int[given.size()];
                for (int i = 0; i < parentEdge.length; i++) {
                    parentEdge[i] = ((Number) given.get(i)).intValue();
                }
            } else {
                parentEdge = (int[]) Algorithms.dag(request).get("parent_edge");
            }
            int[] route = Algorithms.reconstructRoute(source, target, parentEdge, edges);
            StringJoiner out = new StringJoiner(",", "{", "}");
            out.add("\"parent_edge\":" + Json.write(parentEdge));
            out.add("\"route\":" + Json.write(route));
            System.out.println(out);
        }
    }
}
