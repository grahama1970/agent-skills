# SFX Catalog Implementation Roadmap

## Overview

Phased implementation plan for the SFX Catalog system, designed to deliver value incrementally while building toward a comprehensive solution.

## Phase 1: Foundation (MVP) - 2-3 weeks

**Goal**: Basic cataloging and search functionality integrated with memory.

### Deliverables

#### 1. Core Audio Analysis

- [ ] Audio feature extraction ([`audio_analyzer.py`](audio_analyzer.py))
  - Duration, sample rate, channels
  - Frequency profile (dominant freq, centroid, bandwidth)
  - Envelope characteristics (ADSR, type)
  - Loudness metrics (peak, RMS, dynamic range)
  - Zero-crossing rate, harmonic ratio
- [ ] Batch processing with parallelization
- [ ] Progress reporting to [`task-monitor`](../task-monitor)

**Dependencies**: `librosa`, `soundfile`, `scipy`, `numpy`

**Test**: Can extract features from all 166 files in <10 minutes

#### 2. Rule-Based Classification

- [ ] Category taxonomy definition ([`content_classifier.py`](content_classifier.py))
  - Define 9 base categories: impact, ambient, foley, transition, ui, texture, tonal, vocal, nature
  - Implement heuristic rules based on audio features
  - Multi-label classification support
- [ ] Category validation tests

**Test**: Achieves >60% category accuracy on manual validation set

#### 3. Metadata Generation

- [ ] Template-based description generator ([`metadata_generator.py`](metadata_generator.py))
  - Simple template: "{envelope_type} {categories[0]} sound, {duration}s"
  - Keyword extraction from features
  - Use case suggestions based on categories
- [ ] Optional LLM integration via [`scillm`](../scillm) skill
  - Batch generation for better descriptions
  - Fallback to template if LLM unavailable

**Test**: All 166 files have searchable descriptions

#### 4. Memory Integration

- [ ] ArangoDB schema implementation ([`memory_bridge.py`](memory_bridge.py))
  - Create `sfx_library`, `sfx_usage`, `sfx_generated` collections
  - Create indices (fulltext, skiplist, hash)
  - Create edge collections
- [ ] Ingestion pipeline
  - Batch insert SFX documents
  - Generate embeddings via [`embedding`](../embedding) skill
  - Store in memory with scope `horus_lore`
- [ ] Basic search queries
  - Full-text search
  - Semantic search via embeddings
  - Category filtering

**Dependencies**: `python-arango`, common [`memory_client`](../common/memory_client.py)

**Test**: Can ingest 166 files and search returns relevant results

#### 5. CLI Interface

- [ ] Command-line tool ([`cli.py`](cli.py))
  - `catalog` - Analyze directory
  - `ingest` - Import manifest into memory
  - `search` - Query catalog
  - `status` - System health check
- [ ] Rich output formatting (`typer`, `rich`)
- [ ] Error handling and validation

**Test**: All commands work end-to-end

### Acceptance Criteria

1. ✅ All 166 library files cataloged with metadata
2. ✅ Metadata ingested into ArangoDB
3. ✅ Search returns relevant results for 10 test queries
4. ✅ CLI commands documented and functional
5. ✅ Sanity checks passing

### Timeline

- **Week 1**: Audio analysis + classification
- **Week 2**: Memory integration + ingestion
- **Week 3**: CLI + testing + documentation

---

## Phase 2: Integration & Learning - 2 weeks

**Goal**: Integrate with filmmaking pipeline and enable usage tracking.

### Deliverables

#### 1. Usage Tracking

- [ ] Usage recording ([`memory_bridge.py`](memory_bridge.py))
  - Record SFX selections in `sfx_usage` collection
  - Store scene context, rationale, alternatives considered
  - Generate embeddings for usage records
- [ ] Prior usage recall
  - Query similar scenes from usage history
  - Rank by semantic similarity
  - Boost reused SFX (positive feedback signal)

**Test**: Can record usage and recall from prior projects

