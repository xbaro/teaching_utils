import os.path

from github.Repository import Repository
from teaching_utils import ghrepos, config


class CodeRepository:

    def __init__(self, repository: Repository | str, export_path: str = None):
        if isinstance(repository, Repository):
            self._repository = repository
            self._name = repository.name
        else:
            self._name = repository
            self._repository = ghrepos.get_repository(repository)

        self._local_path = None
        if export_path is None:
            export_path = config.settings.EXPORT_PATH
            if os.path.exists(os.path.join(export_path, self._name)):
                self._local_path = os.path.join(export_path, self._name)

    def clone(self, export_path: str = None, force: bool = False):
        self._local_path = ghrepos.clone_repository(self._repository, export_path, force)


class CodeReposotorySet:

    def __init__(self, export_path: str = None):
        self._repos: dict[str, CodeRepository] = {}
        self._export_path = export_path

    def load_repositories(self, base: str, range_min: int = 1, range_max: int = 25):
        repos = ghrepos.get_repository_range(base, range_min, range_max)

        for repo in repos:
            self._repos[repo.name] = CodeRepository(repo, self._export_path)

    def clone_all(self, export_path: str = None, force: bool = False):
        if export_path is None:
            export_path = self._export_path

        for repo_name in self._repos:
            self._repos[repo_name].clone(export_path, force)
