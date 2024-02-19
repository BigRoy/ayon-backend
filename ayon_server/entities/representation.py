from ayon_server.access.utils import ensure_entity_access
from ayon_server.entities.core import ProjectLevelEntity, attribute_library
from ayon_server.entities.models import ModelSet
from ayon_server.types import ProjectLevelEntityType


class RepresentationEntity(ProjectLevelEntity):
    entity_type: ProjectLevelEntityType = "representation"
    model = ModelSet("representation", attribute_library["representation"])

    async def ensure_create_access(self, user, **kwargs) -> None:
        if user.is_manager:
            return

        await ensure_entity_access(
            user,
            self.project_name,
            "version",
            self.version_id,
            "publish",
        )

    #
    # Properties
    #

    @property
    def version_id(self) -> str:
        return self._payload.version_id

    @version_id.setter
    def version_id(self, value: str):
        self._payload.version_id = value

    @property
    def parent_id(self) -> str:
        return self.version_id
