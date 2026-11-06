"""
Graph algorithms, analysis, networkx integration, and background worker.
Covers features 31–40, 51–55, and 70.
"""
import heapq
import math
import threading
import networkx as nx
from networkx.algorithms.community import louvain_communities

DISTINCT_COLORS = [
    "#3b82f6", "#ef4444", "#10b981", "#f59e0b", "#8b5cf6",
    "#ec4899", "#14b8a6", "#f97316", "#06b6d4", "#84cc16",
    "#6366f1", "#d946ef", "#0ea5e9", "#eab308", "#a855f7",
]


def to_networkx(model, directed=True):
    """Convert GraphModel to NetworkX Graph or DiGraph."""
    G = nx.DiGraph() if directed else nx.Graph()
    for nid, n in model.nodes.items():
        G.add_node(nid, text=n["text"], x=n["x"], y=n["y"], shape=n["shape"], color=n["color"], tags=n.get("tags", []))
    for cid, c in model.conns.items():
        if c["a"] in model.nodes and c["b"] in model.nodes:
            weight = float(c.get("weight", 1.0))
            if weight <= 0:
                weight = 1.0
            G.add_edge(c["a"], c["b"], id=cid, weight=weight, label=c.get("label", ""), capacity=weight)
    return G


# ---- 31. A* Search
def a_star_search(model, start_id, goal_id):
    """A* shortest path using Euclidean distance as heuristic."""
    if start_id not in model.nodes or goal_id not in model.nodes:
        return None, 0.0

    target_pos = (model.nodes[goal_id]["x"], model.nodes[goal_id]["y"])

    def heuristic(u, v):
        nu = model.nodes[u]
        nv = model.nodes[v]
        return math.hypot(nu["x"] - nv["x"], nu["y"] - nv["y"])

    G = to_networkx(model, directed=True)
    try:
        path = nx.astar_path(G, start_id, goal_id, heuristic=heuristic, weight="weight")
        length = nx.astar_path_length(G, start_id, goal_id, heuristic=heuristic, weight="weight")
        # Find connection ids
        edge_ids = []
        for i in range(len(path) - 1):
            u, v = path[i], path[i + 1]
            # find edge in conns
            for cid, c in model.conns.items():
                if c["a"] == u and c["b"] == v:
                    edge_ids.append(cid)
                    break
        return path, length, edge_ids
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        return None, 0.0, []


# ---- 32. BFS / DFS Traversal Generators
def bfs_traversal_steps(model, start_id):
    """Yields (visited_nodes, current_node, current_edge_id) step-by-step."""
    G = to_networkx(model, directed=True)
    if start_id not in G:
        return []
    visited = set()
    queue = [start_id]
    visited.add(start_id)
    steps = [(list(visited), start_id, None)]

    while queue:
        curr = queue.pop(0)
        for nbr in G.successors(curr):
            if nbr not in visited:
                visited.add(nbr)
                queue.append(nbr)
                eid = G[curr][nbr].get("id")
                steps.append((list(visited), nbr, eid))
    return steps


def dfs_traversal_steps(model, start_id):
    """Yields (visited_nodes, current_node, current_edge_id) step-by-step."""
    G = to_networkx(model, directed=True)
    if start_id not in G:
        return []
    visited = set()
    steps = []

    def _dfs(u):
        visited.add(u)
        steps.append((list(visited), u, None))
        for v in G.successors(u):
            if v not in visited:
                eid = G[u][v].get("id")
                steps.append((list(visited), v, eid))
                _dfs(v)

    _dfs(start_id)
    return steps


# ---- 33. Minimum Spanning Tree (Kruskal / Prim)
def minimum_spanning_tree(model, algorithm="kruskal"):
    """Compute MST on undirected graph and return (mst_edge_ids, total_weight)."""
    G = to_networkx(model, directed=False)
    if len(G) == 0:
        return [], 0.0
    mst_edges = []
    total_weight = 0.0
    for comp in nx.connected_components(G):
        sub = G.subgraph(comp)
        T = nx.minimum_spanning_tree(sub, weight="weight", algorithm=algorithm)
        for u, v, data in T.edges(data=True):
            mst_edges.append(data.get("id"))
            total_weight += data.get("weight", 1.0)
    return mst_edges, total_weight


