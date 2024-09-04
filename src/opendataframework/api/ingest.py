"""Ingest module."""

import argparse
import csv
import json
import logging
import os
from datetime import datetime
from time import sleep
from typing import Set

import httpx

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s", level=logging.INFO
)

logging.getLogger("httpx").propagate = False


API_URL = "http://0.0.0.0:{port}/api/v1/{entity}/"  # TODO: nginx url format


def load_file(
    filepath: str,
    api_url: str,
    entity: dict,
    positive_path: str,
    negative_path: str,
    skip_cols: Set = None,
    time_interval: int = 0,
):
    """Load file via API."""
    logging.info(f"Uploading {filepath}")
    if skip_cols is None:
        skip_cols = set()

    start_time = datetime.now()
    success = failed = 0
    with open(filepath, newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        for i, row in enumerate(reader, start=1):
            current_row = {k: v for k, v in row.items() if k not in skip_cols}
            row_mapped = {}
            # rename fields to match api model (TODO?)
            for field_name, value in current_row.items():
                try:
                    date_format = entity["fields"][field_name].split("datetime|")[1]
                except IndexError:
                    date_format = None

                if date_format:
                    try:
                        timestamp = datetime.strptime(value, date_format)
                        row_mapped[field_name] = timestamp.isoformat()
                    except ValueError as e:
                        logging.error(f"{e} in [{filepath}], row {i}: {row}")
                        break
                else:
                    row_mapped[field_name] = value

            if not row_mapped:
                failed += 1
                continue

            if time_interval:
                logging.info(f"[{filepath}] Sleep for: {time_interval}")  # noqa
                sleep(time_interval.total_seconds())

            try:
                http_request = httpx.post(api_url, json=row_mapped)
                if http_request.status_code == httpx.codes.CREATED:
                    success += 1
                    logging.info(f"Row {i} ingested successfully")
                    fpath = os.path.join(os.getcwd(), positive_path)

                    if not os.path.exists(fpath):
                        with open(positive_path, "w", newline="") as csvfile:
                            fieldnames = list(row.keys())
                            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                            writer.writeheader()

                    with open(positive_path, "a", newline="") as csvfile:
                        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                        writer.writerow(row)

                    continue

                elif http_request.status_code == httpx.codes.UNPROCESSABLE_ENTITY:
                    logging.error(
                        f"[{api_url}] [{http_request.status_code}] Schema mismatch for the row: {i}. Skipped."  # noqa: E501
                    )
                else:
                    logging.error(
                        f"[{api_url}] [{http_request.status_code}] Request failed for the row: {i}. Skipped."  # noqa: E501
                    )

                failed += 1

                fpath = os.path.join(os.getcwd(), negative_path)

                if not os.path.exists(fpath):
                    with open(negative_path, "w", newline="") as csvfile:
                        fieldnames = list(row.keys())
                        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                        writer.writeheader()

                with open(negative_path, "a", newline="") as csvfile:
                    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                    writer.writerow(row)
            except Exception as e:
                logging.error(f"{e}. URL: {api_url}. The last processed row: {i}")
                break

    end_time = datetime.now()
    logging.info(
        f"File {filepath}. Status: Uploaded {success}/{success + failed}. Time: {end_time - start_time}."  # noqa: E501
    )


def main():
    """Main."""
    parser = argparse.ArgumentParser(description="opendataframework")
    parser.add_argument(
        "-d",
        "--data",
        nargs="?",
        type=str,
        const=None,
        default=None,
        help="Data folder",
    )

    args = parser.parse_args()
    if args.data:
        if os.getcwd() in args.data:
            data_path = args.data
        elif args.data.startswith("/"):
            data_path = os.getcwd() + args.data
        else:
            data_path = os.getcwd() + "/" + args.data
    else:
        data_path = os.getcwd() + "/data"

    settings_path = os.getcwd() + "/settings.json"

    logging.info(f"Data: {data_path}")
    logging.info(f"Settings: {settings_path}")

    with open(settings_path, "r") as file:
        settings = json.load(file)

    entites = settings["entities"]
    folder_name = datetime.now().strftime("%Y%m%d-%H%M%S")
    successful_path = os.path.join(os.getcwd(), f"ingestion/{folder_name}/successful/")
    os.makedirs(successful_path)
    failed_path = os.path.join(os.getcwd(), f"ingestion/{folder_name}/failed/")
    os.makedirs(failed_path)

    for entity in entites:
        csv_path = f"{data_path}/{entity}.csv"

        components = entites[entity].get("layers", {}).get("api", {})
        for component, config in components.items():
            port = config.get("port")
            if not port:
                continue
            api_url = API_URL.format(port=port, entity=entity)
            load_file(
                csv_path,
                api_url,
                entites[entity],
                positive_path=f"{successful_path}/{entity}.csv",
                negative_path=f"{failed_path}/{entity}.csv",
            )


if __name__ == "__main__":
    main()
