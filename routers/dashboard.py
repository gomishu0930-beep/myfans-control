from fastapi import APIRouter, Request, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from database import get_db
from models import Creator, AffiliateLink, PostDraft, PerformanceReport, AppSettings

router = APIRouter()


@router.get("/dashboard")
async def dashboard(request: Request, db: Session = Depends(get_db)):
    from main import templates

    settings = db.query(AppSettings).first()

    total_clicks = db.query(func.sum(PerformanceReport.clicks)).scalar() or 0
    total_conversions = db.query(func.sum(PerformanceReport.conversions)).scalar() or 0
    total_gross_sales = db.query(func.sum(PerformanceReport.gross_sales)).scalar() or 0
    total_commission = db.query(func.sum(PerformanceReport.commission)).scalar() or 0
    total_posts = db.query(PostDraft).count()
    approved_posts = db.query(PostDraft).filter(PostDraft.status == "approved").count()
    posted_posts = db.query(PostDraft).filter(PostDraft.status == "posted").count()

    cvr = (total_conversions / total_clicks * 100) if total_clicks > 0 else 0
    aov = (total_gross_sales / total_conversions) if total_conversions > 0 else 0
    avg_commission_rate = (total_commission / total_gross_sales * 100) if total_gross_sales > 0 else 0

    target = settings.target_monthly_commission if settings else 200000
    s_aov = settings.estimated_aov if settings else 5000
    s_cvr = settings.estimated_cvr if settings else 1.0
    s_rate = settings.default_commission_rate if settings else 15.0

    needed_sales = target / (s_rate / 100) if s_rate > 0 else 0
    needed_purchases = needed_sales / s_aov if s_aov > 0 else 0
    needed_clicks = needed_purchases / (s_cvr / 100) if s_cvr > 0 else 0
    daily_clicks = needed_clicks / 30

    top_creators_by_sales = db.query(
        Creator,
        func.sum(PerformanceReport.gross_sales).label("total_sales"),
        func.sum(PerformanceReport.commission).label("total_commission")
    ).join(PerformanceReport, Creator.id == PerformanceReport.creator_id, isouter=True)\
     .group_by(Creator.id).order_by(func.sum(PerformanceReport.gross_sales).desc()).limit(5).all()

    top_creators_by_clicks = db.query(
        Creator,
        func.sum(PerformanceReport.clicks).label("total_clicks")
    ).join(PerformanceReport, Creator.id == PerformanceReport.creator_id, isouter=True)\
     .group_by(Creator.id).order_by(func.sum(PerformanceReport.clicks).desc()).limit(5).all()

    return templates.TemplateResponse(request, "dashboard.html", {
        "total_clicks": total_clicks,
        "total_conversions": total_conversions,
        "total_gross_sales": total_gross_sales,
        "total_commission": total_commission,
        "total_posts": total_posts,
        "approved_posts": approved_posts,
        "posted_posts": posted_posts,
        "cvr": cvr,
        "aov": aov,
        "avg_commission_rate": avg_commission_rate,
        "target": target,
        "needed_sales": needed_sales,
        "needed_purchases": needed_purchases,
        "needed_clicks": needed_clicks,
        "daily_clicks": daily_clicks,
        "top_creators_by_sales": top_creators_by_sales,
        "top_creators_by_clicks": top_creators_by_clicks,
        "settings": settings,
    })