# ---- 34. Maximum Flow (Edmonds-Karp)
def maximum_flow(model, source_id, sink_id):
    """Computes max flow from source to sink using Edmonds-Karp."""
    G = to_networkx(model, directed=True)
    if source_id not in G or sink_id not in G:
        return 0.0, {}
    try:
        flow_value, flow_dict = nx.maximum_flow(G, source_id, sink_id, flow_func=nx.algorithms.flow.edmonds_karp)
        flow_value = float(flow_value)
        # map flow to connection ids
        edge_flows = {}
        for u in flow_dict:
            for v, fl in flow_dict[u].items():
                if fl > 0:
                    for cid, c in model.conns.items():
                        if c["a"] == u and c["b"] == v:
                            edge_flows[cid] = fl
                            break
        return flow_value, edge_flows
    except (nx.NetworkXError, nx.NetworkXUnbounded):
        return 0.0, {}


# ---- 35. Topological Sort
def topological_sort(model):
    """Returns (is_dag, order_list_or_cycle)."""
    G = to_networkx(model, directed=True)
    if not nx.is_directed_acyclic_graph(G):
        try:
            cycle = nx.find_cycle(G, orientation="original")
            return False, cycle
        except nx.NetworkXNoCycle:
            return False, []
    order = list(nx.topological_sort(G))
    return True, order


# ---- 36. Cycle Detection
def detect_cycles(model):
    """Returns list of cycles (each cycle is a list of node IDs and edge IDs)."""
    G = to_networkx(model, directed=True)
    try:
        cycles = list(nx.simple_cycles(G))
        # Find corresponding edge ids for the first few cycles
        cycle_edges = set()
        for cyc in cycles[:10]:
            for i in range(len(cyc)):
                u = cyc[i]
                v = cyc[(i + 1) % len(cyc)]
                for cid, c in model.conns.items():
                    if c["a"] == u and c["b"] == v:
                        cycle_edges.add(cid)
                        break
        cycle_nodes = set()
        for cyc in cycles:
            cycle_nodes.update(cyc)
        return list(cycle_nodes), list(cycle_edges), len(cycles)
    except Exception:
        return [], [], 0


# ---- 37. Connected Components
def connected_components(model):
    """Groups nodes into weakly connected components, returns {node_id: component_id}."""
    G = to_networkx(model, directed=False)
    comps = list(nx.connected_components(G))
    node_comp_map = {}
    for comp_idx, comp in enumerate(comps):
        for nid in comp:
            node_comp_map[nid] = comp_idx
    return node_comp_map, len(comps)


# ---- 38. Strongly Connected Components (Tarjan)
def strongly_connected_components(model):
    """Tarjan's algorithm for SCCs on directed graph."""
    G = to_networkx(model, directed=True)
    sccs = list(nx.strongly_connected_components(G))
    node_scc_map = {}
    for scc_idx, scc in enumerate(sccs):
        for nid in scc:
            node_scc_map[nid] = scc_idx
    return node_scc_map, len(sccs)


# ---- 39. Centrality Metrics
def compute_centrality(model, metric="degree"):
    """
    Computes centrality metric: 'degree', 'betweenness', 'closeness',
    'eigenvector', or 'pagerank'.
    Returns {node_id: score}.
    """
    G = to_networkx(model, directed=True)
    if len(G) == 0:
        return {}
    if metric == "betweenness":
        return nx.betweenness_centrality(G, weight="weight")
    elif metric == "closeness":
        return nx.closeness_centrality(G, distance="weight")
    elif metric == "eigenvector":
        try:
            return nx.eigenvector_centrality(G, max_iter=500, weight="weight")
        except Exception:
            return nx.degree_centrality(G)
    elif metric == "pagerank":
        node_ids = list(G)
        node_count = len(node_ids)
        outgoing = {node_id: {} for node_id in node_ids}
        for source, target, data in G.edges(data=True):
            outgoing[source][target] = data.get("weight", 1.0)

        scores = {node_id: 1.0 / node_count for node_id in node_ids}
        for _ in range(100):
            dangling_score = sum(
                scores[node_id] for node_id in node_ids if not outgoing[node_id]
            )
            updated = {
                node_id: (1.0 - 0.85) / node_count
                + 0.85 * dangling_score / node_count
                for node_id in node_ids
            }
            for source, targets in outgoing.items():
                total_weight = sum(targets.values())
                if total_weight:
                    for target, weight in targets.items():
                        updated[target] += 0.85 * scores[source] * weight / total_weight

            if sum(abs(updated[node_id] - scores[node_id]) for node_id in node_ids) < 1e-6 * node_count:
                return updated
            scores = updated

        raise nx.PowerIterationFailedConvergence(100)
    else:  # degree
        return nx.degree_centrality(G)


