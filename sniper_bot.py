#!/usr/bin/env python3
"""
GMGN Multi-Filter Bot v2.0
Gabungin: Sniper (Trenches) + Trending Momentum + Smart Money Copy

A Solana meme coin sniper bot using GMGN OpenAPI CLI.
Scans Pump.fun new tokens and trending tokens, scores them, and auto-buys.

⚠️ SANITIZED VERSION — replace placeholders with your own config.
"""

import json, os, time, sys, subprocess, traceback
from datetime import datetime, timezone
from pathlib import Path
from logging.handlers import RotatingFileHandler
import logging

BASE_DIR = Path.home() / ".gmgn_sniper"
CONFIG_FILE = BASE_DIR / "config.json"
POSITIONS_FILE = BASE_DIR / "positions.json"
TRADE_LOG_FILE = BASE_DIR / "trade_log.json"
SOL_MINT = "So11111111111111111111111111111111111111112"

# ── LOGGER ────────────────────────────────────────────────────────────
LOG_FILE = BASE_DIR / "bot.log"
logger = logging.getLogger("gmgn_sniper")
logger.setLevel(logging.DEBUG)
fh = RotatingFileHandler(LOG_FILE, maxBytes=5*1024*1024, backupCount=3)
fh.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
logger.addHandler(fh)
sh = logging.StreamHandler(sys.stdout)
sh.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
logger.addHandler(sh)

# Read bot token from .env file
def _load_bot_token():
    """Load Telegram bot token from ~/.gmgn_sniper/.env or ~/.hermes/.env"""
    local_env = Path.home() / ".gmgn_sniper" / ".env"
    if local_env.exists():
        with open(local_env) as f:
            for line in f:
                line = line.strip()
                if line.startswith("TELEGRAM_BOT_TOKEN="):
                    return line.split("=", 1)[1]
    env_path = Path.home() / ".hermes" / ".env"
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line.startswith("TELEGRAM_BOT_TOKEN="):
                    return line.split("=", 1)[1]
    print("[WARN] TELEGRAM_BOT_TOKEN not found")
    return ""

BOT_TOKEN = _load_bot_token()

with open(CONFIG_FILE) as f:
    CFG = json.load(f)

CHAT_ID = CFG["telegram_chat_id"]
CHAIN = CFG["chain"]
WALLET = CFG["wallet_address"]
MAX_SOL = CFG["max_sol_per_trade"]
MAX_POS = CFG["max_positions"]
SLIPPAGE = CFG["slippage"]
PRIO_FEE = CFG["priority_fee"]
TIP_FEE = CFG["tip_fee"]
ANTI_MEV = CFG["anti_mev"]
LOOP_INT = CFG["loop_interval_seconds"]
STRATS = CFG["strategies"]
FILTER = CFG["filters"]
TP_SL = CFG["tp_sl"]

# ── HELPERS ──────────────────────────────────────────────────────────────────

def now_ts():
    return int(time.time())

def now_str():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

def load_json(path, default):
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return default

def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

def rg(cmd, timeout=15):
    """Run gmgn-cli command and parse JSON output."""
    full = ["gmgn-cli"] + cmd + ["--raw"]
    env = os.environ.copy()
    env.pop("NODE_CHANNEL_FD", None)  # Fixes PM2 SIGABRT crash
    r = subprocess.run(full, capture_output=True, text=True, timeout=timeout, env=env)
    if r.returncode != 0:
        return None, r.stderr[:200]
    try:
        return json.loads(r.stdout), None
    except:
        return None, r.stdout[:200]

def tg(text, pm="HTML"):
    """Send Telegram notification."""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        subprocess.run(["curl", "-s", "-X", "POST", url,
            "-d", f"chat_id={CHAT_ID}", "-d", f"parse_mode={pm}",
            "-d", f"text={text}"], capture_output=True, timeout=5)
    except:
        pass

def cond_orders():
    """Build condition orders JSON for TP/SL."""
    o = []
    for k in ["tp1","tp2","sl"]:
        c = TP_SL[k]
        entry = {"order_type":c["order_type"],"side":"sell",
                   "price_scale":c["price_scale"],"sell_ratio":c["sell_ratio"]}
        if "drawdown_rate" in c:
            entry["drawdown_rate"] = c["drawdown_rate"]
        o.append(entry)
    return json.dumps(o)

