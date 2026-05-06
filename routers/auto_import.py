"""
auto_import.py — アフィリリンク全自動取込ルーター

GET  /auto-import          — 取込ページ
POST /auto-import/analyze  — リンク解析・プレビュー取得 (JSON)
POST /auto-import/save     — DB保存確定
GET  /auto-import/jobs     — 取込履歴
"""

import asyncio
import json
import os
from datetime import datetime
from fastapi import APIRouter, Request, Depends, Form, BackgroundTasks
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.orm import Session
import httpx

from database import get_db
from models import Creator, AffiliateLink, Asset, PostDraft, AutoImportJob
from services.myfans_scraper import scrape_from_affiliate_link, ScrapedCreator

router = APIRouter()

# 進行中ジョブのキャッシュ（プロセス内インメモリ）
_running_jobs: dict[str, dict] = {}


# ─── ページ ────────────────────────────────────────────────────────────────────

@router.get("/auto-import")
async def auto_import_page(request: Request):
    from main import templates
    return templates.TemplateResponse(request, "auto_import.html", {})


@router.get("/generator")
async def post_generator_page(request: Request):
    from main import templates
    return templates.TemplateResponse(request, "post_generator.html", {})


@router.post("/generator/generate")
async def post_generator_generate(request: Request):
    body = await request.json()
    affiliate_url = (body.get("url") or "").strip()
    tone = body.get("tone") or "friendly"
    platform = body.get("platform") or "x"
    if not affiliate_url:
        return JSONResponse({"ok": False, "error": "URLを入力してください"}, status_code=400)

    result = await scrape_from_affiliate_link(affiliate_url)
    if result.error:
        pack = _generate_copy_pack_from_url(affiliate_url, tone, platform)
        return JSONResponse({"ok": True, "mode": "fallback", "warning": result.error, **pack})

    pack = await _generate_ai_copy_pack(result, tone, platform)
    return JSONResponse({"ok": True, "mode": "scraped", **pack})


# ─── SSE 進捗ストリーム ─────────────────────────────────────────────────────────

@router.get("/auto-import/stream/{job_id}")
async def auto_import_stream(job_id: str):
    """Server-Sent Events で取込進捗をリアルタイム配信"""
    async def generate():
        timeout = 120
        elapsed = 0
        while elapsed < timeout:
            job = _running_jobs.get(job_id)
            if not job:
                yield f"data: {json.dumps({'status': 'not_found'})}\n\n"
                break
            yield f"data: {json.dumps(job)}\n\n"
            if job.get("status") in ("done", "error"):
                break
            await asyncio.sleep(0.5)
            elapsed += 0.5

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ─── 非同期スクレイピング ─────────────────────────────────────────────────────

async def _run_scrape(job_id: str, affiliate_url: str):
    """バックグラウンドでスクレイピング実行"""
    logs = []

    def progress(step, detail=""):
        msg = f"{step} {detail}".strip()
        logs.append(msg)
        _running_jobs[job_id] = {
            "status": "running",
            "step": step,
            "detail": detail,
            "logs": logs,
            "result": None,
        }

    try:
        result = await scrape_from_affiliate_link(affiliate_url, progress_callback=progress)
        _running_jobs[job_id] = {
            "status": "done" if not result.error else "error",
            "step": "完了",
            "detail": result.error or f"投稿 {len(result.posts)}件",
            "logs": logs,
            "result": _serialize_result(result),
            "error": result.error or None,
        }
    except Exception as e:
        _running_jobs[job_id] = {
            "status": "error",
            "step": "エラー",
            "detail": str(e),
            "logs": logs,
            "result": None,
            "error": str(e),
        }


