import re
import io
import json
from fastapi import APIRouter, Request, Depends, Form, UploadFile, File
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from database import get_db
from models import CreatorCandidate, Creator
from datetime import datetime
import pandas as pd

router = APIRouter()

MYFANS_POST_RE = re.compile(r"https?://myfans\.jp/[^/]+/posts/", re.I)
MYFANS_CREATOR_RE = re.compile(r"https?://myfans\.jp/[^/?#]+/?$", re.I)
X_POST_RE = re.compile(r"https?://(twitter|x)\.com/[^/]+/status/", re.I)
X_PROFILE_RE = re.compile(r"https?://(twitter|x)\.com/[^/?#]+/?$", re.I)


def classify_url(url: str) -> str:
    url = url.strip()
    if MYFANS_POST_RE.search(url):
        return "myfans_post"
    if MYFANS_CREATOR_RE.search(url):
        return "myfans_creator"
    if X_POST_RE.search(url):
        return "x_post"
    if X_PROFILE_RE.search(url):
        return "x_profile"
    return "unknown"


# ─────────────────────────────────────────────
#  URL bulk import
# ─────────────────────────────────────────────
@router.get("/import/urls")
async def import_urls_form(request: Request):
    from main import templates
    return templates.TemplateResponse(request, "import_urls.html", {})


@router.post("/import/urls")
async def import_urls_submit(
    request: Request,
    urls_text: str = Form(...),
    db: Session = Depends(get_db),
):
    raw_urls = [u.strip() for u in urls_text.splitlines() if u.strip()]
    results = []
    for url in raw_urls:
        existing = db.query(CreatorCandidate).filter(CreatorCandidate.url == url).first()
        if existing:
            results.append({"url": url, "status": "duplicate", "type": existing.url_type})
            continue
        url_type = classify_url(url)
        candidate = CreatorCandidate(
            url=url,
            url_type=url_type,
            status="new",
            source="url_import",
        )
        db.add(candidate)
        results.append({"url": url, "status": "added", "type": url_type})
    db.commit()

    from main import templates
    return templates.TemplateResponse(request, "import_urls.html", {"results": results})


# ─────────────────────────────────────────────
#  CSV import with preview
# ─────────────────────────────────────────────
@router.get("/import/csv")
async def import_csv_form(request: Request):
    from main import templates
    return templates.TemplateResponse(request, "import_csv.html", {})


