from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse, StreamingResponse
from sqlalchemy.orm import Session
from database import get_db
from models import AffiliateLink, Creator
from datetime import datetime
import pandas as pd
import io

router = APIRouter()


@router.get("/links")
async def links_list(request: Request, db: Session = Depends(get_db)):
    from main import templates
    links = db.query(AffiliateLink).order_by(AffiliateLink.created_at.desc()).all()
    creators = db.query(Creator).filter(Creator.affiliate_enabled == True).all()
    return templates.TemplateResponse(request, "links.html", {
        "links": links,
        "creators": creators,
    })


@router.post("/links/new")
async def link_create(
    request: Request,
    creator_id: int = Form(...),
    original_url: str = Form(...),
    affiliate_url: str = Form(...),
    link_type: str = Form("creator_link"),
    estimated_rate: float = Form(10.0),
    cookie_hours: int = Form(720),
    approved_media_name: str = Form(""),
    active: bool = Form(False),
    memo: str = Form(""),
    db: Session = Depends(get_db)
):
    link = AffiliateLink(
        creator_id=creator_id,
        original_url=original_url,
        affiliate_url=affiliate_url,
        link_type=link_type,
        estimated_rate=estimated_rate,
        cookie_hours=cookie_hours,
        approved_media_name=approved_media_name,
        active=active,
        memo=memo,
    )
    db.add(link)
    db.commit()
    return RedirectResponse("/links", status_code=303)


@router.post("/links/{link_id}/edit")
async def link_update(
    link_id: int,
    creator_id: int = Form(...),
    original_url: str = Form(...),
    affiliate_url: str = Form(...),
    link_type: str = Form("creator_link"),
    estimated_rate: float = Form(10.0),
    cookie_hours: int = Form(720),
    approved_media_name: str = Form(""),
    active: bool = Form(False),
    memo: str = Form(""),
    db: Session = Depends(get_db)
):
    link = db.query(AffiliateLink).filter(AffiliateLink.id == link_id).first()
    if link:
        link.creator_id = creator_id
        link.original_url = original_url
        link.affiliate_url = affiliate_url
        link.link_type = link_type
        link.estimated_rate = estimated_rate
        link.cookie_hours = cookie_hours
        link.approved_media_name = approved_media_name
        link.active = active
        link.memo = memo
        link.updated_at = datetime.utcnow()
        db.commit()
    return RedirectResponse("/links", status_code=303)


@router.post("/links/{link_id}/delete")
async def link_delete(link_id: int, db: Session = Depends(get_db)):
    link = db.query(AffiliateLink).filter(AffiliateLink.id == link_id).first()
    if link:
        db.delete(link)
        db.commit()
    return RedirectResponse("/links", status_code=303)


@router.post("/links/{link_id}/toggle")
async def link_toggle(link_id: int, db: Session = Depends(get_db)):
    link = db.query(AffiliateLink).filter(AffiliateLink.id == link_id).first()
    if link:
        link.active = not link.active
        db.commit()
    return RedirectResponse("/links", status_code=303)


@router.get("/links/export/csv")
async def links_export(db: Session = Depends(get_db)):
    links = db.query(AffiliateLink).all()
    data = [{
        "id": l.id, "creator_id": l.creator_id, "original_url": l.original_url,
        "affiliate_url": l.affiliate_url, "link_type": l.link_type,
        "estimated_rate": l.estimated_rate, "cookie_hours": l.cookie_hours,
        "approved_media_name": l.approved_media_name, "active": l.active,
    } for l in links]
    df = pd.DataFrame(data)
    output = io.StringIO()
    df.to_csv(output, index=False, encoding="utf-8-sig")
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=affiliate_links.csv"}
    )
