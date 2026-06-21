#!/usr/bin/env python3
"""
GoldSignal alert -> ntfy.sh
อ่านราคาทองคำล่วงหน้า (GC=F จาก Yahoo Finance) คำนวณ RSI/EMA/MACD สร้างสัญญาณ ซื้อ/ขาย/รอ
แล้วส่งแจ้งเตือนเข้ามือถือผ่าน ntfy.sh "เฉพาะตอนสัญญาณเปลี่ยน" (ไม่สแปม)

ใช้ Yahoo Finance เพราะรันได้จากเซิร์ฟเวอร์ GitHub (สหรัฐ) ซึ่ง Binance มักโดนบล็อก (451)

ตั้งค่าผ่าน environment variables:
  NTFY_TOPIC    (จำเป็น)  ชื่อ topic ของคุณ เช่น gold-9f3k2x-jareeya
  NTFY_SERVER   (ไม่บังคับ) ค่าเริ่มต้น https://ntfy.sh
  TIMEFRAME     (ไม่บังคับ) ค่าเริ่มต้น 1h  เช่น 15m / 1h / 1d
  STATE_FILE    (ไม่บังคับ) ค่าเริ่มต้น last_signal.json
"""
import os, sys, json, urllib.request

# GC=F = ทองคำล่วงหน้า COMEX (ราคา/ออนซ์ ใกล้เคียงราคาทองจริง)
# map ไทม์เฟรม -> (interval, range) ที่ Yahoo รองรับ
YF = {"15m": ("15m", "5d"), "1h": ("60m", "1mo"), "4h": ("60m", "1mo"), "1d": ("1d", "6mo")}
TIMEFRAME   = os.environ.get("TIMEFRAME", "1h")
STATE_FILE  = os.environ.get("STATE_FILE", "last_signal.json")
NTFY_TOPIC  = os.environ.get("NTFY_TOPIC")
NTFY_SERVER = os.environ.get("NTFY_SERVER", "https://ntfy.sh").rstrip("/")

# ---------- indicators ----------
def ema(values, period):
    k = 2 / (period + 1)
    prev = values[0]
    out = [prev]
    for v in values[1:]:
        prev = v * k + prev * (1 - k)
        out.append(prev)
    return out

def rsi(closes, period=14):
    if len(closes) < period + 1:
        return None
    gain = loss = 0.0
    for i in range(1, period + 1):
        d = closes[i] - closes[i - 1]
        if d >= 0: gain += d
        else: loss -= d
    ag, al = gain / period, loss / period
    for i in range(period + 1, len(closes)):
        d = closes[i] - closes[i - 1]
        ag = (ag * (period - 1) + (d if d > 0 else 0)) / period
        al = (al * (period - 1) + (-d if d < 0 else 0)) / period
    if al == 0:
        return 100.0
    return 100 - 100 / (1 + ag / al)

def macd(closes):
    e12, e26 = ema(closes, 12), ema(closes, 26)
    line = [a - b for a, b in zip(e12, e26)]
    sig = ema(line, 9)
    hist = [l - s for l, s in zip(line, sig)]
    return line, sig, hist

