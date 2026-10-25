"""'Oilamga yuborib soʻray': share 1-4 products as a link and let family and friends vote."""
from flask import Blueprint, jsonify, request
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from ..auth import current_visitor
from ..models import Product, Share, ShareVote, db
from ..security import rate_limit
from ..services import product_card, public_products_query, record_event, reserved_counts
from ..utils import clean_str, error, parse_int, token

bp = Blueprint("shares", __name__, url_prefix="/api/shares")


def _ids(share):
    return [int(x) for x in share.product_ids.split(",") if x.isdigit()]


@bp.post("")
def create():
    limited = rate_limit("share", 30, 3600)
    if limited:
        return limited
    data = request.get_json(silent=True) or {}
    raw = data.get("product_ids") or []
    ids = []
    for value in raw if isinstance(raw, list) else []:
        pid = parse_int(value)
        if pid and pid not in ids:
            ids.append(pid)
    if not 1 <= len(ids) <= 4:
        return error("1 tadan 4 tagacha kiyim tanlang.", 400, "VALIDATION")
    s = db()
    products = s.scalars(public_products_query().where(Product.id.in_(ids))).all()
    if len(products) != len(ids):
        return error("Kiyim topilmadi.", 404, "NOT_FOUND")
    visitor = current_visitor()
    share = Share(token=token(9), product_ids=",".join(map(str, ids)), visitor=visitor,
                  question=clean_str(data.get("question"), 160) or "Qaysi biri menga yarashadi?")
    s.add(share)
    for p in products:
        record_event(s, "share", p.shop_id, p.id, visitor)
    s.commit()
    return jsonify(token=share.token, url=f"/s/{share.token}"), 201


@bp.get("/<share_token>")
def show(share_token):
    s = db()
    share = s.get(Share, share_token[:24])
    if share is None:
        return error("Havola topilmadi yoki oʻchirilgan.", 404, "NOT_FOUND")
    ids = _ids(share)
    products = {p.id: p for p in s.scalars(public_products_query().where(Product.id.in_(ids))
                                           .options(selectinload(Product.variants), selectinload(Product.shop)))}
    reserved = reserved_counts(s, [v.id for p in products.values() for v in p.variants])
    votes = dict(s.execute(select(ShareVote.product_id, func.count()).where(ShareVote.share_token == share.token)
                           .group_by(ShareVote.product_id)).all())
    mine = s.scalar(select(ShareVote.product_id).where(ShareVote.share_token == share.token,
                                                       ShareVote.voter == current_visitor()))
    items = [{**product_card(products[i], reserved), "votes": votes.get(i, 0)} for i in ids if i in products]
    return jsonify(question=share.question, items=items, my_vote=mine, total_votes=sum(votes.values()),
                   is_owner=share.visitor == current_visitor())


@bp.post("/<share_token>/vote")
def vote(share_token):
    limited = rate_limit("vote", 60, 3600)
    if limited:
        return limited
    s = db()
    share = s.get(Share, share_token[:24])
    if share is None:
        return error("Havola topilmadi.", 404, "NOT_FOUND")
    product_id = parse_int((request.get_json(silent=True) or {}).get("product_id"))
    if product_id not in _ids(share):
        return error("Bu kiyim soʻrovnomada yoʻq.", 400, "VALIDATION")
    voter = current_visitor()
    existing = s.scalar(select(ShareVote).where(ShareVote.share_token == share.token, ShareVote.voter == voter))
    if existing:
        existing.product_id = product_id
    else:
        s.add(ShareVote(share_token=share.token, product_id=product_id, voter=voter))
    try:
        s.commit()
    except IntegrityError:
        s.rollback()
    return show(share_token)
