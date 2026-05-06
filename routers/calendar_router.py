from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from database import get_db
from models import PostDraft, Creator, AppSettings
from datetime import datetime, timedelta, date
import calendar

router = APIRouter()


@router.get("/calendar")
async def calendar_view(request: Request, year: int = 0, month: int = 0, db: Session = Depends(get_db)):
    from main import templates

    today = date.today()
    if not year:
        year = today.year
    if not month:
        month = today.month

    first_day = date(year, month, 1)
    last_day = date(year, month, calendar.monthrange(year, month)[1])

    settings = db.query(AppSettings).first()
    default_times = ["12:00", "19:00", "21:00", "23:00"]
    if settings and settings.default_post_times:
        default_times = [t.strip() for t in settings.default_post_times.split(",")]

    scheduled_drafts = db.query(PostDraft).filter(
        PostDraft.scheduled_at >= datetime.combine(first_day, datetime.min.time()),
        PostDraft.scheduled_at <= datetime.combine(last_day, datetime.max.time()),
    ).order_by(PostDraft.scheduled_at).all()

    calendar_data = {}
    for day_num in range(1, last_day.day + 1):
        d = date(year, month, day_num)
        calendar_data[d] = {"times": {t: [] for t in default_times}, "other": []}

    for draft in scheduled_drafts:
        d = draft.scheduled_at.date()
        t_str = draft.scheduled_at.strftime("%H:%M")
        if d in calendar_data:
            if t_str in calendar_data[d]["times"]:
                calendar_data[d]["times"][t_str].append(draft)
            else:
                calendar_data[d]["other"].append(draft)

    unscheduled = db.query(PostDraft).filter(
        PostDraft.status == "approved",
        PostDraft.scheduled_at == None,
    ).all()

    creator_map = {c.id: c for c in db.query(Creator).all()}

    prev_month = month - 1 if month > 1 else 12
    prev_year = year if month > 1 else year - 1
    next_month = month + 1 if month < 12 else 1
    next_year = year if month < 12 else year + 1

    cal = calendar.monthcalendar(year, month)

    return templates.TemplateResponse(request, "calendar.html", {
        "year": year,
        "month": month,
        "calendar_data": calendar_data,
        "default_times": default_times,
        "unscheduled": unscheduled,
        "creator_map": creator_map,
        "prev_year": prev_year,
        "prev_month": prev_month,
        "next_year": next_year,
        "next_month": next_month,
        "cal": cal,
        "today": today,
    })


@router.post("/calendar/assign")
async def calendar_assign(
    draft_id: int = Form(...),
    scheduled_at: str = Form(...),
    db: Session = Depends(get_db)
):
    draft = db.query(PostDraft).filter(PostDraft.id == draft_id).first()
    if draft:
        try:
            draft.scheduled_at = datetime.fromisoformat(scheduled_at)
            db.commit()
        except ValueError:
            pass
    return RedirectResponse("/calendar", status_code=303)
