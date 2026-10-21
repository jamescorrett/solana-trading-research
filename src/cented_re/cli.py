import asyncio

from rich.console import Console

from .collector import collect
from .config import Settings

console = Console()


def main() -> None:
    try:
        settings = Settings()
    except Exception as exc:
        console.print(f"[red]Configuration error:[/red] {exc}")
        raise SystemExit(2) from exc
    asyncio.run(collect(settings))


if __name__ == "__main__":
    main()
