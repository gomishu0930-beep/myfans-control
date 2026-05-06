from fastapi import APIRouter, Request, Depends, Form, UploadFile, File
from fastapi.responses import RedirectResponse, StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import or_
from database import get_db
from models import Creator
from datetime import datetime
import pandas as pd
import io

router = APIRouter()


def calc_total_score(creator: Creator) -> float:
    score = 0.0
    score += min(creator.direct_rate or 0, 30) * (100 / 30) * 0.25
    score += min(creator.estimated_aov or 0, 20000) / 200 * 0.20
    score += (creator.content_quality_score or 0) * 0.20
    score += (creator.engagement_score or 0) * 0.15
    score += (creator.conversion_score or 0) * 0.10
    if creator.material_permission_status == "approved":
        score += 10 * 0.10
    return min(round(score, 1), 100.0)


@router.get("/creators")
async def creators_list(request: Request, q: str = "", category: str = "", sort: str = "total_score", db: Session = Depends(get_db)):
    from main import templates
    query = db.query(Creator)
    if q:
        query = query.filter(or_(
            Creator.display_name.contains(q),
            Creator.x_handle.contains(q),
            Creator.tags.contains(q),
        ))
    if category:
        query = query.filter(Creator.category == category)
    if sort == "total_score":
        query = query.order_by(Creator.total_score.desc())
    elif sort == "direct_rate":
        query = query.order_by(Creator.direct_rate.desc())
    elif sort == "estimated_aov":
        query = query.order_by(Creator.estimated_aov.desc())
    else:
        query = query.order_by(Creator.created_at.desc())

    creators = query.all()
    categories = db.query(Creator.category).distinct().all()
    categories = [c[0] for c in categories if c[0]]

    return templates.TemplateResponse(request, "creators.html", {
        "creators": creators,
        "categories": categories,
        "q": q,
        "category": category,
        "sort": sort,
    })


@router.get("/creators/new")
async def creator_new(request: Request):
    from main import templates
    return templates.TemplateResponse(request, "creator_form.html", {"creator": None})


@router.post("/creators/new")
async def creator_create(
    request: Request,
    display_name: str = Form(...),
    myfans_profile_url: str = Form(""),
    x_handle: str = Form(""),
    category: str = Form(""),
    tags: str = Form(""),
    adult_flag: bool = Form(False),
    affiliate_enabled: bool = Form(False),
    estimated_aov: float = Form(5000.0),
    direct_rate: float = Form(10.0),
    category_rate: float = Form(10.0),
    actual_rate_note: str = Form(""),
    content_quality_score: int = Form(0),
    engagement_score: int = Form(0),
    conversion_score: int = Form(0),
    trust_score: int = Form(0),
    approval_status: str = Form("pending"),
    material_permission_status: str = Form("pending"),
    myfans_ad_review_status: str = Form("pending"),
    memo: str = Form(""),
    db: Session = Depends(get_db)
):
    creator = Creator(
        display_name=display_name,
        myfans_profile_url=myfans_profile_url,
        x_handle=x_handle,
        category=category,
        tags=tags,
        adult_flag=adult_flag,
        affiliate_enabled=affiliate_enabled,
        estimated_aov=estimated_aov,
        direct_rate=direct_rate,
        category_rate=category_rate,
        actual_rate_note=actual_rate_note,
        content_quality_score=content_quality_score,
        engagement_score=engagement_score,
        conversion_score=conversion_score,
        trust_score=trust_score,
        approval_status=approval_status,
        material_permission_status=material_permission_status,
        myfans_ad_review_status=myfans_ad_review_status,
        memo=memo,
    )
    creator.total_score = calc_total_score(creator)
    db.add(creator)
    db.commit()
    return RedirectResponse("/creators", status_code=303)


@router.get("/creators/{creator_id}/edit")
async def creator_edit(request: Request, creator_id: int, db: Session = Depends(get_db)):
    from main import templates
    creator = db.query(Creator).filter(Creator.id == creator_id).first()
    return templates.TemplateResponse(request, "creator_form.html", {"creator": creator})


