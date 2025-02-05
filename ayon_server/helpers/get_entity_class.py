from typing import Literal, Type, TypeVar, overload

from ayon_server.entities import (
    FolderEntity,
    ProductEntity,
    RepresentationEntity,
    TaskEntity,
    VersionEntity,
    WorkfileEntity,
)
from ayon_server.entities.core import ProjectLevelEntity
from ayon_server.types import ProjectLevelEntityType

T = TypeVar("T", bound=ProjectLevelEntity)

FolderLiteral = Literal["folder"]
TaskLiteral = Literal["task"]
ProductLiteral = Literal["product"]
VersionLiteral = Literal["version"]
RepresentationLiteral = Literal["representation"]
WorkfileLiteral = Literal["workfile"]


@overload
def get_entity_class(entity_type: FolderLiteral) -> Type[FolderEntity]: ...
@overload
def get_entity_class(entity_type: TaskLiteral) -> Type[TaskEntity]: ...
@overload
def get_entity_class(entity_type: ProductLiteral) -> Type[ProductEntity]: ...
@overload
def get_entity_class(entity_type: VersionLiteral) -> Type[VersionEntity]: ...
@overload
def get_entity_class(
    entity_type: RepresentationLiteral,
) -> Type[RepresentationEntity]: ...
@overload
def get_entity_class(entity_type: WorkfileLiteral) -> Type[WorkfileEntity]: ...


def get_entity_class(entity_type: ProjectLevelEntityType) -> Type[ProjectLevelEntity]:
    return {
        "folder": FolderEntity,
        "task": TaskEntity,
        "product": ProductEntity,
        "version": VersionEntity,
        "representation": RepresentationEntity,
        "workfile": WorkfileEntity,
    }[entity_type]
