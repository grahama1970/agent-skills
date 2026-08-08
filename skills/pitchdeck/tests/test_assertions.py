"""Assertion-atom provenance for every emitted string (#1328).

The P0 breach was that a diagram carried ONE element-level binding, so a label
like "relevance does not cross this gap" reached a slide with no string-level
provenance, and the only way to make verify-publish pass was for a human to type
that text into an approvals file. These tests prove the compiler models it now.
"""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from pitchdeck.document import Bbox, DeckDocument, DiagramEdge, DiagramGraph, DiagramNode
from pitchdeck.publish_verify import atoms_from_document

DOCUMENT = Path("/mnt/storage12tb/skills/pitchdeck/outputs/ticket-1278/approved.document.json")


def _document() -> DeckDocument:
    if not DOCUMENT.is_file():
        pytest.skip(f"materialized document not present at {DOCUMENT}")
    return DeckDocument.model_validate(json.loads(DOCUMENT.read_text(encoding="utf-8")))


def test_labelled_node_without_binding_is_refused():
    """A node label is a visible assertion; unbound means unprovable."""
    with pytest.raises(ValidationError, match="requires binding_paths"):
        DiagramNode(id="n1", bbox=Bbox(x=0.1, y=0.1, w=0.2, h=0.2), label="Retrieval")


def test_blank_label_glyph_needs_no_binding():
    """A bare supporting glyph carries no claim, so it needs no provenance."""
    node = DiagramNode(id="n1", bbox=Bbox(x=0.1, y=0.1, w=0.2, h=0.2), label=" ", icon="users")
    assert node.binding_paths == []


def test_non_decorative_edge_without_binding_is_refused():
    with pytest.raises(ValidationError, match="requires binding_paths"):
        DiagramEdge(id="e1", source="a", target="b", label="traced to")


def test_every_diagram_label_in_the_real_deck_is_individually_bound():
    """The acceptance condition: no label relies on an element-level binding."""
    document = _document()
    diagram_atoms = [a for a in atoms_from_document(document) if a.role.startswith("diagram")]
    assert diagram_atoms, "the deck should contain diagram labels"
    unbound = [a.canonical_id for a in diagram_atoms if not a.claim_id]
    assert not unbound, f"diagram labels without claim provenance: {unbound}"
    for atom in diagram_atoms:
        assert atom.transform_class, f"{atom.canonical_id} has no transform class"


def test_no_label_binds_through_a_coarse_element_path():
    """Element-level paths are the defect, not a satisfied binding."""
    document = _document()
    for slide in document.slides:
        for element in slide.elements:
            if element.diagram is None:
                continue
            for node in element.diagram.nodes:
                if node.label.strip():
                    assert node.binding_paths, node.id
                    assert not any(p.startswith("element:") for p in node.binding_paths), (
                        f"node {node.id} still binds through a coarse element path"
                    )


def test_atom_manifest_covers_every_document_string():
    """Atoms are emitted by the compiler, so nothing needs hand-enumeration."""
    document = _document()
    atoms = atoms_from_document(document)
    texts = {" ".join(a.text.split()) for a in atoms}
    for slide in document.slides:
        for element in slide.elements:
            if element.text and element.text.strip():
                assert " ".join(element.text.split()) in texts, element.id
