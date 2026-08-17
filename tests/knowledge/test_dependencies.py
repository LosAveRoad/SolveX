from pathlib import Path


def test_requirements_pin_fastembed_for_the_knowledge_base() -> None:
    requirements_path = Path(__file__).resolve().parents[2] / "requirements.txt"
    requirements = requirements_path.read_text(encoding="utf-8").splitlines()

    assert "qdrant-client[fastembed]~=1.19.0" in requirements
    assert "fastembed~=0.8.0" in requirements
    assert "pylatexenc~=2.11" in requirements
