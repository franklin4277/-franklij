"""Base class for LLM clients."""

from abc import ABC, abstractmethod
from typing import Any

from ..logger import RetryConfig, async_retry
from ..schema import LLMResponse, Message


class LLMClientBase(ABC):
    """Abstract base class for LLM clients.

    This class defines the interface that all LLM clients must implement,
    regardless of the underlying API protocol (Anthropic, OpenAI, etc.).
    """

    def __init__(
        self,
        api_key: str,
        api_base: str,
        model: str,
        retry_config: RetryConfig | None = None,
    ):
        """Initialize the LLM client.

        Args:
            api_key: API key for authentication
            api_base: Base URL for the API
            model: Model name to use
            retry_config: Optional retry configuration
        """
        self.api_key = api_key
        self.api_base = api_base
        self.model = model
        self.retry_config = retry_config or RetryConfig()

        # Callback for tracking retry count
        self.retry_callback = None

    async def generate(
        self,
        messages: list[Message],
        tools: list[Any] | None = None,
    ) -> LLMResponse:
        """Generate response from LLM.

        Template method implementing the shared 3-step flow used by every
        provider:

        1. ``_prepare_request()`` builds the provider-specific request kwargs
        2. ``_make_api_request()`` performs the call (with retry, if enabled)
        3. ``_parse_response()`` normalizes the raw response to ``LLMResponse``

        Subclasses customize behavior by overriding those three hooks rather
        than this method.

        Args:
            messages: List of conversation messages
            tools: Optional list of Tool objects or dicts

        Returns:
            LLMResponse containing the generated content, thinking, and tool calls
        """
        request_params = self._prepare_request(messages, tools)
        response = await self._request_with_retry(request_params)
        return self._parse_response(response)

    async def _request_with_retry(self, request_params: dict[str, Any]) -> Any:
        """Call ``_make_api_request()``, applying retry logic when enabled.

        Args:
            request_params: Keyword arguments produced by ``_prepare_request()``

        Returns:
            The raw, provider-specific API response
        """
        if self.retry_config.enabled:
            retry_decorator = async_retry(config=self.retry_config, on_retry=self.retry_callback)
            api_call = retry_decorator(self._make_api_request)
            return await api_call(**request_params)

        # Don't use retry
        return await self._make_api_request(**request_params)

    @abstractmethod
    def _prepare_request(
        self,
        messages: list[Message],
        tools: list[Any] | None = None,
    ) -> dict[str, Any]:
        """Prepare the request payload for the API.

        The returned dict is splatted as keyword arguments into
        ``_make_api_request()``, so its keys must match that method's
        parameter names. Providers therefore keep their own request shape
        (e.g. Anthropic passes ``system_message`` separately while OpenAI
        embeds it in ``api_messages``).

        Args:
            messages: List of conversation messages
            tools: Optional list of available tools

        Returns:
            Dictionary containing the request payload
        """
        pass

    @abstractmethod
    async def _make_api_request(self, **request_params: Any) -> Any:
        """Execute the API request (the retryable core call).

        Subclasses declare provider-specific named parameters that must match
        the keys returned by ``_prepare_request()``.

        Args:
            **request_params: Provider-specific request keyword arguments

        Returns:
            The raw, provider-specific API response

        Raises:
            Exception: API call failed
        """
        pass

    @abstractmethod
    def _parse_response(self, response: Any) -> LLMResponse:
        """Parse a raw provider response into an LLMResponse.

        Args:
            response: The raw, provider-specific API response

        Returns:
            LLMResponse object
        """
        pass

    @abstractmethod
    def _convert_messages(self, messages: list[Message]) -> tuple[str | None, list[dict[str, Any]]]:
        """Convert internal message format to API-specific format.

        Args:
            messages: List of internal Message objects

        Returns:
            Tuple of (system_message, api_messages)
        """
        pass
