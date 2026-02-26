import json
import re
import tarfile
import tempfile


def urlpath_sanitize(*args):
    """
    Join an arbitrary number of strings into a /-separated path.

    Replaces uses of urljoin() that don't want/need urljoin's subtle semantics.

    Returns: single string provided arguments separated by single-slashes

    Args:
        Arbitrary list of arguments to be join()ed
    """
    segments = []
    for a in args + ("",):
        stripped = a.strip("/")
        if stripped:
            segments.append(stripped)
    return "/".join(segments)


def extract_package_info(relative_path):
    """
    Tries to extract the name and the version of a package
    from the relative path string.

    Args:
        The relative_path string. "package/-/package-version.tgz"
    """
    pattern = r"^(?P<name>@?[^/]+(?:/[^/]+)?)(?:/-/(?P<base_name>[^/]+)-(?P<version>[\d.]+)\.tgz)?$"
    match = re.match(pattern, relative_path)

    if match:
        name = match.group("name")
        version = match.group("version")
        return name, version
    else:
        return None, None


def extract_npm_metadata_from_artifact(artifact):
    """
    Extract name and version from an npm package tarball.

    npm tarballs are gzipped tar archives containing a ``package/package.json``
    (or ``<name>/package.json`` for scoped packages).

    Args:
        artifact: A Pulp Artifact whose file is an npm tarball (.tgz).

    Returns:
        dict: A dictionary with ``name`` and ``version`` keys.

    Raises:
        ValueError: If the tarball cannot be read or ``package.json`` is missing/invalid.
    """
    try:
        with tempfile.NamedTemporaryFile(suffix=".tgz") as tmp:
            with artifact.file.open("rb") as af:
                for chunk in af.chunks():
                    tmp.write(chunk)
            tmp.flush()
            tmp.seek(0)

            with tarfile.open(fileobj=tmp, mode="r:gz") as tar:
                package_json_member = None
                for member in tar.getmembers():
                    parts = member.name.split("/")
                    if len(parts) == 2 and parts[-1] == "package.json":
                        package_json_member = member
                        break

                if package_json_member is None:
                    raise ValueError("No package.json found in npm tarball.")

                f = tar.extractfile(package_json_member)
                if f is None:
                    raise ValueError("Could not read package.json from npm tarball.")

                package_data = json.load(f)
    except (tarfile.TarError, OSError) as e:
        raise ValueError(f"Failed to read npm tarball: {e}")

    name = package_data.get("name")
    version = package_data.get("version")

    if not name or not version:
        raise ValueError(
            "package.json in npm tarball is missing required 'name' or 'version' fields."
        )

    return {"name": name, "version": version}
