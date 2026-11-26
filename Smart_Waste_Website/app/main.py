from fastapi import FastAPI, Request, Form, Body
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
import sqlite3
from datetime import date, timedelta
import socket

# ---------------- APP SETUP ----------------

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key="dev-secret-key")

templates = Jinja2Templates(directory="app/templates")
DB = "database.db"


def get_db():
    return sqlite3.connect(DB, check_same_thread=False)


def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


# ---------------- DATABASE INIT ----------------

@app.on_event("startup")
def startup():

    con = get_db()
    cur = con.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS skip_days (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        rfid TEXT,
        date TEXT,
        UNIQUE(rfid, date)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        email TEXT UNIQUE,
        password TEXT,
        rfid TEXT UNIQUE,
        role TEXT,
        sector TEXT,
        society TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS pickup_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        rfid TEXT,
        date TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS sector_waste (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sector TEXT,
        date TEXT,
        wet_waste_kg REAL,
        dry_waste_kg REAL,
        total_waste_kg REAL
    )
    """)

    con.commit()
    con.close()

    ip = get_local_ip()
    port = 8000

    print("\n" + "=" * 55)
    print("🚀 SMART WASTE MANAGEMENT SERVER STARTED")
    print("=" * 55)
    print(f"🌐 Local access   : http://127.0.0.1:{port}")
    print(f"📡 Network access : http://{ip}:{port}")
    print(f"🔗 RFID endpoint  : http://{ip}:{port}/api/pickup")
    print("=" * 55 + "\n")


# ---------------- AUTH ----------------

@app.get("/", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.post("/login")
def login(request: Request, email: str = Form(...), password: str = Form(...)):

    con = get_db()
    cur = con.cursor()

    cur.execute(
        "SELECT rfid, role FROM users WHERE email=? AND password=?",
        (email, password)
    )

    row = cur.fetchone()
    con.close()

    if not row:
        return RedirectResponse("/", status_code=302)

    request.session["rfid"] = row[0]
    request.session["role"] = row[1]

    return RedirectResponse(
        "/admin" if row[1] == "admin" else "/user",
        status_code=302
    )


@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/", status_code=302)


# ---------------- SKIP DAY ----------------

@app.post("/api/skip-day")
def mark_skip_day(payload: dict = Body(...)):

    rfid = payload.get("rfid")
    skip_date = payload.get("date")

    if not rfid or not skip_date:
        return JSONResponse(
            {"status": "error", "message": "rfid or date missing"},
            status_code=400
        )

    if skip_date <= date.today().isoformat():
        return JSONResponse(
            {"status": "error", "message": "Only future dates allowed"},
            status_code=400
        )

    con = get_db()
    cur = con.cursor()

    try:
        cur.execute("""
            INSERT INTO skip_days (rfid, date)
            VALUES (?, ?)
        """, (rfid, skip_date))

        con.commit()

    except sqlite3.IntegrityError:

        con.close()

        return JSONResponse({
            "status": "ok",
            "message": "Already marked as skip day",
            "date": skip_date
        })

    con.close()

    return JSONResponse({
        "status": "success",
        "message": "Skip day registered",
        "date": skip_date
    })


# ---------------- RFID PICKUP ----------------

@app.post("/api/pickup")
def register_pickup(payload: dict = Body(...)):

    rfid = payload.get("rfid")

    if not rfid:
        return JSONResponse(
            {"status": "error", "message": "RFID missing"},
            status_code=400
        )

    today = date.today().isoformat()

    con = get_db()
    cur = con.cursor()

    cur.execute("""
        SELECT name, sector
        FROM users
        WHERE rfid = ?
    """, (rfid,))

    user = cur.fetchone()

    if not user:
        con.close()
        return JSONResponse(
            {"status": "error", "message": "Unknown RFID"},
            status_code=404
        )

    name, sector = user

    cur.execute("""
        SELECT id
        FROM pickup_logs
        WHERE rfid = ? AND date = ?
    """, (rfid, today))

    if cur.fetchone():
        con.close()
        return JSONResponse({
            "status": "ok",
            "message": "Already marked for today",
            "name": name,
            "sector": sector,
            "date": today
        })

    cur.execute("""
        INSERT INTO pickup_logs (rfid, date)
        VALUES (?, ?)
    """, (rfid, today))

    con.commit()
    con.close()

    return JSONResponse({
        "status": "success",
        "message": "Pickup recorded",
        "name": name,
        "sector": sector,
        "date": today
    })


# ---------------- SECTOR WASTE API ----------------

@app.post("/api/sector-waste")
def add_sector_waste(payload: dict = Body(...)):

    sector = payload.get("sector")
    wet = float(payload.get("wet", 0))
    dry = float(payload.get("dry", 0))

    if not sector:
        return JSONResponse({"status": "error"}, status_code=400)

    total = wet + dry
    today = date.today().isoformat()

    sector = sector.strip().upper()

    if not sector.startswith("SECTOR"):
        sector = f"SECTOR {sector}"

    sector = sector.title()

    con = get_db()
    cur = con.cursor()

    cur.execute("""
        SELECT id, wet_waste_kg, dry_waste_kg
        FROM sector_waste
        WHERE sector=? AND date=?
    """, (sector, today))

    row = cur.fetchone()

    if row:

        new_wet = row[1] + wet
        new_dry = row[2] + dry
        new_total = new_wet + new_dry

        cur.execute("""
            UPDATE sector_waste
            SET wet_waste_kg=?, dry_waste_kg=?, total_waste_kg=?
            WHERE id=?
        """, (new_wet, new_dry, new_total, row[0]))

    else:

        cur.execute("""
            INSERT INTO sector_waste
            (sector, date, wet_waste_kg, dry_waste_kg, total_waste_kg)
            VALUES (?, ?, ?, ?, ?)
        """, (sector, today, wet, dry, total))

    con.commit()
    con.close()

    return {"status": "success"}


# ---------------- SIGNUP ----------------

@app.get("/signup", response_class=HTMLResponse)
def signup_page(request: Request):
    return templates.TemplateResponse("signup.html", {"request": request})


@app.post("/signup")
def signup(
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    rfid: str = Form(...),
    sector: str = Form(...),
    society: str = Form(...)
):

    con = get_db()
    cur = con.cursor()

    cur.execute("""
        INSERT INTO users (name, email, password, rfid, role, sector, society)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (name, email, password, rfid, "user", sector, society))

    con.commit()
    con.close()

    return RedirectResponse("/", status_code=302)


