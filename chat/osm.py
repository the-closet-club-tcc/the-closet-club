import json
import urllib.parse
import urllib.request

NOMINATIM_URL = 'https://nominatim.openstreetmap.org/search'
USER_AGENT = 'TheClosetClub-PBP/1.0 (university course project)'

# Filter kategori fasilitas umum untuk titik serah-terima
CATEGORIES = {
    'stasiun': 'stasiun',
    'minimarket': 'minimarket',
    'halte': 'halte',
}


def search_places(query, category='', limit=5):
    """Cari tempat lewat OpenStreetMap Nominatim. Gagal jaringan = list kosong."""
    query = (query or '').strip()
    if not query:
        return []
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
        return []

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
    return results