# s05 Panels

Generates storyboard panel images from a storyboard panel contract.

## Input

- `storyboard_panel_contract.json`

## Output

- `panel_NN_storyboard.png`
- `panel_NN_storyboard_receipt.json`
- `panel_NN_storyboard_events.jsonl`

## Contract schema

`contracts/storyboard_panel_contract.schema.json`

## Usage

```bash
python pipeline/s05_panels/create_panel.py \
  --panel 01 \
  --output panel_01_storyboard.png \
  --contract contracts/storyboard_panel_contract.json \
  --backend scillm
```
