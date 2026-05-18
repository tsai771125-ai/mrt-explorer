"""
台北捷運探索 2026 — FastAPI 後端
- GET /               → 前端 HTML
- GET /api/station/{id}   → 站點 AI 資料（含照片）
- POST /api/station/{id}/refresh → 強制重抓 Gemini 資料
- GET /api/batch-status  → 查看快取狀態
"""
import os, json, asyncio, logging
from pathlib import Path
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="MRT Explorer API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

DATA_DIR = Path("stations_data")
DATA_DIR.mkdir(exist_ok=True)

# ── 站點名稱對照表 ──────────────────────────────
STATION_NAMES = {
    "R28":"淡水","R27":"紅樹林","R26":"竹圍","R25":"關渡","R24":"忠義",
    "R23":"復興崗","R22":"北投","R22A":"新北投","R21":"奇岩","R20":"唭哩岸",
    "R19":"石牌","R18":"明德","R17":"芝山","R16":"士林","R15":"劍潭",
    "R14":"圓山","R13":"民權西路","R12":"雙連","R11":"中山","R10":"台北車站",
    "R09":"台大醫院","R08":"中正紀念堂","R07":"東門","R06":"大安森林公園",
    "R05":"大安","R04":"信義安和","R03":"台北101/世貿","R02":"象山",
    "R01":"廣慈/奉天宮",
    "BL01":"頂埔","BL02":"永寧","BL03":"土城","BL04":"海山","BL05":"亞東醫院",
    "BL06":"府中","BL07":"板橋","BL08":"新埔","BL09":"江子翠","BL10":"龍山寺",
    "BL11":"西門","BL12":"台北車站","BL13":"善導寺","BL14":"忠孝新生",
    "BL15":"忠孝復興","BL16":"忠孝敦化","BL17":"國父紀念館","BL18":"市政府",
    "BL19":"永春","BL20":"後山埤","BL21":"昆陽","BL22":"南港","BL23":"南港展覽館",
    "G01":"新店","G02":"新店區公所","G03":"七張","G03A":"小碧潭","G04":"大坪林",
    "G05":"景美","G06":"萬隆","G07":"公館","G08":"台電大樓","G09":"古亭",
    "G10":"中正紀念堂","G11":"小南門","G12":"西門","G13":"北門","G14":"台北車站",
    "G15":"善導寺","G16":"松江南京","G17":"行天宮","G18":"南京三民","G19":"松山",
    "O01":"南勢角","O02":"景安","O03":"永安市場","O04":"頂溪","O05":"古亭",
    "O06":"東門","O07":"忠孝新生","O08":"松江南京","O09":"行天宮","O10":"中山國小",
    "O11":"民權西路","O12":"大橋頭","O13":"台北橋","O14":"菜寮","O15":"三重",
    "O16":"先嗇宮","O17":"頭前庄","O18":"新莊","O19":"輔大","O20":"丹鳳","O21":"迴龍",
    "O50":"三重國小","O51":"三和國中","O52":"徐匯中學","O53":"三民高中","O54":"蘆洲",
    "BR01":"動物園","BR02":"木柵","BR03":"萬芳社區","BR04":"萬芳醫院","BR05":"辛亥",
    "BR06":"麟光","BR07":"六張犁","BR08":"科技大樓","BR09":"大安","BR10":"忠孝復興",
    "BR11":"南京復興","BR12":"中山國中","BR13":"松山機場","BR14":"大直","BR15":"劍南路",
    "BR16":"西湖","BR17":"港墘","BR18":"文德","BR19":"內湖","BR20":"大湖公園",
    "BR21":"葫洲","BR22":"東湖","BR23":"南港軟體園區","BR24":"南港展覽館",
    "Y08":"十四張","Y09":"秀朗橋","Y10":"景平","Y12":"中和","Y13":"橋和",
    "Y14":"中原","Y15":"板新","Y16":"板橋","Y17":"新埔","Y19":"幸福","Y20":"新北產業園區",
    "K01":"雙城","K02":"玫瑰中國城","K03":"台北小城","K04":"耕莘安康院區",
    "K05":"景文科大","K06":"安康","K07":"陽光運動公園","K08":"新和國小","K09":"十四張",
    "V01":"紅樹林","V02":"竿蓁林",
    "A1":"台北","A2":"三重","A3":"新北產業園區","A12":"機場第一航廈",
    "LB06":"三峽","LB07":"臺北大學","LB08":"鶯歌車站","LB09":"鶯歌老街","LB12":"鶯桃福德",
}

