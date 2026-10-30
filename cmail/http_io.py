"""Bounded response reads shared by synchronous provider transports."""

GMAIL_RESPONSE_BYTES = 8 * 1024 * 1024
GRAPH_RESPONSE_BYTES = 2 * 1024 * 1024
ERROR_RESPONSE_BYTES = 256 * 1024


def read_limited(stream, limit: int) -> bytes:
    data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError('A resposta do provedor excede o limite permitido.')
    return data
