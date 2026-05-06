from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse, StreamingResponse
from sqlalchemy.orm import Session
from database import get_db
from models import PostDraft, Creator, AffiliateLink, Asset, AppSettings
from compliance import run_compliance_check
from datetime import datetime
import pandas as pd
import io

router = APIRouter()

TEMPLATES = {
    "introduction": """【今日の注目クリエイター】

{creator_name}さんのMyFansをご紹介します。

ジャンル：{category}
MyFansリンク：{affiliate_url}

※成人向けコンテンツです。18歳未満の方はご覧いただけません。
#PR #MyFans #アフィリエイト""",

    "ranking": """【今週のおすすめクリエイターTOP】

MyFansで注目を集めているクリエイターをまとめました。
詳細はプロフィールのリンクからご確認ください。

※成人向けコンテンツです。18歳未満の方はご覧いただけません。
#PR #MyFans""",

    "campaign": """【お知らせ】

{creator_name}さんのMyFansで新着コンテンツが公開されました。

MyFansリンク：{affiliate_url}

※成人向けコンテンツです。18歳未満の方はご覧いただけません。
#PR #MyFans""",

    "knowhow": """【MyFansアフィリエイト運用ログ】

今月の実績をご報告します。

運用ポイント：
・毎日2投稿を継続
・クリエイターとのコミュニケーション重視
・コンプライアンス遵守

詳細はプロフィールリンクからどうぞ。
#MyFansアフィリエイト #副業""",
}


@router.get("/drafts")
async def drafts_list(
    request: Request,
    status: str = "",
    post_type: str = "",
    db: Session = Depends(get_db)
):
    from main import templates
    query = db.query(PostDraft)
    if status:
        query = query.filter(PostDraft.status == status)
    if post_type:
        query = query.filter(PostDraft.post_type == post_type)
    drafts = query.order_by(PostDraft.created_at.desc()).all()

    creator_map = {c.id: c for c in db.query(Creator).all()}
    link_map = {l.id: l for l in db.query(AffiliateLink).all()}

    return templates.TemplateResponse(request, "drafts.html", {
        "drafts": drafts,
        "creator_map": creator_map,
        "link_map": link_map,
        "status_filter": status,
        "post_type_filter": post_type,
    })


@router.get("/drafts/new")
async def draft_new(request: Request, template_type: str = "", creator_id: int = 0, db: Session = Depends(get_db)):
    from main import templates
    creators = db.query(Creator).filter(Creator.approval_status != "rejected").all()
    links = db.query(AffiliateLink).filter(AffiliateLink.active == True).all()
    assets = db.query(Asset).filter(Asset.rights_status == "approved").all()
    settings = db.query(AppSettings).first()

    prefill_body = ""
    if template_type and template_type in TEMPLATES:
        creator = None
        affiliate_url = ""
        if creator_id:
            creator = db.query(Creator).filter(Creator.id == creator_id).first()
        if creator:
            link = db.query(AffiliateLink).filter(AffiliateLink.creator_id == creator_id, AffiliateLink.active == True).first()
            affiliate_url = link.affiliate_url if link else ""
            prefill_body = TEMPLATES[template_type].format(
                creator_name=creator.display_name,
                category=creator.category or "グラビア",
                affiliate_url=affiliate_url,
            )
        else:
            prefill_body = TEMPLATES[template_type].format(
                creator_name="クリエイター名",
                category="カテゴリ",
                affiliate_url="https://myfans.jp/...",
            )

    return templates.TemplateResponse(request, "draft_form.html", {
        "draft": None,
        "creators": creators,
        "links": links,
        "assets": assets,
        "settings": settings,
        "prefill_body": prefill_body,
        "template_type": template_type,
        "selected_creator_id": creator_id,
        "template_keys": list(TEMPLATES.keys()),
    })


@router.post("/drafts/new")
async def draft_create(
    request: Request,
    creator_id: int = Form(...),
    affiliate_link_id: int = Form(0),
    asset_id: int = Form(0),
    post_type: str = Form("introduction"),
    title: str = Form(""),
    body: str = Form(...),
    hashtags: str = Form(""),
    scheduled_at: str = Form(""),
    account_name: str = Form(""),
    db: Session = Depends(get_db)
):
    scheduled = None
    if scheduled_at:
        try:
            scheduled = datetime.fromisoformat(scheduled_at)
        except ValueError:
            pass

    draft = PostDraft(
        creator_id=creator_id,
        affiliate_link_id=affiliate_link_id if affiliate_link_id else None,
        asset_id=asset_id if asset_id else None,
        post_type=post_type,
        title=title,
        body=body,
        hashtags=hashtags,
        scheduled_at=scheduled,
        account_name=account_name,
        status="draft",
    )
    db.add(draft)
    db.commit()
    db.refresh(draft)
    run_compliance_check(draft, db)
    return RedirectResponse("/drafts", status_code=303)


