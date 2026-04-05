"""
JimnyCamp — SQLAlchemy models
Single SQLite database: jimnycamp.db
"""
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

COLORS = [
    "#059669","#0891B2","#7C3AED","#DB2777",
    "#D97706","#DC2626","#0369A1","#9333EA",
    "#B45309","#0F766E","#be185d","#1d4ed8",
]

# ─────────────────────────────────────────────
# Association: trip membership
# ─────────────────────────────────────────────
class TripMember(db.Model):
    __tablename__ = "trip_member"
    id         = db.Column(db.Integer, primary_key=True)
    trip_id    = db.Column(db.Integer, db.ForeignKey("trip.id"), nullable=False)
    name          = db.Column(db.String(60), nullable=False)
    color         = db.Column(db.String(10), nullable=False)
    is_admin      = db.Column(db.Boolean, default=False)
    joined_at     = db.Column(db.DateTime, default=datetime.utcnow)
    password_hash = db.Column(db.String(256), nullable=True)

    # per-member availability (stored as newline-separated ISO dates)
    available_dates = db.Column(db.Text, default="")
    personal_food   = db.relationship("PersonalItem", back_populates="member",
                                      cascade="all, delete-orphan",
                                      primaryjoin="and_(PersonalItem.member_id==TripMember.id, PersonalItem.kind=='food')")
    personal_gear   = db.relationship("PersonalItem", back_populates="member",
                                      cascade="all, delete-orphan",
                                      primaryjoin="and_(PersonalItem.member_id==TripMember.id, PersonalItem.kind=='gear')",
                                      overlaps="personal_food")
    notes           = db.Column(db.Text, default="")

    @property
    def available_dates_list(self):
        return [d for d in self.available_dates.split("\n") if d]

    def set_dates(self, dates: list[str]):
        self.available_dates = "\n".join(sorted(set(d[:10] for d in dates if d)))

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "color": self.color,
            "is_admin": self.is_admin,
            "available_dates": self.available_dates_list,
        }


# ─────────────────────────────────────────────
# Trip
# ─────────────────────────────────────────────
class Trip(db.Model):
    __tablename__ = "trip"
    id           = db.Column(db.Integer, primary_key=True)
    name         = db.Column(db.String(120), nullable=False)
    description  = db.Column(db.Text, default="")
    join_code    = db.Column(db.String(12), unique=True, nullable=False)
    created_at   = db.Column(db.DateTime, default=datetime.utcnow)

    members      = db.relationship("TripMember", backref="trip", cascade="all, delete-orphan",
                                   foreign_keys=[TripMember.trip_id])
    todos        = db.relationship("TodoItem",       backref="trip", cascade="all, delete-orphan")
    equipment    = db.relationship("EquipmentItem",  backref="trip", cascade="all, delete-orphan")
    food         = db.relationship("FoodItem",        backref="trip", cascade="all, delete-orphan")
    ideas        = db.relationship("Idea",           backref="trip", cascade="all, delete-orphan")
    polls        = db.relationship("Poll",           backref="trip", cascade="all, delete-orphan")
    route_stops  = db.relationship("RouteStop",      backref="trip",
                                   cascade="all, delete-orphan",
                                   order_by="RouteStop.position")
    proposals    = db.relationship("TripDateProposal", cascade="all, delete-orphan",
                                   order_by="TripDateProposal.position")

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "join_code": self.join_code,
            "created_at": self.created_at.isoformat(),
            "member_count": len(self.members),
        }


# ─────────────────────────────────────────────
# Todo items (shared, trip-level)
# ─────────────────────────────────────────────
class TodoItem(db.Model):
    __tablename__ = "todo_item"
    id         = db.Column(db.Integer, primary_key=True)
    trip_id    = db.Column(db.Integer, db.ForeignKey("trip.id"), nullable=False)
    text       = db.Column(db.String(300), nullable=False)
    done       = db.Column(db.Boolean, default=False)
    assignee   = db.Column(db.String(60), default="")
    added_by   = db.Column(db.String(60), default="")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    todo_votes = db.relationship("TodoVote", cascade="all, delete-orphan", backref="todo")

    @property
    def vote_count(self):
        return len(self.todo_votes)

    def to_dict(self):
        return {"id": self.id, "text": self.text, "done": self.done,
                "assignee": self.assignee, "added_by": self.added_by,
                "vote_count": self.vote_count,
                "voter_ids": [v.member_id for v in self.todo_votes]}


