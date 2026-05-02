#!/usr/bin/env python3.11
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from opensignal_job_intel.sources.linkedin_harvest_ops import run_script


raise SystemExit(run_script(__file__))
