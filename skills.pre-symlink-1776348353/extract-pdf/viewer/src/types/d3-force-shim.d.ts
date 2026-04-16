declare module "d3-force" {
  export interface SimulationNodeDatum {
    x?: number;
    y?: number;
    vx?: number;
    vy?: number;
    index?: number;
  }

  export interface Simulation<NodeDatum extends SimulationNodeDatum = SimulationNodeDatum, LinkDatum = never> {
    nodes(nodes?: NodeDatum[]): Simulation<NodeDatum, LinkDatum>;
    force(name: string, force?: unknown): any;
    alpha(value?: number): Simulation<NodeDatum, LinkDatum>;
    alphaDecay(value?: number): Simulation<NodeDatum, LinkDatum>;
    velocityDecay(value?: number): Simulation<NodeDatum, LinkDatum>;
    restart(): Simulation<NodeDatum, LinkDatum>;
    stop(): Simulation<NodeDatum, LinkDatum>;
    tick(iterations?: number): Simulation<NodeDatum, LinkDatum>;
  }

  export interface RadialForce<NodeDatum extends SimulationNodeDatum = SimulationNodeDatum> {
    radius(value: number | ((node: any) => number)): RadialForce<NodeDatum>;
    strength(value: number | ((node: any) => number)): RadialForce<NodeDatum>;
  }

  export interface ManyBodyForce<NodeDatum extends SimulationNodeDatum = SimulationNodeDatum> {
    strength(value: number | ((node: any) => number)): ManyBodyForce<NodeDatum>;
    distanceMax(value: number): ManyBodyForce<NodeDatum>;
  }

  export interface CenterForce<NodeDatum extends SimulationNodeDatum = SimulationNodeDatum> {
    strength(value: number): CenterForce<NodeDatum>;
  }

  export function forceSimulation<NodeDatum extends SimulationNodeDatum = SimulationNodeDatum>(
    nodes?: NodeDatum[],
  ): Simulation<NodeDatum, never>;

  export function forceRadial<NodeDatum extends SimulationNodeDatum = SimulationNodeDatum>(
    radius?: number,
    x?: number,
    y?: number,
  ): RadialForce<NodeDatum>;

  export function forceManyBody<NodeDatum extends SimulationNodeDatum = SimulationNodeDatum>(): ManyBodyForce<NodeDatum>;
  export function forceCenter<NodeDatum extends SimulationNodeDatum = SimulationNodeDatum>(x?: number, y?: number): CenterForce<NodeDatum>;
}
