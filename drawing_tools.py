"""
Drawing Tools, Layers, Multi-page Document, and Brand Kit.
"""
import copy

# Extended Arrowhead Styles
ARROW_STYLES = ["forward", "backward", "both", "none", "diamond", "circle", "crowfoot"]

# Extended Shapes Library (Basic, Symbols, Flowchart, Callouts)
EXTENDED_SHAPES = {
    # Basic
    "rounded": {"name": "Rounded Box", "cat": "Basic"},
    "rectangle": {"name": "Rectangle", "cat": "Basic"},
    "square": {"name": "Square", "cat": "Basic"},
    "circle": {"name": "Circle", "cat": "Basic"},
    "diamond": {"name": "Diamond", "cat": "Basic"},
    "text": {"name": "Text Label", "cat": "Basic"},
    # Flowchart & Symbols
    "hexagon": {"name": "Hexagon", "cat": "Symbols"},
    "triangle": {"name": "Triangle", "cat": "Symbols"},
    "star": {"name": "Star", "cat": "Symbols"},
    "cloud": {"name": "Cloud", "cat": "Symbols"},
    "callout": {"name": "Callout / Speech Bubble", "cat": "Callouts"},
    "cylinder": {"name": "Database (Cylinder)", "cat": "Flowchart"},
    "parallelogram": {"name": "Data (Parallelogram)", "cat": "Flowchart"},
}


class BrandKit:
    """Centralized brand styles: palette, typography, and logos."""
    def __init__(self):
        self.colors = ["#2563eb", "#3b82f6", "#10b981", "#f59e0b", "#ef4444", "#111827", "#ffffff"]
        self.primary_font = "Helvetica"
        self.secondary_font = "Arial"
        self.logo_path = ""
        self.name = "My Brand Kit"

    def apply_to_model(self, model):
        """Applies primary brand colors to graph nodes."""
        model.push_undo()
        if not model.nodes:
            return
        palette = self.colors
        for idx, nid in enumerate(sorted(model.nodes.keys())):
            model.nodes[nid]["color"] = palette[idx % len(palette)]


class LayerManager:
    """Manages canvas layers: 'Background', 'Data', 'Annotations'."""
    def __init__(self, model=None):
        self.model = model
        defaults = {
            "Background": {"visible": True, "locked": False, "order": 0},
            "Data": {"visible": True, "locked": False, "order": 1},
            "Annotations": {"visible": True, "locked": False, "order": 2},
        }
        saved = model.settings.get("layers", {}) if model else {}
        self.layers = defaults
        for name, config in saved.items():
            if name in self.layers and isinstance(config, dict):
                self.layers[name].update(config)
        self.active_layer = "Data"

    def _save(self):
        if self.model is not None:
            self.model.settings["layers"] = copy.deepcopy(self.layers)
            self.model.dirty = True

    def is_visible(self, layer_name):
        return self.layers.get(layer_name, {}).get("visible", True)

    def is_locked(self, layer_name):
        return self.layers.get(layer_name, {}).get("locked", False)

    def toggle_visible(self, layer_name):
        if layer_name in self.layers:
            self.layers[layer_name]["visible"] = not self.layers[layer_name]["visible"]
            self._save()

    def toggle_locked(self, layer_name):
        if layer_name in self.layers:
            self.layers[layer_name]["locked"] = not self.layers[layer_name]["locked"]
            self._save()


class PageManager:
    """Manages multi-page documents (Pages 1, 2, 3...)."""
    def __init__(self, model):
        self.model = model
        default_page = {
            "nodes": copy.deepcopy(model.nodes),
            "conns": copy.deepcopy(model.conns),
            "sticky_notes": copy.deepcopy(model.sticky_notes),
            "freehand_strokes": copy.deepcopy(getattr(model, "freehand_strokes", [])),
        }
        saved_pages = getattr(model, "document_pages", {})
        self.pages = copy.deepcopy(saved_pages) if saved_pages else {
            "Page 1": {
                **default_page,
            }
        }
        for page in self.pages.values():
            for collection in ("nodes", "conns", "sticky_notes"):
                page[collection] = {
                    int(item.get("id", item_id)): item
                    for item_id, item in page.get(collection, {}).items()
                }
        self.current_page = getattr(model, "current_page", "Page 1")
        if self.current_page not in self.pages:
            self.current_page = next(iter(self.pages))
        current = self.pages[self.current_page]
        model.nodes = copy.deepcopy(current.get("nodes", {}))
        model.conns = copy.deepcopy(current.get("conns", {}))
        model.sticky_notes = copy.deepcopy(current.get("sticky_notes", {}))
        model.freehand_strokes = copy.deepcopy(current.get("freehand_strokes", []))
        model.rebuild_spatial_index()
        self.persist()

    def persist(self):
        self.pages[self.current_page] = {
            "nodes": copy.deepcopy(self.model.nodes),
            "conns": copy.deepcopy(self.model.conns),
            "sticky_notes": copy.deepcopy(self.model.sticky_notes),
            "freehand_strokes": copy.deepcopy(getattr(self.model, "freehand_strokes", [])),
        }
        self.model.document_pages = copy.deepcopy(self.pages)
        self.model.current_page = self.current_page

    def switch_page(self, page_name):
        if page_name == self.current_page or page_name not in self.pages:
            return
        # Save current page state
        self.pages[self.current_page] = {
            "nodes": copy.deepcopy(self.model.nodes),
            "conns": copy.deepcopy(self.model.conns),
            "sticky_notes": copy.deepcopy(self.model.sticky_notes),
            "freehand_strokes": copy.deepcopy(getattr(self.model, "freehand_strokes", [])),
        }
        # Load new page
        data = self.pages[page_name]
        self.model.nodes = copy.deepcopy(data["nodes"])
        self.model.conns = copy.deepcopy(data["conns"])
        self.model.sticky_notes = copy.deepcopy(data["sticky_notes"])
        self.model.freehand_strokes = copy.deepcopy(data.get("freehand_strokes", []))
        self.model.rebuild_spatial_index()
        self.current_page = page_name
        self.persist()

    def add_page(self, page_name=None):
        if not page_name:
            page_name = f"Page {len(self.pages) + 1}"
        self.pages[page_name] = {"nodes": {}, "conns": {}, "sticky_notes": {}, "freehand_strokes": []}
        self.switch_page(page_name)
        return page_name