@router.post("/creators/{creator_id}/edit")
async def creator_update(
    request: Request,
    creator_id: int,
    display_name: str = Form(...),
    myfans_profile_url: str = Form(""),
    x_handle: str = Form(""),
    category: str = Form(""),
    tags: str = Form(""),
    adult_flag: bool = Form(False),
    affiliate_enabled: bool = Form(False),
    estimated_aov: float = Form(5000.0),
    direct_rate: float = Form(10.0),
    category_rate: float = Form(10.0),
    actual_rate_note: str = Form(""),
    content_quality_score: int = Form(0),
    engagement_score: int = Form(0),
    conversion_score: int = Form(0),
    trust_score: int = Form(0),
    approval_status: str = Form("pending"),
    material_permission_status: str = Form("pending"),
    myfans_ad_review_status: str = Form("pending"),
    memo: str = Form(""),
    db: Session = Depends(get_db)
):
    creator = db.query(Creator).filter(Creator.id == creator_id).first()
    creator.display_name = display_name
    creator.myfans_profile_url = myfans_profile_url
    creator.x_handle = x_handle
    creator.category = category
    creator.tags = tags
    creator.adult_flag = adult_flag
    creator.affiliate_enabled = affiliate_enabled
    creator.estimated_aov = estimated_aov
    creator.direct_rate = direct_rate
    creator.category_rate = category_rate
    creator.actual_rate_note = actual_rate_note
    creator.content_quality_score = content_quality_score
    creator.engagement_score = engagement_score
    creator.conversion_score = conversion_score
    creator.trust_score = trust_score
    creator.approval_status = approval_status
    creator.material_permission_status = material_permission_status
    creator.myfans_ad_review_status = myfans_ad_review_status
    creator.memo = memo
    creator.updated_at = datetime.utcnow()
    creator.total_score = calc_total_score(creator)
    db.commit()
    return RedirectResponse("/creators", status_code=303)


@router.post("/creators/{creator_id}/delete")
async def creator_delete(creator_id: int, db: Session = Depends(get_db)):
    creator = db.query(Creator).filter(Creator.id == creator_id).first()
    if creator:
        db.delete(creator)
        db.commit()
    return RedirectResponse("/creators", status_code=303)


@router.get("/creators/export/csv")
async def creators_export(db: Session = Depends(get_db)):
    creators = db.query(Creator).all()
    data = [{
        "id": c.id, "display_name": c.display_name, "myfans_profile_url": c.myfans_profile_url,
        "x_handle": c.x_handle, "category": c.category, "tags": c.tags,
        "adult_flag": c.adult_flag, "affiliate_enabled": c.affiliate_enabled,
        "estimated_aov": c.estimated_aov, "direct_rate": c.direct_rate,
        "total_score": c.total_score, "approval_status": c.approval_status,
        "material_permission_status": c.material_permission_status,
        "myfans_ad_review_status": c.myfans_ad_review_status,
    } for c in creators]
    df = pd.DataFrame(data)
    output = io.StringIO()
    df.to_csv(output, index=False, encoding="utf-8-sig")
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=creators.csv"}
    )


@router.post("/creators/import/csv")
async def creators_import(file: UploadFile = File(...), db: Session = Depends(get_db)):
    content = await file.read()
    df = pd.read_csv(io.BytesIO(content))
    for _, row in df.iterrows():
        creator = Creator(
            display_name=str(row.get("display_name", "")),
            myfans_profile_url=str(row.get("myfans_profile_url", "")),
            x_handle=str(row.get("x_handle", "")),
            category=str(row.get("category", "")),
            tags=str(row.get("tags", "")),
        )
        creator.total_score = calc_total_score(creator)
        db.add(creator)
    db.commit()
    return RedirectResponse("/creators", status_code=303)
