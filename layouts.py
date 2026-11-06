"""
Layout algorithms and animated layout transitions.
Covers features 21–30.
"""
import math
from collections import deque
import networkx as nx
import numpy as np


def compute_fruchterman_reingold(model, node_ids, scale=350.0):
    """21. Force-directed layout using Fruchterman-Reingold physics simulation."""
    G = nx.Graph()
    for nid in node_ids:
        G.add_node(nid)
    for cid, c in model.conns.items():
        if c["a"] in node_ids and c["b"] in node_ids and c["a"] != c["b"]:
            G.add_edge(c["a"], c["b"], weight=float(c.get("weight", 1.0)))

    # initial positions if available
    init_pos = {nid: (model.nodes[nid]["x"], model.nodes[nid]["y"]) for nid in node_ids}
    k = max(120.0, math.sqrt(scale * scale * 4.0 / max(1, len(node_ids))))
    pos = nx.spring_layout(G, k=k, iterations=60, pos=init_pos, scale=scale)
    return {nid: (float(pos[nid][0]), float(pos[nid][1])) for nid in node_ids}


def compute_circular(model, node_ids, radius=None):
    """22. Circular layout — evenly space nodes on a circle."""
    n = len(node_ids)
    if n == 0:
        return {}
    if radius is None:
        radius = max(160.0, n * 32.0)
    pos = {}
    for idx, nid in enumerate(node_ids):
        angle = -math.pi / 2 + 2.0 * math.pi * idx / n
        pos[nid] = (radius * math.cos(angle), radius * math.sin(angle))
    return pos


def compute_grid(model, node_ids, cell_w=180.0, cell_h=120.0):
    """23. Grid layout — snap nodes into an N x M grid."""
    n = len(node_ids)
    if n == 0:
        return {}
    cols = math.ceil(math.sqrt(n))
    pos = {}
    for idx, nid in enumerate(node_ids):
        col = idx % cols
        row = idx // cols
        pos[nid] = (col * cell_w, row * cell_h)
    return pos


def compute_concentric(model, node_ids, ring_spacing=170.0):
    """Arrange nodes on rings according to distance from component centers."""
    if not node_ids:
        return {}
    idset = set(node_ids)
    order = {nid: index for index, nid in enumerate(node_ids)}
    adj = {nid: set() for nid in node_ids}
    for conn in model.conns.values():
        a, b = conn["a"], conn["b"]
        if a in idset and b in idset and a != b:
            adj[a].add(b)
            adj[b].add(a)

    distances = {}
    unseen = set(node_ids)
    while unseen:
        component_seed = min(unseen, key=order.get)
        component = []
        queue = deque([component_seed])
        unseen.remove(component_seed)
        while queue:
            nid = queue.popleft()
            component.append(nid)
            for neighbor in sorted(adj[nid], key=order.get):
                if neighbor in unseen:
                    unseen.remove(neighbor)
                    queue.append(neighbor)

        root = max(component, key=lambda nid: (len(adj[nid]), -order[nid]))
        queue = deque([(root, 0)])
        distances[root] = 0
        while queue:
            nid, depth = queue.popleft()
            for neighbor in adj[nid]:
                if neighbor not in distances:
                    distances[neighbor] = depth + 1
                    queue.append((neighbor, depth + 1))

    shells = {}
    for nid in node_ids:
        shells.setdefault(distances[nid], []).append(nid)

    positions = {}
    multiple_centers = len(shells.get(0, [])) > 1
    previous_radius = 0.0
    for depth in sorted(shells):
        shell = shells[depth]
        if depth == 0 and len(shell) == 1:
            positions[shell[0]] = (0.0, 0.0)
            continue
        node_span = max(
            max(model.nodes[nid].get("w", 130), model.nodes[nid].get("h", 60))
            for nid in shell
        )
        base_radius = ring_spacing * (depth + 1 if multiple_centers else depth)
        circumference_radius = node_span * len(shell) * 1.25 / (2.0 * math.pi)
        radius = max(base_radius, circumference_radius, previous_radius + node_span * 1.5)
        previous_radius = radius
        for index, nid in enumerate(shell):
            angle = -math.pi / 2 + 2.0 * math.pi * index / len(shell)
            positions[nid] = (radius * math.cos(angle), radius * math.sin(angle))
    return positions


