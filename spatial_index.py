"""
Spatial Index for fast hit-testing, point queries, and viewport culling.
Uses a spatial hash grid for O(1) average lookup.
"""
import math


class SpatialGrid:
    def __init__(self, cell_size=120):
        self.cell_size = max(20, cell_size)
        self.grid = {}  # (cx, cy) -> set of (item_type, item_id)
        self.item_boxes = {}  # (item_type, item_id) -> (min_x, min_y, max_x, max_y)

    def _cells_for_box(self, x0, y0, x1, y1):
        cs = self.cell_size
        c_x0 = int(math.floor(x0 / cs))
        c_y0 = int(math.floor(y0 / cs))
        c_x1 = int(math.floor(x1 / cs))
        c_y1 = int(math.floor(y1 / cs))
        cells = []
        for cx in range(c_x0, c_x1 + 1):
            for cy in range(c_y0, c_y1 + 1):
                cells.append((cx, cy))
        return cells

    def clear(self):
        self.grid.clear()
        self.item_boxes.clear()

    def insert(self, item_type, item_id, x0, y0, x1, y1):
        key = (item_type, item_id)
        self.remove(item_type, item_id)
        min_x, max_x = (x0, x1) if x0 <= x1 else (x1, x0)
        min_y, max_y = (y0, y1) if y0 <= y1 else (y1, y0)
        self.item_boxes[key] = (min_x, min_y, max_x, max_y)
        for cell in self._cells_for_box(min_x, min_y, max_x, max_y):
            if cell not in self.grid:
                self.grid[cell] = set()
            self.grid[cell].add(key)

    def remove(self, item_type, item_id):
        key = (item_type, item_id)
        if key in self.item_boxes:
            box = self.item_boxes.pop(key)
            for cell in self._cells_for_box(*box):
                if cell in self.grid:
                    self.grid[cell].discard(key)
                    if not self.grid[cell]:
                        del self.grid[cell]

    def query_rect(self, x0, y0, x1, y1, item_type=None):
        """Return all item IDs whose bounding box overlaps (x0, y0, x1, y1)."""
        min_x, max_x = (x0, x1) if x0 <= x1 else (x1, x0)
        min_y, max_y = (y0, y1) if y0 <= y1 else (y1, y0)
        candidates = set()
        for cell in self._cells_for_box(min_x, min_y, max_x, max_y):
            if cell in self.grid:
                candidates.update(self.grid[cell])

        results = set()
        for key in candidates:
            itype, iid = key
            if item_type is not None and itype != item_type:
                continue
            bx0, by0, bx1, by1 = self.item_boxes[key]
            if not (max_x < bx0 or min_x > bx1 or max_y < by0 or min_y > by1):
                results.add(iid)
        return results

    def query_point(self, x, y, radius=5, item_type=None):
        """Return all item IDs within radius of (x, y)."""
        return self.query_rect(x - radius, y - radius, x + radius, y + radius, item_type=item_type)

