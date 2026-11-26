import sqlite3
import random
from datetime import date, timedelta

DB = "database.db"

RFID_USERS = [
    ("033BD5E4", "Sector A", "GreenView", "good"),
    ("239ECEE4", "Sector A", "GreenView", "good"),
    ("536EBFE4", "Sector A", "LakeSide", "average"),
    ("C393CFE4", "Sector A", "LakeSide", "good"),
    ("9352C7E4", "Sector B", "MetroHeights", "defaulter"),
    ("63DED6E4", "Sector B", "MetroHeights", "average"),
    ("439A87E4", "Sector B", "GreenView", "good"),
    ("B3E58FE4", "Sector B", "LakeSide", "average"),
    ("738A86E4", "Sector C", "MetroHeights", "defaulter"),
    ("B3FEC6E4", "Sector C", "MetroHeights", "defaulter"),
    ("C3CCD811", "Sector C", "GreenView", "good"),
    ("330FD2E4", "Sector C", "GreenView", "average"),
    ("732BD7E4", "Sector A", "MetroHeights", "average"),
    ("63A8D8E4", "Sector B", "LakeSide", "good"),
    ("6396D2E4", "Sector C", "LakeSide", "defaulter"),
]

# ---------------- TABLES ----------------

def create_tables(cur):
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        email TEXT,
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

    # ✅ UPDATED: wet + dry + total
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

# ---------------- RESET ----------------

def reset_db(cur):
    cur.execute("DELETE FROM users")
    cur.execute("DELETE FROM pickup_logs")
    cur.execute("DELETE FROM sector_waste")

# ---------------- USERS ----------------

def seed_users(cur):
    # Admin
    cur.execute("""
    INSERT INTO users (name,email,password,rfid,role,sector,society)
    VALUES ('Admin','admin@test.com','admin123','ADMIN','admin','ALL','ALL')
    """)

    for idx, (rfid, sector, society, _) in enumerate(RFID_USERS, start=1):
        cur.execute("""
        INSERT INTO users (name,email,password,rfid,role,sector,society)
        VALUES (?,?,?,?,?,?,?)
        """, (
            f"User {idx}",
            f"user{idx}@test.com",
            "user123",
            rfid,
            "user",
            sector,
            society
        ))

# ---------------- PICKUPS ----------------

def seed_pickups(cur):
    today = date.today()

    for rfid, _, _, behavior in RFID_USERS:
        for i in range(45):
            d = today - timedelta(days=i)

            if behavior == "good":
                miss_chance = 0.05
            elif behavior == "average":
                miss_chance = 0.25
            else:
                miss_chance = 0.5

            # force streak for defaulters
            if behavior == "defaulter" and i in [5, 6, 7]:
                continue

            if random.random() < miss_chance:
                continue

            cur.execute(
                "INSERT INTO pickup_logs (rfid,date) VALUES (?,?)",
                (rfid, d.isoformat())
            )

# ---------------- SECTOR WASTE ----------------

def seed_sector_waste(cur):
    today = date.today()
    sectors = ["Sector A", "Sector B", "Sector C"]

    for sector in sectors:
        base_total = random.randint(90, 160)

        for i in range(7):  # last 7 days
            date_val = (today - timedelta(days=i)).isoformat()

            # realistic wet/dry split
            wet_ratio = random.uniform(0.55, 0.7)   # wet dominates
            wet = round(base_total * wet_ratio + random.randint(-8, 8), 1)
            dry = round(base_total * (1 - wet_ratio) + random.randint(-5, 5), 1)
            total = round(wet + dry, 1)

            cur.execute("""
            INSERT INTO sector_waste
            (sector, date, wet_waste_kg, dry_waste_kg, total_waste_kg)
            VALUES (?, ?, ?, ?, ?)
            """, (
                sector,
                date_val,
                wet,
                dry,
                total
            ))

# ---------------- MAIN ----------------

def main():
    con = sqlite3.connect(DB)
    cur = con.cursor()

    create_tables(cur)
    reset_db(cur)
    seed_users(cur)
    seed_pickups(cur)
    seed_sector_waste(cur)

    con.commit()
    con.close()

    print("✅ Seeded database with wet + dry waste data (stacked-bar ready)")

if __name__ == "__main__":
    main()