def _serialize_result(r: ScrapedCreator) -> dict:
    return {
        "username": r.username,
        "display_name": r.display_name,
        "bio": r.bio,
        "profile_image_url": r.profile_image_url,
        "local_profile_image": r.local_profile_image,
        "cover_image_url": r.cover_image_url,
        "local_cover_image": r.local_cover_image,
        "follower_count": r.follower_count,
        "post_count": r.post_count,
        "myfans_url": r.myfans_url,
        "affiliate_url": r.affiliate_url,
        "x_handle": r.x_handle,
        "posts": [
            {
                "post_id": p.post_id,
                "title": p.title,
                "body": p.body,
                "price": p.price,
                "is_free": p.is_free,
                "thumbnail_url": p.thumbnail_url,
                "local_thumbnail": p.local_thumbnail,
                "local_images": p.local_images,
                "sample_image_urls": p.sample_image_urls,
                "published_at": p.published_at,
            }
            for p in r.posts
        ],
    }


# ─── API: スクレイピング開始 ──────────────────────────────────────────────────

@router.post("/auto-import/start")
async def auto_import_start(
    background_tasks: BackgroundTasks,
    affiliate_url: str = Form(...),
):
    """スクレイピングを非同期で開始し、job_idを返す"""
    job_id = f"job_{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}"
    _running_jobs[job_id] = {
        "status": "running",
        "step": "開始中...",
        "detail": affiliate_url,
        "logs": [],
        "result": None,
    }
    background_tasks.add_task(_run_scrape, job_id, affiliate_url)
    return JSONResponse({"job_id": job_id})


# ─── API: DB保存確定 ──────────────────────────────────────────────────────────

