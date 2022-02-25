import sys
import asyncio

from nxtools import logging, log_traceback, critical_error
from openpype.utils import json_loads
from openpype.lib.postgres import Postgres

from .users import deploy_users
from .roles import deploy_roles
from .attributes import deploy_attributes


# Defaults which should allow OpenPype to run out of the box

DATA = {
    "default_roles": {"viewer": "all"},
    "users": [
        {
            "name": "admin",
            "password": "admin",
            "fullname": "OpenPype admin",
            "roles": {
                "admin": True,
            },
        },
        {
            "name": "manager",
            "password": "manager",
            "fullname": "OpenPype manager",
            "roles": {
                "manager": True,
            },
        },
        {
            "name": "user",
            "password": "user",
            "fullname": "OpenPype user",
        },
    ],
    "roles": [{"name": "viewer", "data": {"read": "all"}}],
}


async def main():
    await Postgres.connect()

    if "-" in sys.argv:
        data = sys.stdin.read()
        try:
            data = json_loads(data)
        except Exception:
            log_traceback()
            critical_error("Invalid setup fileprovided")

        DATA.update(data)
    else:
        logging.warning("No setup file provided. Using defaults")

    await deploy_users(DATA["users"], DATA["default_roles"])
    await deploy_attributes()
    await deploy_roles(DATA.get("roles", {}))

    logging.goodnews("Setup is finished")


if __name__ == "__main__":
    asyncio.run(main())
