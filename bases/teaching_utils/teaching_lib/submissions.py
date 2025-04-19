from csv import reader
import os
import pickle
import shutil
import zipfile
import tarfile
from logging import getLogger

logger = getLogger(__name__)

# from github.Repository import Repository
from teaching_utils import config

class Submission:

    def __init__(self, key: str = None, export_path: str = None, info: dict = None):
        self.valid = True
        self.error = None
        if info is None:
            self._local_path = None
            self._info = {}
            self._key = key
            self._groups = []
            self._students = []
            self._submission_id = None
            if export_path is None:
                export_path = config.settings.EXPORT_PATH
                if os.path.exists(os.path.join(export_path, self._key)):
                    self._local_path = os.path.join(export_path, self._key)
            else:
                self._local_path = export_path
            self._info = {
                'type': 'Submission',
                'key': self._key,
                'groups': self._groups,
                'students': self._students,
                'local_path': self._local_path,
                'submission_id': self._submission_id
            }
        else:
            self._info = info
            self._key = info.get('key')
            self._groups = info.get('groups')
            self._students = info.get('students')
            self._local_path = info.get('local_path')
            self._submission_id = info.get('submission_id')

    def get_info(self):
        return self._info

    def set_info(self, info: dict):
        self._info = info

    def add_info(self, key, value):
        self._info[key] = value

    def get_key(self):
        return self._key

    def get_local_path(self):
        return self._local_path

    def set_local_path(self, local_path):
        self._local_path = local_path

    def get_groups(self):
        return self._groups

    def import_submission(self, path: str, extract: bool = False, exist_ok: bool = False, remove_existing: bool = False):
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

    def export(self, output_folder: str, exist_ok: bool = False, remove_existing: bool = False):
        if os.path.exists(output_folder) and remove_existing:
            shutil.rmtree(output_folder)

        os.makedirs(output_folder, exist_ok=exist_ok)

        shutil.copytree(self._local_path, output_folder, dirs_exist_ok=True)

class SubmissionSet:
    def __init__(self, export_path: str = None):
        self._submissions: dict[str, Submission] = {}
        self._export_path = export_path
        self._info = {
            'base': export_path,
            'type': 'SubmissionSet',
            'submissions': dict()
        }

    def __getitem__(self, index):
        return self._submissions[list(self._submissions.keys())[index]]

    def __len__(self):
        return len(self._submissions)

    def get_info(self):
        return self._info

    def set_info(self, info: dict):
        self._info = info

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

    def build_key(self, text: str):
        return self.clean_filename(text).replace("'", "")

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
        text = text.replace('A' + chr(0x308), "Ä");
        text = text.replace('E' + chr(0x308), "Ë");
        text = text.replace('I' + chr(0x308), "Ë");
        text = text.replace('O' + chr(0x308), "Ë");
        text = text.replace('U' + chr(0x308), "Ü");
        text = text.replace('N' + chr(0x303), "Ñ");
        return text

    def import_submissions(self, base: str, range_min: int = None, range_max: int = None, extract: bool = True, exist_ok: bool = False, remove_existing: bool = False):
        self._info = {
            'base': base,
            'type': 'SubmissionSet',
            'submissions': dict()
        }
        if range_min is not None and range_max is not None and range_max < range_min:
            raise ValueError('Range min must be smaller than range max')
        idx = 0
        for s in self.get_submission_list(base):
            idx += 1
            # Skip submissions not in range
            if range_min is not None and idx < range_min:
                continue
            if range_max is not None and idx > range_max:
                break
            # Create submission
            submission = self.create_submission(os.path.join(self._export_path, self.clean_filename(s)), extract)
            self._submissions[submission.get_key()] = submission
            try:
                submission.import_submission(os.path.join(base, s), extract=extract, exist_ok=exist_ok, remove_existing=remove_existing)
            except Exception as e:
                submission.valid = False
                submission.error = str(e)
                logger.warning(f'Invalid submission {submission.get_key()}. Error: {str(e)}.')
            self._info['submissions'][submission.get_key()] = submission.get_info()

        self._save_data()

    def _save_data(self):
        with open(os.path.join(self._export_path, 'set_info.pkl'), 'wb') as f:
            pickle.dump(self._info, f)

    def add_submission(self, submission: Submission):
        self._submissions[submission.get_key()] = submission
        self._info['submissions'][submission.get_key()] = submission.get_info()

    @staticmethod
    def _load_data(path: str) -> dict:
        with open(os.path.join(path, 'set_info.pkl'), 'rb') as f:
            data = pickle.load(f)
        return data

    @staticmethod
    def load_submissions(path: str):
        info = SubmissionSet._load_data(path)
        submission_set = globals()[info['type']]()
        submission_set.set_info(info)

        for sub_key in info['submissions']:
            sub_info = info['submissions'][sub_key]
            submission = globals()[sub_info['type']](info=sub_info)
            submission.set_info(sub_info)
            submission_set.add_submission(submission)

        return submission_set

    def create_submission(self, path: str, extract: bool = True) -> Submission:
        key = self.build_key(path.split('/')[-1])

        submission = Submission(key, path)

        return submission

    def get_submissions(self) -> dict[str, Submission]:
        return self._submissions

    def exportGroup(self, group: str, output_folder: str, exist_ok: bool = False, remove_existing: bool = False):
        new_submission_set = globals()[self._info['type']](output_folder)
        new_submission_set.set_info(self._info)
        new_submission_set._info['submissions'] = dict[str, Submission]()
        new_submission_set._groups = [group]
        new_submission_set._students = dict()
        for key, submission in self._submissions.items():
            if group in submission._groups:
                out_submission_folder = os.path.join(output_folder, submission.get_key())
                submission.export(out_submission_folder, exist_ok=exist_ok, remove_existing=remove_existing)
                new_submission = globals()[submission.__class__.__name__](info=submission.get_info())
                new_submission._info['local_path'] = out_submission_folder
                new_submission_set.add_submission(new_submission)
                new_submission_set._students[submission._student_fullname] = self._students[submission._student_fullname]

        new_submission_set._export_path = output_folder
        new_submission_set._save_data()

        return new_submission_set