@router.get("/drafts/{draft_id}/edit")
async def draft_edit(request: Request, draft_id: int, db: Session = Depends(get_db)):
    from main import templates
    draft = db.query(PostDraft).filter(PostDraft.id == draft_id).first()
    creators = db.query(Creator).filter(Creator.approval_status != "rejected").all()
    links = db.query(AffiliateLink).filter(AffiliateLink.active == True).all()
    assets = db.query(Asset).filter(Asset.rights_status == "approved").all()
    settings = db.query(AppSettings).first()
    return templates.TemplateResponse(request, "draft_form.html", {
        "draft": draft,
        "creators": creators,
        "links": links,
        "assets": assets,
        "settings": settings,
        "prefill_body": "",
        "template_type": "",
        "selected_creator_id": 0,
        "template_keys": list(TEMPLATES.keys()),
    })


@router.post("/drafts/{draft_id}/edit")
async def draft_update(
    draft_id: int,
    creator_id: int = Form(...),
    affiliate_link_id: int = Form(0),
    asset_id: int = Form(0),
    post_type: str = Form("introduction"),
    title: str = Form(""),
    body: str = Form(...),
    hashtags: str = Form(""),
    scheduled_at: str = Form(""),
    account_name: str = Form(""),
    db: Session = Depends(get_db)
):
    draft = db.query(PostDraft).filter(PostDraft.id == draft_id).first()
    if draft:
        scheduled = None
        if scheduled_at:
            try:
                scheduled = datetime.fromisoformat(scheduled_at)
            except ValueError:
                pass
        draft.creator_id = creator_id
        draft.affiliate_link_id = affiliate_link_id if affiliate_link_id else None
        draft.asset_id = asset_id if asset_id else None
        draft.post_type = post_type
        draft.title = title
        draft.body = body
        draft.hashtags = hashtags
        draft.scheduled_at = scheduled
        draft.account_name = account_name
        draft.status = "draft"
        draft.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(draft)
        run_compliance_check(draft, db)
    return RedirectResponse("/drafts", status_code=303)


@router.post("/drafts/{draft_id}/delete")
async def draft_delete(draft_id: int, db: Session = Depends(get_db)):
    draft = db.query(PostDraft).filter(PostDraft.id == draft_id).first()
    if draft:
        db.delete(draft)
        db.commit()
    return RedirectResponse("/drafts", status_code=303)


@router.post("/drafts/{draft_id}/approve")
async def draft_approve(draft_id: int, db: Session = Depends(get_db)):
    draft = db.query(PostDraft).filter(PostDraft.id == draft_id).first()
    if draft:
        result = run_compliance_check(draft, db)
        if result["can_approve"]:
            draft.status = "approved"
            db.commit()
    return RedirectResponse("/drafts", status_code=303)


@router.post("/drafts/{draft_id}/reject")
async def draft_reject(draft_id: int, db: Session = Depends(get_db)):
    draft = db.query(PostDraft).filter(PostDraft.id == draft_id).first()
    if draft:
        draft.status = "rejected"
        db.commit()
    return RedirectResponse("/drafts", status_code=303)


@router.post("/drafts/{draft_id}/mark-posted")
async def draft_mark_posted(draft_id: int, posted_url: str = Form(""), db: Session = Depends(get_db)):
    draft = db.query(PostDraft).filter(PostDraft.id == draft_id).first()
    if draft and draft.status == "approved":
        draft.status = "posted"
        draft.posted_url = posted_url
        db.commit()
    return RedirectResponse("/drafts", status_code=303)


@router.post("/drafts/{draft_id}/check")
async def draft_compliance_check(draft_id: int, db: Session = Depends(get_db)):
    draft = db.query(PostDraft).filter(PostDraft.id == draft_id).first()
    if draft:
        run_compliance_check(draft, db)
    return RedirectResponse(f"/drafts/{draft_id}/edit", status_code=303)


@router.get("/drafts/export/csv")
async def drafts_export(db: Session = Depends(get_db)):
    drafts = db.query(PostDraft).all()
    data = [{
        "id": d.id, "post_type": d.post_type, "title": d.title, "body": d.body,
        "hashtags": d.hashtags, "scheduled_at": d.scheduled_at,
        "account_name": d.account_name, "status": d.status,
        "compliance_score": d.compliance_score,
    } for d in drafts]
    df = pd.DataFrame(data)
    output = io.StringIO()
    df.to_csv(output, index=False, encoding="utf-8-sig")
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=post_drafts.csv"}
    )


@router.get("/drafts/export/schedule")
async def schedule_export(db: Session = Depends(get_db)):
    drafts = db.query(PostDraft).filter(
        PostDraft.status == "approved",
        PostDraft.scheduled_at != None
    ).order_by(PostDraft.scheduled_at).all()
    data = [{
        "scheduled_at": d.scheduled_at, "account_name": d.account_name,
        "post_type": d.post_type, "title": d.title, "body": d.body,
        "hashtags": d.hashtags,
    } for d in drafts]
    df = pd.DataFrame(data)
    output = io.StringIO()
    df.to_csv(output, index=False, encoding="utf-8-sig")
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=x_schedule.csv"}
    )
