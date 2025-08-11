import os
from datetime import datetime
from functools import wraps

from flask import (
    Flask, render_template, request, redirect, url_for,
    session, jsonify, flash
)
from werkzeug.security import generate_password_hash, check_password_hash

from sqlalchemy import (
    create_engine, Column, Integer, String, Text, DateTime,
    Boolean, ForeignKey, UniqueConstraint
)
from sqlalchemy.orm import (
    declarative_base, sessionmaker, scoped_session, relationship
)

# -----------------------------
# Konfiguration
# -----------------------------
APP_TITLE = "VIP Coding Universe"
DB_PATH = "sqlite:///vip_universe.db"
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-me")
INITIAL_ADMIN_EMAIL = "admin@vip.local"
INITIAL_ADMIN_PASSWORD = "123456789"  # <- hier bei Bedarf eines der obigen Passwörter einsetzen

app = Flask(__name__, static_folder="static", template_folder="templates")
app.config["SECRET_KEY"] = SECRET_KEY

engine = create_engine(DB_PATH, echo=False, future=True)
SessionLocal = scoped_session(sessionmaker(bind=engine, autoflush=False, autocommit=False))
Base = declarative_base()

# -----------------------------
# Datenbank-Modelle
# -----------------------------
class Company(Base):
    __tablename__ = "company"
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    street = Column(String(255))
    house_number = Column(String(50))
    postal_code = Column(String(20))
    city = Column(String(120))
    created_at = Column(DateTime, default=datetime.utcnow)

    users = relationship("User", back_populates="company", cascade="all, delete-orphan")
    records = relationship("Record", back_populates="company", cascade="all, delete-orphan")


class User(Base):
    __tablename__ = "user"
    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    is_superadmin = Column(Boolean, default=False)
    company_id = Column(Integer, ForeignKey("company.id"), nullable=True)

    company = relationship("Company", back_populates="users")

    def set_password(self, raw):
        self.password_hash = generate_password_hash(raw)

    def check_password(self, raw):
        return check_password_hash(self.password_hash, raw)


class Record(Base):
    __tablename__ = "record"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("company.id"), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text, default="")
    group = Column(String(255), default="")
    created_at = Column(DateTime, default=datetime.utcnow)

    company = relationship("Company", back_populates="records")