# ---------- signal engine ----------
def build_signal(closes):
    last = closes[-1]
    r = rsi(closes, 14)
    ef_arr, es_arr = ema(closes, 9), ema(closes, 21)
    ef, es = ef_arr[-1], es_arr[-1]
    efp, esp = ef_arr[-2], es_arr[-2]
    _, _, hist = macd(closes)
    h, hp = hist[-1], hist[-2]

    score = 0
    reasons = []
    if r < 30:   score += 25; reasons.append(f"RSI {r:.0f} — ขายมากเกินไป (โซนน่าซื้อ)")
    elif r > 70: score -= 25; reasons.append(f"RSI {r:.0f} — ซื้อมากเกินไป (โซนน่าขาย)")
    elif r < 45: score += 10; reasons.append(f"RSI {r:.0f} — เอนไปทางอ่อนตัว")
    elif r > 55: score -= 10; reasons.append(f"RSI {r:.0f} — เอนไปทางแข็งแกร่ง")
    else:        reasons.append(f"RSI {r:.0f} — เป็นกลาง")

    if efp <= esp and ef > es:   score += 30; reasons.append("EMA9 ตัดขึ้นเหนือ EMA21 — สัญญาณขาขึ้นใหม่")
    elif efp >= esp and ef < es: score -= 30; reasons.append("EMA9 ตัดลงใต้ EMA21 — สัญญาณขาลงใหม่")
    elif ef > es:                score += 15; reasons.append("EMA9 > EMA21 — แนวโน้มขาขึ้น")
    else:                        score -= 15; reasons.append("EMA9 < EMA21 — แนวโน้มขาลง")

    if h > 0 and h > hp:   score += 15; reasons.append("MACD โมเมนตัมบวกและเพิ่มขึ้น")
    elif h > 0:            score += 5;  reasons.append("MACD ยังบวกแต่ชะลอ")
    elif h < 0 and h < hp: score -= 15; reasons.append("MACD โมเมนตัมลบและเพิ่มขึ้น")
    else:                  score -= 5;  reasons.append("MACD ยังลบแต่ชะลอ")

    conf = min(100, abs(score) / 85 * 100)
    if score >= 35:    label, tag, title, prio = "ซื้อ (BUY)",  "green_circle",  "Gold: BUY",  "high"
    elif score <= -35: label, tag, title, prio = "ขาย (SELL)",  "red_circle",    "Gold: SELL", "high"
    else:              label, tag, title, prio, conf = "รอ (WAIT)", "yellow_circle", "Gold: WAIT", "default", max(15, conf)

    return {"last": last, "rsi": r, "label": label, "tag": tag, "title": title,
            "prio": prio, "score": score, "conf": round(conf), "reasons": reasons}

# ---------- IO ----------
def fetch_closes(tf):
    interval, rng = YF.get(tf, ("60m", "1mo"))
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/GC=F"
           f"?interval={interval}&range={rng}")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (gold-alert)"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode())
    result = data["chart"]["result"][0]
    closes = result["indicators"]["quote"][0]["close"]
    closes = [float(c) for c in closes if c is not None]
    if len(closes) < 30:
        raise RuntimeError(f"ข้อมูลราคาน้อยเกินไป ({len(closes)} แท่ง)")
    return closes[:-1]  # ตัดแท่งล่าสุดที่ยังไม่ปิด เพื่อให้สัญญาณนิ่ง

def load_state():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except Exception:
        return {}

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def send_ntfy(sig):
    reasons = "\n".join(f"• {x}" for x in sig["reasons"])
    body = (
        f"{sig['label']}  ·  ความเชื่อมั่น {sig['conf']}/100\n"
        f"ไทม์เฟรม {TIMEFRAME}  ·  ราคา ≈ ${sig['last']:,.2f}/oz\n\n"
        f"{reasons}\n\n"
        f"เครื่องมือช่วยวิเคราะห์ ไม่ใช่คำแนะนำลงทุน · ตั้ง Stop-Loss เสมอ"
    ).encode("utf-8")
    url = f"{NTFY_SERVER}/{NTFY_TOPIC}"
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Title", sig["title"])       # ASCII เท่านั้น
    req.add_header("Priority", sig["prio"])
    req.add_header("Tags", sig["tag"])
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.status in (200, 201)

def main():
    if not NTFY_TOPIC:
        print("ERROR: ยังไม่ได้ตั้งค่า NTFY_TOPIC (ไปใส่ใน repo Settings > Secrets)", file=sys.stderr)
        sys.exit(1)

    closes = fetch_closes(TIMEFRAME)
    sig = build_signal(closes)
    state = load_state()
    prev_label = state.get("label")

    print(f"signal={sig['label']} score={sig['score']} price={sig['last']:.2f} prev={prev_label}")

    # แจ้งเฉพาะตอนมี "จุดเข้า" จริง (BUY/SELL) และเป็นสัญญาณใหม่เท่านั้น
    # ถ้าเป็น WAIT จะเงียบสนิท ไม่รบกวน
    is_entry = sig["label"] in ("ซื้อ (BUY)", "ขาย (SELL)")
    if is_entry and sig["label"] != prev_label:
        ok = send_ntfy(sig)
        print("ntfy sent:", ok)
    elif not is_entry:
        print("สัญญาณเป็น WAIT — เงียบไว้ ไม่แจ้งจนกว่าจะมีจุดเข้า")
    else:
        print("ยังเป็นสัญญาณเดิม — ไม่แจ้งซ้ำ")

    save_state({"label": sig["label"], "score": sig["score"],
                "price": sig["last"], "timeframe": TIMEFRAME})

if __name__ == "__main__":
    main()
