"""
Operate on GitLab repos in {TARGET_GROUP}

Docs:
https://python-gitlab.readthedocs.io/en/latest/api-objects.html
"""

TARGET_GROUP = "redhat/centos-stream/src"

import pathlib
import requests
import ogr
import os
import time

g = ogr.GitlabService(os.getenv("GITLAB_TOKEN"))

target_group = g.gitlab_instance.groups.get(TARGET_GROUP)

def create_repo(repo_name: str):
    g.gitlab_instance.projects.create({
        "name": repo_name,
        "namespace_id": target_group.id,
        "description": (
            f"Source repo for CentOS Stream package \"{repo_name}\". "
            "You can contribute here by following https://docs.centos.org/en-US/stream-contrib/"
        ),
        "issues_enabled": False,
        "visibility": "public",
    })

def get_modular_packages():
    m = {}  # package: [branches]

    for line in pathlib.Path("branches.txt").read_text().split("\n"):
        try:
            package, branches_str = line.split(" ", 1)
        except ValueError:
            package = line.strip()
            branches = []
        else:
            branches = branches_str.split(" ")
        package = package.rstrip(":")
        m[package] = branches

    response = {}
    for package, branches in m.items():
        for b in branches:
            if "-" in b:
                response.setdefault(package, [])
                response[package].append(b)
                print(f"{package}\t{b}")
    return response


def make_modular_packages_private():
    packages_and_branches = get_modular_packages()

    for package, branches in packages_and_branches.items():
        # import ipdb; ipdb.set_trace()
        project = g.gitlab_instance.projects.get(TARGET_GROUP + f"/{package}")
        project.visibility = "private"
        project.save()


DESCRIPTION = "Source repo for CentOS Stream package \"{package_name}\". Please, follow [this guide](https://docs.centos.org/en-US/stream-contrib/contributing/source-git/) when contributing."


def for_all_projects():
    for n in range(1, 200):
        projects = target_group.projects.list(page=n, per_page=25)
        if not projects:
            break
        for project in projects:
            # import ipdb; ipdb.set_trace()
            # https://python-gitlab.readthedocs.io/en/latest/gl_objects/groups.html#groups
            # "GroupProject objects returned by this API call are very limited"
            project = g.gitlab_instance.projects.get(project.id, lazy=False)
            # branches = " ".join(b.name for b in project.branches.list())
            # print(f"{project.name}: {branches}")
            # time.sleep(0.1)
            # print(f"Processing {project.name}")
            if "wiki.centos.org/Contribute/CentOSStream" not in project.description:
                print(f"Skipping {project.name}")
                continue
            project.description = DESCRIPTION.format(package_name=project.name)
            # project.issues_enabled = False
            project.save()

            # this is already the default
            # project.protectedbranches.create(
            #     {"name": "c8s", "push_access_level": "40", "merge_access_level": "40"}
            # )


for_all_projects()
