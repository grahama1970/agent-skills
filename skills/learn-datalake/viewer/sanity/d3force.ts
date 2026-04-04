/**
 * Sanity check: verify d3-force imports and forceSimulation exists.
 */
import {
  forceSimulation,
  forceLink,
  forceManyBody,
  forceCenter,
  forceCollide,
} from 'd3-force';

if (typeof forceSimulation !== 'function') {
  throw new Error('d3-force: forceSimulation is not a function');
}
if (typeof forceLink !== 'function') {
  throw new Error('d3-force: forceLink is not a function');
}
if (typeof forceManyBody !== 'function') {
  throw new Error('d3-force: forceManyBody is not a function');
}
if (typeof forceCenter !== 'function') {
  throw new Error('d3-force: forceCenter is not a function');
}
if (typeof forceCollide !== 'function') {
  throw new Error('d3-force: forceCollide is not a function');
}

// Verify simulation can be constructed and ticked
const sim = forceSimulation([{ id: 'a' }, { id: 'b' }])
  .force('charge', forceManyBody())
  .force('center', forceCenter(0, 0))
  .stop();

if (typeof sim.tick !== 'function') {
  throw new Error('d3-force: simulation.tick is not a function');
}

console.log('d3-force OK — forceSimulation:', typeof forceSimulation);
console.log('d3-force simulation alpha:', sim.alpha());
