import os

import uvicorn


def resolve_port() -> int:
    """Prefer Railway's injected port while preserving the local default."""
    value = os.getenv("PORT") or os.getenv("AELORA_GATEWAY_PORT", "4100")
    port = int(value)
    if not 1 <= port <= 65_535:
        raise ValueError("Gateway port must be between 1 and 65535.")
    return port


def main() -> None:
    uvicorn.run(
        "aelora_virtual_gateway.main:app",
        host=os.getenv("AELORA_GATEWAY_HOST", "127.0.0.1"),
        port=resolve_port(),
        reload=os.getenv("AELORA_GATEWAY_RELOAD", "false").lower() == "true",
    )


if __name__ == "__main__":
    main()
