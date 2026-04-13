
from setup import _clear_stale_build_outputs


def test_clear_stale_build_outputs_removes_stale_package_files(tmp_path):
    build_lib = tmp_path / "build" / "lib"
    package_dir = build_lib / "epi_recorder"
    package_dir.mkdir(parents=True)
    stale_file = package_dir / "test_script.py"
    stale_file.write_text("print('stale')\n", encoding="utf-8")

    viewer_dir = build_lib / "epi_viewer_static"
    viewer_dir.mkdir(parents=True)
    stale_viewer = viewer_dir / "stale.js"
    stale_viewer.write_text("console.log('stale');\n", encoding="utf-8")

    stale_module = build_lib / "epi_postinstall.py"
    stale_module.write_text("print('stale module')\n", encoding="utf-8")

    _clear_stale_build_outputs(str(build_lib))

    assert not stale_file.exists()
    assert not stale_viewer.exists()
    assert not stale_module.exists()
    assert not package_dir.exists()
    assert not viewer_dir.exists()


def test_clear_stale_build_outputs_is_safe_for_missing_build_dir(tmp_path):
    missing = tmp_path / "missing-build-lib"
    _clear_stale_build_outputs(str(missing))
    assert not missing.exists()