# ─────────────────────────────────────────────
# Equipment items (shared, trip-level)
# ─────────────────────────────────────────────
class EquipmentItem(db.Model):
    __tablename__ = "equipment_item"
    id         = db.Column(db.Integer, primary_key=True)
    trip_id    = db.Column(db.Integer, db.ForeignKey("trip.id"), nullable=False)
    text       = db.Column(db.String(300), nullable=False)
    done       = db.Column(db.Boolean, default=False)
    assignee   = db.Column(db.String(60), default="")
    added_by   = db.Column(db.String(60), default="")
    category   = db.Column(db.String(100), default="")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {"id": self.id, "text": self.text, "done": self.done, "assignee": self.assignee, "added_by": self.added_by, "category": self.category or ""}


# ─────────────────────────────────────────────
# Food items (shared, trip-level)
# ─────────────────────────────────────────────
class FoodItem(db.Model):
    __tablename__ = "food_item"
    id         = db.Column(db.Integer, primary_key=True)
    trip_id    = db.Column(db.Integer, db.ForeignKey("trip.id"), nullable=False)
    text       = db.Column(db.String(300), nullable=False)
    done       = db.Column(db.Boolean, default=False)
    assignee   = db.Column(db.String(60), default="")
    added_by   = db.Column(db.String(60), default="")
    category   = db.Column(db.String(100), default="")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {"id": self.id, "text": self.text, "done": self.done, "assignee": self.assignee, "added_by": self.added_by, "category": self.category or ""}


# ─────────────────────────────────────────────
# Personal items (food & gear per member)
# ─────────────────────────────────────────────
class PersonalItem(db.Model):
    __tablename__ = "personal_item"
    id        = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(db.Integer, db.ForeignKey("trip_member.id"), nullable=False)
    kind      = db.Column(db.String(10), nullable=False)   # 'food' | 'gear'
    text      = db.Column(db.String(300), nullable=False)
    done      = db.Column(db.Boolean, default=False)

    member    = db.relationship("TripMember", back_populates="personal_food",
                                foreign_keys=[member_id],
                                overlaps="personal_gear")

    def to_dict(self):
        return {"id": self.id, "text": self.text, "done": self.done, "kind": self.kind}


# ─────────────────────────────────────────────
# Ideas section
# ─────────────────────────────────────────────
class Idea(db.Model):
    __tablename__ = "idea"
    id         = db.Column(db.Integer, primary_key=True)
    trip_id    = db.Column(db.Integer, db.ForeignKey("trip.id"), nullable=False)
    text       = db.Column(db.String(600), nullable=False)
    added_by   = db.Column(db.String(60), default="")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    idea_votes = db.relationship("IdeaVote", cascade="all, delete-orphan", backref="idea")

    @property
    def votes(self):
        return len(self.idea_votes)

    def to_dict(self):
        return {"id": self.id, "text": self.text, "added_by": self.added_by,
                "votes": self.votes,
                "voter_ids": [v.member_id for v in self.idea_votes]}


# ─────────────────────────────────────────────
# Polls
# ─────────────────────────────────────────────
class Poll(db.Model):
    __tablename__ = "poll"
    id         = db.Column(db.Integer, primary_key=True)
    trip_id    = db.Column(db.Integer, db.ForeignKey("trip.id"), nullable=False)
    question   = db.Column(db.String(300), nullable=False)
    kind       = db.Column(db.String(20), default="general")  # 'date' | 'location' | 'general'
    created_by = db.Column(db.String(60), default="")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    closed     = db.Column(db.Boolean, default=False)
    options    = db.relationship("PollOption", backref="poll",
                                 cascade="all, delete-orphan",
                                 order_by="PollOption.id")

    def to_dict(self):
        return {
            "id": self.id,
            "question": self.question,
            "kind": self.kind,
            "created_by": self.created_by,
            "closed": self.closed,
            "options": [o.to_dict() for o in self.options],
        }


class PollOption(db.Model):
    __tablename__ = "poll_option"
    id       = db.Column(db.Integer, primary_key=True)
    poll_id  = db.Column(db.Integer, db.ForeignKey("poll.id"), nullable=False)
    text     = db.Column(db.String(200), nullable=False)
    votes    = db.relationship("PollVote", backref="option", cascade="all, delete-orphan")

    @property
    def vote_count(self):
        return len(self.votes)

    def to_dict(self):
        return {"id": self.id, "text": self.text, "vote_count": self.vote_count}


class PollVote(db.Model):
    __tablename__ = "poll_vote"
    id        = db.Column(db.Integer, primary_key=True)
    option_id = db.Column(db.Integer, db.ForeignKey("poll_option.id"), nullable=False)
    voter     = db.Column(db.String(60), nullable=False)

    __table_args__ = (
        db.UniqueConstraint("option_id", "voter", name="uq_option_voter"),
    )