def compute_spiral(model, node_ids, spacing=None):
    """Place breadth-first graph order along an expanding spiral."""
    if not node_ids:
        return {}
    idset = set(node_ids)
    order = {nid: index for index, nid in enumerate(node_ids)}
    adj = {nid: set() for nid in node_ids}
    for conn in model.conns.values():
        a, b = conn["a"], conn["b"]
        if a in idset and b in idset and a != b:
            adj[a].add(b)
            adj[b].add(a)

    traversal = []
    unseen = set(node_ids)
    roots = sorted(node_ids, key=lambda nid: (-len(adj[nid]), order[nid]))
    for root in roots:
        if root not in unseen:
            continue
        unseen.remove(root)
        queue = deque([root])
        while queue:
            nid = queue.popleft()
            traversal.append(nid)
            for neighbor in sorted(adj[nid], key=lambda item: (-len(adj[item]), order[item])):
                if neighbor in unseen:
                    unseen.remove(neighbor)
                    queue.append(neighbor)

    if spacing is None:
        largest_node = max(
            max(model.nodes[nid].get("w", 130), model.nodes[nid].get("h", 60))
            for nid in node_ids
        )
        spacing = max(110.0, largest_node * 1.15)
    golden_angle = math.pi * (3.0 - math.sqrt(5.0))
    return {
        nid: (
            spacing * math.sqrt(index) * math.cos(index * golden_angle),
            spacing * math.sqrt(index) * math.sin(index * golden_angle),
        )
        for index, nid in enumerate(traversal)
    }


def compute_hierarchical_sugiyama(model, node_ids, layer_dist=140.0, node_dist=180.0):
    """24. Hierarchical / Layered layout — Sugiyama-style DAG rendering."""
    if not node_ids:
        return {}
    idset = set(node_ids)
    out_edges = {i: [] for i in node_ids}
    in_edges = {i: [] for i in node_ids}
    indeg = {i: 0 for i in node_ids}

    for c in model.conns.values():
        if c["a"] in idset and c["b"] in idset and c["a"] != c["b"]:
            out_edges[c["a"]].append(c["b"])
            in_edges[c["b"]].append(c["a"])
            indeg[c["b"]] += 1

    # Layer assignment (longest path / topological depth)
    levels = {}
    roots = [i for i in node_ids if indeg[i] == 0]
    if not roots:
        roots = [node_ids[0]]

    queue = deque([(r, 0) for r in roots])
    for r in roots:
        levels[r] = 0

    while queue:
        u, d = queue.popleft()
        for v in out_edges[u]:
            if v not in levels or levels[v] < d + 1:
                levels[v] = d + 1
                queue.append((v, d + 1))

    # Catch any unvisited disconnected nodes
    for nid in node_ids:
        if nid not in levels:
            levels[nid] = 0

    max_lvl = max(levels.values()) if levels else 0
    layers = [[] for _ in range(max_lvl + 1)]
    for nid, lvl in levels.items():
        layers[lvl].append(nid)

    # Barycenter heuristic cross-reduction
    pos = {}
    xs = {}
    for lvl in range(max_lvl + 1):
        row = layers[lvl]
        if lvl > 0:
            def avg_parent_pos(node):
                parents = in_edges[node]
                known = [xs[p] for p in parents if p in xs]
                return sum(known) / len(known) if known else 0.0
            row.sort(key=avg_parent_pos)

        w = (len(row) - 1) * node_dist
        for idx, nid in enumerate(row):
            x = idx * node_dist - w / 2.0
            xs[nid] = x
            pos[nid] = (x, lvl * layer_dist)

    return pos


