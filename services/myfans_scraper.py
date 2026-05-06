"""
myfans_scraper.py — MyFans アフィリリンクからの全自動取込サービス

フロー:
  1. アフィリリンク → リダイレクト解決 → MyFans URL取得
  2. MyFans API でクリエイタープロフィール取得
  3. 公開投稿 + サンプル画像一覧取得
  4. 画像ダウンロード → static/uploads/scraped/
  5. DB保存 (Creator + AffiliateLink + Asset + PostDraft)
"""

import re
import os
import asyncio
import hashlib
import httpx
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
from bs4 import BeautifulSoup
from typing import Optional
from dataclasses import dataclass, field


SCRAPED_DIR = "static/uploads/scraped"
os.makedirs(SCRAPED_DIR, exist_ok=True)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/html, */*",
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
    "Referer": "https://myfans.jp/",
}

MYFANS_API = "https://api.myfans.jp"
MYFANS_WEB = "https://myfans.jp"


@dataclass
class ScrapedPost:
    post_id: str
    title: str
    body: str
    price: int
    is_free: bool
    thumbnail_url: str
    sample_image_urls: list[str] = field(default_factory=list)
    published_at: str = ""
    local_thumbnail: str = ""
    local_images: list[str] = field(default_factory=list)


@dataclass
class ScrapedCreator:
    username: str
    display_name: str
    bio: str
    profile_image_url: str
    cover_image_url: str
    follower_count: int
    post_count: int
    myfans_url: str
    affiliate_url: str
    x_handle: str = ""
    local_profile_image: str = ""
    local_cover_image: str = ""
    posts: list[ScrapedPost] = field(default_factory=list)
    error: str = ""


# ─── URL ユーティリティ ────────────────────────────────────────────────────────

def extract_myfans_username(url: str) -> Optional[str]:
    """myfans.jp URLからusernameを抽出"""
    parsed = urlparse(url)
    if "myfans.jp" not in parsed.netloc:
        return None
    path = parsed.path.strip("/")
    parts = path.split("/")
    if not parts or not parts[0]:
        return None
    username = parts[0]
    if username in ("login", "signup", "terms", "privacy", "help", "about"):
        return None
    return username


def build_affiliate_url(base_url: str, original_url: str) -> str:
    """元のアフィリリンクのクエリパラメータを保持"""
    parsed_orig = urlparse(original_url)
    parsed_base = urlparse(base_url)
    orig_params = parse_qs(parsed_orig.query)
    base_params = parse_qs(parsed_base.query)
    merged = {**orig_params, **base_params}
    flat = {k: v[0] for k, v in merged.items()}
    new_query = urlencode(flat)
    return urlunparse(parsed_base._replace(query=new_query))


# ─── リダイレクト解決 ──────────────────────────────────────────────────────────

async def resolve_affiliate_link(url: str) -> str:
    """アフィリリンクをフォローして最終URLを返す"""
    try:
        async with httpx.AsyncClient(
            headers=HEADERS,
            follow_redirects=True,
            timeout=15.0,
        ) as client:
            resp = await client.head(url)
            final = str(resp.url)
            if "myfans.jp" in final:
                return final
            resp2 = await client.get(url)
            return str(resp2.url)
    except Exception:
        return url


# ─── MyFans API 呼び出し ──────────────────────────────────────────────────────

async def fetch_creator_api(username: str, client: httpx.AsyncClient) -> Optional[dict]:
    """MyFans API v2 でクリエイター情報を取得"""
    endpoints = [
        f"{MYFANS_API}/api/v2/users/show?username={username}",
        f"{MYFANS_API}/api/v2/users/{username}",
        f"{MYFANS_API}/api/v2/creators/{username}",
    ]
    for ep in endpoints:
        try:
            resp = await client.get(ep, headers={**HEADERS, "Accept": "application/json"})
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, dict) and ("data" in data or "id" in data or "username" in data):
                    return data.get("data", data)
        except Exception:
            continue
    return None


async def fetch_posts_api(user_id: str, client: httpx.AsyncClient) -> list[dict]:
    """MyFans API v2 で公開投稿一覧を取得"""
    endpoints = [
        f"{MYFANS_API}/api/v2/posts?user_id={user_id}&page=1&per_page=20&sort=newest",
        f"{MYFANS_API}/api/v2/users/{user_id}/posts?page=1&per_page=20",
        f"{MYFANS_API}/api/v2/creators/{user_id}/posts?page=1",
    ]
    for ep in endpoints:
        try:
            resp = await client.get(ep, headers={**HEADERS, "Accept": "application/json"})
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, dict):
                    items = data.get("data", data.get("posts", data.get("items", [])))
                    if isinstance(items, list):
                        return items
                elif isinstance(data, list):
                    return data
        except Exception:
            continue
    return []


# ─── HTMLスクレイピング（APIが失敗した場合のフォールバック）────────────────────

async def scrape_creator_from_html(username: str, client: httpx.AsyncClient) -> Optional[dict]:
    """HTMLをパースしてクリエイター情報を抽出（Next.js __NEXT_DATA__）"""
    try:
        resp = await client.get(
            f"{MYFANS_WEB}/{username}",
            headers={**HEADERS, "Accept": "text/html"},
            follow_redirects=True,
        )
        if resp.status_code != 200:
            return None
        soup = BeautifulSoup(resp.text, "html.parser")

        # Next.js の __NEXT_DATA__ からJSONを抽出
        next_data_tag = soup.find("script", id="__NEXT_DATA__")
        if next_data_tag:
            import json
            try:
                next_data = json.loads(next_data_tag.string or "{}")
                props = next_data.get("props", {}).get("pageProps", {})
                user = props.get("user") or props.get("creator") or props.get("profile")
                if user and isinstance(user, dict):
                    return user
                # 深い階層も探索
                for key in ["initialState", "dehydratedState", "data"]:
                    sub = props.get(key, {})
                    if isinstance(sub, dict):
                        for k, v in sub.items():
                            if isinstance(v, dict) and v.get("username") == username:
                                return v
            except Exception:
                pass

        # OGPメタタグからフォールバック
        og_title = soup.find("meta", property="og:title")
        og_image = soup.find("meta", property="og:image")
        og_desc = soup.find("meta", property="og:description")

        result: dict = {"username": username}
        if og_title:
            result["name"] = og_title.get("content", username)
        if og_image:
            result["profile_image"] = {"url": og_image.get("content", "")}
        if og_desc:
            result["biography"] = og_desc.get("content", "")

        # 名前タグを探す
        h1 = soup.find("h1")
        if h1:
            result["name"] = h1.get_text(strip=True)

        return result if result.get("name") else None
    except Exception:
        return None


async def scrape_posts_from_html(username: str, client: httpx.AsyncClient) -> list[dict]:
    """HTMLから投稿サンプル画像をスクレイピング"""
    posts = []
    try:
        resp = await client.get(
            f"{MYFANS_WEB}/{username}",
            headers={**HEADERS, "Accept": "text/html"},
            follow_redirects=True,
        )
        if resp.status_code != 200:
            return posts
        soup = BeautifulSoup(resp.text, "html.parser")

        # Next.js data
        next_data_tag = soup.find("script", id="__NEXT_DATA__")
        if next_data_tag:
            import json
            try:
                next_data = json.loads(next_data_tag.string or "{}")
                props = next_data.get("props", {}).get("pageProps", {})
                for key in ["posts", "postList", "items"]:
                    items = props.get(key, [])
                    if isinstance(items, list) and items:
                        return items
            except Exception:
                pass

        # img タグから画像URLを収集
        imgs = soup.find_all("img", src=True)
        seen = set()
        for i, img in enumerate(imgs[:20]):
            src = img.get("src", "")
            if not src or src in seen:
                continue
            if any(x in src for x in ["profile", "avatar", "logo", "icon", "banner"]):
                continue
            if src.startswith("http") and ("cdn" in src or "storage" in src or "image" in src):
                seen.add(src)
                posts.append({
                    "id": f"html_{i}",
                    "title": img.get("alt", f"投稿 {i+1}"),
                    "body": "",
                    "price": 0,
                    "thumbnail": {"url": src},
                    "sample_images": [],
                    "is_free": True,
                    "published_at": "",
                })
    except Exception:
        pass
    return posts


# ─── 画像ダウンロード ─────────────────────────────────────────────────────────

async def download_image(url: str, prefix: str, client: httpx.AsyncClient) -> str:
    """画像をダウンロードしてローカルパスを返す"""
    if not url or not url.startswith("http"):
        return ""
    url_hash = hashlib.md5(url.encode()).hexdigest()[:12]
    ext = url.split("?")[0].split(".")[-1].lower()
    if ext not in ("jpg", "jpeg", "png", "gif", "webp"):
        ext = "jpg"
    filename = f"{prefix}_{url_hash}.{ext}"
    filepath = os.path.join(SCRAPED_DIR, filename)
    if os.path.exists(filepath):
        return f"/static/uploads/scraped/{filename}"
    try:
        resp = await client.get(url, headers=HEADERS, timeout=20.0, follow_redirects=True)
        if resp.status_code == 200 and len(resp.content) > 500:
            with open(filepath, "wb") as f:
                f.write(resp.content)
            return f"/static/uploads/scraped/{filename}"
    except Exception:
        pass
    return ""


# ─── データ正規化 ─────────────────────────────────────────────────────────────

def normalize_creator(raw: dict, username: str) -> dict:
    """APIレスポンスを統一フォーマットに変換"""
    def find(d, *keys):
        for k in keys:
            v = d.get(k)
            if v is not None:
                return v
        return None

    name = find(raw, "name", "display_name", "nickname", "username") or username
    bio = find(raw, "biography", "bio", "description", "introduction") or ""
    followers = find(raw, "followers_count", "follower_count", "follow_count") or 0
    post_count = find(raw, "posts_count", "post_count", "contents_count") or 0
    uid = find(raw, "id", "user_id", "creator_id") or username

    profile_img = ""
    for k in ("profile_image", "avatar", "icon", "thumbnail"):
        v = raw.get(k)
        if isinstance(v, dict):
            profile_img = v.get("url", v.get("original_url", ""))
            break
        elif isinstance(v, str) and v.startswith("http"):
            profile_img = v
            break

    cover_img = ""
    for k in ("cover_image", "header_image", "banner_image", "background_image"):
        v = raw.get(k)
        if isinstance(v, dict):
            cover_img = v.get("url", v.get("original_url", ""))
            break
        elif isinstance(v, str) and v.startswith("http"):
            cover_img = v
            break

    x_url = ""
    sns = raw.get("sns_links", raw.get("social_links", {}))
    if isinstance(sns, dict):
        x_url = sns.get("twitter", sns.get("x", ""))
    if not x_url:
        x_url = find(raw, "twitter_url", "x_url", "twitter") or ""

    return {
        "id": str(uid),
        "username": username,
        "name": str(name),
        "bio": str(bio)[:500],
        "profile_image_url": profile_img,
        "cover_image_url": cover_img,
        "followers_count": int(followers) if str(followers).isdigit() else 0,
        "posts_count": int(post_count) if str(post_count).isdigit() else 0,
        "x_url": x_url,
    }


def normalize_post(raw: dict, idx: int) -> dict:
    """投稿データを統一フォーマットに変換"""
    def find(d, *keys):
        for k in keys:
            v = d.get(k)
            if v is not None:
                return v
        return None

    post_id = str(find(raw, "id", "post_id", "content_id") or f"post_{idx}")
    title = str(find(raw, "title", "name", "subject") or f"投稿 {idx+1}")
    body = str(find(raw, "body", "content", "description", "text") or "")[:1000]
    price = int(find(raw, "price", "amount", "point") or 0)
    is_free = price == 0 or bool(find(raw, "is_free", "free"))
    published_at = str(find(raw, "published_at", "created_at", "posted_at") or "")

    thumb = ""
    for k in ("thumbnail", "thumbnail_image", "cover_image", "main_image"):
        v = raw.get(k)
        if isinstance(v, dict):
            thumb = v.get("url", v.get("original_url", v.get("thumb_url", "")))
            break
        elif isinstance(v, str) and v.startswith("http"):
            thumb = v
            break

    samples = []
    for k in ("sample_images", "preview_images", "images", "media"):
        v = raw.get(k, [])
        if isinstance(v, list):
            for item in v[:5]:
                if isinstance(item, dict):
                    url = item.get("url", item.get("original_url", ""))
                    if url:
                        samples.append(url)
                elif isinstance(item, str) and item.startswith("http"):
                    samples.append(item)
            if samples:
                break

    return {
        "post_id": post_id,
        "title": title,
        "body": body,
        "price": price,
        "is_free": is_free,
        "thumbnail_url": thumb,
        "sample_image_urls": samples[:5],
        "published_at": published_at,
    }


# ─── メイン取込関数 ───────────────────────────────────────────────────────────

async def scrape_from_affiliate_link(
    affiliate_url: str,
    progress_callback=None,
) -> ScrapedCreator:
    """
    アフィリリンクから全データを取得してScrapedCreatorを返す。
    progress_callback(step: str, detail: str) で進捗を通知。
    """

    def progress(step, detail=""):
        if progress_callback:
            progress_callback(step, detail)

    progress("リダイレクト解決中...", affiliate_url)

    async with httpx.AsyncClient(
        headers=HEADERS,
        follow_redirects=True,
        timeout=20.0,
    ) as client:
        # 1. リダイレクト解決
        resolved_url = await resolve_affiliate_link(affiliate_url)
        progress("URL解決完了", resolved_url)

        username = extract_myfans_username(resolved_url)
        if not username:
            # 元URLからも試みる
            username = extract_myfans_username(affiliate_url)
        if not username:
            return ScrapedCreator(
                username="", display_name="", bio="",
                profile_image_url="", cover_image_url="",
                follower_count=0, post_count=0,
                myfans_url=affiliate_url, affiliate_url=affiliate_url,
                error=f"MyFansのURLが見つかりません: {resolved_url}",
            )

        myfans_url = f"{MYFANS_WEB}/{username}"
        final_affiliate_url = build_affiliate_url(resolved_url, affiliate_url)
        progress("クリエイター情報取得中...", f"@{username}")

        # 2. クリエイター情報取得（API → HTMLフォールバック）
        raw_creator = await fetch_creator_api(username, client)
        if not raw_creator:
            progress("HTMLスクレイピング中...", myfans_url)
            raw_creator = await scrape_creator_from_html(username, client)

        if not raw_creator:
            raw_creator = {"username": username, "name": username}

        creator_data = normalize_creator(raw_creator, username)
        progress("投稿一覧取得中...", f"{creator_data['posts_count']}件")

        # 3. 投稿一覧取得
        raw_posts = await fetch_posts_api(creator_data["id"], client)
        if not raw_posts:
            raw_posts = await scrape_posts_from_html(username, client)

        posts_data = [normalize_post(p, i) for i, p in enumerate(raw_posts[:15])]
        progress("画像ダウンロード中...", f"プロフィール画像 + {len(posts_data)}件の投稿画像")

        # 4. 画像ダウンロード（並行）
        download_tasks = []

        # プロフィール画像
        if creator_data["profile_image_url"]:
            download_tasks.append(("profile", creator_data["profile_image_url"], f"{username}_profile"))
        if creator_data["cover_image_url"]:
            download_tasks.append(("cover", creator_data["cover_image_url"], f"{username}_cover"))

        # 投稿サムネイル + サンプル画像
        post_img_tasks = []
        for p in posts_data:
            if p["thumbnail_url"]:
                post_img_tasks.append((p["post_id"], "thumb", p["thumbnail_url"], f"{username}_{p['post_id']}_thumb"))
            for si, surl in enumerate(p["sample_image_urls"]):
                post_img_tasks.append((p["post_id"], f"sample_{si}", surl, f"{username}_{p['post_id']}_s{si}"))

        # 並行ダウンロード（最大5並行）
        semaphore = asyncio.Semaphore(5)

        async def dl(url, prefix):
            async with semaphore:
                return await download_image(url, prefix, client)

        creator_imgs = await asyncio.gather(*[dl(url, pfx) for _, url, pfx in download_tasks])
        post_imgs = await asyncio.gather(*[dl(url, pfx) for _, _, url, pfx in post_img_tasks])

        # 結果を紐付け
        local_profile = ""
        local_cover = ""
        for (kind, _, __), local in zip(download_tasks, creator_imgs):
            if kind == "profile":
                local_profile = local
            elif kind == "cover":
                local_cover = local

        post_img_map: dict[str, dict] = {}
        for (pid, kind, _, __), local in zip(post_img_tasks, post_imgs):
            if pid not in post_img_map:
                post_img_map[pid] = {"thumb": "", "samples": []}
            if kind == "thumb":
                post_img_map[pid]["thumb"] = local
            elif kind.startswith("sample"):
                post_img_map[pid]["samples"].append(local)

        # 5. ScrapedPost 組み立て
        scraped_posts = []
        for p in posts_data:
            img_info = post_img_map.get(p["post_id"], {"thumb": "", "samples": []})
            scraped_posts.append(ScrapedPost(
                post_id=p["post_id"],
                title=p["title"],
                body=p["body"],
                price=p["price"],
                is_free=p["is_free"],
                thumbnail_url=p["thumbnail_url"],
                sample_image_urls=p["sample_image_urls"],
                published_at=p["published_at"],
                local_thumbnail=img_info["thumb"],
                local_images=img_info["samples"],
            ))

        progress("取込完了！", f"投稿 {len(scraped_posts)}件 / 画像 {sum(1 for l in (creator_imgs or []) + (post_imgs or []) if l)}枚")

        return ScrapedCreator(
            username=username,
            display_name=creator_data["name"],
            bio=creator_data["bio"],
            profile_image_url=creator_data["profile_image_url"],
            cover_image_url=creator_data["cover_image_url"],
            follower_count=creator_data["followers_count"],
            post_count=creator_data["posts_count"],
            myfans_url=myfans_url,
            affiliate_url=final_affiliate_url,
            x_handle=creator_data.get("x_url", ""),
            local_profile_image=local_profile,
            local_cover_image=local_cover,
            posts=scraped_posts,
        )
