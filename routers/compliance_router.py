from fastapi import APIRouter, Request, Depends
from sqlalchemy.orm import Session
from database import get_db
from models import PostDraft, ComplianceLog, Creator
from compliance import run_compliance_check

router = APIRouter()


@router.get("/compliance")
async def compliance_page(request: Request, db: Session = Depends(get_db)):
    from main import templates

    drafts = db.query(PostDraft).filter(
        PostDraft.status.in_(["draft", "needs_review", "approved"])
    ).order_by(PostDraft.created_at.desc()).limit(50).all()

    creator_map = {c.id: c for c in db.query(Creator).all()}

    compliance_data = []
    for draft in drafts:
        logs = db.query(ComplianceLog).filter(ComplianceLog.post_draft_id == draft.id)\
               .order_by(ComplianceLog.created_at.desc()).all()
        compliance_data.append({
            "draft": draft,
            "creator": creator_map.get(draft.creator_id),
            "logs": logs,
        })

    return templates.TemplateResponse(request, "compliance.html", {
        "compliance_data": compliance_data,
    })


@router.post("/compliance/check-all")
async def compliance_check_all(request: Request, db: Session = Depends(get_db)):
    drafts = db.query(PostDraft).filter(
        PostDraft.status.in_(["draft", "needs_review"])
    ).all()
    for draft in drafts:
        run_compliance_check(draft, db)
    return {"message": f"{len(drafts)}件のチェックが完了しました"}