# ---------------- USER DASHBOARD ----------------

@app.get("/user", response_class=HTMLResponse)
def user_dashboard(request: Request):

    if request.session.get("role") != "user":
        return RedirectResponse("/", status_code=302)

    rfid = request.session["rfid"]
    today = date.today()

    con = get_db()
    cur = con.cursor()

    cur.execute("""
        SELECT name, email, sector, society
        FROM users
        WHERE rfid = ?
    """, (rfid,))

    user_row = cur.fetchone()

    cur.execute("""
        SELECT date
        FROM pickup_logs
        WHERE rfid = ?
    """, (rfid,))

    picked_dates = {row[0] for row in cur.fetchall()}

    cur.execute("""
        SELECT date FROM skip_days WHERE rfid = ?
    """, (rfid,))

    skip_dates = {row[0] for row in cur.fetchall()}

    calendar = []
    picked_days = 0
    missed_days = 0

    for i in range(29, -1, -1):

        d = today - timedelta(days=i)
        iso = d.isoformat()

        is_today = (d == today)
        was_picked = iso in picked_dates
        is_skip = iso in skip_dates

        if is_skip:
            status = "skip"

        elif was_picked:
            status = "picked"
            picked_days += 1

        elif is_today:
            status = "today"

        else:
            status = "missed"
            missed_days += 1

        calendar.append({
            "date": iso,
            "day": d.strftime("%d"),
            "full_date": d.strftime("%d %b %Y"),
            "status": status,
            "is_today": is_today
        })

    compliance = int((picked_days / 30) * 100)

    miss_streak = 0

    for i in range(1, 31):

        d = (today - timedelta(days=i)).isoformat()

        if d in skip_dates:
            continue

        if d not in picked_dates:
            miss_streak += 1
        else:
            break

    fine = miss_streak >= 3
    reward = picked_days == 30

    con.close()

    return templates.TemplateResponse(
        "user.html",
        {
            "request": request,
            "calendar": calendar,
            "picked_days": picked_days,
            "missed_days": missed_days,
            "compliance": compliance,
            "user": {
                "name": user_row[0],
                "email": user_row[1],
                "rfid": rfid,
                "sector": user_row[2],
                "society": user_row[3],
                "miss_streak": miss_streak,
                "fine": fine,
                "reward": reward
            }
        }
    )


