import asyncio
import json
import os
import re
import shutil
import tempfile
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor

import aiofiles
import httpx
import semver
import yaml
from nxtools import logging
from pydantic import BaseModel

from ayon_server.config import ayonconfig
from ayon_server.events import update_event
from ayon_server.exceptions import AyonException
from ayon_server.version import __version__ as ayon_version


class UnsupportedAddonException(AyonException):
    status = 409


class AddonZipInfo(BaseModel):
    name: str
    version: str
    min_ayon_version: str  # inclusive
    max_ayon_version: str | None = None  # exclusive
    is_rez: bool = False


def get_addon_info_from_manifest(manifest_data: str) -> AddonZipInfo:
    """Returns the addon name and version from the manifest"""
    manifest = json.loads(manifest_data)
    if not (manifest.get("addon_name") and manifest.get("addon_version")):
        raise UnsupportedAddonException("Addon name or version not found in manifest")
    return AddonZipInfo(
        name=manifest.get("name"),
        version=manifest.get("version"),
        min_ayon_version="1.0.0",
        max_ayon_version="1.2.0",
    )


def get_addon_info_from_package_py(manifest_data: str) -> AddonZipInfo:
    """Returns the addon name and version from the package file

    This will be reimplemented using Rez in the future
    """

    name_pattern = r'name\s*=\s*"([^"]+)"'
    version_pattern = r'version\s*=\s*"([^"]+)"'

    name_match = re.search(name_pattern, manifest_data)
    version_match = re.search(version_pattern, manifest_data)

    package_name = name_match.group(1) if name_match else None
    package_version = version_match.group(1) if version_match else None

    if not (package_name and package_version):
        raise UnsupportedAddonException("Addon name or version not found in package.py")

    return AddonZipInfo(
        name=package_name,
        version=package_version,
        is_rez=True,
        min_ayon_version="1.0.3",
    )


def get_addon_info_from_package_yaml(manifest_data: str) -> AddonZipInfo:
    manifest = yaml.safe_load(manifest_data)
    if not (manifest.get("name") and manifest.get("version")):
        raise UnsupportedAddonException(
            "Addon name or version not found in package.yaml"
        )

    return AddonZipInfo(
        name=manifest.get("name"),
        version=manifest.get("version"),
        is_rez=True,
        min_ayon_version="1.0.3",
    )


def get_addon_zip_info(path: str) -> AddonZipInfo:
    """Returns the addon name and version from the zip file"""
    zip_info: AddonZipInfo | None = None
    PARSERS = [
        ("manifest.json", get_addon_info_from_manifest),
        ("package.yaml", get_addon_info_from_package_yaml),
        ("package.yml", get_addon_info_from_package_yaml),
        ("package.py", get_addon_info_from_package_py),
    ]
    with zipfile.ZipFile(path, "r") as zip_ref:
        names = zip_ref.namelist()

        for manifest_name, parser in PARSERS:
            if manifest_name in names:
                with zip_ref.open(manifest_name) as manifest_file:
                    manifest = manifest_file.read().decode("utf-8")
                    zip_info = parser(manifest)
                    break

    if zip_info is None:
        raise UnsupportedAddonException("Unsupported addon format")

    if semver.compare(ayon_version, zip_info.min_ayon_version) < 0:
        raise UnsupportedAddonException(
            f"Ayon version {ayon_version} is not supported by this addon"
        )

    if (
        zip_info.max_ayon_version
        and semver.compare(ayon_version, zip_info.max_ayon_version) >= 0
    ):
        raise UnsupportedAddonException(
            f"Ayon version {ayon_version} is not supported by this addon"
        )

    return zip_info


