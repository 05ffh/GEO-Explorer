"""Tavily Search Backend tests — TDD: RED → GREEN."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.search import SearchBackend, SearchResult, get_available_backends
from src.search.tavily_backend import TavilyBackend


def _build_mock_client(resp_results, answer="", status_code=200):
    fake_resp = MagicMock()
    fake_resp.status_code = status_code
    fake_resp.json.return_value = {
        "query": "test query",
        "results": resp_results,
        "answer": answer,
    }
    mock_client = AsyncMock()
    mock_client.post.return_value = fake_resp
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None
    return mock_client


class TestTavilyBackend:

    @pytest.mark.asyncio
    async def test_search_returns_results(self):
        """Search should return SearchResult list mapped from Tavily response."""
        mock_client = _build_mock_client([
            {"title": "Result 1", "url": "https://example.com/1",
             "content": "Content 1", "score": 0.9},
            {"title": "Result 2", "url": "https://example.com/2",
             "content": "Content 2", "score": 0.8},
        ])

        with patch("src.search.tavily_backend.httpx.AsyncClient", return_value=mock_client):
            backend = TavilyBackend(api_key="test-key")
            results = await backend.search("test query", num=5)

        assert len(results) == 2
        assert isinstance(results[0], SearchResult)
        assert results[0].title == "Result 1"
        assert results[0].url == "https://example.com/1"
        assert results[0].snippet == "Content 1"
        assert results[0].source_quality == "medium"

    @pytest.mark.asyncio
    async def test_search_empty_results(self):
        """Empty results from API should return empty list."""
        mock_client = _build_mock_client([])
        with patch("src.search.tavily_backend.httpx.AsyncClient", return_value=mock_client):
            backend = TavilyBackend(api_key="test-key")
            results = await backend.search("no results query", num=5)
        assert results == []

    @pytest.mark.asyncio
    async def test_search_api_error_graceful(self):
        """HTTP error from API should return empty list, not raise."""
        mock_client = AsyncMock()
        mock_client.post.side_effect = Exception("Connection refused")
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        with patch("src.search.tavily_backend.httpx.AsyncClient", return_value=mock_client):
            backend = TavilyBackend(api_key="test-key")
            results = await backend.search("error query", num=5)
        assert results == []

    @pytest.mark.asyncio
    async def test_search_non_200_graceful(self):
        """Non-200 status from API should return empty list."""
        mock_client = _build_mock_client([], status_code=401)
        with patch("src.search.tavily_backend.httpx.AsyncClient", return_value=mock_client):
            backend = TavilyBackend(api_key="test-key")
            results = await backend.search("unauthorized query", num=5)
        assert results == []

    @pytest.mark.asyncio
    async def test_search_calls_correct_endpoint(self):
        """Search should POST to Tavily API with correct payload."""
        mock_client = _build_mock_client([
            {"title": "T", "url": "https://x.com", "content": "C", "score": 0.5},
        ])

        with patch("src.search.tavily_backend.httpx.AsyncClient", return_value=mock_client):
            backend = TavilyBackend(api_key="test-key")
            await backend.search("test query", num=3)

        call_args = mock_client.post.call_args
        assert call_args is not None
        url_arg = call_args[0][0] if call_args[0] else call_args.kwargs.get("url", "")
        assert "tavily.com" in url_arg
        json_arg = call_args.kwargs.get("json", {})
        assert json_arg.get("query") == "test query"
        assert json_arg.get("max_results") == 3

    def test_name_property(self):
        """Backend should have name attribute."""
        backend = TavilyBackend(api_key="test-key")
        assert backend.name == "tavily"

    def test_is_search_backend(self):
        """TavilyBackend should be a SearchBackend subclass."""
        backend = TavilyBackend(api_key="test-key")
        assert isinstance(backend, SearchBackend)


class TestTavilyIntegration:

    def test_get_available_backends_includes_tavily_when_key_present(self):
        """When tavily_api_key is set, TavilyBackend should be in backends."""
        config = MagicMock()
        config.tavily_api_key = "tvly-test-123"
        config.google_search_api_key = ""
        config.google_search_cx = ""

        backends = get_available_backends(config)

        names = [b.name for b in backends]
        assert "tavily" in names

    def test_get_available_backends_omits_tavily_when_no_key(self):
        """When tavily_api_key is empty, TavilyBackend should NOT be in backends."""
        config = MagicMock()
        config.tavily_api_key = ""
        config.google_search_api_key = ""
        config.google_search_cx = ""

        backends = get_available_backends(config)

        names = [b.name for b in backends]
        assert "tavily" not in names


class TestTavilySourceQuality:

    def test_classify_high_quality_domains(self):
        backend = TavilyBackend(api_key="test-key")
        assert backend._classify_quality("https://www.example.gov.cn/doc") == "high"
        assert backend._classify_quality("https://example.com") == "medium"
