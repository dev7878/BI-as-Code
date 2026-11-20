"""`python -m rbc_bi.spec validate [paths...]` (alias of `rbc-bi validate`)."""
import sys

from rbc_bi.cli import main

sys.exit(main(sys.argv[1:]))