def buy_token(addr, symbol):
    amt = str(int(MAX_SOL * 1_000_000_000))
    cmd = ["swap","--chain",CHAIN,"--from",WALLET,
           "--input-token",SOL_MINT,"--output-token",addr,
           "--amount",amt,"--slippage",str(SLIPPAGE),
           "--priority-fee",str(PRIO_FEE),"--tip-fee",str(TIP_FEE),
           "--condition-orders",cond_orders(),"--raw"]
    if ANTI_MEV: cmd.append("--anti-mev")
    d, e = rg(cmd, 30)
    if e: return None, e
    tx = (d or {}).get("tx_hash") or (d or {}).get("order_id","")
    return tx, None

def check_portfolio():
    """Check wallet SOL balance and token holdings."""
    d, e = rg(["portfolio","holdings","--chain",CHAIN,"--wallet",WALLET])
    if e or not d: return None, e
    h = {"tokens":[], "sol":0}
    items = d if isinstance(d,list) else (d.get("holdings") or [d])
    for x in items if isinstance(items,list) else []:
        if not isinstance(x,dict): continue
        mint = x.get("mint") or x.get("address") or x.get("token_address","")
        sym = x.get("symbol","?")
        bal = float(x.get("balance",0))
        if mint == SOL_MINT or sym=="SOL": h["sol"] += bal
        else: h["tokens"].append({"address":mint,"symbol":sym,"balance":bal})
    # Fallback: use Solana RPC if GMGN returns 0 SOL
    if h["sol"] == 0:
        try:
            import urllib.request, json as j
            payload = j.dumps({"jsonrpc":"2.0","id":1,"method":"getBalance","params":[WALLET]})
            req = urllib.request.Request('https://api.mainnet-beta.solana.com', data=payload.encode(), headers={'Content-Type':'application/json'})
            resp = j.loads(urllib.request.urlopen(req, timeout=10).read())
            bal = resp.get('result',{}).get('value',0) / 1e9
            h["sol"] = bal
        except:
            pass
    return h, None


# ── WATCHDOG ────────────────────────────────────────────────────────────────

WATCHDOG = CFG.get("watchdog", {
    "enabled": True,
    "sl_price_scale": 78,
    "time_stop_minutes": 12,
})

def get_token_price(addr):
    """Harga SOL token saat ini via GMGN token info API."""
    d, e = rg(["token", "info", "--chain", CHAIN, "--address", addr])
    if e or not d:
        return None
    try:
        price_obj = d.get("price", {})
        price = float(price_obj.get("price", 0))
        return price if price > 0 else None
    except (TypeError, ValueError):
        return None

def sell_token(addr, symbol):
    """Force market-sell seluruh balance token ke SOL via --percent 100."""
    cmd = ["swap","--chain",CHAIN,"--from",WALLET,
           "--input-token",addr,"--output-token",SOL_MINT,
           "--percent","100",
           "--slippage", str(max(SLIPPAGE, 8)),
           "--priority-fee", str(PRIO_FEE), "--tip-fee", str(TIP_FEE)]
    if ANTI_MEV: cmd.append("--anti-mev")
    d, e = rg(cmd, 30)
    if e: return None, e
    return (d or {}).get("tx_hash",""), None


# ── SCORING ──────────────────────────────────────────────────────────────────

