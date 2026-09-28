from __future__ import annotations

import logging
import signal
import sys
from typing import Any

import upstox_client

from app.core.config import get_settings
from app.services.instruments import download_mcx_instruments, select_gold_futures
from app.services.normalizer import normalize_message
from workers.mongo_writer import MongoMarketWriter


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("gold-collector")


def run() -> None:
    settings = get_settings()
    if not settings.upstox_access_token:
        raise ValueError("UPSTOX_ACCESS_TOKEN is missing in .env")

    logger.info("Downloading today's MCX instrument master")
    instruments = download_mcx_instruments(settings.mcx_instruments_url)
    contracts = select_gold_futures(
        instruments, settings.gold_underlying_symbol, settings.gold_contract_count
    )
    by_key = {contract["instrument_key"]: contract for contract in contracts}
    for contract in contracts:
        logger.info(
            "Selected %s | key=%s | expiry=%s",
            contract.get("trading_symbol"),
            contract["instrument_key"],
            contract.get("expiry"),
        )

    writer = MongoMarketWriter(
        uri=settings.mongodb_uri,
        database=settings.mongodb_database,
        batch_size=settings.write_batch_size,
        flush_seconds=settings.write_flush_seconds,
        queue_max_size=settings.queue_max_size,
    )
    for contract in contracts:
        writer.save_instrument(contract)
    writer.start()

    configuration = upstox_client.Configuration()
    configuration.access_token = settings.upstox_access_token
    streamer = upstox_client.MarketDataStreamerV3(
        upstox_client.ApiClient(configuration),
        list(by_key),
        settings.upstox_mode,
    )
    streamer.auto_reconnect(True, 5, 20)

    def on_open(*_: Any) -> None:
        logger.info("Upstox WebSocket connected; collecting %s Gold contract(s)", len(by_key))

    def on_message(message: Any) -> None:
        if not isinstance(message, dict):
            return
        feeds = message.get("feeds") or {}
        for instrument_key in feeds:
            contract = by_key.get(instrument_key)
            if contract is None:
                continue
            document = normalize_message(
                message,
                instrument_key,
                contract,
                # Raw message holds every contract; keep it once, on the nearest.
                settings.store_raw_message and instrument_key == contracts[0]["instrument_key"],
            )
            if document:
                writer.submit(document)

    def on_error(*args: Any) -> None:
        logger.error("Upstox WebSocket error: %s", args)

    def on_close(*args: Any) -> None:
        logger.warning("Upstox WebSocket closed: %s", args)

    def shutdown(*_: Any) -> None:
        logger.info("Stopping collector")
        try:
            streamer.disconnect()
        finally:
            writer.close()
        raise SystemExit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)
    streamer.on("open", on_open)
    streamer.on("message", on_message)
    streamer.on("error", on_error)
    streamer.on("close", on_close)

    try:
        streamer.connect()
    except KeyboardInterrupt:
        shutdown()
    except Exception:
        logger.exception("Collector stopped because of an unrecoverable error")
        writer.close()
        sys.exit(1)


if __name__ == "__main__":
    run()