@router.post("/auto-import/save")
async def auto_import_save(
    request: Request,
    db: Session = Depends(get_db),
):
    """スクレイピング結果をDBに保存"""
    body = await request.json()
    result = body.get("result", {})
    options = body.get("options", {})

    if not result or not result.get("username"):
        return JSONResponse({"ok": False, "error": "データが不正です"}, status_code=400)

    username = result["username"]

    # Creator 重複チェック
    existing = db.query(Creator).filter(
        Creator.myfans_profile_url == result["myfans_url"]
    ).first()

    if existing and not options.get("update_existing"):
        return JSONResponse({
            "ok": False,
            "error": f"このクリエイター ({username}) はすでに登録されています",
            "creator_id": existing.id,
        })

    if existing and options.get("update_existing"):
        creator = existing
        creator.display_name = result["display_name"] or creator.display_name
        creator.x_handle = result.get("x_handle") or creator.x_handle
        creator.memo = (creator.memo or "") + f"\n[{datetime.utcnow().date()}] 自動更新"
        creator.updated_at = datetime.utcnow()
    else:
        creator = Creator(
            display_name=result["display_name"] or username,
            myfans_profile_url=result["myfans_url"],
            x_handle=result.get("x_handle", ""),
            category=options.get("category", ""),
            tags=options.get("tags", ""),
            adult_flag=True,
            affiliate_enabled=True,
            estimated_aov=float(options.get("estimated_aov", 5000)),
            direct_rate=float(options.get("commission_rate", 10.0)),
            approval_status="pending",
            material_permission_status="pending",
            memo=f"自動取込: {result['affiliate_url']}",
        )
        db.add(creator)

    db.flush()

    # AffiliateLink 登録
    af_link = db.query(AffiliateLink).filter(
        AffiliateLink.affiliate_url == result["affiliate_url"]
    ).first()
    if not af_link:
        af_link = AffiliateLink(
            creator_id=creator.id,
            original_url=result["myfans_url"],
            affiliate_url=result["affiliate_url"],
            link_type="creator_link",
            estimated_rate=float(options.get("commission_rate", 10.0)),
            active=True,
            memo="自動取込",
        )
        db.add(af_link)
        db.flush()

    # Asset 登録（プロフィール画像）
    assets_created = 0
    if result.get("local_profile_image"):
        existing_asset = db.query(Asset).filter(
            Asset.source_url == result.get("profile_image_url", ""),
            Asset.creator_id == creator.id,
        ).first()
        if not existing_asset:
            asset = Asset(
                creator_id=creator.id,
                asset_type="image",
                source_type="myfans_official",
                file_path=result["local_profile_image"],
                asset_url=result["local_profile_image"],
                source_url=result.get("profile_image_url", ""),
                rights_status="pending",
                adult_level="none",
                source_note="プロフィール画像（自動取込）",
            )
            db.add(asset)
            assets_created += 1

    # Asset 登録（カバー画像）
    if result.get("local_cover_image"):
        existing_asset = db.query(Asset).filter(
            Asset.source_url == result.get("cover_image_url", ""),
            Asset.creator_id == creator.id,
        ).first()
        if not existing_asset:
            asset = Asset(
                creator_id=creator.id,
                asset_type="image",
                source_type="myfans_official",
                file_path=result["local_cover_image"],
                asset_url=result["local_cover_image"],
                source_url=result.get("cover_image_url", ""),
                rights_status="pending",
                adult_level="none",
                source_note="カバー画像（自動取込）",
            )
            db.add(asset)
            assets_created += 1

    # 投稿ごとに Asset + PostDraft 登録
    drafts_created = 0
    selected_posts = set(options.get("selected_post_ids", []))

    for post in result.get("posts", []):
        if selected_posts and post["post_id"] not in selected_posts:
            continue

        # サムネイル Asset
        thumb_asset = None
        if post.get("local_thumbnail"):
            existing_asset = db.query(Asset).filter(
                Asset.source_url == post.get("thumbnail_url", ""),
                Asset.creator_id == creator.id,
            ).first()
            if not existing_asset:
                thumb_asset = Asset(
                    creator_id=creator.id,
                    asset_type="thumbnail",
                    source_type="myfans_official",
                    file_path=post["local_thumbnail"],
                    asset_url=post["local_thumbnail"],
                    source_url=post.get("thumbnail_url", ""),
                    rights_status="pending",
                    adult_level="suggestive",
                    sensitive_required=True,
                    source_note=f"投稿サムネイル: {post['title'][:50]}",
                )
                db.add(thumb_asset)
                db.flush()
                assets_created += 1
            else:
                thumb_asset = existing_asset

        # サンプル画像 Asset
        for local_img, src_url in zip(post.get("local_images", []), post.get("sample_image_urls", [])):
            if not local_img:
                continue
            existing_asset = db.query(Asset).filter(
                Asset.source_url == src_url,
                Asset.creator_id == creator.id,
            ).first()
            if not existing_asset:
                a = Asset(
                    creator_id=creator.id,
                    asset_type="image",
                    source_type="myfans_official",
                    file_path=local_img,
                    asset_url=local_img,
                    source_url=src_url,
                    rights_status="pending",
                    adult_level="suggestive",
                    sensitive_required=True,
                    source_note=f"サンプル画像: {post['title'][:50]}",
                )
                db.add(a)
                assets_created += 1

        # PostDraft 生成
        if options.get("generate_drafts", True):
            body_text = _generate_draft_body(
                creator_name=result["display_name"],
                post_title=post["title"],
                post_body=post["body"],
                affiliate_url=result["affiliate_url"],
                commission_rate=float(options.get("commission_rate", 10.0)),
            )
            draft = PostDraft(
                creator_id=creator.id,
                affiliate_link_id=af_link.id,
                asset_id=thumb_asset.id if thumb_asset else None,
                post_type="introduction",
                title=post["title"][:200],
                body=body_text,
                hashtags=_generate_hashtags(result["display_name"], options.get("category", "")),
                status="draft",
                account_name=options.get("x_account", ""),
            )
            db.add(draft)
            drafts_created += 1

    # AutoImportJob 履歴
    job_record = AutoImportJob(
        affiliate_url=result["affiliate_url"],
        myfans_url=result["myfans_url"],
        username=username,
        display_name=result["display_name"],
        creator_id=creator.id,
        posts_fetched=len(result.get("posts", [])),
        assets_created=assets_created,
        drafts_created=drafts_created,
        status="completed",
    )
    db.add(job_record)
    db.commit()

    return JSONResponse({
        "ok": True,
        "creator_id": creator.id,
        "affiliate_link_id": af_link.id,
        "assets_created": assets_created,
        "drafts_created": drafts_created,
        "message": f"クリエイター登録完了！素材 {assets_created}件・下書き {drafts_created}件",
    })


