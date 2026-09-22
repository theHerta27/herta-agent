"""One Windows-compatible loopback service process; never a multiworker launcher."""

import argparse
from pathlib import Path

import uvicorn

from herta_agent.service.app import create_app
from herta_agent.service.settings import ServiceSettings


def main():
    parser = argparse.ArgumentParser(description="Herta local backend")
    parser.add_argument("--provider", choices=("openai", "demo"))
    parser.add_argument("--host", choices=("127.0.0.1",))
    parser.add_argument("--workers", type=int, choices=(1,))
    parser.add_argument("--port", type=int)
    parser.add_argument("--db", type=Path, dest="db_path")
    parser.add_argument("--soul", type=Path, dest="soul_path")
    args = {key: value for key, value in vars(parser.parse_args()).items() if value is not None}
    settings = ServiceSettings(**{**ServiceSettings.from_env().model_dump(), **args})
    uvicorn.run(
        create_app(settings),
        host=settings.host,
        port=settings.port,
        workers=1,
        access_log=False,
        timeout_graceful_shutdown=15,
    )


if __name__ == "__main__":
    main()
