from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, Text, ForeignKey, Date
from sqlalchemy.orm import relationship
from database import Base
from datetime import datetime


class Creator(Base):
    __tablename__ = "creators"

    id = Column(Integer, primary_key=True, index=True)
    display_name = Column(String(200), nullable=False)
    myfans_profile_url = Column(String(500))
    x_handle = Column(String(100))
    category = Column(String(100))
    tags = Column(String(500))
    adult_flag = Column(Boolean, default=True)
    affiliate_enabled = Column(Boolean, default=True)
    estimated_aov = Column(Float, default=5000.0)
    direct_rate = Column(Float, default=10.0)
    category_rate = Column(Float, default=10.0)
    actual_rate_note = Column(Text)
    content_quality_score = Column(Integer, default=0)
    engagement_score = Column(Integer, default=0)
    conversion_score = Column(Integer, default=0)
    trust_score = Column(Integer, default=0)
    total_score = Column(Float, default=0.0)
    approval_status = Column(String(50), default="pending")
    material_permission_status = Column(String(50), default="pending")
    myfans_ad_review_status = Column(String(50), default="pending")
    memo = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    affiliate_links = relationship("AffiliateLink", back_populates="creator")
    post_drafts = relationship("PostDraft", back_populates="creator")
    assets = relationship("Asset", back_populates="creator")
    performance_reports = relationship("PerformanceReport", back_populates="creator")


class CreatorCandidate(Base):
    __tablename__ = "creator_candidates"

    id = Column(Integer, primary_key=True, index=True)
    url = Column(String(500), nullable=False, unique=True)
    url_type = Column(String(50), default="unknown")
    display_name = Column(String(200))
    myfans_url = Column(String(500))
    x_url = Column(String(500))
    category = Column(String(100))
    tags = Column(String(500))
    estimated_aov = Column(Float)
    recommended_post_url = Column(String(500))
    desired_description = Column(Text)
    allowed_media_type = Column(String(200))
    allowed_platforms = Column(String(200))
    usage_expiry_date = Column(Date)
    ng_words = Column(Text)
    memo = Column(Text)
    status = Column(String(50), default="new")
    source = Column(String(50), default="url_import")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    link_queue_items = relationship("LinkQueueItem", back_populates="creator_candidate")


class LinkQueueItem(Base):
    __tablename__ = "link_queue_items"

    id = Column(Integer, primary_key=True, index=True)
    creator_candidate_id = Column(Integer, ForeignKey("creator_candidates.id"), nullable=True)
    creator_id = Column(Integer, ForeignKey("creators.id"), nullable=True)
    original_url = Column(String(500), nullable=False)
    affiliate_url = Column(String(500))
    link_type = Column(String(50), default="creator_link")
    commission_rate = Column(Float, default=10.0)
    active = Column(Boolean, default=True)
    status = Column(String(50), default="pending")
    memo = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    creator_candidate = relationship("CreatorCandidate", back_populates="link_queue_items")


class AffiliateLink(Base):
    __tablename__ = "affiliate_links"

    id = Column(Integer, primary_key=True, index=True)
    creator_id = Column(Integer, ForeignKey("creators.id"), nullable=False)
    original_url = Column(String(500), nullable=False)
    affiliate_url = Column(String(500), nullable=False)
    link_type = Column(String(50), default="creator_link")
    estimated_rate = Column(Float, default=10.0)
    cookie_hours = Column(Integer, default=720)
    approved_media_name = Column(String(200))
    active = Column(Boolean, default=True)
    memo = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    creator = relationship("Creator", back_populates="affiliate_links")
    post_drafts = relationship("PostDraft", back_populates="affiliate_link")
    performance_reports = relationship("PerformanceReport", back_populates="affiliate_link")