class RecordRelation(Base):
    __tablename__ = "record_relation"
    id = Column(Integer, primary_key=True)
    # Wir modellieren eine UNGERICHTETE Relation. Um Duplikate zu vermeiden,
    # speichern wir immer (min_id, max_id) in (a_id, b_id)
    a_id = Column(Integer, ForeignKey("record.id"), nullable=False)
    b_id = Column(Integer, ForeignKey("record.id"), nullable=False)
    company_id = Column(Integer, ForeignKey("company.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("a_id", "b_id", name="uq_relation_pair"),
    )

# -----------------------------
# Helpers / Boilerplate
# -----------------------------
def init_db():
    Base.metadata.create_all(engine)
    db = SessionLocal()
    try:
        admin = db.query(User).filter(User.email == INITIAL_ADMIN_EMAIL).first()
        if not admin:
            admin = User(email=INITIAL_ADMIN_EMAIL, is_superadmin=True)
            admin.set_password(INITIAL_ADMIN_PASSWORD)
            db.add(admin)
            db.commit()
            print(f"[INIT] Super-Admin angelegt: {INITIAL_ADMIN_EMAIL} / {INITIAL_ADMIN_PASSWORD}")
    finally:
        db.close()

def get_db():
    return SessionLocal()

def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapper

def superadmin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("user_id") or not session.get("is_superadmin"):
            flash("Nicht berechtigt.", "error")
            return redirect(url_for("index"))
        return fn(*args, **kwargs)
    return wrapper

def current_user(db):
    uid = session.get("user_id")
    if not uid:
        return None
    return db.query(User).filter(User.id == uid).first()

def normalized_pair(id1:int, id2:int):
    return (id1, id2) if id1 < id2 else (id2, id1)

# -----------------------------
# Routes: Auth / Start
# -----------------------------
@app.route("/")
def index():
    if session.get("user_id"):
        if session.get("is_superadmin"):
            return redirect(url_for("admin"))
        else:
            return redirect(url_for("records"))
    return redirect(url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        db = get_db()
        try:
            user = db.query(User).filter(User.email == email).first()
            if user and user.check_password(password):
                session["user_id"] = user.id
                session["is_superadmin"] = bool(user.is_superadmin)
                session["company_id"] = user.company_id
                return redirect(url_for("index"))
            flash("Login fehlgeschlagen.", "error")
        finally:
            db.close()
    return render_template("login.html", app_title=APP_TITLE)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# -----------------------------
# Routes: Super-Admin
# -----------------------------
@app.route("/admin", methods=["GET", "POST"])
@superadmin_required
def admin():
    db = get_db()
    try:
        companies = db.query(Company).order_by(Company.created_at.desc()).all()
        users = db.query(User).order_by(User.id.desc()).all()
        return render_template("admin.html", app_title=APP_TITLE, companies=companies, users=users)
    finally:
        db.close()

@app.route("/admin/company/create", methods=["POST"])
@superadmin_required
def create_company():
    name = (request.form.get("name") or "").strip()
    street = (request.form.get("street") or "").strip()
    house_number = (request.form.get("house_number") or "").strip()
    postal_code = (request.form.get("postal_code") or "").strip()
    city = (request.form.get("city") or "").strip()
    if not name:
        flash("Firmenname ist erforderlich.", "error")
        return redirect(url_for("admin"))
    db = get_db()
    try:
        c = Company(
            name=name, street=street, house_number=house_number,
            postal_code=postal_code, city=city
        )
        db.add(c)
        db.commit()
        flash("Firma angelegt.", "success")
    finally:
        db.close()
    return redirect(url_for("admin"))

@app.route("/admin/user/create", methods=["POST"])
@superadmin_required
def create_user():
    email = (request.form.get("email") or "").strip().lower()
    password = request.form.get("password") or ""
    company_id = request.form.get("company_id")
    is_superadmin = bool(request.form.get("is_superadmin"))
    if not email or not password:
        flash("E-Mail und Passwort sind erforderlich.", "error")
        return redirect(url_for("admin"))
    db = get_db()
    try:
        if is_superadmin:
            company_id_val = None
        else:
            try:
                company_id_val = int(company_id)
            except (TypeError, ValueError):
                flash("Bitte eine Firma wählen.", "error")
                return redirect(url_for("admin"))
        if db.query(User).filter(User.email == email).first():
            flash("E-Mail bereits vergeben.", "error")
            return redirect(url_for("admin"))
        u = User(email=email, is_superadmin=is_superadmin, company_id=company_id_val)
        u.set_password(password)
        db.add(u)
        db.commit()
        flash("User angelegt.", "success")
    finally:
        db.close()
    return redirect(url_for("admin"))

# -----------------------------
# Routes: Firmen-User – Datensätze & Relationen
# -----------------------------
@app.route("/records", methods=["GET"])
@login_required
def records():
    db = get_db()
    try:
        user = current_user(db)
        if user.is_superadmin:
            flash("Als Super-Admin bitte eine Firma auswählen und /live?company_id=<id> nutzen.", "info")
            return redirect(url_for("admin"))
        company = db.query(Company).filter(Company.id == user.company_id).first()
        # Listen für UI
        recs = db.query(Record).filter(Record.company_id == user.company_id).order_by(Record.created_at.desc()).all()
        # Relationen als (a,b)-Paare
        relations = db.query(RecordRelation).filter(RecordRelation.company_id == user.company_id).all()
        return render_template("records.html", app_title=APP_TITLE, company=company, records=recs, relations=relations)
    finally:
        db.close()

@app.route("/records/create", methods=["POST"])
@login_required
def create_record():
    name = (request.form.get("name") or "").strip()
    description = (request.form.get("description") or "").strip()
    group = (request.form.get("group") or "").strip()
    if not name:
        flash("Name ist erforderlich.", "error")
        return redirect(url_for("records"))
    db = get_db()
    try:
        user = current_user(db)
        if user.is_superadmin or not user.company_id:
            flash("Bitte als Firmen-User agieren.", "error")
            return redirect(url_for("records"))
        r = Record(company_id=user.company_id, name=name, description=description, group=group)
        db.add(r)
        db.commit()
        flash("Datensatz angelegt.", "success")
    finally:
        db.close()
    return redirect(url_for("records"))

@app.route("/relations/create", methods=["POST"])
@login_required
def create_relation():
    a_id = int(request.form.get("a_id"))
    b_id = int(request.form.get("b_id"))
    if a_id == b_id:
        flash("Relation zu sich selbst ist nicht erlaubt.", "error")
        return redirect(url_for("records"))
    db = get_db()
    try:
        user = current_user(db)
        if user.is_superadmin or not user.company_id:
            flash("Bitte als Firmen-User agieren.", "error")
            return redirect(url_for("records"))
        # Validierung: Beide Records gehören zur Firma
        count = db.query(Record).filter(
            Record.company_id == user.company_id,
            Record.id.in_([a_id, b_id])
        ).count()
        if count != 2:
            flash("Ungültige Datensatz-IDs.", "error")
            return redirect(url_for("records"))
        a, b = normalized_pair(a_id, b_id)
        # Anlegen, falls nicht vorhanden
        exists = db.query(RecordRelation).filter_by(a_id=a, b_id=b, company_id=user.company_id).first()
        if not exists:
            rel = RecordRelation(a_id=a, b_id=b, company_id=user.company_id)
            db.add(rel)
            db.commit()
            flash("Relation angelegt.", "success")
        else:
            flash("Relation existiert bereits.", "info")
    finally:
        db.close()
    return redirect(url_for("records"))

@app.route("/relations/delete", methods=["POST"])
@login_required
def delete_relation():
    rel_id = int(request.form.get("rel_id"))
    db = get_db()
    try:
        user = current_user(db)
        if user.is_superadmin or not user.company_id:
            flash("Bitte als Firmen-User agieren.", "error")
            return redirect(url_for("records"))
        rel = db.query(RecordRelation).filter(
            RecordRelation.id == rel_id,
            RecordRelation.company_id == user.company_id
        ).first()
        if rel:
            db.delete(rel)
            db.commit()
            flash("Relation gelöscht.", "success")
        else:
            flash("Relation nicht gefunden.", "error")
    finally:
        db.close()
    return redirect(url_for("records"))

# -----------------------------
# Live-Ansicht (3D)
# -----------------------------
@app.route("/live")
@login_required
def live():
    db = get_db()
    try:
        user = current_user(db)
        # Super-Admin darf per ?company_id=... eine Firma ansehen
        company_id = request.args.get("company_id", type=int)
        if user.is_superadmin:
            if not company_id:
                flash("Bitte company_id als Query-Parameter angeben, z.B. /live?company_id=1", "info")
                return redirect(url_for("admin"))
        else:
            company_id = user.company_id

        company = db.query(Company).filter(Company.id == company_id).first()
        if not company:
            flash("Firma nicht gefunden.", "error")
            return redirect(url_for("index"))
        return render_template("live.html", app_title=APP_TITLE, company=company)
    finally:
        db.close()

@app.route("/api/graph")
@login_required
def api_graph():
    """
    Liefert für die Firma die Knoten (Records) und Kanten (Relations).
    Optional für Super-Admin: ?company_id=...
    """
    db = get_db()
    try:
        user = current_user(db)
        company_id = request.args.get("company_id", type=int)
        if not user.is_superadmin:
            company_id = user.company_id
        elif not company_id:
            return jsonify({"error": "company_id erforderlich"}), 400

        recs = db.query(Record).filter(Record.company_id == company_id).all()
        rels = db.query(RecordRelation).filter(RecordRelation.company_id == company_id).all()

        nodes = [
            {"id": r.id, "name": r.name, "description": r.description or "", "group": r.group or ""}
            for r in recs
        ]
        edges = [{"a": rel.a_id, "b": rel.b_id} for rel in rels]

        return jsonify({"nodes": nodes, "edges": edges, "company_id": company_id, "ts": int(datetime.utcnow().timestamp())})
    finally:
        db.close()

# -----------------------------
# Main
# -----------------------------
if __name__ == "__main__":
    init_db()
    # Debug True für Entwicklung; für Produktion auf False setzen und einen WSGI-Server nutzen
    app.run(host="127.0.0.1", port=5000, debug=True)