def score_token(t, source="sniper"):
    s = 30  # Base score
    rug = t.get("rug_ratio",0.5)
    if isinstance(rug,(int,float)):
        if rug<0.05: s+=20
        elif rug<0.1: s+=10
        elif rug<0.15: s+=5
        elif rug<0.25: s+=0
        else: s-=30

    sm = t.get("smart_degen_count",0)
    if isinstance(sm,(int,float)):
        if sm>=5: s+=15
        elif sm>=3: s+=8
        elif sm>=1: s+=3

    br = t.get("bundler_rate",0.5)
    if isinstance(br,(int,float)):
        if br<0.1: s+=10
        elif br<0.2: s+=5
        elif br>0.50: s-=30
        elif br>0.30: s-=15

    sn = t.get("sniper_count",0)
    if isinstance(sn,(int,float)):
        if 5<=sn<=30: s+=5
        elif sn>50: s-=15

    hc = t.get("holder_count",0)
    if isinstance(hc,(int,float)):
        if hc>500: s+=15
        elif hc>200: s+=10
        elif hc>100: s+=5
        elif hc>50: s+=2
        elif hc<10: s-=10

    mc = t.get("market_cap",0)
    if isinstance(mc,(int,float)):
        if mc>50000: s+=10
        elif mc>20000: s+=5

    # Source-specific bonuses
    if source=="trending":
        pct = t.get("price_change_percent5m",0)
        vol = t.get("volume",0)
        if isinstance(pct,(int,float)) and pct>20: s+=10
        elif isinstance(pct,(int,float)) and pct>10: s+=5
        if isinstance(vol,(int,float)) and vol>50000: s+=5
    elif source=="smart_money":
        s+=5

    # Safety checks
    if t.get("renounced_mint")==1: s+=5
    if t.get("renounced_freeze_account")==1: s+=5
    cs = t.get("creator_token_status","")
    if cs=="creator_close": s+=5
    if cs=="creator_hold": s-=10

    return max(0,min(100,s))

# ── SOURCES ──────────────────────────────────────────────────────────────────

def fetch_sniper():
    """Fetch newly created tokens from Pump.fun trenches."""
    if not STRATS["sniper"]["enabled"]: return []
    age = STRATS["sniper"]["max_age_minutes"]
    pf = STRATS["sniper"]["platforms"][0]
    d, e = rg(["market","trenches","--chain",CHAIN,"--type","new_creation",
                "--limit","50","--launchpad-platform",pf,
                f"--max-created",f"{age}m"])
    if e or not d: return []
    tokens = []
    for cat in ["new_creation"]:
        items = d.get(cat,[])
        if isinstance(items,list): tokens.extend(items)
    return [t for t in tokens if t.get("address")]

def fetch_trending():
    """Fetch trending tokens sorted by momentum."""
    if not STRATS["trending"]["enabled"]: return []
    iv = STRATS["trending"]["interval"]
    lim = STRATS["trending"]["limit"]
    d, e = rg(["market","trending","--chain",CHAIN,"--interval",iv,
                "--limit",str(lim)])
    if e or not d: return []
    tokens = d.get("data",{}).get("rank",[]) if isinstance(d,dict) else []
    min_pct = STRATS["trending"]["min_price_change_5m"]
    min_vol = STRATS["trending"]["min_volume"]
    out = []
    for t in tokens:
        pct = t.get("price_change_percent5m",0)
        vol = t.get("volume",0)
        if isinstance(pct,(int,float)) and pct<min_pct: continue
        if isinstance(vol,(int,float)) and vol<min_vol: continue
        out.append(t)
    return out

def fetch_smart_money():
    """Fetch tokens with high smart money / KOL activity."""
    if not STRATS["smart_money"]["enabled"]: return []
    lim = STRATS["smart_money"]["limit"]
    min_sm = STRATS["smart_money"]["min_smart_degen"]
    d, e = rg(["market","trending","--chain",CHAIN,"--interval","5m",
                "--limit","50"])
    if e or not d: return []
    tokens = d.get("data",{}).get("rank",[]) if isinstance(d,dict) else []
    out = []
    for t in tokens:
        sm = t.get("smart_degen_count",0)
        if isinstance(sm,(int,float)) and sm>=min_sm:
            out.append(t)
    out.sort(key=lambda x: x.get("smart_degen_count",0), reverse=True)
    return out[:lim]

# ── SCREEN ───────────────────────────────────────────────────────────────────

def apply_filters(tokens):
    """Apply rug/dev/holder/market-cap filters."""
    out = []
    for t in tokens:
        addr = t.get("address","")
        if not addr: continue
        rug = t.get("rug_ratio",1)
        if isinstance(rug,(int,float)) and rug>FILTER["max_rug_ratio"]: continue
        mc = t.get("market_cap",0)
        if isinstance(mc,(int,float)) and mc<FILTER.get("min_market_cap",0): continue
        if isinstance(mc,(int,float)) and mc>FILTER.get("max_market_cap",1e12): continue
        hc = t.get("holder_count",0)
        if isinstance(hc,(int,float)) and hc<FILTER["min_holders"]: continue
        dh = t.get("dev_team_hold_rate",0)
        if isinstance(dh,(int,float)) and dh>FILTER.get("max_dev_hold_rate",1): continue
        out.append(t)
    return out

