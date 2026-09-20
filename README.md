# India Catalog for Stremio

A static, catalog-only Stremio addon with six India-focused rows:

- Trending Movies
- Popular Movies
- Top Rated Movies
- Trending Shows
- Popular Shows
- Top Rated Shows

## Install

Manifest URL:

`https://raw.githubusercontent.com/Cosmicator/catalog/main/manifest.json`

Stremio deep link:

`stremio://raw.githubusercontent.com/Cosmicator/catalog/main/manifest.json`

The addon is served directly from this public GitHub repository and refreshes automatically every 4 hours through GitHub Actions. It does not provide streams.

The catalog candidates come from public India-focused Stremio catalog feeds. Top Rated is calculated from their India-relevant candidates using Cinemeta/IMDb ratings. If an upstream row is temporarily unavailable, the updater uses another India-focused fallback rather than publishing an empty catalog.
