"""Expectations module."""

import argparse
import json
import logging
import os

import great_expectations as gx

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s", level=logging.INFO
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

    context = gx.get_context()

    with open(settings_path, "r") as file:
        settings = json.load(file)

    entites = settings["entities"]

    for entity, details in entites.items():
        csv_path = f"{data_path}/{entity}.csv"

        fields = details.get("fields", {})
        for field_name, field_type in fields.items():
            if "datetime" in field_type:
                field_type = "datetime"
            validator = context.sources.pandas_default.read_csv(csv_path)
            result = validator.expect_column_values_to_be_in_type_list(
                field_name, [field_type], parse_strings_as_datetimes=True
            )

            print("")
            logging.info(
                f"Checking expectations for: {csv_path} | column: `{field_name}`"
            )
            logging.info(
                f"Expectations for `{field_name}` values to be type `{field_type}`: {result.get('success')}"  # noqa: E501
            )
            logging.info("Details:")
            logging.info(result)
            print("")


if __name__ == "__main__":
    main()
