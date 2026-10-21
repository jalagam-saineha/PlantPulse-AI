"""
Transparent Visual Health Score.

The score is a weighted combination of four components, each derived
directly from the computer-vision measurements — never randomly assigned.
This is explicitly a *visual screening* score, not a validated
agricultural/scientific diagnostic.
"""

WEIGHTS = {
    "leaf_vitality": 0.40,
    "color_health": 0.25,
    "damage_condition": 0.20,
    "spot_condition": 0.15,
}


def compute_health_score(metrics: dict) -> dict:
    leaf_coverage = metrics.get("leaf_coverage") or 0.0
    yellowing = metrics.get("yellowing") or 0.0
    damage = metrics.get("damage") or 0.0
    dark_spots = metrics.get("dark_spots") or 0.0

    leaf_vitality = max(0.0, min(100.0, leaf_coverage))
    color_health = max(0.0, 100.0 - yellowing * 1.3)
    damage_condition = max(0.0, 100.0 - damage * 1.6)
    spot_condition = max(0.0, 100.0 - dark_spots * 1.8)

    overall = (
        WEIGHTS["leaf_vitality"] * leaf_vitality
        + WEIGHTS["color_health"] * color_health
        + WEIGHTS["damage_condition"] * damage_condition
        + WEIGHTS["spot_condition"] * spot_condition
    )
    overall = round(max(0.0, min(100.0, overall)), 1)

    if overall >= 85:
        label = "Excellent Visual Condition"
    elif overall >= 70:
        label = "Good Visual Condition"
    elif overall >= 50:
        label = "Fair Visual Condition — worth monitoring"
    else:
        label = "Poor Visual Condition — visible stress detected"

    return {
        "overall": overall,
        "label": label,
        "components": {
            "leaf_vitality": round(leaf_vitality, 1),
            "color_health": round(color_health, 1),
            "damage_condition": round(damage_condition, 1),
            "spot_condition": round(spot_condition, 1),
        },
        "weights": WEIGHTS,
    }
