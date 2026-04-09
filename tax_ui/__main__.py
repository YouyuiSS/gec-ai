from __future__ import annotations

import os

import uvicorn


def main() -> None:
    uvicorn.run(
        "tax_ui.app:app",
        host=os.getenv("TAX_UI_HOST", "127.0.0.1"),
        port=int(os.getenv("TAX_UI_PORT", "8000")),
        reload=False,
    )


if __name__ == "__main__":
    main()
