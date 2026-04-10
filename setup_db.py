"""
競合コインランドリー稼働モニタリング - DB初期化スクリプト
"""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "competitor_monitor.db")


def setup_database():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("""CREATE TABLE IF NOT EXISTS stores (
        store_id INTEGER PRIMARY KEY,
        store_name TEXT NOT NULL,
        address TEXT,
        url TEXT,
        is_own_store INTEGER DEFAULT 0
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS machines (
        machine_id INTEGER PRIMARY KEY AUTOINCREMENT,
        store_id INTEGER NOT NULL,
        machine_number TEXT NOT NULL,
        machine_type TEXT,
        capacity TEXT,
        FOREIGN KEY (store_id) REFERENCES stores(store_id),
        UNIQUE(store_id, machine_number)
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS availability_log (
        log_id INTEGER PRIMARY KEY AUTOINCREMENT,
        store_id INTEGER NOT NULL,
        machine_id INTEGER NOT NULL,
        recorded_at TEXT NOT NULL,
        status TEXT NOT NULL,
        remaining_minutes INTEGER DEFAULT 0,
        FOREIGN KEY (store_id) REFERENCES stores(store_id),
        FOREIGN KEY (machine_id) REFERENCES machines(machine_id)
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS scrape_log (
        log_id INTEGER PRIMARY KEY AUTOINCREMENT,
        store_id INTEGER NOT NULL,
        scraped_at TEXT NOT NULL,
        success INTEGER NOT NULL,
        error_message TEXT,
        machine_count INTEGER DEFAULT 0,
        FOREIGN KEY (store_id) REFERENCES stores(store_id)
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS hourly_summary (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        store_id INTEGER NOT NULL,
        hour_start TEXT NOT NULL,
        total_machines INTEGER,
        busy_machines_avg REAL,
        availability_rate REAL,
        UNIQUE(store_id, hour_start)
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS daily_summary (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        store_id INTEGER NOT NULL,
        date TEXT NOT NULL,
        total_machines INTEGER,
        avg_availability_rate REAL,
        min_availability_rate REAL,
        UNIQUE(store_id, date)
    )""")

    # インデックス
    c.execute("CREATE INDEX IF NOT EXISTS idx_avail_store_time ON availability_log(store_id, recorded_at)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_avail_recorded ON availability_log(recorded_at)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_hourly_store ON hourly_summary(store_id, hour_start)")

    # 店舗マスタ登録
    stores = [
        (2, "Baluko Laundry Place 伊勢崎宮子町", "群馬県伊勢崎市宮子町3410-3",
         "https://baluko.jp/baluko-isesakimiyakomachi/", 0),
        (3, "ブルースカイランドリー トライアル伊勢崎中央店", "群馬県伊勢崎市連取町1507",
         "http://edms.bsl-line.jp/shop/G0064", 0),
        (4, "fluffy 伊勢崎韮塚店", "群馬県伊勢崎市韮塚町1211-8",
         "https://www.coin-laundry.co.jp/userp/shop_detail/11001328", 0),
        (5, "コインランドリー Wish", "",
         "https://laundry-wish.com/cgi-bin/kadou.php", 0),
    ]
    for s in stores:
        c.execute("INSERT OR IGNORE INTO stores VALUES (?,?,?,?,?)", s)

    conn.commit()
    conn.close()
    print(f"Database ready: {DB_PATH}")


if __name__ == "__main__":
    setup_database()
