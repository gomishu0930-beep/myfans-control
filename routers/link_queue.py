from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from database import get_db
from models import LinkQueueItem, CreatorCandidate, Creator

router = APIRouter()

LINK_TYPES = ["post_link", "creator_link", "top_link"]


@router.get("/link-queue")
async def link_queue_list(request: Request, status: str = "", db: Session = Depends(get_db)):
    from main import templates
    q = db.query(LinkQueueItem)
    if status:
        q = q.filter(LinkQueueItem.status == status)
    items = q.order_by(LinkQueueItem.created_at.desc()).all()

    candidates = db.query(CreatorCandidate).filter(
        CreatorCandidate.status == "approved"
    ).all()
    creators = db.query(Creator).all()

    pending_count = db.query(LinkQueueItem).filter(LinkQueueItem.status == "pending").count()
    generated_count = db.query(LinkQueueItem).filter(LinkQueueItem.status == "generated").count()

    return templates.TemplateResponse(request, "link_queue.html", {
        "items": items,
        "candidates": candidates,
        "creators": creators,
        "status_filter": status,
        "pending_count": pending_count,
        "generated_count": generated_count,
        "link_types": LINK_TYPES,
    })


@router.post("/link-queue/add")
async def link_queue_add(
    original_url: str = Form(...),
    link_type: str = Form("creator_link"),
    commission_rate: float = Form(10.0),
    creator_candidate_id: int = Form(None),
    creator_id: int = Form(None),
    memo: str = Form(""),
    db: Session = Depends(get_db),
):
    existing = db.query(LinkQueueItem).filter(LinkQueueItem.original_url == original_url).first()
    if not existing:
        item = LinkQueueItem(
            original_url=original_url,
            link_type=link_type,
            commission_rate=commission_rate,
            creator_candidate_id=creator_candidate_id if creator_candidate_id else None,
            creator_id=creator_id if creator_id else None,
            memo=memo,
            status="pending",
        )
        db.add(item)
        db.commit()
    return RedirectResponse("/link-queue", status_code=303)


@router.post("/link-queue/{item_id}/set-affiliate")
async def link_queue_set_affiliate(
    item_id: int,
    affiliate_url: str = Form(...),
    db: Session = Depends(get_db),
):
    item = db.query(LinkQueueItem).filter(LinkQueueItem.id == item_id).first()
    if item:
        item.affiliate_url = affiliate_url
        item.status = "generated"
        db.commit()
    return RedirectResponse("/link-queue", status_code=303)


@router.post("/link-queue/{item_id}/activate")
async def link_queue_activate(item_id: int, db: Session = Depends(get_db)):
    item = db.query(LinkQueueItem).filter(LinkQueueItem.id == item_id).first()
    if item:
        item.status = "active"
        item.active = True
        db.commit()
    return RedirectResponse("/link-queue", status_code=303)


@router.post("/link-queue/{item_id}/deactivate")
async def link_queue_deactivate(item_id: int, db: Session = Depends(get_db)):
    item = db.query(LinkQueueItem).filter(LinkQueueItem.id == item_id).first()
    if item:
        item.status = "inactive"
        item.active = False
        db.commit()
    return RedirectResponse("/link-queue", status_code=303)


@router.post("/link-queue/{item_id}/delete")
async def link_queue_delete(item_id: int, db: Session = Depends(get_db)):
    item = db.query(LinkQueueItem).filter(LinkQueueItem.id == item_id).first()
    if item:
        db.delete(item)
        db.commit()
    return RedirectResponse("/link-queue", status_code=303)
