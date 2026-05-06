from fastapi import APIRouter, Request, Depends, Form, UploadFile, File
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from database import get_db
from models import PerformanceReport, Creator, AffiliateLink, PostDraft
from datetime import date, datetime
import pandas as pd
import io

router = APIRouter()


@router.get("/reports")
async def reports_list(request: Request, db: Session = Depends(get_db)):
    from main import templates

    reports = db.query(PerformanceReport).order_by(PerformanceReport.date.desc()).all()

    total_clicks = db.query(func.sum(PerformanceReport.clicks)).scalar() or 0
    total_conversions = db.query(func.sum(PerformanceReport.conversions)).scalar() or 0
    total_gross_sales = db.query(func.sum(PerformanceReport.gross_sales)).scalar() or 0
    total_commission = db.query(func.sum(PerformanceReport.commission)).scalar() or 0

    by_creator = db.query(
        Creator.display_name,
        func.sum(PerformanceReport.clicks).label("clicks"),
        func.sum(PerformanceReport.conversions).label("conversions"),
        func.sum(PerformanceReport.gross_sales).label("gross_sales"),
        func.sum(PerformanceReport.commission).label("commission"),
    ).join(Creator, PerformanceReport.creator_id == Creator.id, isouter=True)\
     .group_by(Creator.id).order_by(func.sum(PerformanceReport.commission).desc()).all()

    creators = db.query(Creator).all()
    links = db.query(AffiliateLink).all()
    drafts = db.query(PostDraft).all()

    return templates.TemplateResponse(request, "reports.html", {
        "reports": reports,
        "total_clicks": total_clicks,
        "total_conversions": total_conversions,
        "total_gross_sales": total_gross_sales,
        "total_commission": total_commission,
        "by_creator": by_creator,
        "creators": creators,
        "links": links,
        "drafts": drafts,
    })


@router.post("/reports/new")
async def report_create(
    date_str: str = Form(...),
    creator_id: int = Form(0),
    affiliate_link_id: int = Form(0),
    post_draft_id: int = Form(0),
    clicks: int = Form(0),
    conversions: int = Form(0),
    gross_sales: float = Form(0.0),
    commission: float = Form(0.0),
    memo: str = Form(""),
    db: Session = Depends(get_db)
):
    try:
        report_date = date.fromisoformat(date_str)
    except ValueError:
        report_date = date.today()

    cvr = (conversions / clicks * 100) if clicks > 0 else 0
    aov = (gross_sales / conversions) if conversions > 0 else 0

    report = PerformanceReport(
        date=report_date,
        creator_id=creator_id if creator_id else None,
        affiliate_link_id=affiliate_link_id if affiliate_link_id else None,
        post_draft_id=post_draft_id if post_draft_id else None,
        clicks=clicks,
        conversions=conversions,
        gross_sales=gross_sales,
        commission=commission,
        cvr=cvr,
        aov=aov,
        memo=memo,
    )
    db.add(report)
    db.commit()
    return RedirectResponse("/reports", status_code=303)


@router.post("/reports/{report_id}/delete")
async def report_delete(report_id: int, db: Session = Depends(get_db)):
    report = db.query(PerformanceReport).filter(PerformanceReport.id == report_id).first()
    if report:
        db.delete(report)
        db.commit()
    return RedirectResponse("/reports", status_code=303)


@router.post("/reports/import/csv")
async def reports_import(file: UploadFile = File(...), db: Session = Depends(get_db)):
    content = await file.read()
    try:
        df = pd.read_csv(io.BytesIO(content))
        for _, row in df.iterrows():
            try:
                report_date = date.fromisoformat(str(row.get("date", date.today())))
            except Exception:
                report_date = date.today()

            clicks = int(row.get("clicks", 0))
            conversions = int(row.get("conversions", 0))
            gross_sales = float(row.get("gross_sales", 0))
            commission = float(row.get("commission", 0))
            cvr = (conversions / clicks * 100) if clicks > 0 else 0
            aov = (gross_sales / conversions) if conversions > 0 else 0

            report = PerformanceReport(
                date=report_date,
                clicks=clicks,
                conversions=conversions,
                gross_sales=gross_sales,
                commission=commission,
                cvr=cvr,
                aov=aov,
                memo=str(row.get("memo", "")),
            )
            db.add(report)
        db.commit()
    except Exception as e:
        pass
    return RedirectResponse("/reports", status_code=303)
