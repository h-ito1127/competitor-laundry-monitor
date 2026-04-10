"""
競合コインランドリー稼働状況スクレイパー
GitHub Actions で10分間隔実行を想定。
依存: requests, beautifulsoup4
"""
import sqlite3
import os
import re
import sys
from datetime import datetime

import requests
from bs4 import BeautifulSoup

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "competitor_monitor.db")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
}
TIMEOUT = 30


# ──────────────────────────────────────────────
# 店舗別パーサー
# ──────────────────────────────────────────────

def fetch(url: str) -> str:
    resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding or "utf-8"
    return resp.text


def parse_baluko(html: str) -> list[dict]:
    """Baluko Laundry Place 伊勢崎宮子町
    ページ構造: 連続テキストで「番号 機種名 空き/使用中 (残り時間)」が並ぶ
    例: "1Mサイズ乾燥機上段空き" "3Mサイズ乾燥機上段34分"（34分=使用中）
    """
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(separator="\n")
    machines = []

    # 連続テキストから一括パターンマッチ
    # 機器番号 + 機種名 + ステータス + (残り時間)
    full_text = soup.get_text(separator=" ")

    # パターン1: 数字番号の機器
    pattern = re.compile(
        r"(\d+)\s*"
        r"([SMLsml]サイズ(?:乾燥機|洗濯乾燥機|洗濯機)(?:\s*(?:上段|下段))?)\s*"
        r"(空き|使用中|\d+分)"
    )
    for m in pattern.finditer(full_text):
        num = m.group(1)
        mtype = m.group(2)
        status_raw = m.group(3)
        if status_raw == "空き":
            status = "空き"
            remaining = 0
        elif status_raw == "使用中":
            status = "使用中"
            remaining = 0
        else:  # "XX分" → 使用中
            status = "使用中"
            remaining = int(status_raw.replace("分", ""))
        machines.append({
            "number": num,
            "type": mtype,
            "status": status,
            "remaining_minutes": remaining,
        })

    # パターン2: スニーカー
    for name in ("スニーカーウォッシャー", "スニーカードライヤー"):
        match = re.search(rf"{name}\s*(空き|使用中|\d+分)", full_text)
        if match:
            status_raw = match.group(1)
            status = "空き" if status_raw == "空き" else "使用中"
            remaining = 0
            if "分" in status_raw:
                remaining = int(status_raw.replace("分", ""))
                status = "使用中"
            machines.append({
                "number": name[:2],
                "type": name,
                "status": status,
                "remaining_minutes": remaining,
            })

    return machines


def parse_bluesky(html: str) -> list[dict]:
    """ブルースカイランドリー トライアル伊勢崎中央店
    ページ構造: 番号 / 機種 / 容量 / ステータス(使用可能です。 or HH:MM)
    """
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(separator=" ")
    machines = []

    entries = re.findall(
        r"(\d+)\s+(乾燥機|洗濯乾燥機|敷きふとん乾燥機)\s*(\d+kg|[SML])?\s*(使用可能です。|[\d]{1,2}:[\d]{2})",
        text,
    )
    for num, mtype, capacity, status_or_time in entries:
        if "使用可能" in status_or_time:
            status = "空き"
            remaining = 0
        else:
            status = "使用中"
            # HH:MM は終了予定時刻 → 残り時間を計算
            try:
                parts = status_or_time.split(":")
                end_h, end_m = int(parts[0]), int(parts[1])
                now = datetime.now()
                end_today = now.replace(hour=end_h, minute=end_m, second=0, microsecond=0)
                diff = (end_today - now).total_seconds() / 60
                remaining = max(0, int(diff))
            except Exception:
                remaining = 0
        machines.append({
            "number": num,
            "type": f"{mtype} {capacity}".strip() if capacity else mtype,
            "status": status,
            "remaining_minutes": remaining,
        })

    return machines


