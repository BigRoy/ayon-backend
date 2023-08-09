from datetime import datetime

import httpx
from fastapi import Request
from pydantic import Field

from ayon_server.api.dependencies import CurrentUser, YnputConnectKey
from ayon_server.api.responses import EmptyResponse
from ayon_server.config import ayonconfig
from ayon_server.exceptions import ForbiddenException
from ayon_server.installer.models import DependencyPackageManifest, InstallerManifest
from ayon_server.lib.postgres import Postgres
from ayon_server.types import OPModel

from .router import router


class ReleaseAddon(OPModel):
    name: str = Field(..., example="tvpaint")
    version: str = Field(..., example="1.0.0")
    url: str = Field(
        ...,
        description="URL to download the addon zip file",
        example="https://get.ayon.io/addons/tvpaint-1.0.0.zip",
    )
    checksum: str | None = Field(
        None,
        description="Checksum of the zip file",
        example="sha256:1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
    )


class ReleaseInfoModel(OPModel):
    name: str = Field(..., title="Release name", example="2023.08-2D")
    created_at: datetime = Field(default_factory=datetime.now)
    addons: list[ReleaseAddon] = Field(default_factory=list)
    installers: list[InstallerManifest] | None = Field(None)
    dependency_packages: list[DependencyPackageManifest] = Field(None)


class ReleaseListItemModel(OPModel):
    name: str = Field(..., title="Release name", example="2023.08-2D")
    bio: str = Field("", title="Release bio", example="2D Animation")
    icon: str = Field("", title="Release icon", example="skeleton")
    created_at: datetime = Field(...)
    is_latest: bool = Field(...)
    addons: list[str] = Field(...)


class ReleaseListModel(OPModel):
    releases: list[ReleaseListItemModel] = Field(...)


@router.post("/abort")
async def abort_onboarding(request: Request, user: CurrentUser) -> EmptyResponse:
    """Abort the onboarding process (disable nag screen)"""

    if not user.is_admin:
        raise ForbiddenException()

    await Postgres().execute(
        """
        INSERT INTO config (key, value)
        VALUES ('onboardingFinished', 'true'::jsonb)
        """
    )

    return EmptyResponse()


@router.get("/releases")
async def get_releases(ynput_connect_key: YnputConnectKey) -> ReleaseListModel:
    """Get the releases"""

    params = {"key": ynput_connect_key}

    async with httpx.AsyncClient() as client:
        res = await client.get(
            f"{ayonconfig.ynput_connect_url}/api/releases",
            params=params,
        )

    return ReleaseListModel(**res.json())


@router.get("/releases/{release_name}")
async def get_release_info(
    ynput_connect_key: YnputConnectKey, release_name: str
) -> ReleaseInfoModel:
    """Get the release info"""

    params = {"key": ynput_connect_key}

    async with httpx.AsyncClient() as client:
        res = await client.get(
            f"{ayonconfig.ynput_connect_url}/api/releases/{release_name}",
            params=params,
        )

    return ReleaseInfoModel(**res.json())
