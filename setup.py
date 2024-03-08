from setuptools import find_packages, setup

with open("README.md") as f:
    long_description = f.read()

with open("requirements.txt") as requirements:
    requirements = requirements.readlines()

setup(
    name="pulp-npm",
    version="0.1.0a5.dev",
    description="pulp-npm plugin for the Pulp Project",
    long_description=long_description,
    long_description_content_type="text/markdown",
    license="GPLv2+",
    author="Pulp NPM Plugin Project Developers",
    author_email="pulp-dev@redhat.com",
    url="https://github.com/pulp/pulp_npm",
    python_requires=">=3.6",
    install_requires=requirements,
    include_package_data=True,
    packages=find_packages(exclude=["tests", "tests.*"]),
    classifiers=(
        "License :: OSI Approved :: GNU General Public License v2 or later (GPLv2+)",
        "Operating System :: POSIX :: Linux",
        "Framework :: Django",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
    ),
    entry_points={"pulpcore.plugin": ["pulp_npm = pulp_npm:default_app_config"]},
)