def multi_scan():
    """Scan all sources, merge, dedup, score, return sorted candidates."""
    all_tokens = {}

    for t in fetch_sniper():
        addr = t.get("address","")
        if addr: all_tokens[addr] = (t, "sniper")

    for t in fetch_trending():
        addr = t.get("address","")
        if addr:
            if addr not in all_tokens:
                all_tokens[addr] = (t, "trending")

    for t in fetch_smart_money():
        addr = t.get("address","")
        if addr:
            if addr not in all_tokens:
                all_tokens[addr] = (t, "smart_money")

    candidates = []
    for addr, (t, src) in all_tokens.items():
        filtered = apply_filters([t])
        if not filtered: continue
        t2 = filtered[0]
        score = score_token(t2, src)
        if score < 50: continue
        candidates.append({
            "address": addr,
            "symbol": t2.get("symbol","?"),
            "name": t2.get("name","?"),
            "market_cap": t2.get("market_cap",0),
            "liquidity": t2.get("liquidity",0),
            "rug_ratio": t2.get("rug_ratio",0),
            "smart_degen_count": t2.get("smart_degen_count",0),
            "bundler_rate": t2.get("bundler_rate",0),
            "holder_count": t2.get("holder_count",0),
            "sniper_count": t2.get("sniper_count",0),
            "volume": t2.get("volume",0),
            "score": score,
            "source": src,
            "price_change_5m": t2.get("price_change_percent5m",0),
            "price": t2.get("price", 0),
            "token_created_ts": t2.get("open_timestamp") or t2.get("creation_timestamp") or 0,
            "timestamp": now_ts()
        })

    candidates.sort(key=lambda x: x["score"], reverse=True)
    return candidates

# ── POSITION MONITOR ────────────────────────────────────────────────────────

