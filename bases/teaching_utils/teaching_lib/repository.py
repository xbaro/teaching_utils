import os.path

from github.Repository import Repository
from teaching_utils import ghrepos, config, testing
from .submissions import Submission, SubmissionSet


class CodeRepository(Submission):

    def __init__(self, repository: Repository | str, export_path: str = None):
        if isinstance(repository, Repository):
            self._repository = repository
            name = repository.name
        else:
            name = repository
            self._repository = ghrepos.get_repository(repository)
        super().__init__(key=name, export_path=export_path)

    def clone(self, export_path: str = None, force: bool = False):
        self._local_path = ghrepos.clone_repository(self._repository, export_path, force)

    def get_stats(self) -> dict:
        return ghrepos.get_repository_stats(self._repository)

    def export_files(self, export_prefix: str, path_filter: str = None, extension_filter: str = None):
        ghrepos.export_files(self._repository, export_prefix, path_filter, extension_filter)

    def test(self, language: str, relative_path: str = None):
        src_path = self._local_path
        if relative_path is not None:
            src_path = os.path.abspath(os.path.join(src_path, relative_path))

        return testing.run_tests(language, src_path)


class CodeRepositorySet(SubmissionSet):

    def __init__(self, export_path: str = None):
        super().__init__(export_path=export_path)
        self._repos: dict[str, CodeRepository] = {}

    def __getitem__(self, index):
        return self._repos[list(self._repos.keys())[index]]

    def load_repositories(self, base: str, range_min: int = 1, range_max: int = 25):
        repos = ghrepos.get_repository_range(base, range_min, range_max)

        for repo in repos:
            self._repos[repo.name] = CodeRepository(repo, self._export_path)

    @staticmethod
    def get_repository(base: str, index: int, export_path: str = None) -> CodeRepository | None:
        repo = ghrepos.get_repository_idx(base, index)

        return CodeRepository(repo, export_path)

    def clone_all(self, export_path: str = None, force: bool = False):
        if export_path is None:
            export_path = self._export_path

        for repo_name in self._repos:
            self._repos[repo_name].clone(export_path, force)

    def export_files(self, export_prefix: str, path_filter: str = None, extension_filter: str = None):
        for repo_name in self._repos:
            self._repos[repo_name].export_files(export_prefix, path_filter, extension_filter)

    def print_stats(self):
        for repo_name in self._repos:
            stats = self._repos[repo_name].get_stats()
            print("=====================================================================================================")
            print(f'{repo_name}')
            print("=====================================================================================================")
            print("  CONTRIBUTORS")
            print("  ---------------------------------------------------------------------------------------------------")
            print(f"  | {'user[login]':35} | {'+':9} | {'-':9} | {'c':3} | {'b':3} | {'+/c':9} | {'-/c':9} |")
            print("  ---------------------------------------------------------------------------------------------------")
            for contributor in stats['contributors']['contributors']:
                name = ''
                if contributor['name'] is not None:
                    name = contributor['name']
                if contributor['login'] is not None:
                    name += f'[{contributor["login"]}]'
                print(f"  | {name:35} | {contributor['total_additions']:9} | {contributor['total_deletions']:9} | {contributor['num_commits']:3} | {contributor['num_branches']:3} | {contributor['total_additions']/contributor['num_commits']:6.2f} | {contributor['total_deletions']/contributor['num_commits']:6.2f} |")  # noqa: E501
            print("  ---------------------------------------------------------------------------------------------------")
            print("=====================================================================================================")