class MoodleSubmissionSet(SubmissionSet):
    def __init__(self, class_csv: str = None, export_path: str = None):
        super().__init__(export_path)
        self._submissions: dict[str, MoodleSubmission] = {}
        self._class_csv = class_csv
        self._students = {}
        self._groups = set([])

    def _save_data(self):
        self._info['type'] = 'MoodleSubmissionSet'
        self._info['students'] = self._students
        self._info['groups'] = self._groups
        super()._save_data()

    def set_info(self, info: dict):
        super().set_info(info)
        self._students = info['students']
        self._groups = info['groups']

    def import_submissions(self, base: str, range_min: int = None, range_max: int = None, extract: bool = True, exist_ok: bool = False, remove_existing: bool = False):

        super().import_submissions(base, range_min, range_max, extract, exist_ok, remove_existing)

        new_submissions = {}
        if self._class_csv is not None:
            students_csv = reader(open(self._class_csv, 'r'), delimiter=',')
            # Skip headers
            next(students_csv, None)
            self._students = {}
            for row in students_csv:
                full_name = f'{row[1].strip()} {row[0].strip()}'
                self._students[self.build_key(full_name)] = {
                    'full_name': full_name,
                    'name': row[0].strip(),
                    'surname': row[1].strip(),
                    'id': row[2],
                    'groups': [g.strip() for g in row[3].split(',') if len(g) > 0]
                }
                self._groups = self._groups.union(set([g.strip() for g in row[3].split(',') if len(g) > 0]))

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
                self._info['submissions'][sub_key]['type'] = 'MoodleSubmission'
                self._info['submissions'][sub_key]['student_id'] = student_id
                self._info['submissions'][sub_key]['submission_id'] = submission_id
                self._info['submissions'][sub_key]['student_fullname'] = fullname
                self._info['submissions'][sub_key]['student_name'] = name
                self._info['submissions'][sub_key]['student_surname'] = surname
                self._info['submissions'][sub_key]['student_groups'] = set(groups)

        self._submissions = new_submissions
        self._save_data()

class MoodleSubmission (Submission):
    def __init__(self, key: str = None, export_path: str = None, info: dict = None):
        super().__init__(key, export_path, info)
        self._info['type'] = 'MoodleSubmission'
        if info is None:
            self._submission_id = None
            self._student_fullname = None
            self._student_id = None
            self._student_name = None
            self._student_surname = None
            self._student_groups = []
            self._groups = set([])
        else:
            self._submission_id = info['submission_id']
            if 'student' in info:
                self._student_fullname = info['student']['full_name']
                self._student_id = info['student']['id']
                self._student_name = info['student']['name']
                self._student_surname = info['student']['surname']
                self._student_groups = info['student']['groups']
                self._groups = set(info['student']['groups'])
            else:
                self._student_fullname = info.get('student_fullname')
                self._student_id = info.get('student_id')
                self._student_name = info.get('student_name')
                self._student_surname = info.get('student_surname')
                self._student_groups = info.get('student_groups')
                self._groups = set(self._student_groups)

    def set_data(self, submission_id, student_id, name, surname, full_name, groups = None):
        self._submission_id = submission_id
        self._student_fullname = full_name
        self._student_id = student_id
        self._student_name = name
        self._student_surname = surname
        if groups is None:
            groups = []
        self._student_groups = groups
        self._groups = set(groups)
        super().add_info('submission_id', submission_id)
        super().add_info('student', {
            'id': student_id,
            'full_name': full_name,
            'name': name,
            'surname': surname,
            'groups': groups
        })
