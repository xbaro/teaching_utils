from csv import reader
import os
import shutil
import zipfile
import tarfile
from logging import getLogger

logger = getLogger(__name__)

# from github.Repository import Repository
from teaching_utils import config

class Submission:

    def __init__(self, key: str = None, export_path: str = None):
        self._local_path = None
        self._info = {}
        self._key = key
        if export_path is None:
            export_path = config.settings.EXPORT_PATH
            if os.path.exists(os.path.join(export_path, self._key)):
                self._local_path = os.path.join(export_path, self._key)
        else:
            self._local_path = export_path

    def add_info(self, key, value):
        self._info[key] = value

    def get_key(self):
        return self._key

    def get_local_path(self):
        return self._local_path

    def set_local_path(self, local_path):
        self._local_path = local_path

    def load(self, path: str, extract: bool = False, exist_ok: bool = False, remove_existing: bool = False):
        if not os.path.exists(path):
            raise FileNotFoundError(path)
        if os.path.exists(path) and remove_existing:
            os.remove(path)

        os.makedirs(self._local_path, exist_ok=exist_ok)

        for root, _, files in os.walk(path):
            for file in files:
                source_file = os.path.join(root, file)
                dest_file = os.path.join(self._local_path, file)

                shutil.copy2(source_file, dest_file)

                if extract and file.endswith(('.zip', '.tar', '.tar.gz', '.tgz', '.tar.bz2')):
                    extract_folder = os.path.join(self._local_path, os.path.splitext(file)[0])
                    os.makedirs(extract_folder, exist_ok=True)

                    if file.endswith('.zip'):
                        with zipfile.ZipFile(dest_file, 'r') as zip_ref:
                            zip_ref.extractall(extract_folder)
                    elif file.endswith(('.tar', '.tar.gz', '.tgz', '.tar.bz2')):
                        with tarfile.open(dest_file, 'r') as tar_ref:
                            tar_ref.extractall(extract_folder)


class SubmissionSet:
    def __init__(self, export_path: str = None):
        self._submissions: dict[str, Submission] = {}
        self._export_path = export_path

    def __getitem__(self, index):
        return self._submissions[list(self._submissions.keys())[index]]

    def get_submission_list(self, base_path: str) -> list[str]:
        """
        Get a list of all submission paths.
        :param base_path: Base path to search for submissions.
        :return: List of all submission paths
        """
        submissions = []
        for folder in os.listdir(base_path):
            submissions.append(folder)

        return submissions

    def clean_filename(self, text: str) -> str:
        # Fix double encoding problem on filenames
        text = text.replace('A' + chr(0x300), "À");
        text = text.replace('E' + chr(0x300), "È");
        text = text.replace('I' + chr(0x300), "Ì");
        text = text.replace('O' + chr(0x300), "Ò");
        text = text.replace('U' + chr(0x300), "Ù");
        text = text.replace('A' + chr(0x301), "Á");
        text = text.replace('E' + chr(0x301), "É");
        text = text.replace('I' + chr(0x301), "Í");
        text = text.replace('O' + chr(0x301), "Ó");
        text = text.replace('U' + chr(0x301), "Ú");
        return text

    def load_submissions(self, base: str, range_min: int = 1, range_max: int = 25, extract: bool = True, exist_ok: bool = False, remove_existing: bool = False):
        idx = 0
        for s in self.get_submission_list(base):
            idx += 1
            # Skip submissions not in range
            if idx < range_min:
                continue
            if idx > range_max:
                break
            # Create submission
            submission = self.create_submission(os.path.join(self._export_path, self.clean_filename(s)), extract)
            self._submissions[submission.get_key()] = submission
            submission.load(os.path.join(base, s), extract=extract, exist_ok=exist_ok, remove_existing=remove_existing)

    def create_submission(self, path: str, extract: bool = True) -> Submission:
        key = path.split('/')[-1]

        submission = Submission(key, path)

        return submission

    def get_submissions(self) -> dict[str, Submission]:
        return self._submissions

class MoodleSubmissionSet(SubmissionSet):
    def __init__(self, class_csv: str = None, export_path: str = None):
        super().__init__(export_path)
        self._submissions: dict[str, MoodleSubmission] = {}
        self._class_csv = class_csv
        self._students = {}
        self._groups = set([])

    def load_submissions(self, base: str, range_min: int = 1, range_max: int = 25, extract: bool = True, exist_ok: bool = False, remove_existing: bool = False):

        super().load_submissions(base, range_min, range_max, extract, exist_ok, remove_existing)

        if self._class_csv is not None:
            students_csv = reader(open(self._class_csv, 'r'), delimiter=',')
            # Skip headers
            next(students_csv, None)
            self._students = {}
            for row in students_csv:
                full_name = f'{row[1].strip()} {row[0].strip()}'
                self._students[full_name] = {
                    'full_name': full_name,
                    'name': row[0].strip(),
                    'surname': row[1].strip(),
                    'id': row[2],
                    'groups': row[3].split(',')
                }
                self._groups = self._groups.union(set(row[3].split(',')))

            new_submissions = {}
            for sub_key in self._submissions:
                key = sub_key.split('/')[-1]
                fullname = key.split('_')[0]
                submission_id = key.split('_')[1]
                student_id = None
                name = None
                surname = None
                groups = []
                if fullname in self._students:
                    student_id = self._students[fullname]['id']
                    name = self._students[fullname]['name']
                    surname = self._students[fullname]['surname']
                    groups = self._students[fullname]['groups']
                else:
                    logger.warning(f'Student {fullname} not found.')

                new_submission = MoodleSubmission(sub_key, self._submissions[sub_key].get_local_path())
                new_submission.set_data(submission_id, student_id, name, surname, fullname, groups)
                new_submissions[sub_key] = new_submission

        self._submissions = new_submissions

class MoodleSubmission (Submission):
    def __init__(self, key: str = None, export_path: str = None):
        super().__init__(key, export_path)
        self._submission_id = None
        self._student_fullname = None
        self._student_id = None
        self._student_name = None
        self._student_surname = None
        self._student_groups = []
        self._info['type'] = 'MoodleSubmission'

    def set_data(self, submission_id, student_id, name, surname, full_name, groups = None):
        self._submission_id = submission_id
        self._student_fullname = full_name
        self._student_id = student_id
        self._student_name = name
        self._student_surname = surname
        if groups is None:
            groups = []
        self._student_groups = groups
        super().add_info('submission_id', submission_id)
        super().add_info('student', {
            'id': student_id,
            'full_name': full_name,
            'name': name,
            'surname': surname,
            'groups': groups
        })
