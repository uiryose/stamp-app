from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base


DATABASE_URL = "sqlite:///test.db"

# SQLite 用のエンジン作成
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)

# セッションファクトリ
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

# Base クラス
Base = declarative_base()