def compute_radial_tree(model, node_ids):
    """25. Radial tree layout — concentric rings outward from root."""
    if not node_ids:
        return {}
    idset = set(node_ids)
    adj = {i: [] for i in node_ids}
    for c in model.conns.values():
        if c["a"] in idset and c["b"] in idset and c["a"] != c["b"]:
            adj[c["a"]].append(c["b"])
            adj[c["b"]].append(c["a"])

    # Root selection: node with highest degree or first node
    root = max(node_ids, key=lambda i: len(adj[i]))

    # BFS tree levels
    visited = {root}
    tree_children = {i: [] for i in node_ids}
    queue = deque([root])
    while queue:
        curr = queue.popleft()
        for nbr in adj[curr]:
            if nbr not in visited:
                visited.add(nbr)
                tree_children[curr].append(nbr)
                queue.append(nbr)

    # Calculate subtree sizes
    def subtree_size(u):
        return 1 + sum(subtree_size(v) for v in tree_children[u])

    sizes = {i: subtree_size(i) for i in node_ids}

    pos = {root: (0.0, 0.0)}
    ring_spacing = 150.0

    def layout_radial_sector(node, depth, alpha1, alpha2):
        children = tree_children[node]
        if not children:
            return
        total_ch_size = sum(sizes[ch] for ch in children)
        curr_angle = alpha1
        r = depth * ring_spacing
        for ch in children:
            sector = (alpha2 - alpha1) * (sizes[ch] / total_ch_size)
            mid_angle = curr_angle + sector / 2.0
            pos[ch] = (r * math.cos(mid_angle), r * math.sin(mid_angle))
            layout_radial_sector(ch, depth + 1, curr_angle, curr_angle + sector)
            curr_angle += sector

    layout_radial_sector(root, 1, 0.0, 2.0 * math.pi)

    # Position unvisited nodes
    for nid in node_ids:
        if nid not in pos:
            pos[nid] = (0.0, 0.0)

    return pos


def compute_kamada_kawai(model, node_ids, scale=350.0):
    """26. Kamada–Kawai layout — energy-minimizing spring embedding."""
    G = nx.Graph()
    for nid in node_ids:
        G.add_node(nid)
    for c in model.conns.values():
        if c["a"] in node_ids and c["b"] in node_ids and c["a"] != c["b"]:
            G.add_edge(c["a"], c["b"], weight=float(c.get("weight", 1.0)))

    try:
        # Kamada-Kawai operates on connected components or graph
        if nx.is_connected(G):
            pos_dict = nx.kamada_kawai_layout(G, scale=scale)
        else:
            # layout each component
            pos_dict = {}
            comps = list(nx.connected_components(G))
            offset_x = 0
            for comp in comps:
                sub = G.subgraph(comp)
                sub_pos = nx.kamada_kawai_layout(sub, scale=scale * 0.7)
                for nid, (px, py) in sub_pos.items():
                    pos_dict[nid] = (px + offset_x, py)
                offset_x += scale * 1.5
        return {nid: (float(pos_dict[nid][0]), float(pos_dict[nid][1])) for nid in node_ids}
    except Exception:
        return compute_fruchterman_reingold(model, node_ids, scale=scale)


def compute_tutte_embedding(model, node_ids, radius=280.0):
    """27. Tutte embedding — convex planar layout."""
    if len(node_ids) < 3:
        return compute_circular(model, node_ids, radius)

    G = nx.Graph()
    for nid in node_ids:
        G.add_node(nid)
    for c in model.conns.values():
        if c["a"] in node_ids and c["b"] in node_ids and c["a"] != c["b"]:
            G.add_edge(c["a"], c["b"])

    # Find a boundary cycle
    boundary = None
    try:
        cycles = nx.cycle_basis(G)
        if cycles:
            boundary = max(cycles, key=len)
    except Exception:
        pass

    if not boundary or len(boundary) < 3:
        # fallback to circular
        return compute_circular(model, node_ids, radius)

    # Pin boundary nodes on a regular polygon
    pos = {}
    k_bound = len(boundary)
    for idx, nid in enumerate(boundary):
        ang = 2.0 * math.pi * idx / k_bound
        pos[nid] = (radius * math.cos(ang), radius * math.sin(ang))

    interior = [nid for nid in node_ids if nid not in boundary]
    if not interior:
        return pos

    # Interior nodes: x_i = (1 / deg(i)) * sum(x_j)
    # L * x = B_x, L * y = B_y
    idx_map = {nid: i for i, nid in enumerate(interior)}
    n_int = len(interior)
    L = np.eye(n_int)
    Bx = np.zeros(n_int)
    By = np.zeros(n_int)

    for nid in interior:
        i = idx_map[nid]
        neighbors = list(G.neighbors(nid))
        deg = len(neighbors)
        if deg == 0:
            continue
        weight = 1.0 / deg
        for nbr in neighbors:
            if nbr in pos:  # boundary node
                Bx[i] += weight * pos[nbr][0]
                By[i] += weight * pos[nbr][1]
            elif nbr in idx_map:  # interior node
                j = idx_map[nbr]
                L[i, j] -= weight

    try:
        sol_x = np.linalg.solve(L, Bx)
        sol_y = np.linalg.solve(L, By)
        for nid in interior:
            i = idx_map[nid]
            pos[nid] = (float(sol_x[i]), float(sol_y[i]))
    except np.linalg.LinAlgError:
        # Fallback if singular
        return compute_fruchterman_reingold(model, node_ids)

    return pos


