def test_common_names_shim():
    import importlib

    cn = importlib.import_module("core.common_names")

    # Ensure both symbols exist
    assert hasattr(cn, "COMMON_NAMES"), "COMMON_NAMES dict missing"
    assert hasattr(cn, "COMMON_NAMES_SET"), "COMMON_NAMES_SET missing"

    # Types
    assert isinstance(cn.COMMON_NAMES, dict)
    assert isinstance(cn.COMMON_NAMES_SET, set)

    # Legacy mapping should reference the shared set
    assert "en" in cn.COMMON_NAMES
    assert "de" in cn.COMMON_NAMES
    assert cn.COMMON_NAMES["en"] is cn.COMMON_NAMES_SET
    assert cn.COMMON_NAMES["de"] is cn.COMMON_NAMES_SET

    # Sanity: names set not empty
    assert len(cn.COMMON_NAMES_SET) > 0
