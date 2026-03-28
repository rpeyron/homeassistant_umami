#!/usr/bin/env python3
"""
Umami Analytics API Client v4.16
Rémi Peyronnet - March 2026
"""

import httpx
import json
import sys
import re
import hashlib
import tempfile
from urllib.parse import urlparse
from datetime import datetime, timedelta
from pathlib import Path
import pytz
import time

# ==================== CACHE FUNCTIONS ====================
def cache_read(cache_dir: Path, cache_key: str, ttl: int = 300):
    cache_file = cache_dir / f"{cache_key}.json"
    ttl_file = cache_dir / f"{cache_key}.ttl"
    if not cache_file.exists() or not ttl_file.exists():
        return None
    if time.time() > float(ttl_file.read_text()):
        return None
    try:
        with open(cache_file, 'r') as f:
            return json.load(f)
    except:
        return None

def cache_write(cache_dir: Path, cache_key: str, data: dict, ttl: int = 300):
    cache_file = cache_dir / f"{cache_key}.json"
    ttl_file = cache_dir / f"{cache_key}.ttl"
    try:
        with open(cache_file, 'w') as f:
            json.dump(data, f)
        with open(ttl_file, 'w') as f:
            f.write(str(time.time() + ttl))
    except:
        pass

def cache_key(share_id: str, endpoint: str, params: dict = None, body: dict = None) -> str:
    params = params if isinstance(params, dict) else {}
    body = body if isinstance(body, dict) else {}
    param_str = json.dumps(params, sort_keys=True)
    body_str = json.dumps(body, sort_keys=True)
    return hashlib.md5(f"{share_id}:{endpoint}:{param_str}:{body_str}".encode()).hexdigest()