def evaluate_positions():
    """Check positions: watchdog TIME-stop/SL, then reconcile closed positions with PnL."""
    pd = load_json(POSITIONS_FILE, {"open":[],"closed":[]})
    op = pd["open"]
    tlog = load_json(TRADE_LOG_FILE, {"trades":[]})

    h, e = check_portfolio()
    if e: return 0

    held = {t["address"] for t in h["tokens"]} if h else set()
    still = []
    now = now_ts()
    GRACE_SEC = 300
    closing = []

    for pos in op:
        ta = pos["token_address"]
        opened = pos.get("timestamp") or now
        age_sec = now - opened
        age_min = age_sec / 60

        # ── WATCHDOG: TIME-stop & SL enforcement ──
        watchdog_triggered = False
        if WATCHDOG.get("enabled") and ta in held:
            entry_price = pos.get("entry_price_sol") or 0

            # TIME-stop: hold > 12 minutes
            if age_min >= WATCHDOG["time_stop_minutes"]:
                bal = next((t["balance"] for t in h["tokens"] if t["address"] == ta), 0)
                if bal > 0:
                    tx, err = sell_token(ta, pos.get("symbol","?"))
                    if tx:
                        logger.info(f"TIME_STOP — force sell {pos.get('symbol','?')} age={age_min:.1f}m")
                        tg(f"⏱ <b>TIME_STOP</b> {pos.get('symbol','?')} — hold {age_min:.0f}m, force sold", "HTML")
                        pos["close_type"] = "time_stop"
                        watchdog_triggered = True
                    else:
                        logger.error(f"TIME_STOP SELL FAILED {pos.get('symbol','?')}: {err}")

            # SL watchdog: harga turun di bawah threshold
            if not watchdog_triggered and entry_price > 0:
                cur = get_token_price(ta)
                if cur and cur <= entry_price * WATCHDOG["sl_price_scale"] / 100:
                    bal = next((t["balance"] for t in h["tokens"] if t["address"] == ta), 0)
                    if bal > 0:
                        tx, err = sell_token(ta, pos.get("symbol","?"))
                        if tx:
                            drop_pct = (1 - cur / entry_price) * 100
                            logger.info(f"SL_WATCHDOG — force sell {pos.get('symbol','?')} drop={drop_pct:.1f}%")
                            tg(f"🛑 <b>SL_WATCHDOG</b> {pos.get('symbol','?')} — dropped {drop_pct:.0f}%, force sold", "HTML")
                            pos["close_type"] = "sl_watchdog"
                            watchdog_triggered = True
                        else:
                            logger.error(f"SL_WATCHDOG SELL FAILED {pos.get('symbol','?')}: {err}")

        if watchdog_triggered:
            # Don't add to still; next loop will reconcile
            pass
        elif ta in held:
            still.append(pos)
        elif now - pos.get("timestamp", 0) < GRACE_SEC:
            still.append(pos)
        else:
            closing.append(pos)

    if closing:
        sol_now = h["sol"] if h else 0
        total_sol_at_open = sum(p.get("sol_at_open", 0) for p in closing)
        sol_diff = sol_now - total_sol_at_open
        for p in still:
            sol_diff -= p.get("amount_sol", 0.05)
        per_trade_pnl = sol_diff / len(closing) if closing else 0
        is_profit = per_trade_pnl > 0

        for pos in closing:
            logger.info(f"GMGN TRIGGER — {pos.get('symbol','?')} (TP/SL executed by system | PnL: {per_trade_pnl:+.4f} SOL)")
            pd["closed"].append({**pos, "close_type": pos.get("close_type", "gmgn_trigger"), "close_ts": now,
                                 "pnl_sol": round(per_trade_pnl, 6), "is_win": is_profit})
            tlog["trades"].append({
                "token_address": pos["token_address"], "symbol": pos.get("symbol","?"),
                "entry_sol": pos.get("amount_sol", 0),
                "pnl_sol": round(per_trade_pnl, 6),
                "is_win": is_profit,
                "close_type": pos.get("close_type", "gmgn_trigger"),
                "close_reason": pos.get("close_type", "gmgn_trigger"),
                "source": pos.get("source","?"),
                "score_at_buy": pos.get("score", 0),
                "rug_ratio": pos.get("rug_ratio", 0),
                "token_age_min_at_buy": pos.get("token_age_min_at_buy"),
                "liquidity_usd": pos.get("liquidity_usd"),
                "hold_seconds": now - pos.get("timestamp", now),
                "timestamp_open": pos.get("timestamp", 0), "timestamp_close": now
            })

    while len(tlog["trades"])>200: tlog["trades"].pop(0)
    pd["open"] = still
    save_json(POSITIONS_FILE, pd)
    save_json(TRADE_LOG_FILE, tlog)
    return len(closing)

# ── MAIN ────────────────────────────────────────────────────────────────────

