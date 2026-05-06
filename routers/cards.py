import os
import io
import textwrap
from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse, StreamingResponse
from sqlalchemy.orm import Session
from database import get_db
from models import GeneratedCard

router = APIRouter()

CARDS_DIR = "static/cards"
os.makedirs(CARDS_DIR, exist_ok=True)

SIZES = {
    "wide":   (1200, 675),
    "square": (1080, 1080),
    "story":  (1080, 1920),
}


def _hex_to_rgb(hex_color: str):
    hex_color = hex_color.lstrip("#")
    if len(hex_color) == 3:
        hex_color = "".join(c * 2 for c in hex_color)
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))


def generate_card_image(
    size: tuple,
    creator_name: str,
    genre: str,
    catchphrase: str,
    lp_url: str,
    bg_color: str,
) -> bytes:
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        raise RuntimeError("Pillow not installed")

    w, h = size
    bg = _hex_to_rgb(bg_color)
    img = Image.new("RGB", (w, h), bg)
    draw = ImageDraw.Draw(img)

    # Gradient overlay (subtle)
    for y in range(h):
        alpha = int(40 * (1 - y / h))
        overlay = Image.new("RGBA", (w, 1), (255, 255, 255, alpha))
        img.paste(overlay, (0, y))
        draw = ImageDraw.Draw(img)

    # Color accents
    accent = (255, 80, 130)
    draw.rectangle([(0, 0), (w, 6)], fill=accent)
    draw.rectangle([(0, h - 6), (w, h)], fill=accent)

    def try_font(size_pt):
        try:
            return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", size_pt)
        except Exception:
            return ImageFont.load_default()

    # PR badge
    pr_font = try_font(max(20, w // 45))
    pr_text = "PR  広告"
    pr_bbox = draw.textbbox((0, 0), pr_text, font=pr_font)
    pr_w = pr_bbox[2] - pr_bbox[0] + 20
    pr_h = pr_bbox[3] - pr_bbox[1] + 10
    draw.rectangle([(w - pr_w - 20, 20), (w - 20, 20 + pr_h)], fill=accent)
    draw.text((w - pr_w - 10, 25), pr_text, fill="white", font=pr_font)

    # Age warning badge
    age_font = try_font(max(18, w // 50))
    age_text = "18歳未満閲覧禁止"
    draw.text((20, 20), age_text, fill=(255, 220, 50), font=age_font)

    # Genre tag
    genre_font = try_font(max(22, w // 40))
    genre_text = f"【{genre}】"
    draw.text((w // 2, int(h * 0.28)), genre_text, fill=(200, 200, 255), font=genre_font, anchor="mm")

    # Creator name
    name_font = try_font(max(36, w // 22))
    draw.text((w // 2, int(h * 0.42)), creator_name, fill="white", font=name_font, anchor="mm")

    # Catchphrase (word-wrap)
    catch_font = try_font(max(26, w // 32))
    max_chars = max(12, w // 32)
    lines = textwrap.wrap(catchphrase, width=max_chars)
    y_start = int(h * 0.58)
    for i, line in enumerate(lines[:3]):
        draw.text((w // 2, y_start + i * int(h * 0.08)), line, fill=(255, 200, 200), font=catch_font, anchor="mm")

    # CTA
    cta_font = try_font(max(20, w // 42))
    cta_text = "▶ プロフィールのURLから詳細はこちら"
    draw.text((w // 2, int(h * 0.82)), cta_text, fill=(180, 220, 255), font=cta_font, anchor="mm")

    # LP URL (truncated)
    url_font = try_font(max(16, w // 55))
    short_url = lp_url[:50] + "..." if len(lp_url) > 50 else lp_url
    draw.text((w // 2, int(h * 0.90)), short_url, fill=(150, 150, 150), font=url_font, anchor="mm")

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf.read()


@router.get("/cards")
async def cards_list(request: Request, db: Session = Depends(get_db)):
    from main import templates
    cards = db.query(GeneratedCard).order_by(GeneratedCard.created_at.desc()).all()
    return templates.TemplateResponse(request, "cards.html", {"cards": cards})


@router.get("/cards/new")
async def cards_new_form(request: Request):
    from main import templates
    return templates.TemplateResponse(request, "cards.html", {"show_form": True, "cards": []})


@router.post("/cards/generate")
async def cards_generate(
    request: Request,
    creator_name: str = Form(...),
    genre: str = Form(...),
    catchphrase: str = Form(...),
    lp_url: str = Form(""),
    background_color: str = Form("#1a1a2e"),
    db: Session = Depends(get_db),
):
    from main import templates
    ts = int(__import__("time").time())
    paths = {}
    errors = []

    for size_key, dims in SIZES.items():
        try:
            data = generate_card_image(dims, creator_name, genre, catchphrase, lp_url, background_color)
            fname = f"card_{ts}_{size_key}.png"
            fpath = os.path.join(CARDS_DIR, fname)
            with open(fpath, "wb") as f:
                f.write(data)
            paths[size_key] = f"/static/cards/{fname}"
        except Exception as e:
            errors.append(f"{size_key}: {e}")

    card = GeneratedCard(
        creator_name=creator_name,
        genre=genre,
        catchphrase=catchphrase,
        lp_url=lp_url,
        background_color=background_color,
        file_path_wide=paths.get("wide"),
        file_path_square=paths.get("square"),
        file_path_story=paths.get("story"),
    )
    db.add(card)
    db.commit()
    db.refresh(card)

    cards = db.query(GeneratedCard).order_by(GeneratedCard.created_at.desc()).all()
    return templates.TemplateResponse(request, "cards.html", {
        "cards": cards,
        "generated": card,
        "errors": errors,
        "show_form": True,
    })


@router.post("/cards/{card_id}/delete")
async def cards_delete(card_id: int, db: Session = Depends(get_db)):
    card = db.query(GeneratedCard).filter(GeneratedCard.id == card_id).first()
    if card:
        for p in [card.file_path_wide, card.file_path_square, card.file_path_story]:
            if p:
                try:
                    os.remove(p.lstrip("/"))
                except Exception:
                    pass
        db.delete(card)
        db.commit()
    return RedirectResponse("/cards", status_code=303)