# ─── API: ステータス確認（ポーリング用フォールバック）────────────────────────────

@router.get("/auto-import/status/{job_id}")
async def auto_import_status(job_id: str):
    job = _running_jobs.get(job_id)
    if not job:
        return JSONResponse({"status": "not_found"}, status_code=404)
    return JSONResponse(job)


# ─── 取込履歴 ─────────────────────────────────────────────────────────────────

@router.get("/auto-import/jobs")
async def auto_import_jobs(request: Request, db: Session = Depends(get_db)):
    from main import templates
    jobs = db.query(AutoImportJob).order_by(AutoImportJob.created_at.desc()).limit(50).all()
    return templates.TemplateResponse(request, "auto_import.html", {"history": jobs})


# ─── テキスト生成ヘルパー ─────────────────────────────────────────────────────

def _generate_draft_body(
    creator_name: str,
    post_title: str,
    post_body: str,
    affiliate_url: str,
    commission_rate: float,
) -> str:
    name = creator_name or "クリエイター"
    title_part = f"「{post_title}」" if post_title else ""
    preview = post_body[:80] + "..." if len(post_body) > 80 else post_body

    lines = [
        f"✨ {name} さんのMyFansをご紹介！",
        "",
    ]
    if title_part:
        lines.append(f"{title_part}")
    if preview:
        lines.append(preview)
    lines += [
        "",
        f"▶️ 続きはこちら → {affiliate_url}",
        "",
        "※本投稿はアフィリエイトリンクを含みます #PR",
        "※18歳以上限定コンテンツです",
    ]
    return "\n".join(lines)


def _generate_hashtags(creator_name: str, category: str) -> str:
    tags = ["#MyFans", "#アフィリエイト", "#PR"]
    if category:
        tags.append(f"#{category}")
    return " ".join(tags)


async def _generate_ai_copy_pack(result: ScrapedCreator, tone: str, platform: str) -> dict:
    fallback = _generate_copy_pack_from_scraped(result, tone, platform)
    anthropic_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if anthropic_key:
        return await _generate_with_anthropic(result, tone, platform, fallback, anthropic_key)

    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return fallback

    prompt = _build_ai_prompt(result, tone, platform)
    try:
        async with httpx.AsyncClient(timeout=35.0) as client:
            resp = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "You create compliant Japanese affiliate promotion copy. "
                                "Avoid explicit sexual wording, unverifiable claims, and direct promises. "
                                "Always include PR disclosure and 18+ warning."
                            ),
                        },
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.8,
                    "response_format": {"type": "json_object"},
                },
            )
        if resp.status_code >= 400:
            fallback["ai_note"] = f"OpenAI APIエラーのためローカル生成に切替: {resp.status_code}"
            return fallback
        content = resp.json()["choices"][0]["message"]["content"]
        generated = json.loads(content)
        return _merge_generated_pack(fallback, generated, result)
    except Exception as e:
        fallback["ai_note"] = f"AI生成に失敗したためローカル生成に切替: {e}"
        return fallback


