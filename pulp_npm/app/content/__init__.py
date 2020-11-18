from aiohttp import web

from pulpcore.plugin.content import app

from pulp_npm.app.utils import pulp_npm_content_path
from .handler import NpmContentHandler


app.add_routes([web.get(pulp_npm_content_path() + "{path:.+}", NpmContentHandler().stream_content)])
