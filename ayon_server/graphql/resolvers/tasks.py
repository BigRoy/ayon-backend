from typing import Annotated

from strawberry.types import Info

from ayon_server.entities.core import attribute_library
from ayon_server.graphql.connections import TasksConnection
from ayon_server.graphql.edges import TaskEdge
from ayon_server.graphql.nodes.task import TaskNode
from ayon_server.graphql.resolvers.common import (
    ARGAfter,
    ARGBefore,
    ARGFirst,
    ARGHasLinks,
    ARGIds,
    ARGLast,
    AtrributeFilterInput,
    FieldInfo,
    argdesc,
    create_folder_access_list,
    create_pagination,
    get_has_links_conds,
    resolve,
    sortdesc,
)
from ayon_server.types import validate_name_list, validate_status_list
from ayon_server.utils import SQLTool

SORT_OPTIONS = {
    "name": "tasks.name",
    "status": "tasks.status",
    "createdAt": "tasks.created_at",
    "updatedAt": "tasks.updated_at",
    "taskType": "tasks.folder_type",
}


async def get_tasks(
    root,
    info: Info,
    first: ARGFirst = None,
    after: ARGAfter = None,
    last: ARGLast = None,
    before: ARGBefore = None,
    ids: ARGIds = None,
    task_types: Annotated[
        list[str] | None, argdesc("List of task types to filter by")
    ] = None,
    folder_ids: Annotated[
        list[str] | None, argdesc("List of parent folder IDs to filter by")
    ] = None,
    attributes: Annotated[
        list[AtrributeFilterInput] | None, argdesc("Filter by a list of attributes")
    ] = None,
    names: Annotated[list[str] | None, argdesc("List of names to filter by")] = None,
    statuses: Annotated[
        list[str] | None, argdesc("List of statuses to filter by")
    ] = None,
    tags: Annotated[list[str] | None, argdesc("List of tags to filter by")] = None,
    has_links: ARGHasLinks = None,
    sort_by: Annotated[str | None, sortdesc(SORT_OPTIONS)] = None,
    assignees: Annotated[
        list[str] | None, argdesc("List of assignees to filter by")
    ] = None,
    assignees_any: Annotated[
        list[str] | None, argdesc("List tasks with any of the selected assignees")
    ] = None,
) -> TasksConnection:
    """Return a list of tasks."""

    if folder_ids == ["root"]:
        # this is a workaround to allow selecting tasks along with children folders
        # in a single query of the manager page.
        # (assuming the root element of the project cannot have tasks :) )
        return TasksConnection(edges=[])

    project_name = root.project_name
    fields = FieldInfo(info, ["tasks.edges.node", "task"])

    #
    # SQL
    #

    sql_columns = [
        "tasks.id AS id",
        "tasks.name AS name",
        "tasks.label AS label",
        "tasks.folder_id AS folder_id",
        "tasks.task_type AS task_type",
        "tasks.thumbnail_id AS thumbnail_id",
        "tasks.assignees AS assignees",
        "tasks.attrib AS attrib",
        "tasks.data AS data",
        "tasks.status AS status",
        "tasks.tags AS tags",
        "tasks.active AS active",
        "tasks.created_at AS created_at",
        "tasks.updated_at AS updated_at",
        "tasks.creation_order AS creation_order",
    ]
    sql_conditions = []
    sql_joins = []

    if ids is not None:
        if not ids:
            return TasksConnection()
        sql_conditions.append(f"tasks.id IN {SQLTool.id_array(ids)}")

    if folder_ids is not None:
        if not folder_ids:
            return TasksConnection()
        sql_conditions.append(f"tasks.folder_id IN {SQLTool.id_array(folder_ids)}")
    elif root.__class__.__name__ == "FolderNode":
        # cannot use isinstance here because of circular imports
        sql_conditions.append(f"tasks.folder_id = '{root.id}'")

    # if name:
    #     sql_conditions.append(f"tasks.name ILIKE '{name}'")

    if names is not None:
        if not names:
            return TasksConnection()
        validate_name_list(names)
        sql_conditions.append(f"tasks.name IN {SQLTool.array(names)}")

    if task_types is not None:
        if not task_types:
            return TasksConnection()
        validate_name_list(task_types)
        sql_conditions.append(f"tasks.task_type IN {SQLTool.array(task_types)}")

    if statuses is not None:
        if not statuses:
            return TasksConnection()
        validate_status_list(statuses)
        sql_conditions.append(f"status IN {SQLTool.array(statuses)}")
    if tags is not None:
        if not tags:
            return TasksConnection()
        validate_name_list(tags)
        sql_conditions.append(f"tasks.tags @> {SQLTool.array(tags, curly=True)}")

    if assignees is not None:
        if not assignees:
            return TasksConnection()
        sql_conditions.append(
            f"tasks.assignees @> {SQLTool.array(assignees, curly=True)}"
        )

    if assignees_any is not None:
        if not assignees_any:
            return TasksConnection()
        sql_conditions.append(
            f"tasks.assignees && {SQLTool.array(assignees_any, curly=True)}"
        )

    if has_links is not None:
        sql_conditions.extend(get_has_links_conds(project_name, "tasks.id", has_links))

    access_list = await create_folder_access_list(root, info)
    if access_list is not None:
        sql_conditions.append(
            f"hierarchy.path like ANY ('{{ {','.join(access_list)} }}')"
        )

    if attributes:
        for attribute_input in attributes:
            if not attribute_library.is_valid("task", attribute_input.name):
                continue
            values = [v.replace("'", "''") for v in attribute_input.values]
            sql_conditions.append(
                f"""
                (coalesce(pf.attrib, '{{}}'::jsonb ) || tasks.attrib)
                ->>'{attribute_input.name}' IN {SQLTool.array(values)}
                """
            )

    #
    # Joins
    #

    if attributes or fields.any_endswith("attrib"):
        sql_columns.append("pf.attrib as parent_folder_attrib")
        sql_joins.append(
            f"""
            LEFT JOIN project_{project_name}.exported_attributes AS pf
            ON tasks.folder_id = pf.folder_id
            """
        )
    else:
        sql_columns.append("'{}'::JSONB as parent_folder_attrib")

    if "folder" in fields or (access_list is not None):
        sql_columns.extend(
            [
                "folders.id AS _folder_id",
                "folders.name AS _folder_name",
                "folders.label AS _folder_label",
                "folders.folder_type AS _folder_folder_type",
                "folders.thumbnail_id AS _folder_thumbnail_id",
                "folders.parent_id AS _folder_parent_id",
                "folders.attrib AS _folder_attrib",
                "folders.data AS _folder_data",
                "folders.active AS _folder_active",
                "folders.status AS _folder_status",
                "folders.tags AS _folder_tags",
                "folders.created_at AS _folder_created_at",
                "folders.updated_at AS _folder_updated_at",
            ]
        )
        sql_joins.append(
            f"""
            INNER JOIN project_{project_name}.folders
            ON folders.id = tasks.folder_id
            """
        )

        if any(
            field.endswith("folder.path") or field.endswith("folder.parents")
            for field in fields
        ) or (access_list is not None):
            sql_columns.append("hierarchy.path AS _folder_path")
            sql_joins.append(
                f"""
                LEFT JOIN project_{project_name}.hierarchy AS hierarchy
                ON folders.id = hierarchy.id
                """
            )

        if any(field.endswith("folder.attrib") for field in fields):
            sql_columns.extend(
                [
                    "pr.attrib as _folder_project_attributes",
                    "ex.attrib as _folder_inherited_attributes",
                ]
            )
            sql_joins.extend(
                [
                    f"""
                    LEFT JOIN project_{project_name}.exported_attributes AS ex
                    ON folders.parent_id = ex.folder_id
                    """,
                    f"""
                    INNER JOIN public.projects AS pr
                    ON pr.name ILIKE '{project_name}'
                    """,
                ]
            )
        else:
            sql_columns.extend(
                [
                    "'{}'::JSONB as _folder_project_attributes",
                    "'{}'::JSONB as _folder_inherited_attributes",
                ]
            )

    #
    # Pagination
    #

    order_by = ["tasks.creation_order"]
    if sort_by is not None:
        if sort_by in SORT_OPTIONS:
            order_by.insert(0, SORT_OPTIONS[sort_by])
        elif sort_by.startswith("attrib."):
            order_by.insert(0, f"tasks.attrib->>'{sort_by[7:]}'")
        else:
            raise ValueError(f"Invalid sort_by value: {sort_by}")

    paging_fields = FieldInfo(info, ["tasks"])
    need_cursor = paging_fields.has_any(
        "tasks.pageInfo.startCursor",
        "tasks.pageInfo.endCursor",
        "tasks.edges.cursor",
    )

    pagination, paging_conds, cursor = create_pagination(
        order_by,
        first,
        after,
        last,
        before,
        need_cursor=need_cursor,
    )
    sql_conditions.extend(paging_conds)

    #
    # Query
    #

    query = f"""
        SELECT {cursor}, {", ".join(sql_columns)}
        FROM project_{project_name}.tasks AS tasks
        {" ".join(sql_joins)}
        {SQLTool.conditions(sql_conditions)}
        {pagination}
    """

    return await resolve(
        TasksConnection,
        TaskEdge,
        TaskNode,
        project_name,
        query,
        first,
        last,
        context=info.context,
    )


async def get_task(root, info: Info, id: str) -> TaskNode | None:
    """Return a task node based on its ID"""
    if not id:
        return None
    connection = await get_tasks(root, info, ids=[id])
    if not connection.edges:
        return None
    return connection.edges[0].node
