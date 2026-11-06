"""Local entity transforms and metric views for the OSINT sidebar."""
import ipaddress
import re
from urllib.parse import urlsplit

import algorithms


ENTITY_TYPES = {
    "Domain": {"icon": "🌐", "shape": "cloud", "color": "#dbeafe"},
    "URL": {"icon": "🔗", "shape": "rounded", "color": "#ccfbf1"},
    "IP Address": {"icon": "🖥️", "shape": "rectangle", "color": "#dcfce7"},
    "Email": {"icon": "✉️", "shape": "rounded", "color": "#fef9c3"},
    "Person": {"icon": "👤", "shape": "circle", "color": "#ede9fe"},
    "Organization": {"icon": "🏢", "shape": "rectangle", "color": "#fed7aa"},
    "Phone": {"icon": "📞", "shape": "rounded", "color": "#fee2e2"},
    "Location": {"icon": "📍", "shape": "diamond", "color": "#dbeafe"},
    "Username": {"icon": "👤", "shape": "circle", "color": "#ede9fe"},
    "Hash": {"icon": "#", "shape": "hexagon", "color": "#e2e8f0"},
}

_TRANSFORMS = {
    "Domain": (
        ("Create HTTPS URL", "domain_to_url"),
    ),
    "URL": (
        ("Extract hostname", "url_to_domain"),
    ),
    "Email": (
        ("Extract domain", "email_to_domain"),
        ("Extract username", "email_to_username"),
    ),
}

_COLOR_LOW = (219, 234, 254)
_COLOR_HIGH = (220, 38, 38)
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_DOMAIN_RE = re.compile(
    r"^(?=.{1,253}$)(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,63}$",
    re.IGNORECASE,
)


def detect_entity_type(value):
    """Classify common indicators locally without making network requests."""
    text = str(value).strip()
    if not text:
        return ""
    if _EMAIL_RE.fullmatch(text):
        return "Email"
    if text.lower().startswith(("http://", "https://", "www.")):
        return "URL"
    try:
        ipaddress.ip_address(text.strip("[]"))
        return "IP Address"
    except ValueError:
        pass
    compact = text.replace(":", "").replace("-", "").strip()
    if len(compact) in {32, 40, 64, 128} and re.fullmatch(r"[0-9a-fA-F]+", compact):
        return "Hash"
    if re.fullmatch(r"\+?[\d\s().-]{7,20}", text) and sum(char.isdigit() for char in text) >= 7:
        return "Phone"
    hostname = text.lower().removeprefix("https://").removeprefix("http://").split("/", 1)[0].split(":", 1)[0]
    if _DOMAIN_RE.fullmatch(hostname):
        return "Domain"
    return ""


class InvestigationEngine:
    @staticmethod
    def get_available_transforms(entity_type):
        return list(_TRANSFORMS.get(entity_type, ()))

    @staticmethod
    def run_transform(transform_key, node, model):
        value = str(node.get("text", "")).strip()
        if not value:
            return []

        if transform_key == "domain_to_url":
            hostname = value.removeprefix("https://").removeprefix("http://").rstrip("/")
            derived = [("URL", f"https://{hostname}", "website")]
        elif transform_key == "url_to_domain":
            parsed = urlsplit(value if "://" in value else f"//{value}")
            derived = [("Domain", parsed.hostname or "", "hostname")]
        elif transform_key == "email_to_domain" and "@" in value:
            derived = [("Domain", value.rsplit("@", 1)[1].strip().lower(), "email domain")]
        elif transform_key == "email_to_username" and "@" in value:
            derived = [("Username", value.rsplit("@", 1)[0].strip(), "email username")]
        else:
            return []

        derived = [(kind, text, label) for kind, text, label in derived if text]
        source_id = node.get("id")
        if source_id not in model.nodes:
            return []

        targets = []
        for entity_type, text, label in derived:
            existing_id = next(
                (
                    candidate_id
                    for candidate_id, candidate in model.nodes.items()
                    if candidate.get("entity_type") == entity_type
                    and candidate.get("text", "").casefold() == text.casefold()
                ),
                None,
            )
            targets.append((entity_type, text, label, existing_id))

        new_count = sum(existing_id is None for _, _, _, existing_id in targets)
        missing_connections = any(
            not any(
                connection["a"] == source_id and connection["b"] == existing_id
                for connection in model.conns.values()
            )
            for _, _, _, existing_id in targets
            if existing_id is not None
        )
        if new_count or missing_connections:
            model.push_undo()

        spawned = []
        for index, (entity_type, text, label, existing_id) in enumerate(targets):
            if existing_id is None:
                config = ENTITY_TYPES[entity_type]
                target_id = model.make_node(
                    node["x"] + 220,
                    node["y"] + index * 90,
                    text=text,
                    shape=config["shape"],
                    color=config["color"],
                    icon=config["icon"],
                    tags=[entity_type.casefold()],
                )
                model.nodes[target_id]["entity_type"] = entity_type
                spawned.append(target_id)
            else:
                target_id = existing_id

            if not any(
                connection["a"] == source_id and connection["b"] == target_id
                for connection in model.conns.values()
            ):
                model.make_conn(source_id, target_id, label=label)

        return spawned


def _metric_color(score, minimum, maximum):
    ratio = (score - minimum) / (maximum - minimum) if maximum > minimum else 0.5
    rgb = tuple(
        round(low + (high - low) * ratio)
        for low, high in zip(_COLOR_LOW, _COLOR_HIGH)
    )
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def apply_metric_view(model, metric="degree", mode="both"):
    if mode not in {"size", "color", "both"}:
        raise ValueError(f"Unsupported metric view mode: {mode}")

    scores = algorithms.compute_centrality(model, metric)
    if not scores:
        return

    minimum = min(scores.values())
    maximum = max(scores.values())
    max_score = max(maximum, 0)
    for node_id, score in scores.items():
        node = model.nodes.get(node_id)
        if node is None:
            continue
        if mode in {"size", "both"}:
            ratio = score / max_score if max_score > 0 else 0.5
            node["w"] = max(80.0, round(100.0 + 80.0 * ratio))
            node["h"] = max(40.0, round(50.0 + 40.0 * ratio))
            model.update_spatial_node(node_id)
        if mode in {"color", "both"}:
            node["color"] = _metric_color(score, minimum, maximum)
