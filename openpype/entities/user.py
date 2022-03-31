"""User entity."""

from nxtools import logging

from openpype.access.permissions import Permissions
from openpype.access.roles import Roles
from openpype.exceptions import RecordNotFoundException
from openpype.lib.postgres import Postgres
from openpype.utils import SQLTool, dict_exclude

from .common import Entity, EntityType, attribute_library
from .models import ModelSet


class UserEntity(Entity):
    entity_type = EntityType.USER
    entity_name = "user"
    model = ModelSet("user", attribute_library["user"], has_id=False)

    #
    # Load
    #

    @classmethod
    async def load(cls, name: str, transaction=None) -> "UserEntity":
        """Load a user from the database."""

        if not (
            user_data := await Postgres.fetch(
                "SELECT * FROM public.users WHERE name = $1", name
            )
        ):
            raise RecordNotFoundException(f"Unable to load user {name}")
        return cls.from_record(exists=True, validate=False, **dict(user_data[0]))

    #
    # Save
    #

    async def save(self, transaction=None) -> bool:
        """Save the user to the database."""

        conn = transaction or Postgres

        if self.exists:
            data = dict_exclude(self.dict(exclude_none=True), ["ctime", "name"])
            await conn.execute(
                *SQLTool.update(
                    "public.users",
                    f"WHERE name='{self.name}'",
                    **data,
                )
            )
            return True

        await conn.execute(*SQLTool.insert("users", **self.dict(exclude_none=True)))
        return True

    #
    # Delete
    #

    async def delete(self, transaction=None) -> bool:
        """Delete existing user."""
        logging.info(f"Deleting user {self.name}")
        if not self.name:
            raise RecordNotFoundException(
                f"Unable to delete user {self.name}. Not loaded."
            )

        commit = not transaction
        transaction = transaction or Postgres
        res = await transaction.fetch(
            """
            WITH deleted AS (
                DELETE FROM users
                WHERE name=$1
                RETURNING *
            ) SELECT count(*) FROM deleted;
            """,
            self.name,
        )
        count = res[0]["count"]

        if commit:
            await self.commit(transaction)
        if count:
            logging.info(f"Deleted user {self.name}")
        else:
            logging.error(f"Unable to delete user {self.name}")
        return not not count

    #
    # Authorization helpers
    #

    @property
    def is_admin(self) -> bool:
        if not (roles := self._payload.data.get("roles")):
            return False
        return roles.get("admin", False)

    @property
    def is_manager(self) -> bool:
        if not (roles := self._payload.data.get("roles")):
            return False
        return roles.get("manager", False) or roles.get("admin", False)

    def permissions(self, project_name: str | None = None) -> Permissions:
        """Return user permissions on a given project.

        When a project is not specified, only return permissions the user
        has on all projects.
        """

        active_roles = []
        for role_name, projects in self._payload.data.get("roles", {}).items():
            if projects == "all" or (
                isinstance(projects, list) and project_name in projects
            ):
                active_roles.append(role_name)

        return Roles.combine(active_roles, project_name)
