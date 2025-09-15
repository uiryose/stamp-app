from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime
from db import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    employee_code = Column(String, nullable=False, unique=True)
    password = Column(String, nullable=False)
    role = Column(String, nullable=False)  # 'admin' or 'user'
    stamps = Column(Integer, nullable=False, default=0, server_default="0")

    # relationships (optional usage)
    user_events = relationship("UserEvent", back_populates="user", cascade="all, delete-orphan")
    reward_requests = relationship("RewardRequest", back_populates="user", cascade="all, delete-orphan")


class Event(Base):
    __tablename__ = "events"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    description = Column(String, nullable=True)
    date = Column(String, nullable=True)  # simple string date like '2025-09-10'
    is_active = Column(Boolean, nullable=False, default=True, server_default="1")
    # イベント種別: 'single'（単発）, 'annual'（年間イベント）, 'practice'（年間の練習回）, 'survey'（アンケート・応募）
    event_type = Column(String, nullable=False, default="single", server_default="single")
    # 練習回など、親（年間イベント）を指す場合に使用
    parent_event_id = Column(Integer, ForeignKey("events.id"), nullable=True)
    # 拡張フィールド
    location = Column(String, nullable=True)
    start_time = Column(String, nullable=True)  # e.g. '10:00'
    end_time = Column(String, nullable=True)    # e.g. '11:00'
    capacity = Column(Integer, nullable=True)   # 定員
    contact_name = Column(String, nullable=True)
    points = Column(Integer, nullable=False, default=1, server_default="1")
    notes = Column(String, nullable=True)

    participants = relationship("UserEvent", back_populates="event", cascade="all, delete-orphan")
    parent = relationship("Event", remote_side=[id], backref="children")


class UserEvent(Base):
    __tablename__ = "user_events"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    event_id = Column(Integer, ForeignKey("events.id"), nullable=False)
    joined_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    approval_status = Column(String, nullable=False, default="pending", server_default="pending")  # pending/approved/rejected
    approved_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="user_events")
    event = relationship("Event", back_populates="participants")


class StampHistory(Base):
    __tablename__ = "stamp_histories"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    change = Column(Integer, nullable=False)  # +付与 / -消費
    reason = Column(String, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # optional relationships
    user = relationship("User")


class Reward(Base):
    __tablename__ = "rewards"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    required_stamps = Column(Integer, nullable=False)

    requests = relationship("RewardRequest", back_populates="reward", cascade="all, delete-orphan")


class RewardRequest(Base):
    __tablename__ = "reward_requests"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    reward_id = Column(Integer, ForeignKey("rewards.id"), nullable=False)
    status = Column(String, nullable=False, default="pending", server_default="pending")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    user = relationship("User", back_populates="reward_requests")
    reward = relationship("Reward", back_populates="requests")


