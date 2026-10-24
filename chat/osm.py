import hashlib
import json
import urllib.parse
import urllib.request

from django.core.cache import cache

NOMINATIM_URL = 'https://nominatim.openstreetmap.org/search'
USER_AGENT = 'TheClosetClub-PBP/1.0 (university course project)'
CACHE_SECONDS = 60 * 60 * 6

# Filter opsional untuk mempersempit hasil
CATEGORIES = {
    'stasiun': 'stasiun',
    'minimarket': 'minimarket',
    'halte': 'halte',
}


def search_places(query, category='', limit=5):
    """Cari tempat lewat OpenStreetMap Nominatim. Gagal jaringan = list kosong."""
    query = (query or '').strip()[:100]
    if not query:
        return []

    key = 'osm:' + hashlib.md5(
        f'{category}|{query.lower()}|{limit}'.encode('utf-8')
    ).hexdigest()
    cached = cache.get(key)
    if cached is not None:
        return cached

    q = f'{CATEGORIES.get(category, "")} {query}'.strip()
    params = urllib.parse.urlencode({
        'q': q, 'format': 'jsonv2', 'limit': limit, 'countrycodes': 'id',
    })
    req = urllib.request.Request(
        f'{NOMINATIM_URL}?{params}', headers={'User-Agent': USER_AGENT},
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode('utf-8'))
    except (OSError, ValueError):
        return []  # gagal jaringan tidak di-cache

    results = []
    for item in data:
        try:
            lat = round(float(item['lat']), 6)
            lon = round(float(item['lon']), 6)
        except (KeyError, TypeError, ValueError):
            continue
        display = item.get('display_name', '')
        name = item.get('name') or display.split(',')[0]
        results.append({
            'name': name[:150], 'address': display[:255], 'lat': lat, 'lon': lon,
        })
    cache.set(key, results, CACHE_SECONDS)
    return results