def main():
    last_pc = 0
    PC_INT = 60

    s = "sources:"
    if STRATS["sniper"]["enabled"]: s+=" 🔫Sniper"
    if STRATS["trending"]["enabled"]: s+=" 📈Trending"
    if STRATS["smart_money"]["enabled"]: s+=" 🐳SM"
    start = (
        f"🚀 <b>GMGN Multi-Filter — START</b>\n"
        f"Wallet: <code>{WALLET}</code>\n"
        f"{s}\n"
        f"Max/trade: {MAX_SOL} SOL | Max pos: {MAX_POS}\n"
        f"Filter: rug<{FILTER['max_rug_ratio']} dev<{FILTER.get('max_dev_hold_rate',1)} hold>={FILTER['min_holders']}\n"
        f"MC: ${FILTER.get('min_market_cap',0)}-${FILTER.get('max_market_cap','∞')}"
    )
    tg(start, "HTML")
    logger.info("BOT STARTED — GMGN Multi-Filter Sniper")
    logger.info(f"Source: {s} | Max pos: {MAX_POS} | Filter: rug<{FILTER['max_rug_ratio']} dev<{FILTER.get('max_dev_hold_rate',1)} hold>={FILTER['min_holders']} mc={FILTER.get('min_market_cap')}-{FILTER.get('max_market_cap','∞')}")
    sys.stdout.flush()

    bought = set()

    while True:
        ls = time.time()
        try:
            now = now_ts()
            logger.debug(f"LOOP — scan candidates...")
            sys.stdout.flush()

            cands = multi_scan()
            if cands:
                logger.info(f"SCAN {len(cands)} candidates — TOP: {cands[0]['symbol']} ({cands[0]['source']}) score={cands[0]['score']}")
                print(f"[SCAN] {len(cands)} candidates — top: {cands[0]['symbol']} ({cands[0]['source']}) score={cands[0]['score']}")
                sys.stdout.flush()
            else:
                logger.info(f"SCAN 0 candidates")
                sys.stdout.flush()

            if cands:
                pd = load_json(POSITIONS_FILE, {"open":[],"closed":[]})
                already = {p["token_address"] for p in pd["open"]}

                for c in cands:
                    if len(pd["open"]) >= MAX_POS: break
                    if c["address"] in already: continue
                    if c["address"] in bought: continue

                    h, _ = check_portfolio()
                    sb = h["sol"] if h else 0
                    if sb < MAX_SOL + 0.01:
                        tg("⚠️ <b>Saldo GMGN tidak cukup!</b> Bot dihentikan.", "HTML")
                        sys.exit(0)

                    tx, err = buy_token(c["address"], c["symbol"])
                    if tx:
                        bought.add(c["address"])
                        logger.info(f"BUY {c['symbol']} — {MAX_SOL} SOL @ score {c['score']} ({c['source']})")
                        sys.stdout.flush()

                        pd["open"].append({
                            "token_address":c["address"],"symbol":c["symbol"],
                            "name":c["name"],"amount_sol":MAX_SOL,
                            "entry_price":c.get("market_cap",0),
                            "entry_price_sol":c.get("price", 0),
                            "score":c["score"],"source":c["source"],
                            "rug_ratio":c["rug_ratio"],
                            "smart_degen":c["smart_degen_count"],
                            "bundler_rate":c["bundler_rate"],
                            "holder_count":c["holder_count"],
                            "timestamp":now,
                            "sol_at_open": sb,
                            "token_age_min_at_buy": round((now - c.get("token_created_ts", now)) / 60, 1) if c.get("token_created_ts") else None,
                            "liquidity_usd": c.get("liquidity", 0)
                        })
                        save_json(POSITIONS_FILE, pd)

                        pct = c.get("price_change_5m",0)
                        pct_s = f" | 📈 {pct:+.1f}% 5m" if isinstance(pct,(int,float)) and pct!=0 else ""
                        tg(
                            f"🟢 <b>BUY {c['symbol']}</b> ({c['source']})\n"
                            f"💰 {MAX_SOL} SOL | Score: {c['score']}\n"
                            f"📊 MC: ${c['market_cap']:,.0f} | Liq: ${c['liquidity']:,.0f}{pct_s}\n"
                            f"🛡️ Rug: {c['rug_ratio']} | SM: {c['smart_degen_count']} | Bundler: {c['bundler_rate']:.1%}\n"
                            f"👥 Holders: {c['holder_count']}\n"
                            f"🔗 <code>{c['address'][:20]}...{c['address'][-4:]}</code>",
                            "HTML"
                        )
                        time.sleep(1)
                    else:
                        logger.error(f"BUY FAILED {c['symbol']}: {err[:150]}")
                        tg(f"⚠️ <b>BUY FAILED</b> {c['symbol']}: {err[:200]}", "HTML")

            if now - last_pc >= PC_INT:
                closed = evaluate_positions()
                last_pc = now
                oc = len(load_json(POSITIONS_FILE, {"open":[]})["open"])
                logger.info(f"MONITOR — Closed:{closed} Open:{oc}")
                sys.stdout.flush()

        except Exception as e:
            tg(f"⚠️ <b>Bot Error:</b> {str(e)[:200]}", "HTML")
            traceback.print_exc()
            sys.stdout.flush()

        time.sleep(max(1, LOOP_INT - (time.time()-ls)))

if __name__=="__main__":
    print("🚀 GMGN Multi-Filter Bot v2.0 starting...")
    sys.stdout.flush()
    main()