async def _generate_with_anthropic(
    result: ScrapedCreator,
    tone: str,
    platform: str,
    fallback: dict,
    api_key: str,
) -> dict:
    prompt = _build_ai_prompt(result, tone, platform)
    model = os.getenv("ANTHROPIC_MODEL", "claude-opus-4-7")
    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "max_tokens": 1800,
                    "temperature": 0.8,
                    "system": (
                        "You create compliant Japanese affiliate promotion copy. "
                        "Return JSON only. Avoid explicit sexual wording, unverifiable claims, "
                        "and direct promises. Always include PR disclosure and 18+ warning."
                    ),
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
        if resp.status_code >= 400:
            fallback["ai_note"] = f"Anthropic APIエラーのためローカル生成に切替: {resp.status_code}"
            return fallback
        data = resp.json()
        text = _extract_anthropic_text(data)
        generated = json.loads(text)
        pack = _merge_generated_pack(fallback, generated, result)
        pack["ai_note"] = f"Anthropic {model} を使用して生成しました"
        return pack
    except Exception as e:
        fallback["ai_note"] = f"Claude生成に失敗したためローカル生成に切替: {e}"
        return fallback


def _extract_anthropic_text(data: dict) -> str:
    parts = data.get("content", [])
    texts = []
    for part in parts:
        if isinstance(part, dict) and part.get("type") == "text":
            texts.append(part.get("text", ""))
    return "\n".join(texts).strip()


def _build_ai_prompt(result: ScrapedCreator, tone: str, platform: str) -> str:
    sample_posts = []
    for post in result.posts[:3]:
        sample_posts.append({
            "title": post.title,
            "body": post.body[:180],
            "is_free": post.is_free,
            "price": post.price,
        })
    return json.dumps({
        "task": "Create a copy-paste ready Japanese promotion kit.",
        "platform": platform,
        "tone": tone,
        "creator": {
            "name": result.display_name or result.username,
            "username": result.username,
            "bio": result.bio[:300],
            "url": result.affiliate_url,
            "posts": sample_posts,
        },
        "required_json_keys": [
            "post_text",
            "short_text",
            "hashtags",
            "image_prompt",
            "video_prompt",
            "caption_variants",
        ],
        "rules": [
            "Japanese only",
            "No explicit sexual descriptions",
            "Do not mention scraped/private details as guaranteed facts",
            "Include affiliate URL in post_text",
            "Include #PR and 18+ warning",
            "image_prompt and video_prompt should be for safe promotional visuals, no nudity",
        ],
    }, ensure_ascii=False)


def _merge_generated_pack(fallback: dict, generated: dict, result: ScrapedCreator) -> dict:
    pack = fallback.copy()
    for key in ["post_text", "short_text", "hashtags", "image_prompt", "video_prompt"]:
        if isinstance(generated.get(key), str) and generated[key].strip():
            pack[key] = generated[key].strip()
    variants = generated.get("caption_variants")
    if isinstance(variants, list) and variants:
        pack["caption_variants"] = [str(v).strip() for v in variants if str(v).strip()][:3]
    pack["ai_note"] = "OPENAI_API_KEYを使用して生成しました"
    pack["creator"] = _creator_summary(result)
    return pack


def _generate_copy_pack_from_scraped(result: ScrapedCreator, tone: str, platform: str) -> dict:
    name = result.display_name or result.username or "注目クリエイター"
    first_post = result.posts[0] if result.posts else None
    hook = _tone_hook(tone, name)
    post_line = ""
    if first_post and first_post.title:
        post_line = f"\n\n新着・注目投稿: {first_post.title}"
    bio_line = f"\n{name}さんの雰囲気: {result.bio[:70]}" if result.bio else ""
    post_text = (
        f"{hook}{bio_line}{post_line}\n\n"
        f"気になる方はこちらからチェック\n{result.affiliate_url}\n\n"
        "※本投稿はアフィリエイトリンクを含みます #PR\n"
        "※18歳以上の方のみ閲覧できます"
    )
    short_text = (
        f"{name}さんのMyFansをチェック\n{result.affiliate_url}\n\n"
        "#PR ※18歳以上限定"
    )
    hashtags = "#MyFans #PR #アフィリエイト #推し活"
    image_prompt = (
        f"Japanese social media promotional image for {name}, clean premium layout, "
        "smartphone mockup, soft studio lighting, elegant typography space, no nudity, "
        "no explicit sexual content, safe for social ad review, include 18+ and PR label area"
    )
    video_prompt = (
        f"8 second vertical promotional video for {name}, quick cuts of abstract app screen mockups, "
        "glowing notification motion, tasteful creator profile reveal, CTA end card, no nudity, "
        "no explicit sexual content, add space for affiliate URL, Japanese social media style"
    )
    return {
        "creator": _creator_summary(result),
        "post_text": post_text,
        "short_text": short_text,
        "hashtags": hashtags,
        "image_prompt": image_prompt,
        "video_prompt": video_prompt,
        "caption_variants": [
            f"{name}さんの新着をチェック。雰囲気が気になったらリンクへ。 #PR",
            f"今日の注目MyFans: {name}さん。18歳以上の方のみどうぞ。 #PR",
            f"迷ったらまずここから。{name}さんのページをチェック。",
        ],
        "sample_media": _sample_media(result),
        "ai_note": "OPENAI_API_KEY未設定のため、内蔵テンプレートで生成しました",
    }


