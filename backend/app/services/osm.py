"""Turning raw OpenStreetMap tags into ShadowMap categories."""

# Which OSM roads people can walk on. Motorways and roads under construction are left out.
WALKABLE = {
    "trunk", "trunk_link", "primary", "primary_link", "secondary", "secondary_link",
    "tertiary", "tertiary_link", "unclassified", "residential", "living_street", "service",
    "road", "pedestrian", "footway", "path", "track", "steps", "cycleway", "bridleway", "corridor",
}

MAIN = {"trunk", "trunk_link", "primary", "primary_link", "secondary", "secondary_link", "tertiary", "tertiary_link"}
RESIDENTIAL = {"unclassified", "residential", "living_street", "road"}
# everything else walkable (service, footway, path, track, steps, ...) counts as a lane or footpath


def road_class(tags: dict) -> str:
    """Blueprint §7 classes: main / residential / lane / underpass."""
    if tags.get("tunnel") in ("yes", "building_passage", "culvert") or tags.get("covered") == "yes":
        return "underpass"
    hw = tags.get("highway", "")
    if hw in MAIN:
        return "main"
    if hw in RESIDENTIAL:
        return "residential"
    return "lane"


CATEGORIES = ["police", "hospital", "clinic", "pharmacy", "fuel", "atm", "transit", "food_shop", "hotel"]


def place_category(tags: dict) -> str | None:
    """Blueprint §4 safe-place categories. Returns None for things that are not a place to walk into for help."""
    a, shop = tags.get("amenity"), tags.get("shop")
    if a == "police":
        return "police"
    if a == "hospital":
        return "hospital"
    if a in ("clinic", "doctors"):
        return "clinic"
    if a == "pharmacy" or shop == "chemist":
        return "pharmacy"
    if a == "fuel":
        return "fuel"
    if a == "atm" or (a == "bank" and tags.get("atm") == "yes"):
        return "atm"
    if tags.get("highway") == "bus_stop" or a == "bus_station" or tags.get("railway") in ("station", "halt"):
        return "transit"
    if a in ("restaurant", "cafe", "fast_food", "food_court") or shop:
        return "food_shop"
    if tags.get("tourism") in ("hotel", "guest_house", "hostel", "motel"):
        return "hotel"
    return None
