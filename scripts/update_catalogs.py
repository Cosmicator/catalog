#!/usr/bin/env python3
"""Refresh the static Stremio catalogs without requiring API keys."""

from __future__ import annotations

import json
import math
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = "https://indiastreams.rdata.in/catalog"
CINEMETA = "https://v3-cinemeta.strem.io/meta"
LIMIT = 50
USER_AGENT = "Cosmicator-India-Catalog/1.0 (+https://github.com/Cosmicator/catalog)"


def get_json(url: str, timeout: int = 30, retries: int = 3) -> dict:
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            req = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
            with urlopen(req, timeout=timeout) as response:
                return json.load(response)
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = exc
            if attempt + 1 < retries:
                time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"Failed to fetch {url}: {last_error}")


def fetch_catalog(media_type: str, catalog_id: str) -> list[dict]:
    url = f"{UPSTREAM}/{media_type}/{catalog_id}.json"
    try:
        data = get_json(url)
    except Exception as exc:
        print(f"warning: source {media_type}/{catalog_id} failed: {exc}")
        return []
    if not isinstance(data, dict):
        print(f"warning: source {media_type}/{catalog_id} returned no object")
        return []
    metas = data.get("metas")
    if not isinstance(metas, list):
        print(f"warning: source {media_type}/{catalog_id} has no metas list")
        return []
    cleaned = clean_metas(metas, media_type)
    print(f"source {media_type}/{catalog_id}: {len(cleaned)} valid titles")
    return cleaned


def clean_metas(metas: list[dict], media_type: str) -> list[dict]:
    output: list[dict] = []
    seen: set[str] = set()
    for item in metas:
        if not isinstance(item, dict):
            continue
        item_id = str(item.get("id", ""))
        name = item.get("name")
        if not item_id.startswith("tt") or not name or item_id in seen:
            continue
        seen.add(item_id)
        preview = {"id": item_id, "type": media_type, "name": str(name)}
        for key in ("poster", "posterShape", "background", "logo", "description", "releaseInfo", "imdbRating"):
            value = item.get(key)
            if value not in (None, ""):
                preview[key] = value
        output.append(preview)
    return output


def merge_unique(*lists: list[dict]) -> list[dict]:
    merged: list[dict] = []
    seen: set[str] = set()
    max_len = max((len(values) for values in lists), default=0)
    for index in range(max_len):
        for values in lists:
            if index >= len(values):
                continue
            item = values[index]
            if item["id"] not in seen:
                seen.add(item["id"])
                merged.append(item)
    return merged


def rating_number(value: object) -> float:
    try:
        number = float(value)
        return number if math.isfinite(number) else 0.0
    except (TypeError, ValueError):
        return 0.0


def fetch_rated_meta(media_type: str, item: dict) -> tuple[float, dict] | None:
    item_id = item["id"]
    try:
        data = get_json(f"{CINEMETA}/{media_type}/{item_id}.json", timeout=20, retries=2)
        meta = data.get("meta")
        if not isinstance(meta, dict):
            return None
        rating = rating_number(meta.get("imdbRating"))
        if rating <= 0:
            return None
        cleaned = clean_metas([meta], media_type)
        if not cleaned:
            return None
        cleaned[0]["imdbRating"] = str(meta.get("imdbRating"))
        return rating, cleaned[0]
    except Exception as exc:
        print(f"warning: metadata lookup failed for {item_id}: {exc}")
        return None


def make_top_rated(media_type: str, candidates: list[dict]) -> list[dict]:
    candidates = merge_unique(candidates)[:120]
    rated: list[tuple[float, int, dict]] = []
    with ThreadPoolExecutor(max_workers=12) as pool:
        future_map = {pool.submit(fetch_rated_meta, media_type, item): index for index, item in enumerate(candidates)}
        for future in as_completed(future_map):
            result = future.result()
            if result:
                score, meta = result
                rated.append((score, future_map[future], meta))
    rated.sort(key=lambda row: (-row[0], row[1]))
    if len(rated) < 8:
        print("warning: too few rated titles; using the candidate order as fallback")
        return candidates[:LIMIT]
    return [meta for _, _, meta in rated[:LIMIT]]


def save_catalog(relative_path: str, metas: list[dict]) -> None:
    if len(metas) < 5:
        raise RuntimeError(f"Refusing to publish {relative_path}: only {len(metas)} valid titles")
    path = ROOT / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps({"metas": metas[:LIMIT]}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)
    print(f"wrote {relative_path}: {min(len(metas), LIMIT)} titles")


def main() -> None:
    trending_movies = fetch_catalog("movie", "trendingmovies")
    upstream_popular_movies = fetch_catalog("movie", "popmov")
    recommended_movies = fetch_catalog("movie", "recmov")
    netflix_prime_movies = fetch_catalog("movie", "nfxprm")
    other_ott_movies = fetch_catalog("movie", "hstzee")

    upstream_trending_series = fetch_catalog("series", "trendingtv")
    netflix_prime_series = fetch_catalog("series", "nfxprmtv")
    other_ott_series = fetch_catalog("series", "hstzeetv")
    recommended_series = fetch_catalog("series", "atpmub")

    popular_movies = merge_unique(upstream_popular_movies, netflix_prime_movies, other_ott_movies, recommended_movies)
    popular_series = merge_unique(netflix_prime_series, other_ott_series, recommended_series)
    trending_series = upstream_trending_series

    if len(trending_movies) < 5:
        print("warning: trending movies source is thin; falling back to popular movie order")
        trending_movies = popular_movies
    if len(trending_series) < 5:
        print("warning: trending series source is thin; using recommendation-first India fallback")
        trending_series = merge_unique(recommended_series, other_ott_series, netflix_prime_series)

    top_movie_candidates = merge_unique(trending_movies, popular_movies, recommended_movies, netflix_prime_movies, other_ott_movies)
    top_series_candidates = merge_unique(trending_series, popular_series, recommended_series)

    outputs = {
        "catalog/movie/trending_movies.json": trending_movies,
        "catalog/movie/popular_movies.json": popular_movies,
        "catalog/movie/top_rated_movies.json": make_top_rated("movie", top_movie_candidates),
        "catalog/series/trending_series.json": trending_series,
        "catalog/series/popular_series.json": popular_series,
        "catalog/series/top_rated_series.json": make_top_rated("series", top_series_candidates),
    }
    for relative_path, metas in outputs.items():
        save_catalog(relative_path, metas)


if __name__ == "__main__":
    main()
