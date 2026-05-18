"""
station_fetcher.py
用 Gemini Flash + Search Grounding 抓取捷運站點特色，
用 Wikipedia API 取得免費照片。
"""
import os, json, re, httpx, logging
import google.generativeai as genai

logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

PROMPT_TEMPLATE = """你是一個熱愛台灣旅遊的達人，幫一個爸爸帶兒子探索台北捷運每一站的特色。

請用繁體中文，搜尋並整理「台北捷運{name}站」附近（步行10分鐘內）最有趣的景點和特色。

**重要**：必須用 Google Search 搜尋最新真實資訊，不要憑記憶回答。

請回傳以下 JSON 格式（只回傳 JSON，不要其他文字）：
{{
  "intro": "50字以內的站點介紹，說明這站最有特色的地方",
  "tags": ["標籤1", "標籤2", "標籤3"],
  "highlights": [
    {{
      "emoji": "🏛️",
      "name": "景點名稱",
      "desc": "30字以內的有趣描述，要讓小朋友也能理解",
      "wiki_query": "用來搜尋Wikipedia照片的英文關鍵字，例如 Longshan Temple Taipei"
    }}
  ],
  "photo_query": "這個站最具代表性景點的英文名，用來搜尋照片",
  "kids_friendly": true
}}

highlights 請提供 3-4 個，從親子友善到文化古蹟都可以。
"""


def fetch_station_data(station_id: str, station_name: str) -> dict:
    """主要函式：Gemini 搜尋 + Wikipedia 照片"""
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

    if not GEMINI_API_KEY:
        logger.warning("No GEMINI_API_KEY, returning stub data")
        return {**base, "intro": f"{station_name}站資料尚未載入（未設定 GEMINI_API_KEY）"}

    # ── 1. Gemini Search Grounding ────────────────
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel(
            model_name="gemini-2.0-flash",
            tools=[{"google_search": {}}],
        )
        prompt = PROMPT_TEMPLATE.format(name=station_name)
        response = model.generate_content(prompt)
        text = response.text.strip()

        # 清理 markdown code fence
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.MULTILINE)
        text = re.sub(r"\s*```$", "", text, flags=re.MULTILINE)

        ai_data = json.loads(text)
        base.update({
            "intro": ai_data.get("intro", ""),
            "tags": ai_data.get("tags", []),
            "highlights": ai_data.get("highlights", []),
            "kids_friendly": ai_data.get("kids_friendly", True),
            "photo_query": ai_data.get("photo_query", station_name),
        })
    except Exception as e:
        logger.error(f"Gemini error for {station_id}: {e}")
        base["intro"] = f"{station_name}站 — AI 資料抓取中"

    # ── 2. Wikipedia 照片 ────────────────────────
    photo_query = base.get("photo_query") or station_name
    photo_url, credit = get_wikipedia_photo(photo_query)
    if not photo_url:
        # fallback: 用站名搜尋中文 Wikipedia
        photo_url, credit = get_wikipedia_photo(f"{station_name} 台北")
    base["photo_url"] = photo_url
    base["photo_credit"] = credit

    # ── 3. 補充每個 highlight 的照片 ─────────────
    for h in base.get("highlights", []):
        if h.get("wiki_query"):
            url, _ = get_wikipedia_photo(h["wiki_query"])
            h["photo_url"] = url

    return base


def get_wikipedia_photo(query: str) -> tuple[str | None, str | None]:
    """用 Wikipedia API 搜尋並取得代表照片"""
    try:
        # Step 1: 搜尋頁面
        search_url = "https://en.wikipedia.org/w/api.php"
        params = {
            "action": "query",
            "list": "search",
            "srsearch": query,
            "srlimit": 1,
            "format": "json",
        }
        r = httpx.get(search_url, params=params, timeout=10)
        results = r.json().get("query", {}).get("search", [])
        if not results:
            return None, None

        title = results[0]["title"]

        # Step 2: 取得頁面縮圖
        thumb_url = "https://en.wikipedia.org/w/api.php"
        thumb_params = {
            "action": "query",
            "titles": title,
            "prop": "pageimages|info",
            "pithumbsize": 800,
            "inprop": "url",
            "format": "json",
        }
        r2 = httpx.get(thumb_url, params=thumb_params, timeout=10)
        pages = r2.json().get("query", {}).get("pages", {})
        for page in pages.values():
            thumb = page.get("thumbnail", {})
            if thumb.get("source"):
                credit = f"Wikipedia: {title}"
                return thumb["source"], credit

        return None, None
    except Exception as e:
        logger.warning(f"Wikipedia photo failed for '{query}': {e}")
        return None, None
