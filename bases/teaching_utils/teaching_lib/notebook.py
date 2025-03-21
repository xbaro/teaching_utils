from .submissions import Submission, SubmissionSet


class Notebook(Submission):

    def __init__(self, notebook_path: str, export_path: str = None):
        super().__init__(name=notebook_path, export_path=export_path)


class NotebookSet(SubmissionSet):
    def __init__(self, export_path: str = None):
        super().__init__(export_path=export_path)

