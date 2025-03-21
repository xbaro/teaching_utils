import logging
import os
import shutil
import glob

# from teaching_utils import teaching_lib
import nbformat
import json
import datetime
from nbclient import NotebookClient

logger = logging.getLogger(__name__)


def copy_data(src, dst):
    spath = os.path.abspath(src)
    dpath = os.path.abspath(dst)

    #files = os.listdir(spath)
    shutil.copytree(spath, dpath, dirs_exist_ok=True)

    # iterating over all the files in the source directory
    #for fname in files:
        # copying the files to the destination directory
        #shutil.copy2(os.path.join(spath, fname), dpath)
        #shutil.copytree(os.path.join(spath, fname), dpath)

def get_submissions(base_path):

    submissions = []
    for folder in os.listdir(base_path):
        nbs = glob.glob(os.path.join(base_path, folder) + '**/*.ipynb')

        submissions.append({'folder': folder, 'path': os.path.join(base_path, folder), 'notebooks': nbs, 'valid': len(nbs) == 1})

    return submissions


def get_valid_submissions(base_path):
    submissions = get_submissions(base_path)

    return [s for s in submissions if s['valid']]



report: dict = {}

def get_cell_test_name(cell):
    test_name = None
    if 'tags' in cell['metadata'] and 'TEST' in cell['metadata']['tags']:
        for tag in cell['metadata']['tags']:
            if tag.startswith('TEST_'):
                test_name = tag[len('TEST_'):]
    return test_name

def on_cell_start(cell, cell_index):
    global report
    test_name = get_cell_test_name(cell)
    if test_name is not None:
        report['current_submission']['tests'][test_name] = {
            'start': datetime.datetime.now(datetime.UTC).isoformat()
        }
        report['current_submission']['num_test'] += 1

def on_cell_error(cell, cell_index, execute_reply):
    global report
    test_name = get_cell_test_name(cell)
    if test_name is not None:
        if execute_reply['content']['ename'] == 'AssertionError':
            report['current_submission']['tests'][test_name]['status'] = 'failed'
            report['current_submission']['num_failed'] += 1
        else:
            report['current_submission']['tests'][test_name]['error'] = '\n'.join(execute_reply['content']['traceback'])
            report['current_submission']['num_error'] += 1
def on_cell_executed(cell, cell_index, execute_reply):
    global report
    test_name = get_cell_test_name(cell)
    if test_name is not None:
        report['current_submission']['tests'][test_name] = {
            'end': datetime.datetime.now(datetime.UTC).isoformat(),
            'status': execute_reply['content']['status'],
            'passed': execute_reply['content']['status'] == 'ok'
        }
        if execute_reply['content']['status'] == 'ok':
            report['current_submission']['num_passed'] += 1

def on_notebook_start(notebook):
    global report

def on_notebook_complete(notebook):
    global report


def on_notebook_error(notebook):
    global report

def print_test_result(submission):
    print(f"---- {submission['submission']['path']}")
    print(f"{submission['name']}: => {submission['num_passed']} / {submission['num_test']}")
    for t in submission['tests']:
        print(f"\t{t}: status = {submission['tests'][t]['status']}")
    print('------------------------------------------------------------\n')

def prepare_notebooks(source, dest, ref_notebook, extra_data=None):
    global report
    report = {
        'start': datetime.datetime.now(datetime.UTC).isoformat(),
        'submissions': {}
    }

    if os.path.exists(dest):
        shutil.rmtree(dest)
    os.makedirs(dest, exist_ok=False)

    submissions = get_valid_submissions(source)
    test_cells = []
    ref_book = nbformat.read(ref_notebook, as_version=4)
    for cell in ref_book.cells:
        if 'tags' in cell['metadata'] and 'TEST' in cell['metadata']['tags']:
            test_cells.append(cell)
    for submission in submissions:
        test_book = nbformat.read(submission['notebooks'][0], as_version=4)
        test_book.cells.extend(test_cells)

        new_path = os.path.join(dest, submission['path'])
        if os.path.exists(new_path):
            print(f"File already exists: {new_path}. Skip submission")
            continue
        os.makedirs(new_path)
        if extra_data is not None:
            copy_data(extra_data, new_path)
        nbformat.write(test_book, os.path.join(dest, submission['notebooks'][0]))

        client = NotebookClient(test_book, timeout=600, kernel_name='python3',
                                resources={'metadata': {'path': new_path}}, allow_errors=True,
                                on_cell_executed=on_cell_executed, on_cell_error=on_cell_error,
                                on_notebook_start=on_notebook_start, on_notebook_complete=on_notebook_complete,
                                on_notebook_error=on_notebook_error, on_cell_start=on_cell_start)

        report['current_submission'] = {
            'submission': submission,
            'name': os.path.basename(submission['notebooks'][0]),
            'start': datetime.datetime.now(datetime.UTC).isoformat(),
            'tests': {},
            'num_test': 0,
            'num_passed': 0,
            'num_error': 0,
            'num_failed': 0,
        }

        try:
            client.execute()
            print_test_result(report['current_submission'])
        except Exception as exc:
            print(f'{new_path}: ERROR => {exc.__str__()}')

        try:
            nbformat.write(test_book, os.path.join(dest, submission['notebooks'][0]))
        except Exception:
            pass

        report['submissions'][submission['path']] = {
            'submission': submission['path'],
            'name': report['current_submission']['name'],
            'start': report['current_submission']['start'],
            'end': datetime.datetime.now(datetime.UTC).isoformat(),
            'tests': report['current_submission']['tests'],
            'num_test': report['current_submission']['num_test'],
            'num_passed': report['current_submission']['num_passed'],
            'num_error': report['current_submission']['num_error'],
            'num_failed': report['current_submission']['num_failed'],
        }
        del report['current_submission']

    report['end'] = datetime.datetime.now(datetime.UTC).isoformat()


def prepare_submissions(base_path, reference_notebook, extra_data=None):
    # PREPARE SUBMISSIONS
    prepare_notebooks(os.path.join(base_path, 'submissions'),
                      os.path.join(base_path, 'prepared'),
                      reference_notebook,
                      extra_data)

    with open(os.path.join(base_path, 'report.json'), 'w') as output:
        output.write(json.dumps(report))

    # CREATE CSV REPORT
    with open(os.path.join(base_path, 'report.json'), 'r') as report_json:
        with open(os.path.join(base_path, 'report_summary.csv'), 'w') as report_csv:
            rep = json.load(report_json)
            s0 = rep['submissions'][next(iter(rep['submissions']))]

            # Write header
            tests = s0['tests'].keys()
            report_csv.write(f'Name_submission;{";".join(tests)}\n')

            # Write test results
            for element in rep['submissions']:
                # Write the submission author name
                report_csv.write(f"{rep['submissions'][element]['submission'][len(os.path.join(base_path, 'submissions/')):-len('_assignsubmission_file')]}")
                # Write test results
                for test in tests:
                    try:
                        report_csv.write(f';{rep["submissions"][element]["tests"][test]["passed"]}')
                    except KeyError:
                        report_csv.write(';')

                # End CSV line
                report_csv.write('\n')


if __name__ == '__main__':

    logging.basicConfig(level=logging.DEBUG)
    prepare_submissions('./_data/scenario', './_data/scenario/ref/LAB04_Enumeratius_sol_AA2023.ipynb')





