import os
import io
from datetime import date
from fastapi import APIRouter, Request, Depends, Form, UploadFile, File
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from database import get_db
from models import Asset, Creator

router = APIRouter()

UPLOAD_DIR = "static/uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

SOURCE_TYPES = ["self_made", "creator_provided", "myfans_official", "x_post", "unknown"]
ASSET_TYPES = ["image", "video", "card", "thumbnail"]
RIGHTS_STATUSES = ["pending", "approved", "rejected", "expired"]
ADULT_LEVELS = ["none", "suggestive", "adult", "explicit"]
PLATFORMS = ["x", "lp", "note", "blog", "none"]
AD_REVIEW_STATUSES = ["not_required", "pending", "approved", "rejected"]


def asset_can_be_used(asset: Asset, platform: str = None) -> tuple[bool, list[str]]:
    issues = []
    if asset.rights_status != "approved":
        issues.append(f"権利確認ステータスが '{asset.rights_status}' です")
    if asset.source_type == "unknown":
        issues.append("素材ソースが不明（unknown）のため使用不可")
    if asset.source_type == "x_post" and not asset.creator_permission_note:
        issues.append("X投稿素材はクリエイター許諾メモが必要です")
    if asset.usage_expiry_date and asset.usage_expiry_date < date.today():
        issues.append(f"使用期限切れ（{asset.usage_expiry_date}）")
    if platform and asset.allowed_platforms:
        allowed = [p.strip() for p in asset.allowed_platforms.split(",")]
        if platform not in allowed and "none" not in allowed:
            issues.append(f"投稿先 '{platform}' がallowed_platformsに含まれていません")
    return len(issues) == 0, issues


@router.get("/assets")
async def assets_list(
    request: Request,
    creator_id: int = 0,
    rights_status: str = "",
    source_type: str = "",
    db: Session = Depends(get_db),
):
    from main import templates
    q = db.query(Asset)
    if creator_id:
        q = q.filter(Asset.creator_id == creator_id)
    if rights_status:
        q = q.filter(Asset.rights_status == rights_status)
    if source_type:
        q = q.filter(Asset.source_type == source_type)
    assets = q.order_by(Asset.created_at.desc()).all()
    creators = db.query(Creator).all()

    for a in assets:
        ok, issues = asset_can_be_used(a)
        a._usable = ok
        a._issues = issues

    return templates.TemplateResponse(request, "assets.html", {
        "assets": assets,
        "creators": creators,
        "filter_creator_id": creator_id,
        "filter_rights": rights_status,
        "filter_source": source_type,
        "source_types": SOURCE_TYPES,
        "rights_statuses": RIGHTS_STATUSES,
        "adult_levels": ADULT_LEVELS,
        "platforms": PLATFORMS,
    })


@router.get("/assets/new")
async def asset_new(request: Request, db: Session = Depends(get_db)):
    from main import templates
    creators = db.query(Creator).all()
    return templates.TemplateResponse(request, "asset_form.html", {
        "asset": None,
        "creators": creators,
        "source_types": SOURCE_TYPES,
        "asset_types": ASSET_TYPES,
        "rights_statuses": RIGHTS_STATUSES,
        "adult_levels": ADULT_LEVELS,
        "platforms": PLATFORMS,
        "ad_review_statuses": AD_REVIEW_STATUSES,
    })


@router.post("/assets/new")
async def asset_create(
    request: Request,
    creator_id: int = Form(...),
    asset_type: str = Form("image"),
    source_type: str = Form("unknown"),
    source_url: str = Form(""),
    rights_status: str = Form("pending"),
    allowed_platforms: str = Form("none"),
    adult_level: str = Form("none"),
    sensitive_required: bool = Form(False),
    usage_expiry_date: str = Form(""),
    myfans_ad_review_status: str = Form("not_required"),
    creator_permission_note: str = Form(""),
    ng_notes: str = Form(""),
    memo: str = Form(""),
    file: UploadFile = File(None),
    db: Session = Depends(get_db),
):
    # Forbidden: MyFans paid post screenshots / screen recordings
    if source_type == "myfans_official" and asset_type == "video":
        from main import templates
        creators = db.query(Creator).all()
        return templates.TemplateResponse(request, "asset_form.html", {
            "error": "MyFans公式動画（有料投稿の録画・スクリーンキャプチャ）は登録不可です。",
            "creators": creators,
            "source_types": SOURCE_TYPES, "asset_types": ASSET_TYPES,
            "rights_statuses": RIGHTS_STATUSES, "adult_levels": ADULT_LEVELS,
            "platforms": PLATFORMS, "ad_review_statuses": AD_REVIEW_STATUSES,
        })

    file_path = None
    if file and file.filename:
        safe_name = f"{int(__import__('time').time())}_{file.filename}"
        dest = os.path.join(UPLOAD_DIR, safe_name)
        with open(dest, "wb") as f:
            f.write(await file.read())
        file_path = f"/static/uploads/{safe_name}"

    expiry = None
    if usage_expiry_date:
        try:
            expiry = date.fromisoformat(usage_expiry_date)
        except Exception:
            pass

    # Auto-set sensitive_required for adult/explicit on X
    platforms_list = [p.strip() for p in allowed_platforms.split(",")]
    if adult_level in ("adult", "explicit") and "x" in platforms_list:
        sensitive_required = True

    asset = Asset(
        creator_id=creator_id,
        asset_type=asset_type,
        source_type=source_type,
        source_url=source_url,
        file_path=file_path,
        rights_status=rights_status,
        allowed_platforms=allowed_platforms,
        adult_level=adult_level,
        sensitive_required=sensitive_required,
        usage_expiry_date=expiry,
        myfans_ad_review_status=myfans_ad_review_status,
        creator_permission_note=creator_permission_note,
        ng_notes=ng_notes,
        memo=memo,
    )
    db.add(asset)
    db.commit()
    return RedirectResponse("/assets", status_code=303)


@router.post("/assets/{asset_id}/approve")
async def asset_approve(asset_id: int, db: Session = Depends(get_db)):
    a = db.query(Asset).filter(Asset.id == asset_id).first()
    if a:
        a.rights_status = "approved"
        db.commit()
    return RedirectResponse("/assets", status_code=303)


@router.post("/assets/{asset_id}/reject")
async def asset_reject(asset_id: int, db: Session = Depends(get_db)):
    a = db.query(Asset).filter(Asset.id == asset_id).first()
    if a:
        a.rights_status = "rejected"
        db.commit()
    return RedirectResponse("/assets", status_code=303)


@router.post("/assets/{asset_id}/delete")
async def asset_delete(asset_id: int, db: Session = Depends(get_db)):
    a = db.query(Asset).filter(Asset.id == asset_id).first()
    if a:
        db.delete(a)
        db.commit()
    return RedirectResponse("/assets", status_code=303)
