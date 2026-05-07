import base64
import os
import time
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

router = APIRouter()

GENERATED_DIR = Path("static/affiliate-copy-desk/generated")
GENERATED_DIR.mkdir(parents=True, exist_ok=True)


class ImageGenerateRequest(BaseModel):
    prompts: list[str] = Field(default_factory=list, max_length=4)
    count: int = Field(default=2, ge=1, le=4)
    work_index: int | None = None


def _safe_prompt(prompt: str) -> str:
    return "\n".join(
        [
            prompt.strip()[:1800],
            "",
            "Safety constraints: adult-looking person only, tasteful non-explicit promotional image,",
            "no nudity, no visible sexual act, no minors, no realistic identification of a real person,",
            "no watermark, no platform logo, no copyrighted character.",
        ]
    )


async def _generate_one_image(prompt: str, work_index: int | None, slot: int) -> dict[str, Any]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="OPENAI_API_KEY is not configured. Add it to Replit Secrets and retry.",
        )

    model = os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-1.5")
    payload = {
        "model": model,
        "prompt": _safe_prompt(prompt),
        "n": 1,
        "size": os.getenv("OPENAI_IMAGE_SIZE", "1024x1024"),
        "quality": os.getenv("OPENAI_IMAGE_QUALITY", "low"),
        "background": "opaque",
    }

    async with httpx.AsyncClient(timeout=180) as client:
        response = await client.post(
            "https://api.openai.com/v1/images/generations",
            headers={"Authorization": f"Bearer {api_key}"},
            json=payload,
        )

    if response.status_code >= 400:
        try:
            error = response.json()
        except Exception:
            error = response.text
        raise HTTPException(status_code=response.status_code, detail=error)

    data = response.json()
    b64_json = data["data"][0].get("b64_json")
    if not b64_json:
        raise HTTPException(status_code=502, detail="OpenAI image response did not include b64_json.")

    image_bytes = base64.b64decode(b64_json)
    stamp = int(time.time() * 1000)
    work = work_index or 0
    filename = f"affiliate_{work}_{slot}_{stamp}.png"
    output_path = GENERATED_DIR / filename
    output_path.write_bytes(image_bytes)

    return {
        "url": f"/static/affiliate-copy-desk/generated/{filename}",
        "model": model,
        "prompt": prompt,
    }


@router.get("/affiliate-copy-desk")
async def affiliate_copy_desk(request: Request):
    from main import templates

    return templates.TemplateResponse(request, "affiliate_copy_desk.html", {})


@router.post("/api/affiliate-copy-desk/generate-images")
async def generate_affiliate_images(payload: ImageGenerateRequest):
    prompts = [prompt for prompt in payload.prompts[: payload.count] if prompt.strip()]
    if not prompts:
        raise HTTPException(status_code=400, detail="At least one prompt is required.")

    images = []
    for slot, prompt in enumerate(prompts, start=1):
        images.append(await _generate_one_image(prompt, payload.work_index, slot))

    return {"images": images}
