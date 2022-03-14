import strawberry

from openpype.utils import json_loads
from openpype.entities.user import UserEntity


def parse_json_data(target_type, json_string):
    data = json_loads(json_string)
    if not data:
        return target_type()
    result = {}
    for key in target_type.__dataclass_fields__.keys():
        if key in data:
            result[key] = data[key]
    return target_type(**result)


def parse_attrib_data(
    target_type,
    json_string: str,
    user: UserEntity,
    project_name: str = None,
):
    """ACL agnostic attribute list parser"""

    if user.is_manager:
        attr_limit = "all"
    else:
        perms = user.permissions(project_name)
        attr_limit = perms.attrib_read

    data = json_loads(json_string)
    if not data:
        return target_type()
    result = {}
    for key in target_type.__dataclass_fields__.keys():
        if key in data:
            if attr_limit == "all" or key in attr_limit:
                result[key] = data[key]
    return target_type(**result)


def lazy_type(name: str, module: str) -> strawberry.LazyType:
    """Create a lazy type for the given module and name.

    When used, module path must be relative
    to THIS file (root of the graphql module)
    e.g. `.nodes.node` or `.connection`
    """
    return strawberry.LazyType[name, module]
