from flask import Flask, render_template, request, redirect, url_for, session, flash, g
from db import SessionLocal
from init_db import init_db as ensure_db
from models import User, Event, UserEvent, Reward, RewardRequest, StampHistory
from sqlalchemy import func


def create_app() -> Flask:
    app = Flask(__name__)
    # 開発用の簡易秘密鍵（本番では環境変数などで厳重に管理）
    app.secret_key = "dev-secret-key"

    # 起動時にスキーマと不足テーブル/カラムを確実化（開発用の簡易マイグレーション）
    try:
        ensure_db()
    except Exception:
        # 起動継続。以降のDBアクセス時にエラーが出た場合は手動で init_db.py を実行
        pass

    @app.template_filter('ymd')
    def format_ymd(value):
        if value is None:
            return ""
        try:
            # datetime -> YYYY-MM-DD
            return value.strftime('%Y-%m-%d')
        except Exception:
            s = str(value)
            return s[:10]

    @app.teardown_appcontext
    def shutdown_session(exception=None):
        # アプリコンテキスト終了時にDBセッションをクローズ
        db_session = g.pop("db", None)
        if db_session is not None:
            db_session.close()

    def get_db():
        if "db" not in g:
            g.db = SessionLocal()
        return g.db

    @app.route("/")
    def index():
        if session.get("user_id"):
            return redirect(url_for("mypage"))
        return redirect(url_for("login"))

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            employee_code = request.form.get("employee_code", "").strip()
            password = request.form.get("password", "")

            db = get_db()
            user = (
                db.query(User)
                .filter(User.employee_code == employee_code)
                .one_or_none()
            )

            if user and user.password == password:
                session["user_id"] = user.id
                session["employee_code"] = user.employee_code
                session["role"] = user.role
                flash("ログインしました", "success")
                return redirect(url_for("mypage"))
            else:
                flash("社員コードまたはパスワードが違います", "danger")

        return render_template("login.html")

    @app.route("/logout")
    def logout():
        session.clear()
        flash("ログアウトしました", "info")
        return redirect(url_for("login"))

    @app.route("/mypage")
    def mypage():
        user_id = session.get("user_id")
        if not user_id:
            return redirect(url_for("login"))

        db = get_db()
        user = db.query(User).filter(User.id == user_id).one_or_none()
        if not user:
            session.clear()
            return redirect(url_for("login"))

        # 参加イベント一覧・直近
        user_event_q = (
            db.query(UserEvent)
            .filter(UserEvent.user_id == user.id)
            .order_by(UserEvent.joined_at.desc())
        )
        recent_user_events = user_event_q.limit(5).all()
        recent_events = [ue.event for ue in recent_user_events]

        # 参加済みイベントID
        joined_ids = set(ue.event_id for ue in user_event_q.all())

        # 参加状況別リスト
        all_events = db.query(Event).order_by(Event.date).all()
        joined_active = [e for e in all_events if e.id in joined_ids and e.is_active]
        joined_finished = [e for e in all_events if e.id in joined_ids and not e.is_active]
        finished_not_joined = [e for e in all_events if e.id not in joined_ids and not e.is_active]

        # 参加者数（最近イベント用表示）
        if recent_events:
            ids = [e.id for e in recent_events]
            counts = dict(
                db.query(UserEvent.event_id, func.count(UserEvent.id))
                .filter(UserEvent.event_id.in_(ids))
                .group_by(UserEvent.event_id)
                .all()
            )
        else:
            counts = {}

        # スタンプ履歴（最新20件）
        histories = (
            db.query(StampHistory)
            .filter(StampHistory.user_id == user.id)
            .order_by(StampHistory.created_at.desc())
            .limit(20)
            .all()
        )

        return render_template(
            "mypage.html",
            user=user,
            recent_events=recent_events,
            recent_counts=counts,
            joined_active=joined_active,
            joined_finished=joined_finished,
            finished_not_joined=finished_not_joined,
            histories=histories,
        )

    @app.route("/events")
    def events():
        user_id = session.get("user_id")
        if not user_id:
            return redirect(url_for("login"))

        db = get_db()
        all_events = db.query(Event).order_by(Event.date).all()

        # 参加済みのイベントIDセット
        joined_ids = set(
            e.event_id for e in db.query(UserEvent).filter(UserEvent.user_id == user_id).all()
        )

        return render_template("events.html", events=all_events, joined_ids=joined_ids, role=session.get("role"))

    @app.post("/events/<int:event_id>/join")
    def join_event(event_id: int):
        user_id = session.get("user_id")
        if not user_id:
            return redirect(url_for("login"))

        db = get_db()
        event = db.query(Event).filter(Event.id == event_id).one_or_none()
        if not event:
            flash("イベントが見つかりません", "danger")
            return redirect(url_for("events"))

        if not event.is_active:
            flash("イベントは終了しました", "warning")
            return redirect(url_for("events"))

        exists = (
            db.query(UserEvent)
            .filter(UserEvent.user_id == user_id, UserEvent.event_id == event_id)
            .one_or_none()
        )
        if exists:
            flash("すでに参加済みです", "info")
            return redirect(url_for("events"))

        db.add(UserEvent(user_id=user_id, event_id=event_id, approval_status="pending"))
        db.commit()

        flash("参加申請を受け付けました（承認後にスタンプ付与）", "success")
        return redirect(url_for("events"))

    @app.get("/events/<int:event_id>")
    def event_detail(event_id: int):
        user_id = session.get("user_id")
        if not user_id:
            return redirect(url_for("login"))

        db = get_db()
        event = db.query(Event).filter(Event.id == event_id).one_or_none()
        if not event:
            flash("イベントが見つかりません", "danger")
            return redirect(url_for("events"))

        participants = (
            db.query(User)
            .join(UserEvent, User.id == UserEvent.user_id)
            .filter(UserEvent.event_id == event_id)
            .order_by(User.id)
            .all()
        )
        # 参加者数
        current_count = len(participants)

        return render_template(
            "event_detail.html",
            event=event,
            participants=participants,
            current_count=current_count,
            role=session.get("role"),
        )

    @app.post("/events/<int:event_id>/toggle")
    def toggle_event(event_id: int):
        if session.get("role") != "admin":
            flash("権限がありません", "danger")
            return redirect(url_for("events"))

        db = get_db()
        event = db.query(Event).filter(Event.id == event_id).one_or_none()
        if not event:
            flash("イベントが見つかりません", "danger")
            return redirect(url_for("events"))

        event.is_active = not event.is_active
        db.commit()
        flash("イベント状態を切り替えました", "success")
        return redirect(url_for("event_detail", event_id=event_id))

    # ========== Admin ==========
    def require_admin():
        if session.get("role") != "admin":
            flash("管理者のみアクセス可能です", "danger")
            return False
        return True

    @app.get("/admin")
    def admin():
        if not require_admin():
            return redirect(url_for("mypage"))
        db = get_db()
        events = db.query(Event).order_by(Event.date).all()
        rewards = db.query(Reward).order_by(Reward.required_stamps, Reward.name).all()
        users = db.query(User).order_by(User.id).all()
        pending_requests = db.query(RewardRequest).filter(RewardRequest.status == "pending").order_by(RewardRequest.created_at.desc()).all()
        return render_template("admin.html", events=events, rewards=rewards, users=users, pending_requests=pending_requests)

    @app.get("/admin/events/new")
    def admin_event_new():
        if not require_admin():
            return redirect(url_for("mypage"))
        return render_template("admin_event_new.html")

    @app.post("/admin/events/new")
    def admin_create_event_step1():
        if not require_admin():
            return redirect(url_for("mypage"))
        f = request.form
        title = f.get("title", "").strip()
        if not title:
            flash("イベント名を入力してください", "warning")
            return redirect(url_for("admin_event_new"))
        db = get_db()
        ev = Event(
            title=title,
            date=f.get("date") or None,
            start_time=f.get("start_time") or None,
            end_time=f.get("end_time") or None,
            location=f.get("location") or None,
            contact_name=f.get("contact_name") or None,
            description=f.get("description") or None,
            notes=f.get("notes") or None,
            is_active=True,
            event_type=(f.get("event_type") or "single"),
        )
        try:
            ev.points = int(f.get("points")) if f.get("points") else 1
        except ValueError:
            ev.points = 1
        try:
            ev.capacity = int(f.get("capacity")) if f.get("capacity") else None
        except ValueError:
            ev.capacity = None
        db.add(ev)
        db.commit()
        flash("イベントを登録しました", "success")
        return redirect(url_for("admin"))

    @app.get("/admin/events/<int:event_id>/edit")
    def admin_event_edit(event_id: int):
        if not require_admin():
            return redirect(url_for("mypage"))
        db = get_db()
        event = db.query(Event).filter(Event.id == event_id).one_or_none()
        if not event:
            flash("イベントが見つかりません", "danger")
            return redirect(url_for("admin"))
        return render_template("admin_event_edit.html", event=event)

    @app.post("/admin/events/<int:event_id>/edit")
    def admin_update_event(event_id: int):
        if not require_admin():
            return redirect(url_for("mypage"))
        db = get_db()
        event = db.query(Event).filter(Event.id == event_id).one_or_none()
        if not event:
            flash("イベントが見つかりません", "danger")
            return redirect(url_for("admin"))
        f = request.form
        event.title = f.get("title") or event.title
        event.date = f.get("date") or None
        event.start_time = f.get("start_time") or None
        event.end_time = f.get("end_time") or None
        event.location = f.get("location") or None
        event.contact_name = f.get("contact_name") or None
        event.description = f.get("description") or None
        event.notes = f.get("notes") or None
        event.event_type = f.get("event_type") or event.event_type
        try:
            event.points = int(f.get("points")) if f.get("points") else event.points
        except ValueError:
            pass
        try:
            event.capacity = int(f.get("capacity")) if f.get("capacity") else None
        except ValueError:
            event.capacity = None
        db.commit()
        flash("イベントを更新しました", "success")
        return redirect(url_for("admin_event_edit", event_id=event.id))

    @app.post("/admin/events/create")
    def admin_create_event():
        if not require_admin():
            return redirect(url_for("mypage"))
        form = request.form
        title = form.get("title", "").strip()
        if not title:
            flash("イベント名を入力してください", "warning")
            return redirect(url_for("admin"))
        db = get_db()
        event = Event(
            title=title,
            date=form.get("date") or None,
            start_time=form.get("start_time") or None,
            end_time=form.get("end_time") or None,
            location=form.get("location") or None,
            contact_name=form.get("contact_name") or None,
            description=form.get("description") or None,
            notes=form.get("notes") or None,
            is_active=True,
            event_type=(form.get("event_type") or "single"),
        )
        try:
            points_val = int(form.get("points")) if form.get("points") else 1
        except ValueError:
            points_val = 1
        event.points = points_val
        try:
            capacity_val = int(form.get("capacity")) if form.get("capacity") else None
        except ValueError:
            capacity_val = None
        event.capacity = capacity_val

        db.add(event)
        db.commit()
        flash("イベントを作成しました", "success")
        return redirect(url_for("admin"))

    @app.post("/admin/events/<int:event_id>/delete")
    def admin_delete_event(event_id: int):
        if not require_admin():
            return redirect(url_for("mypage"))
        db = get_db()
        event = db.query(Event).filter(Event.id == event_id).one_or_none()
        if not event:
            flash("イベントが見つかりません", "danger")
            return redirect(url_for("admin"))
        db.delete(event)
        db.commit()
        flash("イベントを削除しました", "success")
        return redirect(url_for("admin"))

    @app.get("/admin/rewards/new")
    def admin_reward_new():
        if not require_admin():
            return redirect(url_for("mypage"))
        return render_template("admin_reward_new.html")

    @app.post("/admin/rewards/new")
    def admin_create_reward():
        if not require_admin():
            return redirect(url_for("mypage"))
        name = request.form.get("name", "").strip()
        try:
            required_stamps = int(request.form.get("required_stamps", "0"))
        except ValueError:
            required_stamps = 0
        if not name or required_stamps <= 0:
            flash("景品名と必要スタンプを正しく入力してください", "warning")
            return redirect(url_for("admin_reward_new"))
        db = get_db()
        db.add(Reward(name=name, required_stamps=required_stamps))
        db.commit()
        flash("景品を作成しました", "success")
        return redirect(url_for("admin"))

    @app.post("/admin/rewards/<int:reward_id>/delete")
    def admin_delete_reward(reward_id: int):
        if not require_admin():
            return redirect(url_for("mypage"))
        db = get_db()
        reward = db.query(Reward).filter(Reward.id == reward_id).one_or_none()
        if not reward:
            flash("景品が見つかりません", "danger")
            return redirect(url_for("admin"))
        db.delete(reward)
        db.commit()
        flash("景品を削除しました", "success")
        return redirect(url_for("admin"))

    @app.post("/admin/requests/<int:request_id>/approve")
    def admin_approve_request(request_id: int):
        if not require_admin():
            return redirect(url_for("mypage"))
        db = get_db()
        req = db.query(RewardRequest).filter(RewardRequest.id == request_id).one_or_none()
        if not req:
            flash("申請が見つかりません", "danger")
            return redirect(url_for("admin"))
        req.status = "approved"
        db.commit()
        flash("申請を承認しました", "success")
        return redirect(url_for("admin"))

    @app.post("/admin/requests/<int:request_id>/reject")
    def admin_reject_request(request_id: int):
        if not require_admin():
            return redirect(url_for("mypage"))
        db = get_db()
        req = db.query(RewardRequest).filter(RewardRequest.id == request_id).one_or_none()
        if not req:
            flash("申請が見つかりません", "danger")
            return redirect(url_for("admin"))
        req.status = "rejected"
        db.commit()
        flash("申請を却下しました", "success")
        return redirect(url_for("admin"))

    # ========== Stamp Approval (Admin) ==========
    @app.get("/admin/stamps")
    def admin_stamps():
        if not require_admin():
            return redirect(url_for("mypage"))
        db = get_db()
        user_id = request.args.get("user_id")
        event_id = request.args.get("event_id")
        q = db.query(UserEvent).filter(UserEvent.approval_status == "pending")
        if user_id:
            try:
                q = q.filter(UserEvent.user_id == int(user_id))
            except ValueError:
                pass
        if event_id:
            try:
                q = q.filter(UserEvent.event_id == int(event_id))
            except ValueError:
                pass
        pendings = q.order_by(UserEvent.joined_at.desc()).all()
        users = db.query(User).order_by(User.id).all()
        events = db.query(Event).order_by(Event.date).all()
        return render_template("admin_stamps.html", pendings=pendings, users=users, events=events)

    @app.post("/admin/stamps/approve")
    def admin_stamps_approve():
        if not require_admin():
            return redirect(url_for("mypage"))
        db = get_db()
        ids = request.form.getlist("ue_ids")
        count = 0
        for sid in ids:
            try:
                ue = db.query(UserEvent).filter(UserEvent.id == int(sid), UserEvent.approval_status == "pending").one_or_none()
            except ValueError:
                ue = None
            if not ue:
                continue
            ue.approval_status = "approved"
            ue.approved_at = func.now()
            user = db.query(User).filter(User.id == ue.user_id).one()
            event = db.query(Event).filter(Event.id == ue.event_id).one()
            # 付与ポイント
            add = 0
            if event.event_type in ("single", "survey"):
                add = event.points or 1
            elif event.event_type == "practice":
                if event.parent_event_id:
                    has_parent = db.query(UserEvent).filter(
                        UserEvent.user_id == ue.user_id,
                        UserEvent.event_id == event.parent_event_id,
                    ).one_or_none()
                    if has_parent:
                        add = event.points or 1
            if add:
                user.stamps = (user.stamps or 0) + add
                db.add(StampHistory(user_id=user.id, change=add, reason=f"{event.title} 参加承認"))
            else:
                db.add(StampHistory(user_id=user.id, change=0, reason=f"{event.title} は対象外のためスタンプ無し"))
            count += 1
        db.commit()
        flash(f"{count}件を承認しました", "success")
        return redirect(url_for("admin_stamps"))

    @app.post("/admin/stamps/reject")
    def admin_stamps_reject():
        if not require_admin():
            return redirect(url_for("mypage"))
        db = get_db()
        ids = request.form.getlist("ue_ids")
        count = 0
        for sid in ids:
            try:
                ue = db.query(UserEvent).filter(UserEvent.id == int(sid), UserEvent.approval_status == "pending").one_or_none()
            except ValueError:
                ue = None
            if not ue:
                continue
            ue.approval_status = "rejected"
            user = db.query(User).filter(User.id == ue.user_id).one()
            event = db.query(Event).filter(Event.id == ue.event_id).one()
            db.add(StampHistory(user_id=user.id, change=0, reason=f"{event.title} 不承認のためスタンプ無し"))
            count += 1
        db.commit()
        flash(f"{count}件を却下しました", "success")
        return redirect(url_for("admin_stamps"))

    @app.post("/admin/stamps/grant")
    def admin_stamps_grant():
        if not require_admin():
            return redirect(url_for("mypage"))
        db = get_db()
        try:
            user_id = int(request.form.get("user_id"))
            amount = int(request.form.get("amount"))
        except (TypeError, ValueError):
            flash("入力値が不正です", "danger")
            return redirect(url_for("admin_stamps"))
        reason = (request.form.get("reason") or "特別付与")
        user = db.query(User).filter(User.id == user_id).one_or_none()
        if not user:
            flash("ユーザーが見つかりません", "danger")
            return redirect(url_for("admin_stamps"))
        user.stamps = (user.stamps or 0) + amount
        db.add(StampHistory(user_id=user.id, change=amount, reason=reason))
        db.commit()
        flash("特別付与を反映しました", "success")
        return redirect(url_for("admin_stamps"))

    @app.get("/rewards")
    def rewards():
        user_id = session.get("user_id")
        if not user_id:
            return redirect(url_for("login"))

        db = get_db()
        rewards = db.query(Reward).order_by(Reward.required_stamps, Reward.name).all()
        user = db.query(User).filter(User.id == user_id).one()

        # 自分の最新申請状況（直近10件）
        recent_requests = (
            db.query(RewardRequest)
            .filter(RewardRequest.user_id == user_id)
            .order_by(RewardRequest.created_at.desc())
            .limit(10)
            .all()
        )
        return render_template("rewards.html", rewards=rewards, user=user, recent_requests=recent_requests)

    @app.post("/rewards/<int:reward_id>/request")
    def request_reward(reward_id: int):
        user_id = session.get("user_id")
        if not user_id:
            return redirect(url_for("login"))

        db = get_db()
        user = db.query(User).filter(User.id == user_id).one()
        reward = db.query(Reward).filter(Reward.id == reward_id).one_or_none()
        if not reward:
            flash("景品が見つかりません", "danger")
            return redirect(url_for("rewards"))

        if (user.stamps or 0) < reward.required_stamps:
            flash("スタンプが不足しています", "warning")
            return redirect(url_for("rewards"))

        # 重複申請を許可するかは運用次第。ここでは常に新規申請を作成。
        req = RewardRequest(user_id=user_id, reward_id=reward_id, status="pending")
        db.add(req)
        # スタンプ減算 + 履歴
        user.stamps = (user.stamps or 0) - reward.required_stamps
        db.add(StampHistory(user_id=user.id, change=-reward.required_stamps, reason=f"景品交換申請: {reward.name}"))
        db.commit()
        flash("交換申請を受け付けました", "success")
        return redirect(url_for("rewards"))

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True)