def unpack_addon_sync(zip_path: str, zip_info: AddonZipInfo) -> None:
    addon_root_dir = ayonconfig.addons_dir
    os.makedirs(addon_root_dir, exist_ok=True)
    target_dir = os.path.join(addon_root_dir, zip_info.name, zip_info.version)

    with tempfile.TemporaryDirectory(dir=addon_root_dir) as tmpdirname:
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            for member in zip_ref.infolist():
                extracted_path = zip_ref.extract(member, tmpdirname)

                # Preserve the file permissions
                original_mode = member.external_attr >> 16
                if original_mode:
                    os.chmod(extracted_path, original_mode)

        if os.path.isdir(target_dir):
            logging.info(f"Removing existing addon {zip_info.name} {zip_info.version}")
            shutil.rmtree(target_dir)

        # move the extracted files to the target directory
        if zip_info.is_rez:
            # rez packages don't have 'addon' directory, we need to move all files
            # from the temp directory to the target directory

            for root, dirs, files in os.walk(tmpdirname):
                for file in files:
                    source_file = os.path.join(root, file)
                    target_file = os.path.join(
                        target_dir, os.path.relpath(source_file, tmpdirname)
                    )
                    os.makedirs(os.path.dirname(target_file), exist_ok=True)
                    shutil.move(source_file, target_file)

            # and remove the temp directory
            shutil.rmtree(tmpdirname)

        else:
            shutil.move(os.path.join(tmpdirname, "addon"), target_dir)


async def unpack_addon(event_id: str, zip_path: str, zip_info: AddonZipInfo):
    """Unpack the addon from the zip file and install it

    Unpacking is done in a separate thread to avoid blocking the main thread
    (unzipping is a synchronous operation and it is also cpu-bound)

    After the addon is unpacked, the event is finalized and the zip file is removed.
    """

    await update_event(
        event_id,
        description=f"Unpacking addon {zip_info.name} {zip_info.version}",
        status="in_progress",
    )

    loop = asyncio.get_event_loop()

    try:
        with ThreadPoolExecutor() as executor:
            task = loop.run_in_executor(executor, unpack_addon_sync, zip_path, zip_info)
            await asyncio.gather(task)
    except Exception as e:
        logging.error(f"Error while unpacking addon: {e}")
        await update_event(
            event_id,
            description=f"Error while unpacking addon: {e}",
            status="failed",
        )

    try:
        os.remove(zip_path)
    except Exception as e:
        logging.error(f"Error while removing zip file: {e}")

    await update_event(
        event_id,
        description=f"Addon {zip_info.name} {zip_info.version} installed",
        status="finished",
    )


async def install_addon_from_url(event_id: str, url: str) -> None:
    """Download the addon zip file from the URL and install it"""

    await update_event(
        event_id,
        description=f"Downloading addon from URL {url}",
        status="in_progress",
    )

    # Download the zip file
    # we do not use download_file() here because using NamedTemporaryFile
    # is much more convenient than manually creating a temporary file

    file_size = 0
    last_time = 0.0

    i = 0
    with tempfile.NamedTemporaryFile(dir=ayonconfig.addons_dir) as temporary_file:
        zip_path = temporary_file.name
        async with httpx.AsyncClient(timeout=ayonconfig.http_timeout) as client:
            async with client.stream("GET", url) as response:
                file_size = int(response.headers.get("content-length", 0))
                async with aiofiles.open(zip_path, "wb") as f:
                    async for chunk in response.aiter_bytes():
                        await f.write(chunk)
                        i += len(chunk)

                        if file_size and (time.time() - last_time > 1):
                            percent = int(i / file_size * 100)
                            await update_event(
                                event_id,
                                progress=int(percent / 2),
                                store=False,
                            )
                            last_time = time.time()

        # Get the addon name and version from the zip file

        zip_info = get_addon_zip_info(zip_path)
        await update_event(
            event_id,
            description=f"Installing addon {zip_info.name} {zip_info.version}",
            status="in_progress",
            summary={
                "zip_info": zip_info.dict(),
                "url": url,
            },
            progress=50,
        )

        # Unpack the addon

        loop = asyncio.get_event_loop()

        with ThreadPoolExecutor() as executor:
            task = loop.run_in_executor(
                executor,
                unpack_addon_sync,
                zip_path,
                zip_info,
            )
            await asyncio.gather(task)

    await update_event(
        event_id,
        description=f"Addon {zip_info.name} {zip_info.version} installed",
        status="finished",
    )
