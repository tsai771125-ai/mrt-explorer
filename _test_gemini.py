"""本機完整測試：確認 Gemini + Wikipedia 站點資料"""
import os, json, sys
os.environ.setdefault("GEMINI_API_KEY", "")

from station_fetcher import fetch_station_data

result = fetch_station_data("R28", "淡水")
print(f"station_id : {result['station_id']}")
print(f"name       : {result['name']}")
print(f"model used : {result.get('_model_used', 'N/A')}")
print(f"intro      : {result['intro']}")
print(f"tags       : {', '.join(result['tags'])}")
print(f"highlights : {len(result['highlights'])} 個")
for h in result['highlights']:
    print(f"  {h.get('emoji','')} {h['name']}: {h['desc']}")
    print(f"     photo: {h.get('photo_url','none')}")
print(f"photo_url  : {result['photo_url']}")
print(f"photo_cred : {result['photo_credit']}")
