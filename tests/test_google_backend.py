"""Google Custom Search Backend tests — TDD: RED → GREEN."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.search import SearchBackend, SearchResult, get_available_backends
from src.search.google_backend import GoogleBackend


def _build_mock_client(resp_items, status_code=200):
    fake_resp = MagicMock()
    fake_resp.status_code = status_code
    fake_resp.json.return_value = {
        "items": resp_items,
    }
    mock_client = AsyncMock()
    mock_client.get.return_value = fake_resp
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None
    return mock_client


class TestGoogleBackend:

    @pytest.mark.asyncio
    async def test_search_returns_results(self):
        mock_client = _build_mock_client([
            {"title": "Result 1", "link": "https://example.com/1",
             "snippet": "Snippet 1"},
            {"title": "Result 2", "link": "https://example.com/2",
             "snippet": "Snippet 2"},
        ])

        with patch("src.search.google_backend.httpx.AsyncClient", return_value=mock_client):
            backend = GoogleBackend(api_key="test-key", cx="test-cx")
            results = await backend.search("test query", num=5)

        assert len(results) == 2
        assert isinstance(results[0], SearchResult)
        assert results[0].title == "Result 1"
        assert results[0].url == "https://example.com/1"
        assert results[0].snippet == "Snippet 1"
        assert results[0].source_quality == "medium"

    @pytest.mark.asyncio
    async def test_search_empty_results(self):
        mock_client = _build_mock_client([])
        with patch("src.search.google_backend.httpx.AsyncClient", return_value=mock_client):
            backend = GoogleBackend(api_key="test-key", cx="test-cx")
            results = await backend.search("no results query", num=5)
        assert results == []

    @pytest.mark.asyncio
    async def test_search_no_items_key(self):
        """Response without 'items' key should return empty list."""
        fake_resp = MagicMock()
        fake_resp.status_code = 200
        fake_resp.json.return_value = {}
        mock_client = AsyncMock()
        mock_client.get.return_value = fake_resp
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        with patch("src.search.google_backend.httpx.AsyncClient", return_value=mock_client):
            backend = GoogleBackend(api_key="test-key", cx="test-cx")
            results = await backend.search("query", num=5)
        assert results == []

    @pytest.mark.asyncio
    async def test_search_api_error_graceful(self):
        mock_client = AsyncMock()
        mock_client.get.side_effect = Exception("Connection refused")
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        with patch("src.search.google_backend.httpx.AsyncClient", return_value=mock_client):
            backend = GoogleBackend(api_key="test-key", cx="test-cx")
            results = await backend.search("error query", num=5)
        assert results == []

    @pytest.mark.asyncio
    async def test_search_non_200_graceful(self):
        mock_client = _build_mock_client([], status_code=403)
        with patch("src.search.google_backend.httpx.AsyncClient", return_value=mock_client):
            backend = GoogleBackend(api_key="test-key", cx="test-cx")
            results = await backend.search("forbidden query", num=5)
        assert results == []

    @pytest.mark.asyncio
    async def test_search_calls_correct_endpoint(self):
        mock_client = _build_mock_client([
            {"title": "T", "link": "https://x.com", "snippet": "S"},
        ])

        with patch("src.search.google_backend.httpx.AsyncClient", return_value=mock_client):
            backend = GoogleBackend(api_key="my-key", cx="my-cx")
            await backend.search("test query", num=3)

        call_args = mock_client.get.call_args
        assert call_args is not None
        url_arg = call_args[0][0] if call_args[0] else call_args.kwargs.get("url", "")
        assert "googleapis.com/customsearch" in url_arg
        params = call_args.kwargs.get("params", {})
        assert params.get("key") == "my-key"
        assert params.get("cx") == "my-cx"
        assert params.get("q") == "test query"
        assert params.get("num") == 3

    @pytest.mark.asyncio
    async def test_search_respects_max_num_10(self):
        """Google CSE max is 10 per request; backend should cap at 10."""
        mock_client = _build_mock_client([
            {"title": "T", "link": "https://x.com", "snippet": "S"},
        ])
        with patch("src.search.google_backend.httpx.AsyncClient", return_value=mock_client):
            backend = GoogleBackend(api_key="k", cx="c")
            await backend.search("query", num=20)

        params = mock_client.get.call_args.kwargs.get("params", {})
        assert params.get("num") == 10

    def test_name_property(self):
        backend = GoogleBackend(api_key="test-key", cx="test-cx")
        assert backend.name == "google"

    def test_is_search_backend(self):
        backend = GoogleBackend(api_key="test-key", cx="test-cx")
        assert isinstance(backend, SearchBackend)


class TestGoogleIntegration:

    def test_get_available_backends_includes_google_when_keys_present(self):
        config = MagicMock()
        config.tavily_api_key = ""
        config.google_search_api_key = "key-123"
        config.google_search_cx = "cx-456"

        backends = get_available_backends(config)

        names = [b.name for b in backends]
        assert "google" in names

    def test_get_available_backends_omits_google_when_no_key(self):
        config = MagicMock()
        config.tavily_api_key = ""
        config.google_search_api_key = ""
        config.google_search_cx = ""

        backends = get_available_backends(config)

        names = [b.name for b in backends]
        assert "google" not in names

    def test_get_available_backends_omits_google_when_no_cx(self):
        config = MagicMock()
        config.tavily_api_key = ""
        config.google_search_api_key = "key-123"
        config.google_search_cx = ""

        backends = get_available_backends(config)

        names = [b.name for b in backends]
        assert "google" not in names


class TestGoogleSourceQuality:

    def test_classify_high_quality_domains(self):
        backend = GoogleBackend(api_key="k", cx="c")
        assert backend._classify_quality("https://www.example.gov.cn/doc") == "high"
        assert backend._classify_quality("https://tianyancha.com/company/123") == "high"
        assert backend._classify_quality("https://example.com") == "medium"
