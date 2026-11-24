from typing import Any, cast

import httpx

from ..config import settings
from ..observability import logger, metrics, timed

MARKETPLACE_PRIORITY = ["US", "UK", "DE", "FR", "JP", "IN", "CA", "IT", "ES", "AU"]


class CatalogService:
    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = base_url or settings.catalog_api_url
        self.timeout = httpx.Timeout(10.0, connect=5.0)

    @timed("catalog_fetch")
    def fetch_product(
        self, product_id: str, marketplaces: list[str] | None = None
    ) -> dict[str, Any]:
        if marketplaces is None:
            marketplaces = MARKETPLACE_PRIORITY[: settings.max_marketplaces]

        results: dict[str, dict[str, Any]] = {}
        primary_data: dict[str, Any] = {}

        for mp in marketplaces:
            try:
                data = self._fetch_marketplace(product_id, mp)
                if data:
                    results[mp] = data
                    if not primary_data:
                        primary_data = data
                    metrics.increment("catalog.marketplace_hit")
            except httpx.TimeoutException:
                logger.warning(f"Timeout fetching {product_id} from {mp}")
                metrics.increment("catalog.timeout")
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 404:
                    continue
                logger.error(
                    f"HTTP error fetching {product_id} from {mp}: {e.response.status_code}"
                )
                metrics.increment("catalog.http_error")

        if not primary_data:
            logger.warning(
                f"No catalog data found for {product_id} across {len(marketplaces)} marketplaces"
            )
            return {}

        primary_data["marketplace_results"] = results
        primary_data["marketplaces_scanned"] = len(marketplaces)
        primary_data["marketplaces_found"] = len(results)
        return primary_data

    def _fetch_marketplace(self, product_id: str, marketplace: str) -> dict[str, Any] | None:
        url = f"{self.base_url}/products/{product_id}"
        params = {"marketplace": marketplace}

        with httpx.Client(timeout=self.timeout) as client:
            response = client.get(url, params=params)
            response.raise_for_status()
            return cast(dict[str, Any] | None, response.json())