#### 2. Query Engine

- [ ] Multi-strategy search ([`query_engine.py`](query_engine.py))
  - Strategy 1: Memory First (check prior usage)
  - Strategy 2: Semantic search (catalog)
  - Strategy 3: Structured filters (category + duration)
  - Strategy 4: Generation (if enabled)
- [ ] Result ranking and scoring
- [ ] Confidence thresholds

**Test**: Query engine returns best matches for test scenarios

#### 3. create-movie Integration

- [ ] Hook into Phase 4 - Generate
- [ ] Parse audio cues from screenplay
- [ ] Query SFX for each cue
- [ ] Record usage after selection
- [ ] Integration testing with full movie workflow

**Test**: Can generate audio for a test movie scene

#### 4. create-storyboard Integration

- [ ] SFX suggestions during storyboarding
- [ ] Natural language recommendations
- [ ] Preview capability
- [ ] Integration testing

**Test**: Storyboard asks for SFX suggestions and gets relevant results

### Acceptance Criteria

1. ✅ Usage tracking works end-to-end
2. ✅ Query engine implements all 3 search strategies
3. ✅ create-movie can query and use SFX
4. ✅ create-storyboard suggests SFX during planning
5. ✅ Memory First pattern demonstrably improves over time

### Timeline

- **Week 4**: Usage tracking + query engine
- **Week 5**: Integration with create-movie and create-storyboard

---

## Phase 3: Generation & Caching - 2 weeks

**Goal**: Generate missing SFX and cache for reuse.

### Deliverables

#### 1. Audio Generation

- [ ] Stable Audio Open integration ([`audio_generator.py`](audio_generator.py))
  - Text-to-audio generation
  - Duration control
  - Quality parameters (steps, CFG scale)
  - Seed management for reproducibility
- [ ] Generated SFX ingestion
  - Auto-catalog generated files
  - Add to `sfx_library` with `source: "generated"`
- [ ] GPU memory management
  - Handle VRAM constraints
  - Fallback to CPU if needed

**Dependencies**: `stable-audio-tools`, `torch`

**Test**: Can generate 3-second SFX from text prompt

#### 2. Generation Caching

- [ ] Cache lookup before generation ([`query_engine.py`](query_engine.py))
  - Check `sfx_generated` for similar prompts
  - Semantic similarity on prompt embeddings
  - Return cached result if >0.90 similarity
- [ ] Cache management
  - Track reuse count
  - Prune low-quality generations
  - User approval workflow

**Test**: Second request for similar prompt returns cached result instantly

#### 3. Similarity Graph

- [ ] Compute acoustic similarity ([`similarity_graph.py`](similarity_graph.py))
  - Pairwise embedding similarity
  - Create `sfx_similar_to` edges
  - Threshold tuning (0.75-0.85)
- [ ] Similar SFX search
  - Find alternatives to a given SFX
  - Useful for "find me something like this but different"

**Test**: Similarity graph recommends relevant alternatives

### Acceptance Criteria

1. ✅ Can generate SFX on demand
2. ✅ Generation cache prevents duplicate work
3. ✅ Generated SFX are cataloged and searchable
4. ✅ Similarity graph provides useful recommendations
5. ✅ End-to-end generation workflow documented

### Timeline

- **Week 6**: Stable Audio integration + generation
- **Week 7**: Caching + similarity graph

---

## Phase 4: Enhancement & Scale - 1-2 weeks

**Goal**: Improve accuracy, performance, and user experience.

### Deliverables

#### 1. Advanced Classification

- [ ] Zero-shot audio classifier ([`content_classifier.py`](content_classifier.py))
  - Replace rule-based with ML model
  - Options: LAION CLAP, AudioSet models
  - A/B test against rule-based
- [ ] Category refinement
  - Add subcategories based on usage patterns
  - User feedback integration

**Test**: Classification accuracy improves to >80%

#### 2. Usage Analytics

