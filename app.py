"""
JimnyCamp — Flask application factory
"""
import hmac
import os
import random
import string
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import date as _Date
from functools import wraps
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

from flask import (
    Flask, render_template, request, redirect,
    url_for, session, jsonify, abort, flash,
)

from models import (
    db, COLORS,
    Trip, TripMember, TodoItem, EquipmentItem, FoodItem,
    PersonalItem, Idea, Poll, PollOption, PollVote, RouteStop,
    TripDateProposal, ProposalVote, IdeaVote, TodoVote,
)


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def _gen_code(length: int = 8) -> str:
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=length))


def _member(code: str) -> TripMember | None:
    name = session.get("user")
    if not name:
        return None
    trip = Trip.query.filter_by(join_code=code).first()
    if not trip:
        return None
    return TripMember.query.filter_by(trip_id=trip.id, name=name).first()


def _require_member(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        code = kwargs.get("code", "")
        if not _member(code):
            return redirect(url_for("index"))
        return f(*args, **kwargs)
    return decorated


def _admin_auth_key(code: str) -> str:
    return f"admin_auth_{code}"


def _check_admin_password(candidate: str) -> bool:
    """Timing-safe comparison against ADMIN_PASSWORD from .env."""
    stored = os.environ.get("ADMIN_PASSWORD", "")
    if not stored:
        return False
    return hmac.compare_digest(stored.encode(), candidate.encode())


_GLOBAL_ADMIN_KEY = "global_admin"


def _compute_best_windows(date_map: dict) -> list:
    """Group consecutive dates into overlap windows sorted by attendee count desc."""
    if not date_map:
        return []
    sorted_dates = sorted(date_map.keys())
    windows = []
    i = 0
    while i < len(sorted_dates):
        d = sorted_dates[i]
        members_today = frozenset(p["name"] for p in date_map[d])
        if len(members_today) < 2:
            i += 1
            continue
        window_start = d
        window_end = d
        window_members = members_today
        j = i + 1
        while j < len(sorted_dates):
            prev = _Date.fromisoformat(sorted_dates[j - 1])
            curr = _Date.fromisoformat(sorted_dates[j])
            if (curr - prev).days != 1:
                break
            overlap = window_members & frozenset(p["name"] for p in date_map[sorted_dates[j]])
            if len(overlap) < 2:
                break
            window_members = overlap
            window_end = sorted_dates[j]
            j += 1
        if len(window_members) >= 2:
            days = (_Date.fromisoformat(window_end) - _Date.fromisoformat(window_start)).days + 1
            # Build member details preserving color
            member_details = [
                {"name": n, "color": next((p["color"] for p in date_map[window_start] if p["name"] == n), "#9CA3AF")}
                for n in sorted(window_members)
            ]
            windows.append({
                "start": window_start,
                "end": window_end,
                "days": days,
                "count": len(window_members),
                "members": member_details,
            })
        i = j if j > i else i + 1
    windows.sort(key=lambda w: (-w["count"], -w["days"]))
    return windows[:6]


def _member_ranges(members) -> list:
    """Return a list of {name, color, ranges} where ranges are {start, end, days}."""
    result = []
    for m in members:
        sorted_dates = sorted(m.available_dates_list)
        ranges = []
        if sorted_dates:
            s = sorted_dates[0]
            e = sorted_dates[0]
            for i in range(1, len(sorted_dates)):
                prev = _Date.fromisoformat(sorted_dates[i - 1])
                curr = _Date.fromisoformat(sorted_dates[i])
                if (curr - prev).days == 1:
                    e = sorted_dates[i]
                else:
                    days = (_Date.fromisoformat(e) - _Date.fromisoformat(s)).days + 1
                    ranges.append({"start": s, "end": e, "days": days})
                    s = sorted_dates[i]
                    e = sorted_dates[i]
            days = (_Date.fromisoformat(e) - _Date.fromisoformat(s)).days + 1
            ranges.append({"start": s, "end": e, "days": days})
        result.append({"id": m.id, "name": m.name, "color": m.color, "ranges": ranges})
    return result


def _overlap_stats(member_ranges_data: list, total_members: int) -> list:
    """Show windows where 2+ members have the exact same from-to pair.

    Groups members by their (start, end) range key.  Only ranges where at least
    two members share the identical from and to dates are returned.
    """
    # Build a map: (start, end) -> list of members who have that exact range
    window_map: dict = {}
    for mr in member_ranges_data:
        for r in mr["ranges"]:
            key = (r["start"], r["end"])
            window_map.setdefault(key, []).append(
                {"name": mr["name"], "color": mr["color"]}
            )

    rows = []
    for (start, end), members in window_map.items():
        if len(members) < 2:
            continue
        days = (_Date.fromisoformat(end) - _Date.fromisoformat(start)).days + 1
        pct  = round(len(members) / total_members * 100) if total_members else 0
        rows.append({
            "start":   start,
            "end":     end,
            "days":    days,
            "count":   len(members),
            "pct":     pct,
            "members": sorted(members, key=lambda p: p["name"]),
        })

    rows.sort(key=lambda r: (-r["count"], -r["days"], r["start"]))
    return rows


def _is_global_admin() -> bool:
    return bool(session.get(_GLOBAL_ADMIN_KEY))


def _require_admin(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        code = kwargs.get("code", "")
        # Global admin (password-verified via /admin dashboard) bypasses membership check
        if _is_global_admin():
            return f(*args, **kwargs)
        m = _member(code)
        if not m or not m.is_admin:
            abort(403)
        if not session.get(_admin_auth_key(code)):
            return redirect(url_for("admin_login", code=code))
        return f(*args, **kwargs)
    return decorated


def _json_require_member(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        code = kwargs.get("code", "")
        if not _member(code):
            abort(401)
        return f(*args, **kwargs)
    return decorated


def _json_require_admin(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        code = kwargs.get("code", "")
        if _is_global_admin():
            return f(*args, **kwargs)
        m = _member(code)
        if not m or not m.is_admin:
            abort(403)
        if not session.get(_admin_auth_key(code)):
            abort(401)
        return f(*args, **kwargs)
    return decorated


def _color_for_trip(trip: Trip) -> str:
    return COLORS[len(trip.members) % len(COLORS)]


# ──────────────────────────────────────────────
# App factory
# ──────────────────────────────────────────────

def create_app() -> Flask:
    app = Flask(__name__)
    app.secret_key = os.environ.get("SECRET_KEY", "jimnycamp-dev-secret-change-in-prod")

    db_path = Path(os.environ.get("DB_PATH", str(Path(__file__).parent / "jimnycamp.db")))
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{db_path}"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    db.init_app(app)
    with app.app_context():
        db.create_all()

    @app.template_filter("dmy")
    def dmy_filter(value):
        """Convert YYYY-MM-DD string or datetime/date to DD/MM/YYYY."""
        if not value:
            return value
        s = str(value)[:10]  # handles datetime objects too
        try:
            y, m, d = s.split("-")
            return f"{d}/{m}/{y}"
        except Exception:
            return s

    # ──────────────────────────────────────────
    # Page routes
    # ──────────────────────────────────────────

    @app.route("/")
    def index():
        name = session.get("user")
        my_trips = []
        if name:
            memberships = TripMember.query.filter_by(name=name).all()
            for m in memberships:
                my_trips.append({"trip": m.trip, "is_admin": m.is_admin})
        all_trips = Trip.query.order_by(Trip.created_at.desc()).all()
        return render_template("index.html", trips=my_trips, all_trips=all_trips, current_user=name)

    @app.route("/admin", methods=["GET", "POST"])
    def admin_dashboard():
        if request.method == "POST":
            password = request.form.get("password", "")
            if _check_admin_password(password):
                session[_GLOBAL_ADMIN_KEY] = True
                # Grant per-trip admin keys for every trip
                for t in Trip.query.all():
                    session[_admin_auth_key(t.join_code)] = True
                return redirect(url_for("admin_dashboard"))
            flash("Incorrect admin password.", "error")
        if not _is_global_admin():
            return render_template("admin_dashboard.html", locked=True, trips=None)
        trips = Trip.query.order_by(Trip.created_at.desc()).all()
        return render_template("admin_dashboard.html", locked=False, trips=trips)

    @app.route("/admin/logout", methods=["POST"])
    def admin_global_logout():
        session.pop(_GLOBAL_ADMIN_KEY, None)
        return redirect(url_for("index"))

    @app.route("/admin/create-trip", methods=["GET", "POST"])
    def admin_create_trip():
        if request.method == "POST":
            password = request.form.get("password", "")
            name = request.form.get("user_name", "").strip()[:60]
            trip_name = request.form.get("trip_name", "").strip()[:120]
            trip_desc = request.form.get("trip_desc", "").strip()[:500]

            if not _check_admin_password(password):
                flash("Incorrect admin password.", "error")
                return render_template("admin_create.html", current_user=session.get("user"))

            if not name or not trip_name:
                flash("Please fill in your name and a trip name.", "error")
                return render_template("admin_create.html", current_user=session.get("user"))

            session["user"] = name

            code = _gen_code()
            while Trip.query.filter_by(join_code=code).first():
                code = _gen_code()

            trip = Trip(name=trip_name, description=trip_desc, join_code=code)
            db.session.add(trip)
            db.session.flush()

            member = TripMember(trip_id=trip.id, name=name, color=COLORS[0], is_admin=True)
            db.session.add(member)
            db.session.commit()

            # Grant admin panel access for this trip automatically
            session[_admin_auth_key(code)] = True
            session[_GLOBAL_ADMIN_KEY] = True
            return redirect(url_for("admin_dashboard"))

        return render_template("admin_create.html", current_user=session.get("user"))

    @app.route("/join", methods=["POST"])
    def join_trip():
        name = request.form.get("user_name", "").strip()[:60]
        # Form may contain two join_code fields (hidden dropdown + visible text);
        # pick the first non-empty value.
        codes = [c.strip().upper()[:12] for c in request.form.getlist("join_code") if c.strip()]
        code = codes[0] if codes else ""
        password = request.form.get("password", "")

        if not name or not code:
            flash("Please enter your name and a trip code.", "error")
            return redirect(url_for("index"))

        if not password:
            flash("Please enter a password.", "error")
            return redirect(url_for("index"))

        trip = Trip.query.filter_by(join_code=code).first()
        if not trip:
            flash("Trip code not found. Check it and try again.", "error")
            return redirect(url_for("index"))

        existing = TripMember.query.filter_by(trip_id=trip.id, name=name).first()
        if existing:
            # Returning member — verify password
            if not existing.password_hash:
                # Legacy member with no password yet — accept any password and set it
                existing.password_hash = generate_password_hash(password)
                db.session.commit()
            elif not check_password_hash(existing.password_hash, password):
                flash("Incorrect password for that name. Try a different name or check your password.", "error")
                return redirect(url_for("index"))
        else:
            # New member — create with hashed password
            member = TripMember(
                trip_id=trip.id,
                name=name,
                color=_color_for_trip(trip),
                password_hash=generate_password_hash(password),
            )
            db.session.add(member)
            db.session.commit()

        session["user"] = name
        return redirect(url_for("trip_dashboard", code=code))

    @app.route("/trip/<code>")
    @_require_member
    def trip_dashboard(code):
        trip = Trip.query.filter_by(join_code=code).first_or_404()
        me = _member(code)

        date_map: dict[str, list] = {}
        for m in trip.members:
            for d in m.available_dates_list:
                date_map.setdefault(d, []).append({"name": m.name, "color": m.color})

        voted_options: dict[int, int] = {}
        for poll in trip.polls:
            v = PollVote.query.join(PollOption).filter(
                PollOption.poll_id == poll.id,
                PollVote.voter == me.name,
            ).first()
            if v:
                voted_options[poll.id] = v.option_id

        best_windows = _compute_best_windows(date_map)
        member_ranges = _member_ranges(trip.members)
        overlap_stats = _overlap_stats(member_ranges, len(trip.members))
        proposals = trip.proposals
        my_vote_ids = {v.proposal_id for v in ProposalVote.query.filter(
            ProposalVote.member_id == me.id,
            ProposalVote.proposal_id.in_([p.id for p in proposals]),
        ).all()} if proposals else set()

        # Build per-member proposal votes for Crew Calendar
        proposal_map = {p.id: p for p in proposals}
        all_pvotes = ProposalVote.query.filter(
            ProposalVote.proposal_id.in_([p.id for p in proposals])
        ).all() if proposals else []
        member_proposal_votes: dict = {}
        for pv in all_pvotes:
            member_proposal_votes.setdefault(pv.member_id, []).append(proposal_map[pv.proposal_id])

        idea_ids = [i.id for i in trip.ideas]
        my_idea_vote_ids = {v.idea_id for v in IdeaVote.query.filter(
            IdeaVote.member_id == me.id,
            IdeaVote.idea_id.in_(idea_ids),
        ).all()} if idea_ids else set()
        todo_ids = [t.id for t in trip.todos]
        my_todo_vote_ids = {v.todo_id for v in TodoVote.query.filter(
            TodoVote.member_id == me.id,
            TodoVote.todo_id.in_(todo_ids),
        ).all()} if todo_ids else set()

        return render_template(
            "trip.html",
            trip=trip,
            me=me,
            date_map=date_map,
            best_windows=best_windows,
            member_ranges=member_ranges,
            overlap_stats=overlap_stats,
            proposals=proposals,
            my_vote_ids=my_vote_ids,
            member_proposal_votes=member_proposal_votes,
            my_idea_vote_ids=my_idea_vote_ids,
            my_todo_vote_ids=my_todo_vote_ids,
            voted_options=voted_options,
        )

    @app.route("/trip/<code>/my-plan")
    @_require_member
    def my_plan(code):
        trip = Trip.query.filter_by(join_code=code).first_or_404()
        me = _member(code)
        personal_food = PersonalItem.query.filter_by(member_id=me.id, kind="food").all()
        personal_gear = PersonalItem.query.filter_by(member_id=me.id, kind="gear").all()
        date_map: dict[str, list] = {}
        for m in trip.members:
            for d in m.available_dates_list:
                date_map.setdefault(d, []).append({"name": m.name, "color": m.color})
        best_windows = _compute_best_windows(date_map)
        member_ranges = _member_ranges(trip.members)
        overlap_stats = _overlap_stats(member_ranges, len(trip.members))
        proposals = trip.proposals
        my_vote_ids = {v.proposal_id for v in ProposalVote.query.filter(
            ProposalVote.member_id == me.id,
            ProposalVote.proposal_id.in_([p.id for p in proposals]),
        ).all()} if proposals else set()
        return render_template(
            "my_plan.html",
            trip=trip,
            me=me,
            personal_food=personal_food,
            personal_gear=personal_gear,
            date_map=date_map,
            best_windows=best_windows,
            member_ranges=member_ranges,
            overlap_stats=overlap_stats,
            proposals=proposals,
            my_vote_ids=my_vote_ids,
        )

    @app.route("/admin/<code>/login", methods=["GET", "POST"])
    def admin_login(code):
        trip = Trip.query.filter_by(join_code=code).first_or_404()
        m = _member(code)
        if not m or not m.is_admin:
            abort(403)
        if request.method == "POST":
            password = request.form.get("password", "")
            if _check_admin_password(password):
                session[_admin_auth_key(code)] = True
                return redirect(url_for("admin_panel", code=code))
            flash("Incorrect admin password.", "error")
        return render_template("admin_login.html", trip=trip, me=m)

    @app.route("/admin/<code>/auth-logout", methods=["POST"])
    def admin_auth_logout(code):
        session.pop(_admin_auth_key(code), None)
        return redirect(url_for("trip_dashboard", code=code))

    @app.route("/admin/<code>")
    @_require_admin
    def admin_panel(code):
        trip = Trip.query.filter_by(join_code=code).first_or_404()
        me = _member(code)
        # Global admin may not be a trip member — create a lightweight stand-in
        if me is None:
            class _AdminProxy:
                name = "Admin"
                color = "#D97706"
                is_admin = True
                available_dates_list = []
                joined_at = trip.created_at
            me = _AdminProxy()
        return render_template("admin.html", trip=trip, me=me)

    @app.route("/admin/<code>/settings", methods=["POST"])
    @_require_admin
    def admin_settings(code):
        trip = Trip.query.filter_by(join_code=code).first_or_404()
        trip.name = request.form.get("trip_name", trip.name).strip()[:120]
        trip.description = request.form.get("trip_desc", trip.description).strip()[:500]
        db.session.commit()
        flash("Trip settings updated.", "success")
        return redirect(url_for("admin_panel", code=code))

    @app.route("/admin/<code>/kick/<int:member_id>", methods=["POST"])
    @_require_admin
    def admin_kick(code, member_id):
        me = _member(code)
        target = TripMember.query.filter_by(id=member_id).first_or_404()
        if target.id == me.id:
            abort(400)
        db.session.delete(target)
        db.session.commit()
        flash(f"{target.name} removed from the trip.", "success")
        return redirect(url_for("admin_panel", code=code))

    @app.route("/admin/<code>/delete", methods=["POST"])
    @_require_admin
    def admin_delete_trip(code):
        trip = Trip.query.filter_by(join_code=code).first_or_404()
        db.session.delete(trip)
        db.session.commit()
        flash(f"Trip \u2018{trip.name}\u2019 has been deleted.", "success")
        return redirect(url_for("admin_dashboard"))

    # ──────────────────────────────────────────
    # Admin API — Date proposals
    # ──────────────────────────────────────────

    @app.route("/admin/<code>/proposals", methods=["POST"])
    @_json_require_admin
    def admin_add_proposal(code):
        trip = Trip.query.filter_by(join_code=code).first_or_404()
        data = request.get_json(silent=True) or {}
        start = str(data.get("start", ""))[:10]
        end   = str(data.get("end",   ""))[:10]
        label = str(data.get("label", ""))[:100].strip()
        if not start or not end or end < start:
            return jsonify({"ok": False, "error": "Invalid dates"}), 400
        max_pos = db.session.query(db.func.max(TripDateProposal.position)).filter_by(trip_id=trip.id).scalar() or 0
        p = TripDateProposal(trip_id=trip.id, start=start, end=end, label=label, position=max_pos + 1)
        db.session.add(p)
        db.session.commit()
        return jsonify({"ok": True, "proposal": p.to_dict()})

    @app.route("/admin/<code>/proposals/<int:pid>", methods=["DELETE"])
    @_json_require_admin
    def admin_delete_proposal(code, pid):
        trip = Trip.query.filter_by(join_code=code).first_or_404()
        p = TripDateProposal.query.filter_by(id=pid, trip_id=trip.id).first_or_404()
        db.session.delete(p)
        db.session.commit()
        return jsonify({"ok": True})

    @app.route("/logout")
    def logout():
        session.clear()
        return redirect(url_for("index"))

    # ──────────────────────────────────────────
    # API — Todos
    # ──────────────────────────────────────────

    @app.route("/api/<code>/todos", methods=["POST"])
    @_json_require_member
    def api_todo_add(code):
        trip = Trip.query.filter_by(join_code=code).first_or_404()
        data = request.get_json(silent=True) or {}
        text = str(data.get("text", "")).strip()[:300]
        if not text:
            abort(400)
        item = TodoItem(trip_id=trip.id, text=text,
                        assignee=str(data.get("assignee", "")).strip()[:60],
                        added_by=session.get("user", ""))
        db.session.add(item)
        db.session.commit()
        return jsonify(item.to_dict()), 201

    @app.route("/api/<code>/todos/<int:item_id>/toggle", methods=["POST"])
    @_json_require_member
    def api_todo_toggle(code, item_id):
        item = TodoItem.query.filter_by(id=item_id).first_or_404()
        item.done = not item.done
        db.session.commit()
        return jsonify(item.to_dict())

    @app.route("/api/<code>/todos/<int:item_id>", methods=["DELETE"])
    @_json_require_member
    def api_todo_delete(code, item_id):
        item = TodoItem.query.filter_by(id=item_id).first_or_404()
        db.session.delete(item)
        db.session.commit()
        return jsonify({"ok": True})

    # ──────────────────────────────────────────
    # API — Equipment
    # ──────────────────────────────────────────

    @app.route("/api/<code>/equipment", methods=["POST"])
    @_json_require_member
    def api_equip_add(code):
        trip = Trip.query.filter_by(join_code=code).first_or_404()
        data = request.get_json(silent=True) or {}
        text = str(data.get("text", "")).strip()[:300]
        if not text:
            abort(400)
        assignee = str(data.get("assignee", "")).strip()[:60]
        item = EquipmentItem(trip_id=trip.id, text=text, assignee=assignee, added_by=session.get("user", ""))
        db.session.add(item)
        db.session.commit()
        return jsonify(item.to_dict()), 201

    @app.route("/api/<code>/equipment/<int:item_id>/toggle", methods=["POST"])
    @_json_require_member
    def api_equip_toggle(code, item_id):
        item = EquipmentItem.query.filter_by(id=item_id).first_or_404()
        item.done = not item.done
        db.session.commit()
        return jsonify(item.to_dict())

    @app.route("/api/<code>/equipment/<int:item_id>", methods=["DELETE"])
    @_json_require_member
    def api_equip_delete(code, item_id):
        item = EquipmentItem.query.filter_by(id=item_id).first_or_404()
        db.session.delete(item)
        db.session.commit()
        return jsonify({"ok": True})

    @app.route("/api/<code>/equipment/<int:item_id>/assign", methods=["PATCH"])
    @_json_require_member
    def api_equip_assign(code, item_id):
        item = EquipmentItem.query.filter_by(id=item_id).first_or_404()
        data = request.get_json(silent=True) or {}
        item.assignee = str(data.get("assignee", "")).strip()[:60]
        db.session.commit()
        return jsonify(item.to_dict())

    # ──────────────────────────────────────────
    # API — Food
    # ──────────────────────────────────────────

    @app.route("/api/<code>/food", methods=["POST"])
    @_json_require_member
    def api_food_add(code):
        trip = Trip.query.filter_by(join_code=code).first_or_404()
        data = request.get_json(silent=True) or {}
        text = str(data.get("text", "")).strip()[:300]
        if not text:
            abort(400)
        assignee = str(data.get("assignee", "")).strip()[:60]
        item = FoodItem(trip_id=trip.id, text=text, assignee=assignee, added_by=session.get("user", ""))
        db.session.add(item)
        db.session.commit()
        return jsonify(item.to_dict()), 201

    @app.route("/api/<code>/food/<int:item_id>/toggle", methods=["POST"])
    @_json_require_member
    def api_food_toggle(code, item_id):
        item = FoodItem.query.filter_by(id=item_id).first_or_404()
        item.done = not item.done
        db.session.commit()
        return jsonify(item.to_dict())

    @app.route("/api/<code>/food/<int:item_id>", methods=["DELETE"])
    @_json_require_member
    def api_food_delete(code, item_id):
        item = FoodItem.query.filter_by(id=item_id).first_or_404()
        db.session.delete(item)
        db.session.commit()
        return jsonify({"ok": True})

    @app.route("/api/<code>/food/<int:item_id>/assign", methods=["PATCH"])
    @_json_require_member
    def api_food_assign(code, item_id):
        item = FoodItem.query.filter_by(id=item_id).first_or_404()
        data = request.get_json(silent=True) or {}
        item.assignee = str(data.get("assignee", "")).strip()[:60]
        db.session.commit()
        return jsonify(item.to_dict())

    # ──────────────────────────────────────────
    # API — Ideas
    # ──────────────────────────────────────────

    @app.route("/api/<code>/ideas", methods=["POST"])
    @_json_require_member
    def api_idea_add(code):
        trip = Trip.query.filter_by(join_code=code).first_or_404()
        data = request.get_json(silent=True) or {}
        text = str(data.get("text", "")).strip()[:600]
        if not text:
            abort(400)
        idea = Idea(trip_id=trip.id, text=text, added_by=session.get("user", ""))
        db.session.add(idea)
        db.session.commit()
        return jsonify(idea.to_dict()), 201

    @app.route("/api/<code>/ideas/<int:idea_id>/upvote", methods=["POST"])
    @_json_require_member
    def api_idea_upvote(code, idea_id):
        me = _member(code)
        idea = Idea.query.filter_by(id=idea_id).first_or_404()
        existing = IdeaVote.query.filter_by(idea_id=idea_id, member_id=me.id).first()
        if existing:
            db.session.delete(existing)
        else:
            db.session.add(IdeaVote(idea_id=idea_id, member_id=me.id))
        db.session.commit()
        return jsonify(idea.to_dict())

    @app.route("/api/<code>/ideas/<int:idea_id>", methods=["DELETE"])
    @_json_require_member
    def api_idea_delete(code, idea_id):
        me = _member(code)
        idea = Idea.query.filter_by(id=idea_id).first_or_404()
        if not me.is_admin and idea.added_by != me.name:
            abort(403)
        db.session.delete(idea)
        db.session.commit()
        return jsonify({"ok": True})

    @app.route("/api/<code>/todos/<int:todo_id>/vote", methods=["POST"])
    @_json_require_member
    def api_todo_vote(code, todo_id):
        me = _member(code)
        todo = TodoItem.query.filter_by(id=todo_id).first_or_404()
        existing = TodoVote.query.filter_by(todo_id=todo_id, member_id=me.id).first()
        if existing:
            db.session.delete(existing)
        else:
            db.session.add(TodoVote(todo_id=todo_id, member_id=me.id))
        db.session.commit()
        return jsonify(todo.to_dict())

    @app.route("/api/<code>/suggest-period", methods=["POST"])
    @_json_require_member
    def api_suggest_period(code):
        trip = Trip.query.filter_by(join_code=code).first_or_404()
        me = _member(code)
        data = request.get_json(silent=True) or {}
        start = str(data.get("start", ""))[:10]
        end   = str(data.get("end",   ""))[:10]
        label = str(data.get("label", "")).strip()[:100]
        if not start or not end or end < start:
            return jsonify({"ok": False, "error": "Invalid dates"}), 400
        pos = db.session.query(db.func.count(TripDateProposal.id)).filter_by(trip_id=trip.id).scalar()
        p = TripDateProposal(trip_id=trip.id, start=start, end=end,
                             label=label, position=pos, suggested_by=me.name)
        db.session.add(p)
        db.session.commit()
        return jsonify({"ok": True, "proposal": p.to_dict()}), 201

    # ──────────────────────────────────────────
    # API — Polls
    # ──────────────────────────────────────────

    @app.route("/api/<code>/polls", methods=["POST"])
    @_json_require_admin
    def api_poll_create(code):
        trip = Trip.query.filter_by(join_code=code).first_or_404()
        data = request.get_json(silent=True) or {}
        question = str(data.get("question", "")).strip()[:300]
        kind = str(data.get("kind", "general")).strip()
        if kind not in ("date", "location", "general"):
            kind = "general"
        options_raw = data.get("options", [])
        if not question or len(options_raw) < 2:
            abort(400)
        poll = Poll(trip_id=trip.id, question=question, kind=kind,
                    created_by=session.get("user", ""))
        db.session.add(poll)
        db.session.flush()
        for opt_text in options_raw[:10]:
            db.session.add(PollOption(poll_id=poll.id, text=str(opt_text).strip()[:200]))
        db.session.commit()
        return jsonify(poll.to_dict()), 201

    @app.route("/api/<code>/polls/<int:poll_id>/vote", methods=["POST"])
    @_json_require_member
    def api_poll_vote(code, poll_id):
        poll = Poll.query.filter_by(id=poll_id).first_or_404()
        if poll.closed:
            abort(400)
        data = request.get_json(silent=True) or {}
        option_id = int(data.get("option_id", 0))
        voter = session.get("user", "")
        existing = PollVote.query.join(PollOption).filter(
            PollOption.poll_id == poll_id, PollVote.voter == voter).first()
        if existing:
            db.session.delete(existing)
        option = PollOption.query.filter_by(id=option_id, poll_id=poll_id).first_or_404()
        db.session.add(PollVote(option_id=option.id, voter=voter))
        db.session.commit()
        return jsonify(poll.to_dict())

    @app.route("/api/<code>/polls/<int:poll_id>/close", methods=["POST"])
    @_json_require_admin
    def api_poll_close(code, poll_id):
        poll = Poll.query.filter_by(id=poll_id).first_or_404()
        poll.closed = True
        db.session.commit()
        return jsonify(poll.to_dict())

    @app.route("/api/<code>/polls/<int:poll_id>", methods=["DELETE"])
    @_json_require_admin
    def api_poll_delete(code, poll_id):
        poll = Poll.query.filter_by(id=poll_id).first_or_404()
        db.session.delete(poll)
        db.session.commit()
        return jsonify({"ok": True})

    # ──────────────────────────────────────────
    # API — Route stops
    # ──────────────────────────────────────────

    @app.route("/api/<code>/route", methods=["POST"])
    @_json_require_member
    def api_route_add(code):
        trip = Trip.query.filter_by(join_code=code).first_or_404()
        data = request.get_json(silent=True) or {}
        name = str(data.get("name", "")).strip()[:150]
        if not name:
            abort(400)
        pos = RouteStop.query.filter_by(trip_id=trip.id).count() + 1
        lat = float(data["lat"]) if data.get("lat") is not None else None
        lng = float(data["lng"]) if data.get("lng") is not None else None
        stop = RouteStop(trip_id=trip.id, position=pos, name=name,
                         description=str(data.get("description", "")).strip()[:500],
                         lat=lat, lng=lng, added_by=session.get("user", ""))
        db.session.add(stop)
        db.session.commit()
        return jsonify(stop.to_dict()), 201

    @app.route("/api/<code>/route/<int:stop_id>", methods=["DELETE"])
    @_json_require_member
    def api_route_delete(code, stop_id):
        me = _member(code)
        stop = RouteStop.query.filter_by(id=stop_id).first_or_404()
        if not me.is_admin and stop.added_by != me.name:
            abort(403)
        db.session.delete(stop)
        db.session.commit()
        return jsonify({"ok": True})

    @app.route("/api/<code>/route/reorder", methods=["PUT"])
    @_json_require_member
    def api_route_reorder(code):
        trip = Trip.query.filter_by(join_code=code).first_or_404()
        data = request.get_json(silent=True) or {}
        order = data.get("order", [])
        for pos, stop_id in enumerate(order, 1):
            RouteStop.query.filter_by(id=int(stop_id), trip_id=trip.id).update({"position": pos})
        db.session.commit()
        return jsonify({"ok": True})

    # ──────────────────────────────────────────
    # API — Availability
    # ──────────────────────────────────────────

    @app.route("/api/<code>/availability", methods=["POST"])
    @_json_require_member
    def api_availability(code):
        me = _member(code)
        data = request.get_json(silent=True) or {}
        dates = [str(d)[:10] for d in data.get("dates", []) if isinstance(d, str)]
        me.set_dates(dates)
        db.session.commit()
        return jsonify({"ok": True, "dates": me.available_dates_list})

    @app.route("/api/<code>/proposal-vote", methods=["POST"])
    @_json_require_member
    def api_proposal_vote(code):
        me = _member(code)
        trip = Trip.query.filter_by(join_code=code).first_or_404()
        data = request.get_json(silent=True) or {}
        pid  = int(data.get("proposal_id", 0))
        attending = bool(data.get("attending", True))
        p = TripDateProposal.query.filter_by(id=pid, trip_id=trip.id).first_or_404()
        existing = ProposalVote.query.filter_by(proposal_id=pid, member_id=me.id).first()
        if attending and not existing:
            db.session.add(ProposalVote(
                proposal_id=pid, member_id=me.id,
                member_name=me.name, member_color=me.color,
            ))
        elif not attending and existing:
            db.session.delete(existing)
        db.session.commit()
        p = TripDateProposal.query.get(pid)
        return jsonify({"ok": True, "proposal": p.to_dict()})

    # ──────────────────────────────────────────
    # API — Personal items
    # ──────────────────────────────────────────

    def _personal_add(code, kind):
        me = _member(code)
        if not me:
            abort(401)
        data = request.get_json(silent=True) or {}
        text = str(data.get("text", "")).strip()[:300]
        if not text:
            abort(400)
        item = PersonalItem(member_id=me.id, kind=kind, text=text)
        db.session.add(item)
        db.session.commit()
        return jsonify(item.to_dict()), 201

    def _personal_toggle(code, kind, item_id):
        me = _member(code)
        if not me:
            abort(401)
        item = PersonalItem.query.filter_by(id=item_id, member_id=me.id, kind=kind).first_or_404()
        item.done = not item.done
        db.session.commit()
        return jsonify(item.to_dict())

    def _personal_delete(code, kind, item_id):
        me = _member(code)
        if not me:
            abort(401)
        item = PersonalItem.query.filter_by(id=item_id, member_id=me.id, kind=kind).first_or_404()
        db.session.delete(item)
        db.session.commit()
        return jsonify({"ok": True})

    @app.route("/api/<code>/personal/food", methods=["POST"])
    def api_pfood_add(code): return _personal_add(code, "food")

    @app.route("/api/<code>/personal/food/<int:item_id>/toggle", methods=["POST"])
    def api_pfood_toggle(code, item_id): return _personal_toggle(code, "food", item_id)

    @app.route("/api/<code>/personal/food/<int:item_id>", methods=["DELETE"])
    def api_pfood_delete(code, item_id): return _personal_delete(code, "food", item_id)

    @app.route("/api/<code>/personal/gear", methods=["POST"])
    def api_pgear_add(code): return _personal_add(code, "gear")

    @app.route("/api/<code>/personal/gear/<int:item_id>/toggle", methods=["POST"])
    def api_pgear_toggle(code, item_id): return _personal_toggle(code, "gear", item_id)

    @app.route("/api/<code>/personal/gear/<int:item_id>", methods=["DELETE"])
    def api_pgear_delete(code, item_id): return _personal_delete(code, "gear", item_id)

    @app.route("/api/<code>/personal/notes", methods=["POST"])
    def api_personal_notes(code):
        me = _member(code)
        if not me:
            abort(401)
        data = request.get_json(silent=True) or {}
        me.notes = str(data.get("notes", ""))[:2000]
        db.session.commit()
        return jsonify({"ok": True})

    return app