# ─────────────────────────────────────────────
# Route stops / map points
# ─────────────────────────────────────────────
class RouteStop(db.Model):
    __tablename__ = "route_stop"
    id         = db.Column(db.Integer, primary_key=True)
    trip_id    = db.Column(db.Integer, db.ForeignKey("trip.id"), nullable=False)
    position   = db.Column(db.Integer, default=0)        # ordering
    name       = db.Column(db.String(150), nullable=False)
    description= db.Column(db.Text, default="")
    lat        = db.Column(db.Float, nullable=True)       # optional GPS
    lng        = db.Column(db.Float, nullable=True)
    added_by   = db.Column(db.String(60), default="")

    def to_dict(self):
        return {
            "id": self.id,
            "position": self.position,
            "name": self.name,
            "description": self.description,
            "lat": self.lat,
            "lng": self.lng,
            "added_by": self.added_by,
        }


# ─────────────────────────────────────────────
# Admin-proposed date windows
# ─────────────────────────────────────────────
class TripDateProposal(db.Model):
    __tablename__ = "trip_date_proposal"
    id       = db.Column(db.Integer, primary_key=True)
    trip_id  = db.Column(db.Integer, db.ForeignKey("trip.id"), nullable=False)
    start    = db.Column(db.String(10), nullable=False)   # ISO date
    end      = db.Column(db.String(10), nullable=False)   # ISO date
    label    = db.Column(db.String(100), default="")
    position     = db.Column(db.Integer, default=0)
    suggested_by = db.Column(db.String(60), default="")  # empty = admin
    votes        = db.relationship("ProposalVote", cascade="all, delete-orphan",
                                   backref="proposal")

    @property
    def days(self):
        from datetime import date
        return (date.fromisoformat(self.end) - date.fromisoformat(self.start)).days + 1

    def to_dict(self):
        return {
            "id": self.id,
            "start": self.start,
            "end": self.end,
            "label": self.label,
            "days": self.days,
            "voters": [{"name": v.member_name, "color": v.member_color} for v in self.votes],
        }


class ProposalVote(db.Model):
    __tablename__ = "proposal_vote"
    id           = db.Column(db.Integer, primary_key=True)
    proposal_id  = db.Column(db.Integer, db.ForeignKey("trip_date_proposal.id"), nullable=False)
    member_id    = db.Column(db.Integer, db.ForeignKey("trip_member.id"), nullable=False)
    member_name  = db.Column(db.String(60), nullable=False)
    member_color = db.Column(db.String(10), nullable=False, default="")
    __table_args__ = (db.UniqueConstraint("proposal_id", "member_id"),)


# ─────────────────────────────────────────────
# Per-member idea votes (one per member per idea)
# ─────────────────────────────────────────────
class IdeaVote(db.Model):
    __tablename__ = "idea_vote"
    id        = db.Column(db.Integer, primary_key=True)
    idea_id   = db.Column(db.Integer, db.ForeignKey("idea.id"), nullable=False)
    member_id = db.Column(db.Integer, db.ForeignKey("trip_member.id"), nullable=False)
    __table_args__ = (db.UniqueConstraint("idea_id", "member_id"),)


# ─────────────────────────────────────────────
# Per-member todo votes (one per member per todo)
# ─────────────────────────────────────────────
class TodoVote(db.Model):
    __tablename__ = "todo_vote"
    id        = db.Column(db.Integer, primary_key=True)
    todo_id   = db.Column(db.Integer, db.ForeignKey("todo_item.id"), nullable=False)
    member_id = db.Column(db.Integer, db.ForeignKey("trip_member.id"), nullable=False)
    __table_args__ = (db.UniqueConstraint("todo_id", "member_id"),)


# ─────────────────────────────────────────────
# Member role votes (Leader, Chef, Guide, etc.)
# ─────────────────────────────────────────────
TRIP_ROLES = ["Leader", "Chef", "Guide", "Entertainment", "Apothikarios"]

class RoleVote(db.Model):
    __tablename__ = "role_vote"
    id           = db.Column(db.Integer, primary_key=True)
    trip_id      = db.Column(db.Integer, db.ForeignKey("trip.id"), nullable=False)
    role         = db.Column(db.String(40), nullable=False)
    voter_name   = db.Column(db.String(60), nullable=False)
    nominee_name = db.Column(db.String(60), nullable=False)
    __table_args__ = (db.UniqueConstraint("trip_id", "role", "voter_name", name="uq_role_voter"),)