def parse_fluffy(html: str) -> list[dict]:
    """fluffy 伊勢崎韮塚店
    ページ構造: XX号機(上段/下段) / 空or使用中 / 残りXX分 / 種別 / 容量
    実際のテキスト例:
      "01号機 空 スニーカーウォッシャー"
      "08号機(上段) 使用中 26分 2段式乾燥機 14Kg"
      "12号機 空 洗濯乾燥機 洗濯：27kg／洗濯乾燥：16kg"
    """
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(separator=" ")
    machines = []

    # 各「XX号機」を起点にして次の「XX号機」までを1レコードとして処理
    # まず全ての号機位置を特定
    machine_pattern = re.compile(r"(\d+号機(?:\((?:上段|下段)\))?)")
    positions = [(m.start(), m.group(1)) for m in machine_pattern.finditer(text)]

    for idx, (pos, num_raw) in enumerate(positions):
        # この号機から次の号機までのテキストを切り出し
        end_pos = positions[idx + 1][0] if idx + 1 < len(positions) else len(text)
        segment = text[pos + len(num_raw):end_pos].strip()

        number = num_raw.replace("号機", "")

        # ステータス
        status_match = re.search(r"(空|使用中)", segment)
        if not status_match:
            continue
        status = "空き" if status_match.group(1) == "空" else "使用中"

        # 残り時間
        remaining_match = re.search(r"(\d+)分", segment)
        mins = int(remaining_match.group(1)) if remaining_match else 0

        # 機種名
        type_match = re.search(
            r"(スニーカーウォッシャー|スニーカードライヤー|洗濯乾燥機|2段式乾燥機|乾燥機|洗濯機)",
            segment,
        )
        mtype = type_match.group(1) if type_match else "不明"

        # 容量
        cap_match = re.search(r"(\d+[Kk]g)", segment)
        cap = cap_match.group(1) if cap_match else ""

        machines.append({
            "number": number,
            "type": f"{mtype} {cap}".strip() if cap else mtype,
            "status": status,
            "remaining_minutes": mins,
        })

    return machines


def parse_wish(html: str) -> list[dict]:
    """コインランドリー Wish
    ページ構造: XX号機 / 空き or 使用中 / XX分 / 機種名
    """
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(separator=" ")
    machines = []

    entries = re.findall(
        r"(\d+)号機\s+(空き|使用中)\s+(\d+)\s*分\s+"
        r"(大型洗濯乾燥機|ふとん乾燥機|中型乾燥機(?:\s*\[(?:上段|下段)\])?)",
        text,
    )
    for num, status, remaining, mtype in entries:
        machines.append({
            "number": num,
            "type": mtype.strip(),
            "status": status,
            "remaining_minutes": int(remaining),
        })

    return machines


# ──────────────────────────────────────────────
# 店舗設定
# ──────────────────────────────────────────────

STORE_CONFIG = {
    2: {"url": "https://baluko.jp/baluko-isesakimiyakomachi/", "parser": parse_baluko},
    3: {"url": "http://edms.bsl-line.jp/shop/G0064", "parser": parse_bluesky},
    4: {"url": "https://www.coin-laundry.co.jp/userp/shop_detail/11001328", "parser": parse_fluffy},
    5: {"url": "https://laundry-wish.com/cgi-bin/kadou.php", "parser": parse_wish},
}


# ──────────────────────────────────────────────
# DB操作
# ──────────────────────────────────────────────

def get_or_create_machine(conn: sqlite3.Connection, store_id: int, number: str, mtype: str) -> int:
    c = conn.cursor()
    c.execute("SELECT machine_id FROM machines WHERE store_id=? AND machine_number=?", (store_id, number))
    row = c.fetchone()
    if row:
        # 機種名が変わっていたら更新
        c.execute("UPDATE machines SET machine_type=? WHERE machine_id=?", (mtype, row[0]))
        return row[0]
    c.execute(
        "INSERT INTO machines (store_id, machine_number, machine_type, capacity) VALUES (?,?,?,?)",
        (store_id, number, mtype, ""),
    )
    conn.commit()
    return c.lastrowid


