"""AI stylist API: profile in, analysis + outfit from in-stock products out. Nothing is stored."""
from flask import Blueprint, current_app, jsonify, request

from .. import stylist
from ..models import db
from ..security import rate_limit
from ..utils import OCCASIONS, SEASONS, error, parse_float
from .catalog import find_products

bp = Blueprint("stylist", __name__, url_prefix="/api/stylist")


@bp.get("/options")
def options():
    cfg = current_app.config["CLOTHES"]
    return jsonify(
        skin_tones=[{"key": k, "label": v} for k, v in stylist.SKIN_TONES.items()],
        seasons=[{"key": k, "label": v} for k, v in SEASONS.items()],
        occasions=[{"key": k, "label": v} for k, v in OCCASIONS.items()],
        current_season=stylist.current_season(),
        ai=cfg.STYLIST_PROVIDER == "anthropic",
    )


@bp.post("")
def recommend():
    cfg = current_app.config["CLOTHES"]
    use_ai = cfg.STYLIST_PROVIDER == "anthropic"
    limited = rate_limit("stylist-ai" if use_ai else "stylist", 15 if use_ai else 60, 3600)
    if limited:
        return limited
    data = request.get_json(silent=True) or {}
    try:
        profile = stylist.parse_profile(data)
    except stylist.ProfileError as exc:
        return error(str(exc), 400, "VALIDATION")
    lat, lng = parse_float(data.get("lat"), -90, 90), parse_float(data.get("lng"), -180, 180)
    filters = {"q": "", "categories": [], "colors": [], "size": "", "min_price": None, "max_price": None,
               "shop": "", "in_stock": True, "point": (lat, lng) if lat is not None and lng is not None else None,
               "radius_km": None}
    rows = find_products(db(), filters)
    analysis = stylist.analyse(profile)
    picks, by_slot = stylist.build_outfit(rows, profile, analysis)

    engine, summary, tips, color_note, why = "rules", None, analysis["tips"], analysis["palette"]["note"], {}
    if use_ai and picks:
        refined = stylist.ai_refine(cfg, profile, analysis, by_slot, picks)
        if refined:
            picks, summary, ai_tips, ai_color, why = refined
            engine = "ai"
            tips = ai_tips or tips
            color_note = ai_color or color_note
    items, missing = stylist.outfit_payload(picks, by_slot, analysis)
    for item in items:
        if why.get(item["slot"]):
            item["why"] = why[item["slot"]]
    if not summary:
        summary = stylist.rules_summary(profile, analysis, items) if items else \
            "Hozircha katalogda sizning oʻlchamingiz va faslingizga mos kiyim topilmadi."
    total = sum(i["product"]["price"] for i in items)
    return jsonify(engine=engine, profile=profile, analysis=analysis | {"tips": tips, "color_note": color_note},
                   summary=summary, outfit=items, missing=missing, total_price=total,
                   over_budget=bool(profile["budget"] and total > profile["budget"]))