- [ ] Statistics dashboard ([`stats.py`](stats.py))
  - Most used SFX
  - Category distribution
  - Project usage patterns
  - Trend analysis over time
- [ ] Export capabilities (CSV, JSON)

**Test**: Analytics provide actionable insights

#### 3. Performance Optimization

- [ ] Query performance tuning
  - Index optimization
  - Query plan analysis
  - Caching strategies
- [ ] Batch operations
  - Parallel ingestion
  - Bulk usage recording
- [ ] Benchmark suite

**Goal**: <100ms for typical searches

#### 4. Developer Experience

- [ ] Better error messages
- [ ] Verbose logging modes
- [ ] Debug utilities
- [ ] API documentation improvements

### Acceptance Criteria

1. ✅ Classification accuracy measurably improved
2. ✅ Analytics provide useful insights
3. ✅ Query performance meets <100ms target
4. ✅ Developer documentation complete

### Timeline

- **Week 8**: Advanced classification + analytics
- **Week 9** (optional): Performance optimization + polish

---

## Phase 5: Future Enhancements (Backlog)

Ideas for future development, prioritized by value:

### High Priority

1. **Multi-modal search**
   - Search by audio example ("find me something like this")
   - Screenshot-to-SFX (visual scene → sound suggestions)
   - Video context analysis

2. **Collaborative filtering**
   - Learn from other filmmakers' choices
   - Cross-project pattern analysis
   - Community catalog sharing

3. **Audio effects pipeline**
   - Apply EQ, reverb, compression
   - Adjust duration without pitch shift
   - Layering and mixing suggestions

### Medium Priority

4. **Fine-tuned models**
   - Train CLAP on filmmaking-specific sounds
   - Custom generation model for cinematic SFX
   - Personalized to Horus's style

5. **Multi-language descriptions**
   - Generate descriptions in multiple languages
   - Support international collaborations

6. **Mobile/Web UI**
   - Browser-based SFX search and preview
   - Mobile app for field recording ingestion
   - Collaborative review tools

### Low Priority

7. **Advanced features**
   - Automatic scene audio layout
   - Dialogue-aware SFX placement
   - Music-to-SFX synchronization
   - Real-time preview during storyboarding

---

## Dependencies & Risks

### Critical Dependencies

| Component        | Dependency                        | Risk Level | Mitigation                     |
| ---------------- | --------------------------------- | ---------- | ------------------------------ |
| Memory           | ArangoDB running                  | Medium     | Sanity checks on startup       |
| Embeddings       | [`embedding`](../embedding) skill | Low        | Fallback to keyword search     |
| LLM              | [`scillm`](../scillm) skill       | Low        | Template-based fallback        |
| Audio Generation | Stable Audio + GPU                | High       | Optional feature, CPU fallback |

### Technical Risks

1. **Audio analysis accuracy**
   - Risk: Heuristic classification may be too simplistic
   - Mitigation: Start with rule-based, upgrade to ML in Phase 4

2. **Generation quality**
   - Risk: Stable Audio may not produce usable results
   - Mitigation: Cache only user-approved generations, provide rating system

3. **Memory performance at scale**
   - Risk: Query times degrade with large catalogs
   - Mitigation: Indexing strategy, query optimization in Phase 4

4. **GPU availability for generation**
   - Risk: VRAM constraints or no GPU
   - Mitigation: CPU fallback, queue-based generation, cloud GPU option

---

## Testing Strategy

### Unit Tests

- Audio feature extraction accuracy
- Category classification correctness
- Metadata generation quality
- Database operations (CRUD)
- Search ranking algorithm

### Integration Tests

- End-to-end cataloging workflow
- Memory ingestion pipeline
- Query engine search strategies
- create-movie integration
- create-storyboard integration

### Performance Tests

- Catalog 1000 files (stress test)
- Query latency under load
- Generation throughput
- Memory usage profiling

### User Acceptance Tests

- Manual validation of search results
- Filmmaking workflow integration
- Usage tracking correctness
- Generation quality assessment