class Asset(Base):
    __tablename__ = "assets"

    id = Column(Integer, primary_key=True, index=True)
    creator_id = Column(Integer, ForeignKey("creators.id"), nullable=False)
    asset_type = Column(String(50), default="image")
    source_type = Column(String(50), default="unknown")
    file_path = Column(String(500))
    asset_url = Column(String(500))
    source_url = Column(String(500))
    rights_status = Column(String(50), default="pending")
    allowed_platforms = Column(String(200), default="none")
    adult_level = Column(String(50), default="none")
    sensitive_required = Column(Boolean, default=False)
    sensitive_flag = Column(Boolean, default=False)
    usage_expiry_date = Column(Date)
    expiry_date = Column(Date)
    myfans_ad_review_status = Column(String(50), default="not_required")
    creator_permission_note = Column(Text)
    ng_notes = Column(Text)
    source_note = Column(Text)
    memo = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    creator = relationship("Creator", back_populates="assets")


class GeneratedCard(Base):
    __tablename__ = "generated_cards"

    id = Column(Integer, primary_key=True, index=True)
    creator_name = Column(String(200))
    genre = Column(String(100))
    catchphrase = Column(String(300))
    lp_url = Column(String(500))
    background_color = Column(String(50), default="#1a1a2e")
    file_path_wide = Column(String(500))
    file_path_square = Column(String(500))
    file_path_story = Column(String(500))
    created_at = Column(DateTime, default=datetime.utcnow)


class PostDraft(Base):
    __tablename__ = "post_drafts"

    id = Column(Integer, primary_key=True, index=True)
    creator_id = Column(Integer, ForeignKey("creators.id"), nullable=False)
    affiliate_link_id = Column(Integer, ForeignKey("affiliate_links.id"))
    asset_id = Column(Integer, ForeignKey("assets.id"))
    post_type = Column(String(50), default="introduction")
    title = Column(String(300))
    body = Column(Text, nullable=False)
    hashtags = Column(String(500))
    scheduled_at = Column(DateTime)
    account_name = Column(String(100))
    status = Column(String(50), default="draft")
    compliance_score = Column(Float, default=0.0)
    compliance_notes = Column(Text)
    duplicate_score = Column(Float, default=0.0)
    manual_review_required = Column(Boolean, default=False)
    posted_url = Column(String(500))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    creator = relationship("Creator", back_populates="post_drafts")
    affiliate_link = relationship("AffiliateLink", back_populates="post_drafts")
    compliance_logs = relationship("ComplianceLog", back_populates="post_draft")
    performance_reports = relationship("PerformanceReport", back_populates="post_draft")


class PerformanceReport(Base):
    __tablename__ = "performance_reports"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date, nullable=False)
    creator_id = Column(Integer, ForeignKey("creators.id"))
    affiliate_link_id = Column(Integer, ForeignKey("affiliate_links.id"))
    post_draft_id = Column(Integer, ForeignKey("post_drafts.id"))
    clicks = Column(Integer, default=0)
    conversions = Column(Integer, default=0)
    gross_sales = Column(Float, default=0.0)
    commission = Column(Float, default=0.0)
    cvr = Column(Float, default=0.0)
    aov = Column(Float, default=0.0)
    memo = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    creator = relationship("Creator", back_populates="performance_reports")
    affiliate_link = relationship("AffiliateLink", back_populates="performance_reports")
    post_draft = relationship("PostDraft", back_populates="performance_reports")


class ComplianceLog(Base):
    __tablename__ = "compliance_logs"

    id = Column(Integer, primary_key=True, index=True)
    post_draft_id = Column(Integer, ForeignKey("post_drafts.id"), nullable=False)
    check_name = Column(String(200), nullable=False)
    result = Column(String(20), nullable=False)
    message = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    post_draft = relationship("PostDraft", back_populates="compliance_logs")


class AppSettings(Base):
    __tablename__ = "app_settings"

    id = Column(Integer, primary_key=True, index=True)
    x_account_name = Column(String(100), default="")
    external_lp_url = Column(String(500), default="")
    default_post_times = Column(String(200), default="12:00,19:00,21:00,23:00")
    default_pr_text = Column(String(200), default="#PR")
    default_age_warning = Column(String(300), default="※成人向けコンテンツです。18歳未満の方はご覧いただけません。")
    estimated_aov = Column(Float, default=5000.0)
    estimated_cvr = Column(Float, default=1.0)
    target_monthly_commission = Column(Float, default=200000.0)
    default_commission_rate = Column(Float, default=15.0)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
