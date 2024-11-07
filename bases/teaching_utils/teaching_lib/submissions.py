import os.path

from github.Repository import Repository
from teaching_utils import ghrepos, config


class Submission:

    def __init__(self):
        pass


class SubmissionSet:
    def __init__(self, export_path: str = None):
        self._submissions: dict[str, Submission] = {}
        self._export_path = export_path

    def __getitem__(self, index):
        return self._submissions[list(self._submissions.keys())[index]]

    def load_submissions(self, base: str, range_min: int = 1, range_max: int = 25):
        repos = ghrepos.get_repository_range(base, range_min, range_max)

        for submission in repos:
            self._repos[repo.name] = CodeRepository(repo, self._export_path)

