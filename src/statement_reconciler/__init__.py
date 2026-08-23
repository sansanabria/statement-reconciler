"""Cross-check a PDF statement against a spreadsheet of the same records.

The workflow has three steps, each a CLI subcommand:

    fetch      pull matching attachments out of Outlook into dated per-source folders
    check      read the PDF and the spreadsheet in one folder and report the differences
    inventory  list folders that are missing a document

Nothing about a particular sender, document layout or column name lives in the code.
It all comes from a YAML config file -- see config.example.yaml.
"""

__version__ = "0.1.0"
