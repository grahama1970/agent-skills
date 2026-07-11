# s02 Memories

Deep persona memory recall biased by the idea contract.

## Input

- `idea_contract.json` from s01_idea

## Output

`residue_links.json` — top 20 residues ranked by impact, with contradiction detection. Consumed by s03 Story.

## Behavior

1. Reads `idea_contract.json` — extracts persona_ids, dream themes, and source memory IDs from the selected candidate
2. **Graph edge following**: traces multi-hop connections from source memory IDs
3. **Theme recall**: runs targeted queries on emotional themes detected in the dream (grief, betrayal, hope, etc.)
4. **ToM edge recall**: surfaces theory-of-mind states (beliefs, desires, intentions) for each persona
5. **Contradiction detection**: finds residue pairs with opposing tom_state_types or emotional tones
6. Ranks all recalled residue by impact score and writes the top 20

## Usage

```bash
python pipeline/s02_memories/residue.py \
  --idea-contract outputs/<run-id>/idea_contract.json \
  --output-dir outputs/<run-id>/
```

## Contract schema

`persona_dream.residue_links.v1`

| Field | Description |
|---|---|
| `persona_ids` | Personas for this dream |
| `graph_edges_followed` | Source memory IDs traced via graph |
| `total_chunks_recalled` | Graph + theme + ToM chunks |
| `contradictions` | Conflicting residue pairs detected |
| `residue[]` | Top 20 chunks with impact, text, emotional metadata |
