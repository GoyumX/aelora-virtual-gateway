import os

import uvicorn


def main() -> None:
    uvicorn.run(
        "aelora_virtual_gateway.main:app",
        host=os.getenv("AELORA_GATEWAY_HOST", "127.0.0.1"),
        port=int(os.getenv("AELORA_GATEWAY_PORT", "4100")),
        reload=os.getenv("AELORA_GATEWAY_RELOAD", "false").lower() == "true",
    )


if __name__ == "__main__":
    main()
