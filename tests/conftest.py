from __future__ import annotations

import os
import tempfile
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="skillhub-test-"))
os.environ["SKILLHUB_DATA"] = str(TMP)
os.environ["SKILLHUB_SECRET"] = "test-secret-test-secret-32bytes!!"
os.environ["SKILLHUB_PUBLIC_READ"] = "true"
os.environ["SKILLHUB_PUBLIC_URL"] = "http://testserver"
os.environ["SKILLHUB_ORG"] = "Test SkillHub"
