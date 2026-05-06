import re
from sqlalchemy.orm import Session
from models import PostDraft, ComplianceLog, Creator, AffiliateLink, Asset
from datetime import datetime, timedelta, date


FORBIDDEN_WORDS = [
    "無修正", "児童", "未成年", "子供", "幼", "ロリ",
    "保証", "確実に", "絶対稼げる", "必ず稼げる",
    "自動DM", "自動リプ", "自動フォロー", "自動いいね",
]

PR_PATTERNS = [
    r"#PR", r"#pr", r"＃PR", r"＃pr",
    r"\bPR\b", r"\bpr\b", r"広告", r"アフィリエイト",
    r"宣伝", r"プロモーション",
]

AGE_WARNING_PATTERNS = [
    r"18歳未満", r"成人向け", r"R-18", r"R18",
    r"年齢確認", r"18\+", r"大人向け",
]


def run_compliance_check(post_draft: PostDraft, db: Session, target_platform: str = "x") -> dict:
    logs = []
    score = 100.0
    has_errors = False

    creator = db.query(Creator).filter(Creator.id == post_draft.creator_id).first()

    def add_log(check_name, result, message):
        nonlocal score, has_errors
        logs.append({"check_name": check_name, "result": result, "message": message})
        if result == "error":
            score -= 20.0
            has_errors = True
        elif result == "warning":
            score -= 5.0

    body = post_draft.body or ""

    # 1. PR表記チェック
    if any(re.search(p, body) for p in PR_PATTERNS):
        add_log("PR表記", "ok", "#PR または PR表記が含まれています。")
    else:
        add_log("PR表記", "error", "#PR または PR表記がありません。投稿文に必ず追加してください。")

    # 2. 成人向け注意文チェック
    if any(re.search(p, body) for p in AGE_WARNING_PATTERNS):
        add_log("年齢確認表記", "ok", "成人向け・18歳未満不可の表記があります。")
    else:
        add_log("年齢確認表記", "error", "「18歳未満不可」または「成人向け」の表記がありません。")

    # 3. アフィリエイトURL登録チェック
    if post_draft.affiliate_link_id:
        link = db.query(AffiliateLink).filter(AffiliateLink.id == post_draft.affiliate_link_id).first()
        if link and link.active:
            add_log("アフィリエイトURL", "ok", f"有効なアフィリエイトリンクが設定されています: {link.affiliate_url[:50]}...")
        else:
            add_log("アフィリエイトURL", "warning", "アフィリエイトリンクが無効または削除されています。")
    else:
        add_log("アフィリエイトURL", "warning", "アフィリエイトリンクが設定されていません。")

    # 4. 素材権利確認チェック（拡張）
    asset = None
    if post_draft.asset_id:
        asset = db.query(Asset).filter(Asset.id == post_draft.asset_id).first()
        if not asset:
            add_log("素材権利確認", "warning", "選択された素材が見つかりません。")
        elif asset.rights_status != "approved":
            add_log("素材権利確認", "error",
                    f"素材の権利確認ステータスが '{asset.rights_status}' です。approved にしてから投稿してください。")
        elif asset.source_type == "unknown":
            add_log("素材権利確認", "error", "ソースが unknown の素材は投稿に使用できません。")
        elif asset.source_type == "x_post" and not asset.creator_permission_note:
            add_log("素材権利確認", "error", "X投稿素材はクリエイターの許諾メモが必要です。")
        elif asset.usage_expiry_date and asset.usage_expiry_date < date.today():
            add_log("素材権利確認", "error", f"素材の使用期限が切れています（{asset.usage_expiry_date}）。")
        else:
            add_log("素材権利確認", "ok", "素材の利用権利が確認済みです。")

        # 4b. 投稿先プラットフォームチェック
        if asset and asset.allowed_platforms:
            allowed = [p.strip() for p in asset.allowed_platforms.split(",")]
            if target_platform in allowed or "none" not in allowed and len(allowed) > 0:
                if target_platform not in allowed and allowed != ["none"]:
                    add_log("掲載先チェック", "error",
                            f"投稿先 '{target_platform}' がallowed_platformsに含まれていません（許可: {asset.allowed_platforms}）。")
                else:
                    add_log("掲載先チェック", "ok", f"投稿先 '{target_platform}' は許可されています。")

        # 4c. センシティブ設定チェック
        if asset and asset.adult_level in ("adult", "explicit") and target_platform == "x":
            if asset.sensitive_required:
                add_log("センシティブ設定", "warning",
                        "adult/explicit素材をXに投稿する場合、センシティブ設定が必要です。投稿前に確認してください。")
            else:
                add_log("センシティブ設定", "error",
                        "adult/explicit素材はXでのセンシティブ設定が必要ですが、素材のsensitive_requiredが未設定です。")
    else:
        add_log("素材権利確認", "ok", "素材なし（テキストのみ投稿）。")

    # 5. MyFans広告物確認チェック（素材 + クリエイター）
    if asset and asset.myfans_ad_review_status not in ("approved", "not_required"):
        add_log("MyFans広告物確認", "error",
                f"素材のMyFans広告審査ステータスが '{asset.myfans_ad_review_status}' です。")
    elif creator:
        if creator.myfans_ad_review_status == "approved":
            add_log("MyFans広告物確認", "ok", "MyFans広告物の審査が完了しています。")
        else:
            add_log("MyFans広告物確認", "error",
                    f"クリエイターのMyFans広告物確認ステータスが '{creator.myfans_ad_review_status}' です。")

    # 6. クリエイター素材許諾チェック
    if creator:
        if creator.material_permission_status == "approved":
            add_log("クリエイター素材許諾", "ok", "クリエイターからの素材利用許諾が完了しています。")
        else:
            add_log("クリエイター素材許諾", "error",
                    f"素材利用許諾ステータスが '{creator.material_permission_status}' です。")

    # 7. クリエイター承認チェック
    if creator:
        if creator.approval_status == "approved":
            add_log("クリエイター承認", "ok", "クリエイターは承認済みです。")
        elif creator.approval_status == "rejected":
            add_log("クリエイター承認", "error", "このクリエイターはrejectされています。使用できません。")
        else:
            add_log("クリエイター承認", "warning",
                    f"クリエイターの承認ステータスが '{creator.approval_status}' です。")

    # 8. 禁止ワードチェック（自動DM・自動いいね含む）
    found_forbidden = [w for w in FORBIDDEN_WORDS if w in body]
    if found_forbidden:
        add_log("禁止ワード", "error", f"禁止ワードが含まれています: {', '.join(found_forbidden)}")
    else:
        add_log("禁止ワード", "ok", "禁止ワードは検出されませんでした。")

    # 9. 重複投稿チェック（直近30投稿）
    recent_posts = db.query(PostDraft).filter(
        PostDraft.id != post_draft.id,
        PostDraft.status != "rejected"
    ).order_by(PostDraft.created_at.desc()).limit(30).all()

    duplicate_score = 0.0
    for recent in recent_posts:
        if recent.body and body:
            body_words = set(body.split())
            recent_words = set(recent.body.split())
            if body_words and recent_words:
                overlap = len(body_words & recent_words) / max(len(body_words), len(recent_words))
                if overlap > duplicate_score:
                    duplicate_score = overlap

    if duplicate_score > 0.8:
        add_log("重複チェック", "error",
                f"類似投稿が直近30件内に存在します（類似度: {duplicate_score:.0%}）。内容を変更してください。")
    elif duplicate_score > 0.5:
        add_log("重複チェック", "warning", f"類似度の高い投稿があります（類似度: {duplicate_score:.0%}）。")
    else:
        add_log("重複チェック", "ok", "重複投稿は検出されませんでした。")

    # 10. 同一素材の短時間連投チェック（3時間以内）
    if post_draft.asset_id:
        three_hours_ago = datetime.utcnow() - timedelta(hours=3)
        same_asset_count = db.query(PostDraft).filter(
            PostDraft.id != post_draft.id,
            PostDraft.asset_id == post_draft.asset_id,
            PostDraft.scheduled_at >= three_hours_ago,
            PostDraft.status.in_(["approved", "posted"])
        ).count()
        if same_asset_count > 0:
            add_log("素材連投チェック", "warning",
                    f"同じ素材を使った投稿が3時間以内に{same_asset_count}件あります。")
        else:
            add_log("素材連投チェック", "ok", "同一素材の連投はありません。")

    # 11. 同一クリエイター連投チェック（1時間以内）
    if creator:
        one_hour_ago = datetime.utcnow() - timedelta(hours=1)
        recent_same_creator = db.query(PostDraft).filter(
            PostDraft.id != post_draft.id,
            PostDraft.creator_id == post_draft.creator_id,
            PostDraft.scheduled_at >= one_hour_ago,
            PostDraft.status.in_(["approved", "posted"])
        ).count()
        if recent_same_creator > 0:
            add_log("連投チェック", "warning",
                    f"同じクリエイターの投稿が1時間以内に{recent_same_creator}件あります。")
        else:
            add_log("連投チェック", "ok", "同一クリエイターの連投はありません。")

    score = max(0.0, score)

    # DBに保存
    db.query(ComplianceLog).filter(ComplianceLog.post_draft_id == post_draft.id).delete()
    for log in logs:
        db.add(ComplianceLog(
            post_draft_id=post_draft.id,
            check_name=log["check_name"],
            result=log["result"],
            message=log["message"],
        ))

    post_draft.compliance_score = score
    post_draft.compliance_notes = "\n".join(
        [f"[{l['result'].upper()}] {l['check_name']}: {l['message']}" for l in logs]
    )
    post_draft.duplicate_score = duplicate_score
    post_draft.manual_review_required = has_errors
    db.commit()

    return {
        "score": score,
        "logs": logs,
        "has_errors": has_errors,
        "can_approve": not has_errors and score >= 60,
    }
