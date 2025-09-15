from typing import List, Dict

from db import Base, engine, SessionLocal
from models import User, Event, Reward, UserEvent, StampHistory


def create_tables() -> None:
    Base.metadata.create_all(bind=engine)


def migrate_sqlite_schema() -> None:
    """SQLiteの既存テーブルに不足カラムを追加（開発用の簡易マイグレーション）。"""
    with engine.connect() as conn:
        # events テーブルの不足カラムを確認
        try:
            cols = [r[1] for r in conn.exec_driver_sql("PRAGMA table_info('events')").fetchall()]
        except Exception:
            cols = []
        # ない場合は追加
        if cols:
            if "event_type" not in cols:
                conn.exec_driver_sql("ALTER TABLE events ADD COLUMN event_type TEXT NOT NULL DEFAULT 'single'")
            if "parent_event_id" not in cols:
                conn.exec_driver_sql("ALTER TABLE events ADD COLUMN parent_event_id INTEGER NULL")
            if "location" not in cols:
                conn.exec_driver_sql("ALTER TABLE events ADD COLUMN location TEXT NULL")
            if "start_time" not in cols:
                conn.exec_driver_sql("ALTER TABLE events ADD COLUMN start_time TEXT NULL")
            if "end_time" not in cols:
                conn.exec_driver_sql("ALTER TABLE events ADD COLUMN end_time TEXT NULL")
            if "capacity" not in cols:
                conn.exec_driver_sql("ALTER TABLE events ADD COLUMN capacity INTEGER NULL")
            if "contact_name" not in cols:
                conn.exec_driver_sql("ALTER TABLE events ADD COLUMN contact_name TEXT NULL")
            if "points" not in cols:
                conn.exec_driver_sql("ALTER TABLE events ADD COLUMN points INTEGER NOT NULL DEFAULT 1")
            if "notes" not in cols:
                conn.exec_driver_sql("ALTER TABLE events ADD COLUMN notes TEXT NULL")
        # rewards テーブルは create_all で作られるが念のため存在確認のみ
        # user_events: 承認フラグ列
        try:
            ue_cols = [r[1] for r in conn.exec_driver_sql("PRAGMA table_info('user_events')").fetchall()]
        except Exception:
            ue_cols = []
        if ue_cols:
            if "approval_status" not in ue_cols:
                conn.exec_driver_sql("ALTER TABLE user_events ADD COLUMN approval_status TEXT NOT NULL DEFAULT 'pending'")
            if "approved_at" not in ue_cols:
                conn.exec_driver_sql("ALTER TABLE user_events ADD COLUMN approved_at TEXT NULL")


def seed_initial_users() -> None:
    initial_users: List[Dict] = [
        {"id": 999, "employee_code": "999", "password": "99", "role": "admin"},
        {"id": 1, "employee_code": "1", "password": "99", "role": "user"},
        {"id": 2, "employee_code": "2", "password": "99", "role": "user"},
        {"id": 3, "employee_code": "3", "password": "99", "role": "user"},
    ]

    session = SessionLocal()
    try:
        for u in initial_users:
            # 既存チェック（ID優先、なければ社員コード）
            user = session.query(User).filter(User.id == u["id"]).one_or_none()
            if user is None:
                user = session.query(User).filter(User.employee_code == u["employee_code"]).one_or_none()

            if user is None:
                user = User(
                    id=u["id"],
                    employee_code=u["employee_code"],
                    password=u["password"],
                    role=u["role"],
                    stamps=0,
                )
                session.add(user)
            else:
                # 既存の場合は最低限の内容を同期
                user.employee_code = u["employee_code"]
                user.password = u["password"]
                user.role = u["role"]
                if user.stamps is None:
                    user.stamps = 0

        session.commit()
    finally:
        session.close()


