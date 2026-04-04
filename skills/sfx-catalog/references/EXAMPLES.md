## Usage Examples

### Example 1: Initial Library Cataloging

```bash

## Testing

```bash

## Troubleshooting

### "ArangoDB connection failed"

```bash

## Roadmap

### Phase 1: Foundation (MVP) - Weeks 1-3

- ✅ Audio analysis with librosa
- ✅ Rule-based classification
- ✅ Memory integration
- ✅ CLI interface

### Phase 2: Integration - Weeks 4-5

- ⏳ Usage tracking
- ⏳ Query engine (multi-strategy)
- ⏳ create-movie integration
- ⏳ create-storyboard integration

### Phase 3: Generation - Weeks 6-7

- ⏳ Stable Audio integration
- ⏳ Generation caching
- ⏳ Similarity graph

### Phase 4: Enhancement - Weeks 8-9

- ⏳ Advanced classification (ML-based)
- ⏳ Usage analytics
- ⏳ Performance optimization

**Full Plan**: See [`ROADMAP.md`](ROADMAP.md) for detailed implementation timeline.

## Contributing

This skill follows the conventions in [`../CONVENTIONS.md`](../CONVENTIONS.md):

- **Code**: Stored in `.pi/skills/sfx-catalog/`
- **Data**: Stored in `~/.pi/sfx-catalog/` (persistent across syncs)
- **Progress**: Reported to [`task-monitor`](../task-monitor) for long operations
- **Memory**: Uses `horus_lore` scope via [`memory`](../memory) skill

## Documentation

- [`ARCHITECTURE.md`](ARCHITECTURE.md) - System design and component specs
- [`MEMORY_SCHEMA.md`](MEMORY_SCHEMA.md) - ArangoDB collections and queries
- [`API.md`](API.md) - Complete CLI and Python API reference
- [`ROADMAP.md`](ROADMAP.md) - Implementation plan and timeline

## License

Part of Horus's filmmaking toolkit. For private use.

---

**Status**: Design phase complete, ready for implementation.

**Next Step**: Begin Phase 1 implementation (audio analysis + cataloging).
