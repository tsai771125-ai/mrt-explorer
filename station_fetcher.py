"""
station_fetcher.py
用 Gemini 1.5 Flash 抓取捷運站點特色，
用 Wikipedia API 取得免費照片。
"""
import os, json, re, httpx, logging
import google.generativeai as genai

logger = logging.getLogger(__name__)

PROMPT_TEMPLATE = """你是一個熱愛台灣旅遊的達人，幫一個爸爸帶兒子探索台北捷運每一站的特色。

請用繁體中文，整理「台北捷運{name}站」附近（步行10分鐘內）最有趣的景點和特色。
根據你對台北的知識，提供真實準確的資訊。

請只回傳以下 JSON 格式，不要任何其他文字、markdown 或說明：
{{
  "intro": "50字以內的站點介紹，說明這站最有特色的地方",
  "tags": ["標籤1", "標籤2", "標籤3"],
  "highlights": [
    {{
      "emoji": "🏛️",
      "name": "景點名稱",
      "desc": "30字以內的有趣描述，要讓小朋友也能理解",
      "wiki_query": "景點的英文名稱，用來搜尋Wikipedia照片，如 Longshan Temple Taipei"
    }}
  ],
  "photo_query": "這站最具代表性景點的英文搜尋詞",
  "kids_friendly": true
}}

highlights 請提供 3-4 個真實景點，優先選親子友善的。"""


def fetch_station_data(station_id: str, station_name: str) -> dict:
    """主要函式：Gemini 生成站點資料 + Wikipedia 照片"""
    base = {
        "station_id": station_id,
        "name": station_name,
        "status": "ok",
        "intro": "",
        "tags": [],
        "highlights": [],
        "photo_url": None,
        "photo_credit": None,
    }

    # 每次即時讀取 API key
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        logger.warning(f"No GEMINI_API_KEY for {station_id}")
        return {**base, "intro": f"{station_name}站：請設定 GEMINI_API_KEY"}

    # ── 1. Gemini 生成站點資料 ──────────────────────
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(
            model_name="gemini-1.5-flash",
            generation_config=genai.GenerationConfig(
                temperature=0.7,
                response_mime_type="application/json",
            ),
        )
        prompt = PROMPT_TEMPLATE.format(name=station_name)
        response = model.generate_content(prompt)
        text = response.text.strip()

        # 清除可能的 markdown code fence
        text = re.sub(r"^```(?:json)?\s*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
        text = text.strip()

        ai_data = json.loads(text)
        base.update({
            "intro": ai_data.get("intro", ""),
            "tags": ai_data.get("tags", []),
            "highlights": ai_data.get("highlights", []),
            "kids_friendly": ai_data.get("kids_friendly", True),
            "photo_query": ai_data.get("photo_query", station_name),
        })
        logger.info(f"Gemini OK: {station_id} — {len(ai_data.get('highlights',[]))} highlights")

    except json.JSONDecodeError as e:
        logger.error(f"JSON parse error for {station_id}: {e}\nText: {text[:200]}")
        base["intro"] = f"{station_name}站 — 資料解析失敗，稍後重試"
    except Exception as e:
        logger.error(f"Gemini error for {station_id}: {type(e).__name__}: {e}")
        base["intro"] = f"{station_name}站 — AI 搜尋失敗（{type(e).__name__}）"

    # ── 2. Wikipedia 主照片 ─────────────────────────
    photo_query = base.get("photo_query") or station_name
    photo_url, credit = get_wikipedia_photo(photo_query)
    if not photo_url:
        photo_url, credit = get_wikipedia_photo(f"{station_name} Taipei")
    base["photo_url"] = photo_url
    base["photo_credit"] = credit

    # ── 3. 每個 highlight 補照片 ────────────────────
    for h in base.get("highlights", []):
        q = h.get("wiki_query") or h.get("name", "")
        if q:
            url, _ = get_wikipedia_photo(q)
            h["photo_url"] = url

    return base


def get_wikipedia_photo(query: str) -> tuple:
    """用 Wikipedia API 搜尋代表照片（免費，無需 API key）"""
    try:
        # Step 1: 搜尋頁面
        r = httpx.get(
            "https://en.wikipedia.org/w/api.php",
            params={
                "action": "query", "list": "search",
                "srsearch": query, "srlimit": 1, "format": "json",
            },
            timeout=8,
        )
        results = r.json().get("query", {}).get("search", [])
        if not results:
            return None, None

        title = results[0]["title"]

        # Step 2: 取縮圖
        r2 = httpx.get(
            "https://en.wikipedia.org/w/api.php",
            params={
                "action": "query", "titles": title,
                "prop": "pageimages", "pithumbsize": 800,
                "format": "json",
            },
            timeout=8,
        )
        pages = r2.json().get("query", {}).get("pages", {})
        for page in pages.values():
            src = page.get("thumbnail", {}).get("source")
            if src:
                return src, f"© Wikipedia: {title}"

        return None, None
    except Exception as e:
        logger.warning(f"Wikipedia photo failed '{query}': {e}")
        return None, None