@router.post("/import/csv/preview")
async def import_csv_preview(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    from main import templates
    content = await file.read()
    try:
        df = pd.read_csv(io.BytesIO(content), dtype=str)
        df = df.fillna("")
    except Exception as e:
        return templates.TemplateResponse(request, "import_csv.html", {"error": f"CSV読み込みエラー: {e}"})

    required = ["display_name", "myfans_url", "category"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        return templates.TemplateResponse(request, "import_csv.html", {
            "error": f"必須列が不足しています: {', '.join(missing)}"
        })

    rows = df.to_dict(orient="records")
    existing_urls = {c.url for c in db.query(CreatorCandidate.url).all()}
    existing_creator_urls = {c.myfans_profile_url for c in db.query(Creator.myfans_profile_url).all() if c.myfans_profile_url}

    previews = []
    for row in rows:
        url = row.get("myfans_url", "")
        dup = url in existing_urls or url in existing_creator_urls
        previews.append({**row, "_duplicate": dup})

    rows_json = json.dumps(rows, ensure_ascii=False)
    return templates.TemplateResponse(request, "import_csv.html", {
        "previews": previews,
        "rows_json": rows_json,
        "total": len(rows),
        "dup_count": sum(1 for p in previews if p["_duplicate"]),
    })


@router.post("/import/csv/confirm")
async def import_csv_confirm(
    request: Request,
    rows_json: str = Form(...),
    db: Session = Depends(get_db),
):
    rows = json.loads(rows_json)
    added = 0
    skipped = 0
    for row in rows:
        url = row.get("myfans_url", "")
        if not url:
            skipped += 1
            continue
        existing = db.query(CreatorCandidate).filter(CreatorCandidate.url == url).first()
        if existing:
            skipped += 1
            continue
        candidate = CreatorCandidate(
            url=url,
            url_type="myfans_creator",
            display_name=row.get("display_name", ""),
            myfans_url=row.get("myfans_url", ""),
            x_url=row.get("x_url", ""),
            category=row.get("category", ""),
            tags=row.get("tags", ""),
            estimated_aov=float(row["estimated_aov"]) if row.get("estimated_aov") else None,
            memo=row.get("memo", ""),
            status="new",
            source="csv_import",
        )
        db.add(candidate)
        added += 1
    db.commit()
    return RedirectResponse(f"/candidates?added={added}&skipped={skipped}", status_code=303)


# ─────────────────────────────────────────────
#  Creator self-intake form
# ─────────────────────────────────────────────
@router.get("/creator-intake")
async def creator_intake_form(request: Request):
    from main import templates
    return templates.TemplateResponse(request, "creator_intake.html", {})


@router.post("/creator-intake")
async def creator_intake_submit(
    request: Request,
    creator_name: str = Form(...),
    myfans_url: str = Form(...),
    x_url: str = Form(""),
    category: str = Form(""),
    recommended_post_url: str = Form(""),
    desired_description: str = Form(""),
    allowed_media_type: str = Form(""),
    allowed_platforms: str = Form(""),
    usage_expiry_date: str = Form(""),
    ng_words: str = Form(""),
    memo: str = Form(""),
    db: Session = Depends(get_db),
):
    from main import templates
    existing = db.query(CreatorCandidate).filter(CreatorCandidate.url == myfans_url).first()
    if existing:
        return templates.TemplateResponse(request, "creator_intake.html", {
            "error": "このURLはすでに登録されています。"
        })

    from datetime import date
    expiry = None
    if usage_expiry_date:
        try:
            expiry = date.fromisoformat(usage_expiry_date)
        except Exception:
            pass

    candidate = CreatorCandidate(
        url=myfans_url,
        url_type="myfans_creator",
        display_name=creator_name,
        myfans_url=myfans_url,
        x_url=x_url,
        category=category,
        recommended_post_url=recommended_post_url,
        desired_description=desired_description,
        allowed_media_type=allowed_media_type,
        allowed_platforms=allowed_platforms,
        usage_expiry_date=expiry,
        ng_words=ng_words,
        memo=memo,
        status="pending_review",
        source="self_intake",
    )
    db.add(candidate)
    db.commit()
    return templates.TemplateResponse(request, "creator_intake.html", {"success": True})


# ─────────────────────────────────────────────
#  CreatorCandidate list / management
# ─────────────────────────────────────────────
@router.get("/candidates")
async def candidates_list(
    request: Request,
    status: str = "",
    added: int = 0,
    skipped: int = 0,
    db: Session = Depends(get_db),
):
    from main import templates
    q = db.query(CreatorCandidate)
    if status:
        q = q.filter(CreatorCandidate.status == status)
    candidates = q.order_by(CreatorCandidate.created_at.desc()).all()
    return templates.TemplateResponse(request, "candidates.html", {
        "candidates": candidates,
        "status_filter": status,
        "added": added,
        "skipped": skipped,
    })


@router.post("/candidates/{cid}/approve")
async def candidate_approve(cid: int, db: Session = Depends(get_db)):
    c = db.query(CreatorCandidate).filter(CreatorCandidate.id == cid).first()
    if c:
        c.status = "approved"
        db.commit()
    return RedirectResponse("/candidates", status_code=303)


@router.post("/candidates/{cid}/reject")
async def candidate_reject(cid: int, db: Session = Depends(get_db)):
    c = db.query(CreatorCandidate).filter(CreatorCandidate.id == cid).first()
    if c:
        c.status = "rejected"
        db.commit()
    return RedirectResponse("/candidates", status_code=303)


@router.post("/candidates/{cid}/to-creator")
async def candidate_to_creator(cid: int, db: Session = Depends(get_db)):
    """Promote approved candidate to full Creator record."""
    c = db.query(CreatorCandidate).filter(CreatorCandidate.id == cid).first()
    if not c:
        return RedirectResponse("/candidates", status_code=303)
    creator = Creator(
        display_name=c.display_name or c.url,
        myfans_profile_url=c.myfans_url or c.url,
        x_handle=c.x_url,
        category=c.category or "",
        tags=c.tags or "",
        memo=c.memo or "",
        approval_status="pending",
    )
    db.add(creator)
    c.status = "approved"
    db.commit()
    return RedirectResponse("/creators", status_code=303)


@router.post("/candidates/{cid}/delete")
async def candidate_delete(cid: int, db: Session = Depends(get_db)):
    c = db.query(CreatorCandidate).filter(CreatorCandidate.id == cid).first()
    if c:
        db.delete(c)
        db.commit()
    return RedirectResponse("/candidates", status_code=303)
