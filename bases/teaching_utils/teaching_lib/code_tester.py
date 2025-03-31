import os.path

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
        super().__init__(name=name, export_path=export_path)

    def clone(self, export_path: str = None, force: bool = False):
        self._local_path = ghrepos.clone_repository(self._repository, exp