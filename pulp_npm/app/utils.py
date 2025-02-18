import re


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
    pattern = r"^(?P<name>@?[^/]+(?:/[^/]+)?)/-/(?P<base_name>[^/]+)-(?P<version>[\d.]+)\.tgz$"
    match = re.match(pattern, relative_path)

    if match:
        name = match.group("name")
        version = match.group("version")
        return name, version
    else:
        return None, None
