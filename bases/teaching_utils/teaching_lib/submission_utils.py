import logging
import os
import shutil
from typing import Union

from teaching_utils.teaching_lib.submissions import SubmissionSet, MoodleSubmissionSet


logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def export_groups(
    input_path: str,
    participants_csv: str,
    output_folder: str,
    remove_existing: bool = False,
    groups: Union[str, list[str]] = "__all__"
) -> None:
    """
    Imports student submissions and exports them by group.

    Args:
        input_path (str): Path to the input submissions.
        participants_csv (str): Path to the participants CSV file from Moodle.
        output_folder (str): Directory where submissions will be saved.
        remove_existing (bool): If True, removes existing contents in output_folder before import.
        groups (Union[str, list[str]]): Group name(s) to export. Use "__all__" to export all groups.

    Raises:
        FileNotFoundError: If the input path does not exist.

    Workflow:
        - If `remove_existing` is True, the output folder will be cleared.
        - Submissions are loaded either from a ZIP file (Moodle) or from an existing folder.
        - If `groups` is "__all__", all groups are exported; otherwise, only the specified ones.
        - For each group, submissions are saved to a separate folder.
    """

    if not os.path.exists(input_path):
        logger.error(f"Input path '{input_path}' does not exist.")
        raise FileNotFoundError(f"Input path '{input_path}' does not exist.")

    # Remove existing submissions if requested
    if remove_existing and os.path.exists(output_folder):
        shutil.rmtree(output_folder)
        logger.info(f"Removed existing data in output folder: {output_folder}")

    # Load or import submissions
    out_submissions_folder = os.path.join(output_folder, "submissions")
    if not os.path.exists(out_submissions_folder):
        # Import new submissions from Moodle ZIP
        submissions = MoodleSubmissionSet(participants_csv, out_submissions_folder)
        submissions.import_submissions(input_path)
        logger.info(f"Imported {len(submissions)} submissions.")
    else:
        # Load already-extracted submissions
        submissions = SubmissionSet.load_submissions(out_submissions_folder)
        logger.info(f"Loaded submissions from existing folder: {out_submissions_folder}")

    # Determine group list
    if isinstance(groups, str):
        if groups == "__all__":
            groups = submissions.get_groups()
        else:
            groups = [groups]

    # Export submissions per group
    for group in groups:
        group_path = os.path.join(output_folder, "groups", group)
        exported = submissions.exportGroup(
            group=group,
            output_folder=group_path,
            exist_ok=True,
            remove_existing=True
        )
        logger.info(f"Exported {len(exported)} submissions for group: {group}")