def compute_orthogonal_routes(model):
    """28. Orthogonal routing — computes manhattan/right-angle waypoints for connections."""
    routes = {}
    for cid, c in model.conns.items():
        if c["a"] in model.nodes and c["b"] in model.nodes:
            na, nb = model.nodes[c["a"]], model.nodes[c["b"]]
            ax, ay, bx, by = na["x"], na["y"], nb["x"], nb["y"]
            dx, dy = bx - ax, by - ay
            if abs(dx) >= abs(dy):
                sg = 1 if dx >= 0 else -1
                s = (ax + sg * na["w"] / 2, ay)
                e = (bx - sg * nb["w"] / 2, by)
                mx = (s[0] + e[0]) / 2
                pts = [s, (mx, s[1]), (mx, e[1]), e]
            else:
                sg = 1 if dy >= 0 else -1
                s = (ax, ay + sg * na["h"] / 2)
                e = (bx, by - sg * nb["h"] / 2)
                my = (s[1] + e[1]) / 2
                pts = [s, (s[0], my), (e[0], my), e]
            routes[cid] = pts
    return routes


def auto_detect_preset(model, node_ids=None):
    """30. Layout presets by graph type — auto-pick layout based on structure."""
    if node_ids is None:
        node_ids = list(model.nodes.keys())
    if len(node_ids) < 2:
        return "grid"

    G_dir = nx.DiGraph()
    G_undir = nx.Graph()
    for nid in node_ids:
        G_dir.add_node(nid)
        G_undir.add_node(nid)
    for c in model.conns.values():
        if c["a"] in node_ids and c["b"] in node_ids and c["a"] != c["b"]:
            G_dir.add_edge(c["a"], c["b"])
            G_undir.add_edge(c["a"], c["b"])

    n_nodes = len(node_ids)
    n_edges = G_undir.number_of_edges()

    # Check if tree
    if nx.is_tree(G_undir):
        return "radial_tree"

    # Check if DAG
    if nx.is_directed_acyclic_graph(G_dir) and n_edges > 0:
        return "hierarchical"

    # Check if single cycle
    if n_nodes >= 3 and n_edges == n_nodes and nx.is_connected(G_undir):
        degrees = [d for _, d in G_undir.degree()]
        if all(d == 2 for d in degrees):
            return "circle"

    # Check if planar or dense
    if n_nodes > 6 and n_edges > n_nodes * 1.5:
        return "kamada_kawai"

    return "force_directed"


# ---- 29. Incremental layout / animated transitions
class LayoutAnimator:
    """Animates transitions between node positions smoothly over N frames."""
    def __init__(self, app, duration_ms=400, frames=18):
        self.app = app
        self.duration_ms = duration_ms
        self.frames = frames
        self.step_delay = max(10, duration_ms // frames)
        self.current_frame = 0
        self.start_positions = {}
        self.target_positions = {}
        self.timer_id = None

    def start(self, target_positions):
        if self.timer_id:
            self.app.root.after_cancel(self.timer_id)
            self.timer_id = None

        self.start_positions = {nid: (self.app.model.nodes[nid]["x"], self.app.model.nodes[nid]["y"])
                                for nid in target_positions if nid in self.app.model.nodes}
        self.target_positions = target_positions
        self.current_frame = 0
        self._step()

    def _step(self):
        self.current_frame += 1
        t = self.current_frame / self.frames
        # Smooth ease-in-out cosine interpolation
        ease_t = (1.0 - math.cos(t * math.pi)) / 2.0

        for nid, (tx, ty) in self.target_positions.items():
            if nid in self.app.model.nodes and nid in self.start_positions:
                sx, sy = self.start_positions[nid]
                self.app.model.nodes[nid]["x"] = round(sx + (tx - sx) * ease_t)
                self.app.model.nodes[nid]["y"] = round(sy + (ty - sy) * ease_t)
                self.app.model.update_spatial_node(nid)

        self.app.redraw()

        if self.current_frame < self.frames:
            self.timer_id = self.app.root.after(self.step_delay, self._step)
        else:
            self.timer_id = None
            self.app.model.mark_dirty if hasattr(self.app.model, "mark_dirty") else None
            self.app.fit()
