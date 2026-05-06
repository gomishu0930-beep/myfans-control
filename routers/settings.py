from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from database import get_db
from models import AppSettings
from datetime import datetime

router = APIRouter()


@router.get("/settings")
async def settings_page(request: Request, db: Session = Depends(get_db)):
    from main import templates
    settings = db.query(AppSettings).first()
    return templates.TemplateResponse(request, "settings.html", {
        "settings": settings,
    })


@router.post("/settings")
async def settings_update(
    x_account_name: str = Form(""),
    external_lp_url: str = Form(""),
    default_post_times: str = Form("12:00,19:00,21:00,23:00"),
    default_pr_text: str = Form("#PR"),
    default_age_warning: str = Form("※成人向けコンテンツです。18歳未満の方はご覧いただけません。"),
    estimated_aov: float = Form(5000.0),
    estimated_cvr: float = Form(1.0),
    target_monthly_commission: float = Form(200000.0),
    default_commission_rate: float = Form(15.0),
    db: Session = Depends(get_db)
):
    settings = db.query(AppSettings).first()
    if not settings:
        settings = AppSettings()
        db.add(settings)

    settings.x_account_name = x_account_name
    settings.external_lp_url = external_lp_url
    settings.default_post_times = default_post_times
    settings.default_pr_text = default_pr_text
    settings.default_age_warning = default_age_warning
    settings.estimated_aov = estimated_aov
    settings.estimated_cvr = estimated_cvr
    settings.target_monthly_commission = target_monthly_commission
    settings.default_commission_rate = default_commission_rate
    settings.updated_at = datetime.utcnow()
    db.commit()
    return RedirectResponse("/settings", status_code=303)
