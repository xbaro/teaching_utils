import logging
import os
import shutil

from teaching_utils import teaching_lib
from teaching_utils.teaching_lib.submissions import SubmissionSet, MoodleSubmissionSet

logger = logging.getLogger(__name__)

if __name__ == '__main__':

    print("ED")

    shutil.rmtree('../_data/ed/pr1/out/submissions')
    submissions = MoodleSubmissionSet('../_data/ed/pr1/courseid_87000_participants.csv', '../_data/ed/pr1/out/submissions')

    submissions.load_submissions('../_data/ed/pr1/lliuraments')

    print(len(submissions.get_submissions()))


