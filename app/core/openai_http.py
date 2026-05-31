import httpx

from app.core.exceptions import ConfigurationError, OpenAIAPIError

OPENAI_BASE_URL = "https://api.openai.com/v1"


def _extract_openai_error_message(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return response.text or f"HTTP {response.status_code}"

    error = payload.get("error")
    if isinstance(error, dict):
        return str(error.get("message") or error)
    if error:
        return str(error)
    return response.text or f"HTTP {response.status_code}"


def post_openai(
    path: str,
    *,
    api_key: str | None,
    json_body: dict,
    timeout: float,
    operation: str,
) -> dict:
    if not api_key:
        raise ConfigurationError(f"OPENAI_API_KEY is required for {operation}")

    url = f"{OPENAI_BASE_URL}/{path.lstrip('/')}"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        response = httpx.post(url, headers=headers, json=json_body, timeout=timeout)
    except httpx.TimeoutException as exc:
        raise OpenAIAPIError(
            f"OpenAI {operation} timed out after {timeout}s",
            operation=operation,
        ) from exc
    except httpx.RequestError as exc:
        raise OpenAIAPIError(
            f"OpenAI {operation} request failed: {exc}",
            operation=operation,
        ) from exc

    if response.is_error:
        detail = _extract_openai_error_message(response)
        raise OpenAIAPIError(
            f"OpenAI {operation} failed ({response.status_code}): {detail}",
            operation=operation,
            status_code=response.status_code,
        )

    try:
        return response.json()
    except ValueError as exc:
        raise OpenAIAPIError(
            f"OpenAI {operation} returned invalid JSON",
            operation=operation,
            status_code=response.status_code,
        ) from exc