# ---- 40. Community Detection (Louvain)
def detect_communities(model):
    """Louvain community detection on undirected projection."""
    G = to_networkx(model, directed=False)
    if len(G) == 0:
        return {}, 0
    try:
        comms = louvain_communities(G, weight="weight", seed=42)
    except Exception:
        # fallback to connected components
        comms = list(nx.connected_components(G))
    node_comm_map = {}
    for c_idx, comm in enumerate(comms):
        for nid in comm:
            node_comm_map[nid] = c_idx
    return node_comm_map, len(comms)


# ---- 51–55. Graph Properties Panel
def compute_graph_properties(model):
    """
    Computes graph density, diameter, radius, clustering coefficient,
    path-length distribution, degree distribution.
    """
    G_dir = to_networkx(model, directed=True)
    G_undir = to_networkx(model, directed=False)
    n_nodes = len(G_dir)
    n_edges = len(model.conns)

    props = {
        "nodes": n_nodes,
        "edges": n_edges,
        "density": 0.0,
        "diameter": None,
        "radius": None,
        "avg_clustering": 0.0,
        "avg_path_length": None,
        "degree_hist": {},  # degree -> count
        "path_hist": {},  # length -> count
        "is_connected": False,
        "is_dag": False,
    }

    if n_nodes == 0:
        return props

    # Density
    props["density"] = nx.density(G_dir)
    props["is_dag"] = nx.is_directed_acyclic_graph(G_dir)

    # Degree distribution
    degrees = [d for _, d in G_dir.degree()]
    for d in degrees:
        props["degree_hist"][d] = props["degree_hist"].get(d, 0) + 1

    # Clustering
    try:
        props["avg_clustering"] = nx.average_clustering(G_undir)
    except Exception:
        props["avg_clustering"] = 0.0

    # Connectedness, Diameter, Radius, Path lengths on largest component
    if n_nodes > 1 and n_edges > 0:
        comps = list(nx.connected_components(G_undir))
        props["is_connected"] = len(comps) == 1
        largest_comp = max(comps, key=len)
        if len(largest_comp) > 1:
            sub = G_undir.subgraph(largest_comp)
            try:
                props["diameter"] = nx.diameter(sub)
                props["radius"] = nx.radius(sub)
                props["avg_path_length"] = round(nx.average_shortest_path_length(sub), 2)

                # Path length histogram
                lengths = dict(nx.all_pairs_shortest_path_length(sub))
                for u in lengths:
                    for v in lengths[u]:
                        if u < v:
                            l = lengths[u][v]
                            props["path_hist"][l] = props["path_hist"].get(l, 0) + 1
            except Exception:
                pass

    return props


# ---- 55. Isomorphism Check
def check_isomorphism(model, node_subset1, node_subset2):
    """Checks if two subgraphs formed by node_subset1 and node_subset2 are isomorphic."""
    G = to_networkx(model, directed=True)
    g1 = G.subgraph(node_subset1)
    g2 = G.subgraph(node_subset2)
    return nx.is_isomorphic(g1, g2)


# ---- 70. Background Recomputation
def run_in_background(task_fn, on_success, on_error=None):
    """Executes task_fn on a background daemon thread, then calls on_success(result) on Tk root via after."""
    def worker():
        try:
            res = task_fn()
            on_success(res)
        except Exception as e:
            if on_error:
                on_error(e)
            else:
                print("Background task error:", e)

    t = threading.Thread(target=worker, daemon=True)
    t.start()
    return t
