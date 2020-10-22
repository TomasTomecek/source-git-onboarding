import os
import shutil
from logging import getLogger
from shutil import copyfile

import git
import requests

from ogr.services.pagure import PagureService

logger = getLogger(__name__)

work_dir = "/tmp/playground"
readme_path = f"{os.path.dirname(os.path.realpath(__file__))}/README.md"
service = PagureService(
    token=os.getenv("PAGURE_TOKEN"), instance_url="https://git.stg.centos.org/"
)


class AddMasterBranch:
    def __init__(self, pkg_name):
        self.pkg_name = pkg_name
        self.project = service.get_project(namespace="source-git", repo=self.pkg_name)
        self.pkg_dir = f"{work_dir}/{self.pkg_name}"

    def run(self):
        logger.info(f"Processing package: {self.pkg_name}")
        if "master" in self.project.get_branches():
            logger.info("\tBranch already exists")
        else:
            logger.info("\tCreating master branch")
            self.add_master()

    def add_master(self):
        if not os.path.exists(self.pkg_dir):
            git.Git(work_dir).clone(self.project.get_git_urls()["ssh"])
        repo = git.Repo(self.pkg_dir)
        copyfile(readme_path, f"{self.pkg_dir}/README.md")
        repo.index.add([f"{self.pkg_dir}/README.md"])
        repo.index.commit("Initialize master branch")
        repo.git.push("origin", "master")

        # cleanup
        shutil.rmtree(self.pkg_dir)


if __name__ == "__main__":
    if not os.path.exists(work_dir):
        logger.warning("Your work_dir is missing.")
    page = "https://git.stg.centos.org/api/0/projects?namespace=source-git&short=true"
    i = 0
    while True:
        logger.info(page)
        r = requests.get(page)
        for p in r.json()["projects"]:
            mb = AddMasterBranch(p["name"])
            mb.run()
        page = r.json()["pagination"]["next"]
        if not page:
            break
        i = i + 1