# ==================== MAIN CLASS (RAW DATA UNIQUEMENT) ====================
# https://umami.is/docs/api/website-stats
class UmamiShareStatsFetcher:
    def __init__(self, share_url: str, timezone_str: str = 'Europe/Paris', use_cache: bool = True):
        self.share_url = share_url
        self.timezone_str = timezone_str
        self.use_cache = use_cache
        self.cache_dir = Path(tempfile.gettempdir()) / 'umami_cache'
        self.cache_dir.mkdir(exist_ok=True)

        self.domain = self._extract_domain(share_url)
        self.share_id = self._extract_share_id(share_url)
        self.api_base = f"https://{self.domain}/analytics/eu/api"
        self.token = None
        self.website_id = None

    def _extract_domain(self, url: str) -> str:
        return urlparse(url).netloc

    def _extract_share_id(self, url: str) -> str:
        path = urlparse(url).path
        match = re.search(r'/share/([a-zA-Z0-9-]+)', path)
        return match.group(1) if match else None

    def _get_timestamps(self, days: int):
        tz = pytz.timezone(self.timezone_str)
        end = datetime.now(tz).replace(hour=23, minute=59, second=59, microsecond=999999)
        start = end - timedelta(days=days)
        return int(start.timestamp() * 1000), int(end.timestamp() * 1000)

    def _get_dates(self, days: int):
        tz = pytz.timezone(self.timezone_str)
        end = datetime.now(tz).replace(hour=23, minute=59, second=59, microsecond=999999)
        start = end - timedelta(days=days)
        return start.isoformat(), end.isoformat()

    def get_token_and_website(self) -> tuple:
        if self.token and self.website_id:
            return self.token, self.website_id

        ck = cache_key(self.share_id, "token", {})
        if self.use_cache:
            cached = cache_read(self.cache_dir, ck, 3600)
            if cached and cached.get('token') and cached.get('website_id'):
                self.token = cached['token']
                self.website_id = cached['website_id']
                return self.token, self.website_id

        url = f"{self.api_base}/share/{self.share_id}"
        resp = httpx.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        self.token = data.get('token')
        self.website_id = data.get('websiteId') or data.get('website_id')

        if not self.token or not self.website_id:
            raise ValueError(f"Auth failed: {data}")

        if self.use_cache:
            cache_write(self.cache_dir, ck, {
                'token': self.token,
                'website_id': self.website_id
            }, 3600)

        return self.token, self.website_id

    def _api_raw(self, endpoint: str, params: dict = None, method: str = 'GET', body: dict = None):
        self.get_token_and_website()
        if not self.website_id:
            raise ValueError("website_id is None!")

        headers = {"X-Umami-Share-Token": self.token}
        url = f"{self.api_base}{endpoint}"
        if method == 'POST':
            resp = httpx.post(url, headers=headers, params=params, json=body, timeout=30)
        else:
            resp = httpx.get(url, headers=headers, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def _api_call(self, endpoint: str, params: dict = None, ttl: int = 300, method: str = 'GET', body: dict = None):
        if self.use_cache:
            ck = cache_key(self.share_id, f"{method}:{endpoint}", params,  body)
            cached = cache_read(self.cache_dir, ck, ttl)
            if cached is not None:
                return cached
        data = self._api_raw(endpoint, params, method, body)
        if self.use_cache:
            cache_write(self.cache_dir, ck, data, ttl)
        return data

    def _api_website(self, info: str, params: dict, ttl: int = 300):
        self.get_token_and_website()
        return self._api_call(f"/websites/{self.website_id}/{info}", params, ttl)

    def _api_breakdown(self, fields: list, start_date: str, end_date: str, parameters: dict = None, filters: dict = None, ttl: int = 300):
        self.get_token_and_website()
        parameters = parameters or {}
        return self._api_call("/reports/breakdown", method='POST', ttl=ttl, body={
                "websiteId": self.website_id,
                "type": "breakdown",
                "filters": filters or {},
                "parameters": {
                    "fields": fields,
                    "startDate": start_date,
                    "endDate": end_date,
                    **parameters
                }
        })

    # ==================== RAW DATA SEULEMENT ====================
    def fetch_token(self):
        self.get_token_and_website()
        return {'website_id': self.website_id, 'token': self.token }

    def fetch_website_info(self, ttl: int = 300):
        self.get_token_and_website()
        return self._api_call(f"/websites/{self.website_id}", {}, ttl)

    def fetch_website_stats(self, days: int, ttl: int = 300):
        start_ts, end_ts = self._get_timestamps(days)
        return self._api_website("stats", {'startAt': start_ts, 'endAt': end_ts}, ttl)

    def fetch_pageviews_history(self, days: int, ttl: int = 300):
        """Pageviews RAW (sans Chart.js)"""
        start_ts, end_ts = self._get_timestamps(days)
        return self._api_website("pageviews", {
            'startAt': start_ts, 'endAt': end_ts, 'unit': 'day', 'timezone': self.timezone_str
        }, ttl)

    def fetch_metric_top_path(self, days: int, limit: int, ttl: int = 300):
        """Top pages RAW (sans Chart.js)"""
        start_ts, end_ts = self._get_timestamps(days)
        return self._api_website("metrics", {
            'startAt': start_ts, 'endAt': end_ts, 'type': 'path', 'limit': limit, 'timezone': self.timezone_str
        }, ttl)


    def fetch_metric_top_titles(self, days: int, limit: int, ttl: int = 300):
        """Top pages RAW (sans Chart.js)"""
        start_ts, end_ts = self._get_timestamps(days)
        return self._api_website("metrics", {
            'startAt': start_ts, 'endAt': end_ts, 'type': 'title', 'limit': limit, 'timezone': self.timezone_str
        }, ttl)

    # Deprecated, use breakdown report instead
    def fetch_metric_top_path_titles_merged(self, days: int, limit: int, ttl: int = 300):
        """Top pages + titles RAW (sans Chart.js)"""
        start_ts, end_ts = self._get_timestamps(days)
        paths = self._api_website("metrics", {
            'startAt': start_ts, 'endAt': end_ts, 'type': 'path', 'limit': limit, 'timezone': self.timezone_str
        }, ttl)
        titles = self._api_website("metrics", {
            'startAt': start_ts, 'endAt': end_ts, 'type': 'title', 'limit': limit, 'timezone': self.timezone_str
        }, ttl)

        def titleToFirstWord(s):
            return re.sub(r'[^A-Za-z0-9]', ' ', s.lower()).split()[0] if s else ''

        def pathToFirstWord(s):
            return re.sub(r'[^A-Za-z0-9]', ' ', re.sub(r'[0-9]+/','', re.sub(r'/category/', '', re.sub(r'/tag/', '', s.lower())))).strip().split(" ")[0]

        firstwords = { titleToFirstWord(title['x']): title for title in titles}
        #print(firstwords)

        merged = [ {'index': i, 'count': path['y'], 'path': path['x'],
                    # Merge first word lookup
                    #'path_firstword': pathToFirstWord(path['x']),
                    'title_firstword': firstwords.get(pathToFirstWord(path['x']), {}).get('x', ''),
                    # Merge paths and titles based on same order (not ideal but API doesn't provide direct mapping)
                    'title_pos': titles[i]['x'],
                    'title_pos_count': titles[i]['y'],
                    # We check if counts are equal to avoid mismatches, this is not always the case because of, some different pages can have same title, and also count can not to be accurate
                    #'title': titles[i]['x'] if titles[i]['y'] == path['y'] else None
                    } for i,path in enumerate(paths) ]

        return [ { 'index': item['index'], 'count': item['count'], 'path': item['path'],
                  'title': item['title_firstword'] or (item['title_pos'] if item['title_pos_count'] == item['count'] else None)
                  } for item in merged ]

    def fetch_top_pages(self, days: int, limit: int = 10, ttl: int = 300):
        """ Top Page url with titles with breakdown API """
        start_date, end_date = self._get_dates(days)
        pages = self._api_breakdown(['path', 'title'], start_date, end_date)
        return pages[:limit]

# ==================== CHART.JS CONVERSION (GLOBALES) ====================
def to_chartjs_convert_time(time, timezone_str: str = 'Europe/Paris'):
    """Convertit timestamp en DD/MM/AA avec timezone"""
    tz = pytz.timezone(timezone_str)

    if isinstance(time, (int, float)):
        dt = datetime.fromtimestamp(time / 1000, tz=tz)
    else:
        dt = datetime.strptime(time[:10], '%Y-%m-%d').replace(tzinfo=tz)

    return dt.strftime('%d/%m/%y')

def to_chartjs_convert_timeserie(series, timezone_str: str = 'Europe/Paris'):
    return [{'x': to_chartjs_convert_time(item['x'], timezone_str), 'y': item['y']}
            for item in series]

def to_chartjs_pageviews(umami_data, timezone_str: str = 'Europe/Paris'):
    """Convert Umami pageviews → Chart.js Line chart (DD/MM/AA)"""
    if not umami_data:
        return {'labels': [], 'datasets': []}

    pageviews = umami_data.get('pageviews', [])
    sessions = umami_data.get('sessions', [])

    labels = [to_chartjs_convert_time(item['x'], timezone_str) for item in pageviews] if pageviews else []

    datasets = []

    if pageviews:
        datasets.append({
            'label': 'Pageviews',
            'data': to_chartjs_convert_timeserie(pageviews, timezone_str),
        })

    if sessions:
        datasets.append({
            'label': 'Sessions',
            'data': to_chartjs_convert_timeserie(sessions, timezone_str),
        })

    return {
        'labels': labels,
        'datasets': datasets,
    }

# ==================== CLI (CONVERSION CHART.JS ICI) ====================
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Umami Analytics + Chart.js")
    parser.add_argument("share_url")
    parser.add_argument("--days", type=int, default=7, help="Number of days to fetch (default: 7)")
    parser.add_argument("--data", choices=['stats','info', 'token', 'pageviews', 'path', 'titles', 'path_with_titles', 'pages'], default='stats', help="Type of data to fetch (default: stats)")
    parser.add_argument("--chartjs", action='store_true', help="Chart.js output format for compatible data (pageviews)", default=False)
    parser.add_argument("--limit", type=int, default=10, help="Limit for metrics (default: 10)")
    parser.add_argument("--ttl", type=int, default=300, help="Cache TTL in seconds (default: 300)")
    parser.add_argument("--no-cache", action='store_true', help="Disable caching", default=False)
    parser.add_argument("--timezone", default='Europe/Paris', help="Timezone (ex: Europe/Paris)")

    args = parser.parse_args()

    try:
        fetcher = UmamiShareStatsFetcher(
            args.share_url,
            timezone_str=args.timezone,
            use_cache=not args.no_cache
        )

        if args.data == 'token':
            result = fetcher.fetch_token()
        elif args.data == 'pageviews':
            result = fetcher.fetch_pageviews_history(args.days, args.ttl)
        elif args.data == 'path':
            result = fetcher.fetch_metric_top_path(args.days, args.limit,args.ttl)
        elif args.data == 'path_with_titles':
            result = fetcher.fetch_metric_top_path_titles_merged(args.days, args.limit,args.ttl)
        elif args.data == 'titles':
            result = fetcher.fetch_metric_top_titles(args.days, args.limit,args.ttl)
        elif args.data == 'pages':
            result = fetcher.fetch_top_pages(args.days, args.limit, ttl=args.ttl)
        elif args.data == 'info':
            result = fetcher.fetch_website_info(args.ttl)
        else:
            result = fetcher.fetch_website_stats(args.days, args.ttl)

        if args.chartjs:
            if args.data == 'pageviews':
                result = to_chartjs_pageviews(result, args.timezone)

        print(json.dumps(result, indent=2))

    except Exception as e:
        print(json.dumps({'error': str(e)}, indent=2), file=sys.stderr)
        sys.exit(1)
