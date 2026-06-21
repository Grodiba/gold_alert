#!/usr/bin/env python3
"""
Backtest — ทดสอบว่ากลยุทธ์สัญญาณ "ในอดีต" แม่นแค่ไหน
จำลองการเทรดตามสัญญาณ BUY/SELL บนข้อมูลทองคำย้อนหลัง (GC=F) แล้วสรุปสถิติ:
อัตราชนะ, จำนวนเทรด, ผลตอบแทนรวม, ฯลฯ

โมเดล: stop-and-reverse — BUY = ถือ long, SELL = สลับเป็น short, WAIT = ถือตำแหน่งเดิม
เข้า/ออกที่ราคาปิดของแท่ง ณ จุดที่สัญญาณเปลี่ยน

⚠️ เป็นการจำลองในอุดมคติ: ยังไม่หักค่าสเปรด/ค่าธรรมเนียม/สลิปเพจ ผลจริงจะแย่กว่านี้

env:
  BT_INTERVAL  (ไม่บังคับ) ค่าเริ่มต้น 60m  เช่น 60m / 1d / 15m
  BT_RANGE     (ไม่บังคับ) ค่าเริ่มต้น 2y   เช่น 2y / 1y / 60d
  NTFY_TOPIC   (ไม่บังคับ) ถ้าตั้งไว้จะส่งสรุปเข้า ntfy ด้วย
"""
import os, json, urllib.request
from gold_alert import build_signal, BUY, SELL

BT_INTERVAL = os.environ.get("BT_INTERVAL", "60m")
BT_RANGE    = os.environ.get("BT_RANGE", "2y")
NTFY_TOPIC  = os.environ.get("NTFY_TOPIC")
NTFY_SERVER = os.environ.get("NTFY_SERVER", "https://ntfy.sh").rstrip("/")

def fetch(interval, rng):
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/GC=F"
           f"?interval={interval}&range={rng}")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (gold-backtest)"})
    with urllib.request.urlopen(req, timeout=40) as resp:
        data = json.loads(resp.read().decode())
    q = data["chart"]["result"][0]["indicators"]["quote"][0]["close"]
    return [float(c) for c in q if c is not None]

def simulate(closes, warmup=40):
    """คืนค่า list ของผลตอบแทนแต่ละเทรด (สัดส่วน เช่น 0.012 = +1.2%)"""
    pos = 0        # 1=long, -1=short, 0=flat
    entry = 0.0
    trades = []
    for i in range(warmup, len(closes)):
        label = build_signal(closes[:i + 1])["label"]
        price = closes[i]
        if label == BUY and pos <= 0:
            if pos == -1:
                trades.append((entry - price) / entry)   # ปิด short
            pos, entry = 1, price                        # เปิด long
        elif label == SELL and pos >= 0:
            if pos == 1:
                trades.append((price - entry) / entry)   # ปิด long
            pos, entry = -1, price                       # เปิด short
        # WAIT = ถือเดิม
    return trades

def stats(trades):
    n = len(trades)
    if n == 0:
        return None
    wins = [t for t in trades if t > 0]
    losses = [t for t in trades if t <= 0]
    win_rate = len(wins) / n * 100
    equity = 1.0
    for t in trades:
        equity *= (1 + t)
    total_ret = (equity - 1) * 100
    avg_win = (sum(wins) / len(wins) * 100) if wins else 0.0
    avg_loss = (sum(losses) / len(losses) * 100) if losses else 0.0
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    pf = (gross_win / gross_loss) if gross_loss > 0 else float("inf")
    best = max(trades) * 100
    worst = min(trades) * 100
    return {"n": n, "win_rate": win_rate, "total_ret": total_ret,
            "avg_win": avg_win, "avg_loss": avg_loss, "pf": pf,
            "best": best, "worst": worst}

def post_ntfy(title, body):
    if not NTFY_TOPIC:
        return
    req = urllib.request.Request(f"{NTFY_SERVER}/{NTFY_TOPIC}",
                                 data=body.encode("utf-8"), method="POST")
    req.add_header("Title", title)
    req.add_header("Tags", "bar_chart")
    req.add_header("Priority", "low")
    urllib.request.urlopen(req, timeout=30)

def main():
    closes = fetch(BT_INTERVAL, BT_RANGE)
    if len(closes) < 60:
        print(f"ข้อมูลน้อยเกินไป ({len(closes)} แท่ง) — ลองเปลี่ยน BT_RANGE")
        return
    s = stats(simulate(closes))
    if not s:
        print("ไม่มีเทรดเกิดขึ้นในช่วงนี้")
        return

    pf = "∞" if s["pf"] == float("inf") else f"{s['pf']:.2f}"
    report = (
        f"ผลทดสอบย้อนหลัง (GC=F · {BT_INTERVAL} · {BT_RANGE} · {len(closes)} แท่ง)\n"
        f"จำนวนเทรด: {s['n']}\n"
        f"อัตราชนะ: {s['win_rate']:.1f}%\n"
        f"ผลตอบแทนรวม (ทบต้น): {s['total_ret']:+.1f}%\n"
        f"กำไรเฉลี่ย/ไม้: {s['avg_win']:+.2f}%  |  ขาดทุนเฉลี่ย/ไม้: {s['avg_loss']:+.2f}%\n"
        f"Profit Factor: {pf}\n"
        f"ไม้ดีสุด: {s['best']:+.1f}%  |  แย่สุด: {s['worst']:+.1f}%\n"
        f"\n⚠️ จำลองในอุดมคติ ไม่หักค่าสเปรด/ค่าธรรมเนียม ผลจริงจะแย่กว่านี้"
    )
    print(report)
    post_ntfy("Gold: ผลทดสอบย้อนหลัง", report)

if __name__ == "__main__":
    main()