def init_db() -> None:
    create_tables()
    migrate_sqlite_schema()
    seed_initial_users()
    # 既存DBにも不足分のみ追加するシード
    session = SessionLocal()
    try:
        def get_or_create(title: str, description: str, date: str, event_type: str, parent_title: str = None):
            ex = session.query(Event).filter(Event.title == title).one_or_none()
            if ex:
                return ex
            parent_id = None
            if parent_title:
                parent = session.query(Event).filter(Event.title == parent_title).one_or_none()
                if parent:
                    parent_id = parent.id
            ev = Event(title=title, description=description, date=date, event_type=event_type, parent_event_id=parent_id)
            session.add(ev)
            session.flush()
            return ev

        # 年間（親）を先に用意
        annual_futsal = get_or_create("フットサルクラブ（年間）", "年間を通して活動", "2025-01-01", "annual")
        annual_marathon = get_or_create("マラソン練習クラブ（年間）", "年間ラン練習", "2025-01-01", "annual")

        # 単発/アンケート（拡張フィールド付きで上書き）
        get_or_create("健康セミナー: 睡眠編", "良質な睡眠とは", "2025-09-25", "single")
        sem = session.query(Event).filter(Event.title == "健康セミナー: 睡眠編").one()
        sem.location = sem.location or "会議室A"
        sem.start_time = sem.start_time or "10:00"
        sem.end_time = sem.end_time or "11:00"
        sem.capacity = sem.capacity or 30
        sem.contact_name = sem.contact_name or "総務 太郎"
        sem.points = sem.points or 1
        sem.notes = sem.notes or "入室は開始10分前から"

        get_or_create("社内ゴルフコンペ", "初心者歓迎", "2025-10-12", "single")
        golf = session.query(Event).filter(Event.title == "社内ゴルフコンペ").one()
        golf.location = golf.location or "〇〇カントリークラブ"
        golf.start_time = golf.start_time or "08:00"
        golf.end_time = golf.end_time or "15:00"
        golf.capacity = golf.capacity or 24
        golf.contact_name = golf.contact_name or "人事 花子"
        golf.points = golf.points or 2
        golf.notes = golf.notes or "レンタルクラブ有"

        get_or_create("市民マラソン大会", "10km/ハーフ", "2025-11-03", "single")
        run = session.query(Event).filter(Event.title == "市民マラソン大会").one()
        run.location = run.location or "市役所前スタート"
        run.start_time = run.start_time or "09:00"
        run.end_time = run.end_time or "13:00"
        run.capacity = run.capacity or 100
        run.contact_name = run.contact_name or "健康推進部"
        run.points = run.points or 2
        run.notes = run.notes or "雨天決行"

        get_or_create("健康経営アンケート(秋)", "所要3分", "2025-10-01", "survey")
        ank = session.query(Event).filter(Event.title == "健康経営アンケート(秋)").one()
        ank.location = ank.location or "オンラインURL"
        ank.start_time = ank.start_time or "00:00"
        ank.end_time = ank.end_time or "23:59"
        ank.capacity = ank.capacity or None
        ank.contact_name = ank.contact_name or "コーポレート部門"
        ank.points = ank.points or 1
        ank.notes = ank.notes or "匿名回答可"

        get_or_create("社内掲示写真 募集(秋)", "テーマ: スポーツの秋", "2025-10-10", "survey")
        pic = session.query(Event).filter(Event.title == "社内掲示写真 募集(秋)").one()
        pic.location = pic.location or "オンライン提出"
        pic.start_time = pic.start_time or "00:00"
        pic.end_time = pic.end_time or "23:59"
        pic.capacity = pic.capacity or None
        pic.contact_name = pic.contact_name or "広報 課"
        pic.points = pic.points or 1
        pic.notes = pic.notes or "JPEG/PNG可"

        # 練習（子）
        get_or_create("フットサル練習 10月第1週", "社内体育館", "2025-10-05", "practice", parent_title="フットサルクラブ（年間）")
        p1 = session.query(Event).filter(Event.title == "フットサル練習 10月第1週").one()
        p1.location = p1.location or "社内体育館"
        p1.start_time = p1.start_time or "19:00"
        p1.end_time = p1.end_time or "21:00"
        p1.capacity = p1.capacity or 20
        p1.contact_name = p1.contact_name or "運営 佐藤"
        p1.points = p1.points or 1

        get_or_create("フットサル練習 10月第3週", "社内体育館", "2025-10-19", "practice", parent_title="フットサルクラブ（年間）")
        p2 = session.query(Event).filter(Event.title == "フットサル練習 10月第3週").one()
        p2.location = p2.location or "社内体育館"
        p2.start_time = p2.start_time or "19:00"
        p2.end_time = p2.end_time or "21:00"
        p2.capacity = p2.capacity or 20
        p2.contact_name = p2.contact_name or "運営 佐藤"
        p2.points = p2.points or 1

        get_or_create("ラン練習 10kmビルドアップ", "土曜朝", "2025-10-12", "practice", parent_title="マラソン練習クラブ（年間）")
        p3 = session.query(Event).filter(Event.title == "ラン練習 10kmビルドアップ").one()
        p3.location = p3.location or "会社前集合"
        p3.start_time = p3.start_time or "07:00"
        p3.end_time = p3.end_time or "08:30"
        p3.capacity = p3.capacity or 30
        p3.contact_name = p3.contact_name or "コーチ 山田"
        p3.points = p3.points or 1

        session.commit()
        # リワードのサンプルを未登録のみ追加
        samples = [
            ("カフェドリンク無料券", 3),
            ("コンビニスイーツ券", 3),
            ("スポーツタオル", 4),
            ("プロテインバー", 4),
            ("ヘルシーランチ割引券", 5),
            ("ボトルウォーターセット", 5),
            ("ワークアウト手袋", 6),
            ("ランニングソックス", 7),
            ("トレーニングチューブ", 8),
            ("スマート体組成計(割引券)", 10),
        ]
        for name, req in samples:
            if session.query(Reward).filter(Reward.name == name).one_or_none() is None:
                session.add(Reward(name=name, required_stamps=req))
        session.commit()
    finally:
        session.close()


if __name__ == "__main__":
    init_db()