LINE_NAMES = {
    "R":"淡水信義線","BL":"板南線","G":"松山新店線","O":"中和新蘆線",
    "BR":"文湖線","Y":"環狀線","K":"安坑輕軌","V":"淡海輕軌",
    "A":"機場捷運","LB":"三鶯線",
}

def get_line(sid: str) -> str:
    import re
    m = re.match(r'^([A-Za-z]+)', sid)
    return m.group(1).upper() if m else ""

# ── API 路由 ────────────────────────────────────
@app.get("/")
async def root():
    return FileResponse("index.html")

@app.get("/api/station/{station_id}")
async def get_station(station_id: str, background_tasks: BackgroundTasks):
    sid = station_id.upper()
    cache = DATA_DIR / f"{sid}.json"

    if cache.exists():
        data = json.loads(cache.read_text(encoding="utf-8"))
        return JSONResponse(data)

    # 快取不存在 → 背景執行抓取，先回傳骨架
    name = STATION_NAMES.get(sid, sid)
    background_tasks.add_task(fetch_and_cache, sid)
    return JSONResponse({
        "station_id": sid,
        "name": name,
        "line": LINE_NAMES.get(get_line(sid), ""),
        "status": "fetching",
        "intro": f"正在透過 AI 搜尋{name}站的特色，請稍後重新整理…",
        "tags": [],
        "highlights": [],
        "photo_url": None,
    })

@app.post("/api/station/{station_id}/refresh")
async def refresh_station(station_id: str, background_tasks: BackgroundTasks):
    sid = station_id.upper()
    cache = DATA_DIR / f"{sid}.json"
    if cache.exists():
        cache.unlink()
    background_tasks.add_task(fetch_and_cache, sid)
    return {"message": f"{sid} 快取已清除，正在重新抓取"}

@app.get("/api/diagnose")
async def diagnose():
    """診斷 Gemini API 連線狀態"""
    import httpx, os
    api_key = os.environ.get("GEMINI_API_KEY", "")
    result = {"api_key_set": bool(api_key), "api_key_prefix": api_key[:8]+"..." if api_key else ""}

    if not api_key:
        return result

    # 直接 REST 測試（繞過 SDK）
    models_to_test = ["gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-flash-001"]
    for model in models_to_test:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
            r = httpx.post(
                url,
                params={"key": api_key},
                json={"contents": [{"parts": [{"text": "Say OK"}]}]},
                timeout=15,
            )
            result[model] = {"status": r.status_code, "ok": r.status_code == 200,
                             "snippet": r.text[:100]}
        except Exception as e:
            result[model] = {"error": str(e)[:100]}

    return result

@app.get("/api/batch-status")
async def batch_status():
    total = len(STATION_NAMES)
    cached = len(list(DATA_DIR.glob("*.json")))
    return {"total": total, "cached": cached, "remaining": total - cached,
            "stations": [f.stem for f in sorted(DATA_DIR.glob("*.json"))]}

@app.post("/api/batch-fetch")
async def batch_fetch(background_tasks: BackgroundTasks):
    """觸發批次抓取所有未快取站點"""
    missing = [sid for sid in STATION_NAMES if not (DATA_DIR / f"{sid}.json").exists()]
    for sid in missing:
        background_tasks.add_task(fetch_and_cache, sid)
    return {"message": f"開始批次抓取 {len(missing)} 個站點", "stations": missing}

# ── Gemini + Wikipedia 抓取邏輯 ──────────────────
async def fetch_and_cache(sid: str):
    """用 Gemini Search Grounding 抓取站點資料並快取"""
    from station_fetcher import fetch_station_data
    name = STATION_NAMES.get(sid, sid)
    logger.info(f"Fetching: {sid} {name}")
    try:
        data = await asyncio.to_thread(fetch_station_data, sid, name)
        # 只快取成功資料（_retry=True 表示 AI 全部失敗，不快取讓下次重試）
        if data.get("_retry"):
            logger.warning(f"Not caching {sid} due to _retry flag")
            return
        cache = DATA_DIR / f"{sid}.json"
        cache.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info(f"✅ Cached: {sid}")
    except Exception as e:
        logger.error(f"Failed {sid}: {e}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.environ.get("PORT", 8080)), reload=False)