@app.get("/user/awareness", response_class=HTMLResponse)
def awareness_page(request: Request):

    if request.session.get("role") != "user":
        return RedirectResponse("/", status_code=302)

    return templates.TemplateResponse(
        "awareness.html",
        {"request": request}
    )


# ---------------- ADMIN DASHBOARD ----------------

@app.get("/admin", response_class=HTMLResponse)
def admin_dashboard(request: Request):

    if request.session.get("role") != "admin":
        return RedirectResponse("/", status_code=302)

    con = get_db()
    cur = con.cursor()

    cur.execute("SELECT COUNT(*) FROM users WHERE role='user'")
    total_users = cur.fetchone()[0]

    trend = []

    for i in range(7):

        d = date.today() - timedelta(days=i)

        cur.execute("""
            SELECT COUNT(DISTINCT rfid)
            FROM pickup_logs
            WHERE date=?
        """, (d.isoformat(),))

        trend.append({
            "date": d.strftime("%d %b"),
            "count": cur.fetchone()[0]
        })

    cur.execute("""
        SELECT
            sector,
            SUM(wet_waste_kg),
            SUM(dry_waste_kg)
        FROM sector_waste
        GROUP BY sector
    """)

    sector_waste = cur.fetchall()

    con.close()

    return templates.TemplateResponse(
        "admin.html",
        {
            "request": request,
            "total_users": total_users,
            "trend": trend[::-1],
            "sector_waste": sector_waste
        }
    )


# ---------------- ADMIN ACTION ----------------

@app.post("/admin/add-waste")
def add_waste(
    request: Request,
    sector: str = Form(...),
    wet: float = Form(...),
    dry: float = Form(...)
):

    if request.session.get("role") != "admin":
        return RedirectResponse("/", status_code=302)

    sector = sector.strip().upper()

    if not sector.startswith("SECTOR"):
        sector = f"SECTOR {sector}"

    sector = sector.title()

    today = date.today().isoformat()

    total = wet + dry

    con = get_db()
    cur = con.cursor()

    cur.execute("""
        SELECT id, wet_waste_kg, dry_waste_kg
        FROM sector_waste
        WHERE sector=? AND date=?
    """, (sector, today))

    row = cur.fetchone()

    if row:

        new_wet = row[1] + wet
        new_dry = row[2] + dry
        new_total = new_wet + new_dry

        cur.execute("""
            UPDATE sector_waste
            SET wet_waste_kg=?, dry_waste_kg=?, total_waste_kg=?
            WHERE id=?
        """, (new_wet, new_dry, new_total, row[0]))

    else:

        cur.execute("""
            INSERT INTO sector_waste
            (sector, date, wet_waste_kg, dry_waste_kg, total_waste_kg)
            VALUES (?, ?, ?, ?, ?)
        """, (sector, today, wet, dry, total))

    con.commit()
    con.close()

    return RedirectResponse("/admin", status_code=302)