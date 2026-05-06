"""
auto_import.py — アフィリリンク全自動取込ルーター

GET  /auto-import          — 取込ページ
POST /auto-import/analyze  — リンク解析・プレビュー取得 (JSON)
POST /auto-import/save     — DB保存確定
GET  /auto-import/jobs     — 取込履歴
"""

import asyncio
import json
from datetime import datetime
from fastapi import APIRouter, Request, Depends, Form, BackgroundTasks
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.orm import Session

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
