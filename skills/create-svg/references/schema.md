# Scene and theme schema

External YAML is parsed with `yaml.safe_load` and then validated with Pydantic using
`extra="forbid"`. Unknown keys fail closed.

## Scene

Every scene includes:

- `schema_version: 1`
- `theme`: bundled theme name or a theme YAML path
- `template`: `positive-negative` or `fanout-anatomy`
- `metadata.title` and `metadata.description`
- template-specific semantic content
- optional `timeline`

## Timeline

```yaml
timeline:
  cycle_ms: 12000
  events:
    - target: source-node
      recipe: fade-slide-y
      start_ms: 150
      end_ms: 900
      from_y: -24
```

Supported recipes:

- `fade`
- `fade-slide-x`
- `fade-slide-y`
- `draw-stroke`
- `color-pin`
- `pulse`
- `halo-pulse`

Each event receives a unique class. Multiple events can target one element because the
compiler adds multiple classes rather than overwriting one `animation` declaration.

## Target names

`positive-negative` exposes:

- `left-glow`
- `right-glow`
- `left-card`
- `right-card`

`fanout-anatomy` exposes:

- `source-node`
- `source-glow`
- `connector-0`, `connector-1`, ...
- `target-card-0`, `target-card-1`, ...

Unknown targets fail before SVG emission.

## Component output contract

Generated scenes may expose semantically meaningful groups using stable `id` and
`data-component` attributes. Downstream checks should bind labels, nodes, pills,
and cards to those component groups rather than inferring meaning from visual
order alone.
