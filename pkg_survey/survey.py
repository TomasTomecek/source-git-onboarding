import re
import shutil
import subprocess
from logging import getLogger
from pathlib import Path
from typing import Dict, Any, Optional, List

import git
import requests
import yaml
from click.testing import CliRunner
from dist2src.core import Dist2Src

from packit.cli.utils import get_packit_api
from packit.config import Config
from packit.local_project import LocalProject

logger = getLogger(__name__)

work_dir = Path("/tmp/playground")
rpms_dir = work_dir / "rpms"
src_dir = work_dir / "src"
result = []
packit_conf = Config.get_user_config()
runner = CliRunner()

BRANCH = "c8s"


class CentosPkgValidatedConvert:
    def __init__(self, package_name: str, distgit_branch: str):
        self.package_name = package_name
        self.rpm_package_dir: Path = rpms_dir / package_name
        self.src_package_dir: Path = src_dir / package_name
        self.result: Dict[str, Any] = {}
        self.srpm_path = ""
        self.distgit_branch = distgit_branch
        self.d2s: Optional[Dist2Src] = None

    def clone(self, git_url: str, dir: Path) -> bool:
        git_repo_path = dir / self.package_name
        try:
            if not git_repo_path.is_dir():
                git.Git(dir).clone(git_url)
            r = git.Repo(git_repo_path)
            r.git.checkout(self.distgit_branch)
            return True
        except Exception as ex:
            if f"Remote branch {self.distgit_branch} not found" in str(
                ex
            ) or f"pathspec '{self.distgit_branch}' did not match" in str(ex):
                return False
            self.result["package_name"] = self.package_name
            self.result["error"] = f"CloneError: {ex}"
            return False

    def run_srpm(self):
        try:
            packit_api = get_packit_api(
                config=packit_conf,
                local_project=LocalProject(git.Repo(self.src_package_dir)),
            )
            self.srpm_path = packit_api.create_srpm(srpm_dir=self.src_package_dir)
        except Exception as e:
            self.result["error"] = f"SRPMError: {e}"

    def convert(self) -> bool:
        try:
            self.d2s = Dist2Src(
                dist_git_path=self.rpm_package_dir,
                source_git_path=self.src_package_dir,
            )
            self.d2s.convert(self.distgit_branch, self.distgit_branch)
            return True
        except Exception as ex:
            self.result["error"] = f"ConvertError: {ex}"
            return False

    def cleanup(self):
        if self.rpm_package_dir.is_dir():
            shutil.rmtree(self.rpm_package_dir)
        if self.src_package_dir.is_dir():
            shutil.rmtree(self.src_package_dir)

    def do_mock_build(self):
        c = subprocess.run(
            ["mock", "-r", "centos-stream-x86_64", "rebuild", self.srpm_path]
        )
        if not c.returncode:
            return
        self.result["error"] = "mock build failed"

    @staticmethod
    def get_conditional_info(spec_cont) -> List[str]:
        conditions = re.findall(r"\n%if.*?\n%endif", spec_cont, re.DOTALL)
        result = []
        p = re.compile("\n%if (.*)\n")
        for con in conditions:
            if "\n%patch" in con:
                found = p.search(con)
                if found:
                    result.append(found.group(1))
        return result

    def run(
        self, cleanup: bool = False, skip_build: bool = False, clone_sg: bool = False
    ):
        if not self.clone(
            git_url=f"https://git.centos.org/rpms/{self.package_name}", dir=rpms_dir
        ):
            return
        if clone_sg:
            self.clone(
                git_url=f"https://git.stg.centos.org/source-git/{self.package_name}",
                dir=src_dir,
            )

        self.result["package_name"] = self.package_name
        specfile_path = self.rpm_package_dir / "SPECS" / f"{self.package_name}.spec"
        if not specfile_path.is_file():
            self.result["error"] = "Specfile not found."
            self.cleanup()
            return

        with specfile_path.open() as spec:
            spec_cont = spec.read()
            self.result.update(
                {
                    "autosetup": bool(re.search(r"\n%autosetup", spec_cont)),
                    "setup": bool(re.search(r"\n%setup", spec_cont)),
                    "conditional_patch": self.get_conditional_info(spec_cont),
                }
            )

        if self.convert():
            self.run_srpm()
            self.result["size"] = (
                subprocess.check_output(["du", "-sh", self.src_package_dir])
                .split()[0]
                .decode("utf-8")
            )
            if self.srpm_path and not skip_build:
                self.do_mock_build()
        else:
            self.result["size_rpms"] = (
                subprocess.check_output(["du", "-sh", self.rpm_package_dir])
                .split()[0]
                .decode("utf-8")
            )
        if cleanup:
            self.cleanup()


def get_centos_packages() -> List[str]:
    i = 0
    url = "https://git.centos.org/api/0/projects?namespace=rpms&owner=centosrcm&short=true"
    packages: List[str] = []
    while True:
        logger.info(url)
        r = requests.get(url)
        for p in r.json()["projects"]:
            package_name = p["name"]
            logger.info(f"Processing package: {package_name}")
            packages.append(package_name)
        url = r.json()["pagination"]["next"]
        if not url:
            break
        i += 1
    return packages


if __name__ == "__main__":
    Path("all-centos-packages.yml").write_text(yaml.safe_dump(get_centos_packages()))