### Continuous Testing

```bash
# Sanity checks (pre-commit)
./sanity/run_all.sh

# Unit tests
uv run pytest tests/

# Integration tests
uv run pytest tests/integration/

# Performance benchmarks
uv run python tests/bench/benchmark_search.py
```

---

## Success Metrics

### Phase 1 (MVP)

- [ ] 166 library files cataloged
- [ ] Search precision@5 > 80% on test queries
- [ ] Cataloging time < 10 minutes
- [ ] Zero data loss during ingestion

### Phase 2 (Integration)

- [ ] create-movie successfully uses SFX catalog
- [ ] Usage tracking captures >90% of selections
- [ ] Memory First improves relevance by 20%
- [ ] Integration tests passing

### Phase 3 (Generation)

- [ ] Can generate SFX for 100% of prompts
- [ ] Cache hit rate > 40% after 10 generated SFX
- [ ] User approval rate for generations > 70%
- [ ] Generation time < 60 seconds

### Phase 4 (Enhancement)

- [ ] Search latency < 100ms (p95)
- [ ] Classification accuracy > 80%
- [ ] Analytics dashboard used weekly
- [ ] Zero critical bugs in production

---

## Resource Requirements

### Development Time

- **Phase 1**: 80-120 hours (2-3 weeks)
- **Phase 2**: 60-80 hours (2 weeks)
- **Phase 3**: 60-80 hours (2 weeks)
- **Phase 4**: 40-60 hours (1-2 weeks)
- **Total**: 240-340 hours (7-10 weeks)

### Compute Resources

- **Development**: Local machine with 16GB RAM, GPU optional
- **Production**: Same as existing memory system (ArangoDB)
- **Generation**: GPU with 8GB+ VRAM (or CPU fallback)

### Storage Requirements

- **Library**: 166 files × ~1MB = ~166MB (existing)
- **Metadata**: ~50MB (JSON + ArangoDB)
- **Embeddings**: ~2MB (166 × 384 dimensions × 4 bytes)
- **Generated SFX**: ~1GB over time (100 files × 10MB)
- **Total**: ~1.2GB

---

## Deployment Plan

### Phase 1 Deployment

```bash
# 1. Install skill
cd .pi/skills/sfx-catalog
uv sync

# 2. Run sanity checks
./sanity/run_all.sh

# 3. Catalog library
./run.sh catalog /mnt/storage12tb/media/sfx/ --output library_manifest.json

# 4. Ingest into memory
./run.sh ingest library_manifest.json

# 5. Test search
./run.sh search "door creak"

# 6. Verify status
./run.sh status
```

### Integration Deployment

```bash
# Update create-movie skill
cd .pi/skills/create-movie
# (add sfx-catalog import)

# Test integration
./run.sh create "test movie" --dry-run

# Full test
./run.sh create "short test film" --output test.mp4
```

### Monitoring

- Monitor query latency via logs
- Track usage patterns via analytics
- Watch for errors in task-monitor
- Review generation quality feedback

---

## Maintenance

### Weekly Tasks

- Review usage statistics
- Check for failed generations
- Verify search quality
- Update documentation

### Monthly Tasks

- Recompute similarity graph
- Prune low-quality generations
- Optimize indices
- Backup catalog and usage data

### Quarterly Tasks

- Evaluate classification accuracy
- Review category taxonomy
- Audit usage patterns
- Plan enhancements

---

## Next Steps

1. **Review this roadmap** with stakeholders
2. **Set up development environment** (Phase 1 dependencies)
3. **Create project structure** (files, directories)
4. **Begin Phase 1 implementation** starting with audio analysis
5. **Establish testing infrastructure** (unit tests, sanity checks)

For detailed architecture, see [`ARCHITECTURE.md`](ARCHITECTURE.md).  
For API reference, see [`API.md`](API.md).  
For database schema, see [`MEMORY_SCHEMA.md`](MEMORY_SCHEMA.md).
