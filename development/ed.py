import logging
import os
import shutil

from teaching_utils import teaching_lib
from teaching_utils.teaching_lib.submissions import SubmissionSet, MoodleSubmissionSet

logger = logging.getLogger(__name__)

if __name__ == '__main__':

    print("ED")

    clean_data = False

    # Remove imported data
    if clean_data:
        shutil.rmtree('../_data/ed/pr1/out/submissions')
        print(f'Removed all imported submissions')

    # Import submissions from Moodle ZIP download
    out_path = '../_data/ed/pr1/out/submissions'
    if not os.path.exists(out_path):
        submissions = MoodleSubmissionSet('../_data/ed/pr1/courseid_87000_participants.csv', '../_data/ed/pr1/out/submissions')
        submissions.import_submissions('../_data/ed/pr1/lliuraments')
        print(f'Imported {len(submissions)} submissions')

    # Alternative (Import already extracted submissions)
    #subs = SubmissionSet.load_submissions('../_data/ed/pr1/out/submissions')

    # Export submissions of a particular group
    group = 'GrupB'
    if not os.path.exists(f'../_data/ed/pr1/out/groups/{group}'):
        grupB = submissions.exportGroup(group=group, output_folder=f'../_data/ed/pr1/out/groups/{group}', exist_ok=True, remove_existing=True)
        print(f'Exported {len(grupB)} submissions for group {group}')

    # Grup B
    subs = SubmissionSet.load_submissions('../_data/ed/pr1/out/groups/GrupB')
    print("Num lliuraments:", len(subs))


