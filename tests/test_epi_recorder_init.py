"""Regression tests for side-effect free `import epi_recorder`."""

import importlib
import sys
from unittest.mock import patch


def test_import_epi_recorder_does_not_register_file_association():
    sys.modules.pop("epi_recorder", None)

    with patch("epi_core.platform.associate.register_file_association") as mock_register:
        module = importlib.import_module("epi_recorder")
        importlib.reload(module)

    mock_register.assert_not_called()
