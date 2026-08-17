import pytest
from pydantic import ValidationError


def _manifest_data(**overrides):
    data = {
        "schema_version": 1,
        "paper_id": "mcm-2025-c-outstanding-01",
        "title": "A Useful Model",
        "competition": "MCM",
        "year": 2025,
        "problem": "C",
        "award": "Outstanding Winner",
        "language": "en",
        "main_tex": "paper/main.tex",
    }
    data.update(overrides)
    return data


def test_manifest_accepts_required_metadata_and_defaults_methods() -> None:
    from app.knowledge.manifest import PaperManifest

    manifest = PaperManifest(**_manifest_data())

    assert manifest.paper_id == "mcm-2025-c-outstanding-01"
    assert manifest.methods == []
    assert manifest.main_tex == "paper/main.tex"


def test_manifest_requires_the_declared_schema_version() -> None:
    from app.knowledge.manifest import PaperManifest

    with pytest.raises(ValidationError):
        PaperManifest(**_manifest_data(schema_version=2))


@pytest.mark.parametrize("main_tex", ["/tmp/main.tex", "../main.tex", "paper/../../main.tex"])
def test_manifest_rejects_absolute_and_parent_traversal_main_tex(main_tex: str) -> None:
    from app.knowledge.manifest import PaperManifest

    with pytest.raises(ValidationError):
        PaperManifest(**_manifest_data(main_tex=main_tex))


def test_manifest_forbids_unknown_fields_and_normalizes_method_names() -> None:
    from app.knowledge.manifest import PaperManifest

    manifest = PaperManifest(**_manifest_data(methods=[" optimization ", "regression"]))

    assert manifest.methods == ["optimization", "regression"]
    with pytest.raises(ValidationError):
        PaperManifest(**_manifest_data(unexpected="not permitted"))


@pytest.mark.parametrize("methods", [[""], ["   "], ["valid", " "]])
def test_manifest_rejects_empty_method_names_after_normalization(methods: list[str]) -> None:
    from app.knowledge.manifest import PaperManifest

    with pytest.raises(ValidationError, match="methods"):
        PaperManifest(**_manifest_data(methods=methods))


@pytest.mark.parametrize("year", [0, 1899, 2101])
def test_manifest_rejects_years_outside_the_supported_competition_range(year: int) -> None:
    from app.knowledge.manifest import PaperManifest

    with pytest.raises(ValidationError, match="year"):
        PaperManifest(**_manifest_data(year=year))


@pytest.mark.parametrize(
    ("field_name", "limit_name"),
    [
        ("paper_id", "MAX_PAPER_ID_LENGTH"),
        ("title", "MAX_TITLE_LENGTH"),
        ("competition", "MAX_COMPETITION_LENGTH"),
        ("problem", "MAX_PROBLEM_LENGTH"),
        ("award", "MAX_AWARD_LENGTH"),
        ("language", "MAX_LANGUAGE_LENGTH"),
        ("main_tex", "MAX_MAIN_TEX_LENGTH"),
    ],
)
def test_manifest_rejects_oversized_string_metadata(field_name: str, limit_name: str) -> None:
    import app.knowledge.manifest as manifest_module
    from app.knowledge.manifest import PaperManifest

    limit = getattr(manifest_module, limit_name)

    with pytest.raises(ValidationError, match=field_name):
        PaperManifest(**_manifest_data(**{field_name: "x" * (limit + 1)}))


def test_manifest_bounds_method_count_and_each_method_length() -> None:
    import app.knowledge.manifest as manifest_module
    from app.knowledge.manifest import PaperManifest

    with pytest.raises(ValidationError, match="methods"):
        PaperManifest(
            **_manifest_data(methods=["method"] * (manifest_module.MAX_METHODS_PER_PAPER + 1))
        )
    with pytest.raises(ValidationError, match="methods"):
        PaperManifest(
            **_manifest_data(methods=["m" * (manifest_module.MAX_METHOD_LENGTH + 1)])
        )