def _generate_copy_pack_from_url(affiliate_url: str, tone: str, platform: str) -> dict:
    name = "注目クリエイター"
    post_text = (
        f"{_tone_hook(tone, name)}\n\n"
        f"気になる方はこちらからチェック\n{affiliate_url}\n\n"
        "※本投稿はアフィリエイトリンクを含みます #PR\n"
        "※18歳以上の方のみ閲覧できます"
    )
    return {
        "creator": {
            "name": name,
            "username": "",
            "bio": "",
            "url": affiliate_url,
            "profile_image": "",
        },
        "post_text": post_text,
        "short_text": f"{name}をチェック\n{affiliate_url}\n\n#PR ※18歳以上限定",
        "hashtags": "#MyFans #PR #アフィリエイト",
        "image_prompt": (
            "Japanese social media promotional image for an adult creator platform affiliate post, "
            "premium clean design, smartphone mockup, CTA area, PR label, 18+ label, no nudity, no explicit content"
        ),
        "video_prompt": (
            "8 second vertical promotional video, app profile mockup, tasteful motion graphics, CTA end card, "
            "PR and 18+ labels, no nudity, no explicit content"
        ),
        "caption_variants": [
            "気になる方はこちらからチェック。 #PR",
            "18歳以上の方のみどうぞ。 #PR",
            "今日の注目ページはこちら。",
        ],
        "sample_media": [],
        "ai_note": "URL解析ができなかったため、URLだけで生成しました",
    }


def _tone_hook(tone: str, name: str) -> str:
    hooks = {
        "friendly": f"今日の注目は {name} さん。",
        "premium": f"大人向けに、落ち着いた雰囲気で楽しめる {name} さんのMyFans。",
        "urgent": f"あとで見返せるように保存推奨。{name} さんのページをチェック。",
        "soft": f"雰囲気重視で選ぶなら、{name} さんをチェック。",
    }
    return hooks.get(tone, hooks["friendly"])


def _creator_summary(result: ScrapedCreator) -> dict:
    return {
        "name": result.display_name or result.username,
        "username": result.username,
        "bio": result.bio,
        "url": result.affiliate_url,
        "myfans_url": result.myfans_url,
        "profile_image": result.local_profile_image or result.profile_image_url,
        "cover_image": result.local_cover_image or result.cover_image_url,
        "post_count": result.post_count,
        "follower_count": result.follower_count,
    }


def _sample_media(result: ScrapedCreator) -> list[dict]:
    media = []
    for post in result.posts[:8]:
        image = post.local_thumbnail or post.thumbnail_url
        if image:
            media.append({"type": "image", "url": image, "title": post.title or "サンプル画像"})
        for img in (post.local_images or post.sample_image_urls or [])[:2]:
            media.append({"type": "image", "url": img, "title": post.title or "サンプル画像"})
    return media[:12]
