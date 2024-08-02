from datetime import datetime
from typing import Optional

import asyncclick as click
from tqdm.asyncio import tqdm
from tqdm.contrib.logging import logging_redirect_tqdm

from spire_csda.client import Client
from spire_csda.config import Settings
from spire_csda.models.search import CSDASearch


@click.group()
@click.option("--username", envvar="CSDA_USERNAME", required=False)
@click.option("--password", envvar="CSDA_PASSWORD", required=False)
@click.option("--settings-file", envvar="CSDA_SETTINGS_FILE", default=".env")
@click.pass_context
def cli(ctx, username, password, settings_file):
    config = Settings(_env_file=settings_file)
    if username is not None:
        config = config.copy(update={"username": username})
    if password is not None:
        config = config.copy(update={"password": username})
    ctx.ensure_object(dict)
    ctx.obj["config"] = ctx.with_resource(config.context())
    ctx.obj["client"] = Client()


@cli.command()
@click.pass_obj
async def token(obj):
    """Print an authentication token for STAC endpoints.

    This will log into the STAC catalog with the provided credentials.  The
    token returned will be valid for up to one hour.  In order to use this
    token, pass it as a Bearer token in the Authentication header.

    \b
    For example
    curl -H "Authentication:Bearer <token>" https://nasa-csda.wx.spire.com/stac/collections
    """
    client: Client = obj["client"]
    async with client.session():
        click.echo(await client.get_token())


@cli.command()
@click.option("--start-date", type=click.DateTime(), default=datetime(2019, 1, 1))
@click.option("--end-date", type=click.DateTime(), default=datetime.now())
@click.option("--min-latitude", type=click.FloatRange(min=-90, max=90), default=-90)
@click.option("--max-latitude", type=click.FloatRange(min=-90, max=90), default=90)
@click.option("--min-longitude", type=click.FloatRange(min=-180, max=180), default=-180)
@click.option("--max-longitude", type=click.FloatRange(min=-180, max=180), default=180)
@click.option("--products", default="", help="A comma-separated list of product names")
@click.option("--limit", type=click.IntRange(min=1), help="Stop after finding this many items")
@click.option(
    "--mode",
    type=click.Choice(["download", "list", "raw"]),
    default="download",
    help="Operational mode (see help)",
)
@click.option(
    "--progress/--no-progress",
    default=True,
    help="Enable progress reporting while downloading",
)
@click.option(
    "--destination",
    default="csda/{product}/{datetime:%Y}/{datetime:%m}/{datetime:%d}",
    help="Configure download location",
)
@click.option(
    "--overwrite/--no-overwrite",
    default=True,
    help="Overwrite existing files when downloading",
)
@click.pass_context
async def query(
    ctx,
    start_date: datetime,
    end_date: datetime,
    min_latitude: float,
    max_latitude: float,
    min_longitude: float,
    max_longitude: float,
    products: str,
    limit: Optional[int],
    mode: str,
    progress: bool,
    destination: str,
    overwrite: bool,
):
    """
    Query data from the CSDA STAC catalog.

    This command can return data in three modes:

    \b
    * download: download files
    * list:     show urls
    * raw:      show raw geojson items

    When in download mode, you can configure the path where the file is placed
    with a format-style string as the `destination` parameter. This parameter
    allows you to provide any static path as well as sort the downloads into
    prefixes based on properties of the file.  These properties include:

    \b
    * collection
    * datetime
    * receiver
    * product

    In addition, it supports standard python format strings, so you can extract
    components of the datetime as path elements such as `{datetime:%Y-%m-%d}`
    to make a subdirectory for each day.

    The default destination is `csda/{product}/{datetime:%Y}/{datetime:%m}/{datetime:%d}`.
    """
    obj = ctx.obj
    if min_latitude > max_latitude:
        raise click.BadParameter(
            "min-latitude must be <= max-latitude",
            ctx,
            "max-latitude",
            ["min-latitude", "max-latitude"],
        )
    if min_longitude > max_longitude:
        raise click.BadParameter(
            "min-longitude must be <= max-longitude",
            ctx,
            "max-longitude",
            ["min-longitude", "max-longitude"],
        )
    if start_date > end_date:
        raise click.BadParameter(
            "start-date must be <= end-date",
            ctx,
            "end-date",
            ["start-date", "end-date"],
        )

    client: Client = obj["client"]
    search = CSDASearch.build_query(
        start_date,
        end_date,
        min_latitude,
        max_latitude,
        min_longitude,
        max_longitude,
        products,
    )
    async with client.session():
        if mode == "download":
            with tqdm(unit=" files", disable=not progress) as pbar, logging_redirect_tqdm():
                async for link in client.download_query(
                    search,
                    limit=limit,
                    progress=progress,
                    overwrite=overwrite,
                    prefix=destination,
                ):
                    pbar.update(1)
        elif mode == "list":
            async for link in client.download_links(search, limit=limit):
                click.echo(link)
        elif mode == "raw":
            async for item in client.search_parallel(search, limit=limit):
                click.echo(item.json(exclude_none=True, by_alias=True))