def scrape_and_store() -> dict:
    conn = sqlite3.connect(DB_PATH)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    results = {}

    for store_id, config in STORE_CONFIG.items():
        try:
            html = fetch(config["url"])
            machines = config["parser"](html)

            for m in machines:
                mid = get_or_create_machine(conn, store_id, m["number"], m["type"])
                conn.execute(
                    "INSERT INTO availability_log (store_id, machine_id, recorded_at, status, remaining_minutes) "
                    "VALUES (?,?,?,?,?)",
                    (store_id, mid, now, m["status"], m["remaining_minutes"]),
                )

            conn.execute(
                "INSERT INTO scrape_log (store_id, scraped_at, success, machine_count) VALUES (?,?,1,?)",
                (store_id, now, len(machines)),
            )
            results[store_id] = {"success": True, "machines": len(machines)}

        except Exception as e:
            conn.execute(
                "INSERT INTO scrape_log (store_id, scraped_at, success, error_message) VALUES (?,?,0,?)",
                (store_id, now, str(e)),
            )
            results[store_id] = {"success": False, "error": str(e)}

    conn.commit()
    conn.close()
    return results


def compress_old_data() -> dict:
    """7日以上前の生データ→時間帯集計、90日以上前の時間帯データ→日次集計"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # 7日以上前 → hourly_summary
    c.execute("""
        INSERT OR REPLACE INTO hourly_summary (store_id, hour_start, total_machines, busy_machines_avg, availability_rate)
        SELECT
            store_id,
            strftime('%Y-%m-%d %H:00:00', recorded_at) AS hour_start,
            COUNT(DISTINCT machine_id),
            AVG(CASE WHEN status = '使用中' THEN 1.0 ELSE 0.0 END) * COUNT(DISTINCT machine_id),
            AVG(CASE WHEN status = '空き' THEN 1.0 ELSE 0.0 END)
        FROM availability_log
        WHERE recorded_at < datetime('now', 'localtime', '-7 days')
        GROUP BY store_id, strftime('%Y-%m-%d %H:00:00', recorded_at)
    """)

    c.execute("DELETE FROM availability_log WHERE recorded_at < datetime('now', 'localtime', '-7 days')")
    deleted_raw = c.rowcount

    # 90日以上前 → daily_summary
    c.execute("""
        INSERT OR REPLACE INTO daily_summary (store_id, date, total_machines, avg_availability_rate, min_availability_rate)
        SELECT
            store_id,
            strftime('%Y-%m-%d', hour_start),
            MAX(total_machines),
            AVG(availability_rate),
            MIN(availability_rate)
        FROM hourly_summary
        WHERE hour_start < datetime('now', 'localtime', '-90 days')
        GROUP BY store_id, strftime('%Y-%m-%d', hour_start)
    """)

    c.execute("DELETE FROM hourly_summary WHERE hour_start < datetime('now', 'localtime', '-90 days')")
    deleted_hourly = c.rowcount

    conn.commit()
    conn.close()
    return {"raw_deleted": deleted_raw, "hourly_deleted": deleted_hourly}


# ──────────────────────────────────────────────
# メイン
# ──────────────────────────────────────────────

if __name__ == "__main__":
    from setup_db import setup_database

    setup_database()

    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] Scraping started...")
    results = scrape_and_store()

    success_count = 0
    for sid, r in sorted(results.items()):
        if r["success"]:
            print(f"  Store {sid}: OK ({r['machines']} machines)")
            success_count += 1
        else:
            print(f"  Store {sid}: FAILED - {r['error']}")

    comp = compress_old_data()
    print(f"  Compression: raw={comp['raw_deleted']}, hourly={comp['hourly_deleted']}")

    if success_count == 0:
        print("ERROR: All stores failed.")
        sys.exit(1)

    print(f"Done. {success_count}/{len(results)} stores OK.")
