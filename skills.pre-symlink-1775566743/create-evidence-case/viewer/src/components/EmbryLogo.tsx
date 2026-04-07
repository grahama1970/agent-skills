import { useRef, useEffect, useMemo, useCallback } from 'react';
import {
  forceSimulation,
  forceRadial,
  forceManyBody,
  forceCenter,
  type Simulation,
  type SimulationNodeDatum,
} from 'd3-force';
import particleData from '../assets/particle_data.json';

// ─── Types ──────────────────────────────────────────────────────

export type EmbryState = 'idle' | 'listening' | 'thinking' | 'synthesizing' | 'speaking';

interface ParticleNode extends SimulationNodeDatum {
  restX: number;
  restY: number;
  size: number;
  alpha: number;
  group: number;
}

const DISTANCE_SCALE: Record<string, number> = {
  far: 0.7,
  mid: 1.0,
  close: 1.1,
  hud: 0.8,
  phone: 1.0,
};

interface EmbryLogoProps {
  size?: number;
  state?: EmbryState;
  thinking?: boolean;
  audioLevel?: number;
  nvis?: boolean;
  distance?: 'far' | 'mid' | 'close' | 'hud' | 'phone';
  className?: string;
  'aria-label'?: string;
}

interface StateConfig {
  radiusMul: number;
  charge: number;
  breathHz: number;
  breathAmp: number;
  sparkEvery: number;
  dualRing?: boolean;
  pulseOut?: boolean;
  orbitSpeed?: number;
  converge?: boolean;
}

const STATE_CONFIGS: Record<EmbryState, StateConfig> = {
  idle:          { radiusMul: 1.0,  charge: -0.15, breathHz: 0.15, breathAmp: 0.03, sparkEvery: 0 },
  listening:     { radiusMul: 0.65, charge: -0.05, breathHz: 0.4,  breathAmp: 0.08, sparkEvery: 0 },
  thinking:      { radiusMul: 1.0,  charge: -0.3,  breathHz: 1.2,  breathAmp: 0.0,  sparkEvery: 3, dualRing: true, orbitSpeed: 1.5 },
  synthesizing:  { radiusMul: 0.45, charge: -0.4,  breathHz: 0.8,  breathAmp: 0.06, sparkEvery: 3, dualRing: true, converge: true },
  speaking:      { radiusMul: 1.0,  charge: -0.2,  breathHz: 3.0,  breathAmp: 0.08, sparkEvery: 4, pulseOut: true },
};

interface RingConfig {
  width: number;
  alpha: number;
  dashPattern?: number[];
  pulseHz?: number;
  pulseAmp?: number;
  rippleCount?: number;
  rotateSpeed?: number;
}

const STATE_RING_CONFIGS: Record<EmbryState, RingConfig | null> = {
  idle:          null,
  listening:     { width: 3, alpha: 0.85, pulseHz: 0.8, pulseAmp: 6 },
  thinking:      { width: 3, alpha: 0.80, dashPattern: [12, 8], rotateSpeed: 1.5 },
  synthesizing:  { width: 5, alpha: 0.85, dashPattern: [4, 4], rotateSpeed: -2.0 },
  speaking:      { width: 3, alpha: 0.85, rippleCount: 5 },
};

const RING_EMERGE_MS = 250;

interface StateColor {
  particle: readonly [number, number, number];
  glow: readonly [number, number, number];
  glowAlpha: number;
}

const STATE_COLORS: Record<EmbryState, StateColor> = {
  idle:          { particle: [0, 200, 180],  glow: [212, 175, 55],  glowAlpha: 0.18 },
  listening:     { particle: [0, 207, 255],  glow: [0, 207, 255],   glowAlpha: 0.25 },
  thinking:      { particle: [255, 140, 0],  glow: [255, 140, 0],   glowAlpha: 0.28 },
  synthesizing:  { particle: [180, 100, 255], glow: [140, 80, 220],  glowAlpha: 0.32 },
  speaking:      { particle: [136, 255, 0],  glow: [170, 215, 30],  glowAlpha: 0.30 },
};

const STATE_COLORS_NVIS: Record<EmbryState, StateColor> = {
  idle:          { particle: [0, 80, 40],    glow: [0, 60, 30],     glowAlpha: 0.10 },
  listening:     { particle: [0, 255, 60],   glow: [0, 255, 60],    glowAlpha: 0.35 },
  thinking:      { particle: [200, 255, 0],  glow: [200, 255, 0],   glowAlpha: 0.32 },
  synthesizing:  { particle: [0, 180, 180],  glow: [0, 180, 180],   glowAlpha: 0.36 },
  speaking:      { particle: [80, 255, 0],   glow: [80, 255, 0],    glowAlpha: 0.40 },
};

const ARIA_LABELS: Record<EmbryState, string> = {
  idle: 'Embry is idle',
  listening: 'Embry is listening',
  thinking: 'Embry is thinking',
  synthesizing: 'Embry is synthesizing a response',
  speaking: 'Embry is speaking',
};

const BG = [14, 14, 28] as const;
const BG_NVIS = [8, 12, 8] as const;

const RING = particleData.ring;
const FONT = particleData.font;

const COLOR_TRANSITION_MS = 300;

function sampleParticles(targetSize: number) {
  const all = particleData.particles;
  const ratio = Math.min(1, (targetSize / 1024) * 2);
  const minParticles = targetSize < 64 ? 40 : 100;
  const count = Math.max(minParticles, Math.round(all.length * ratio));
  if (count >= all.length) return all;
  const stride = all.length / count;
  return Array.from({ length: count }, (_, i) => all[Math.floor(i * stride)]);
}

function letterSizeForCanvas(baseRatio: number, canvasSize: number): number {
  if (canvasSize >= 128) return baseRatio;
  const boost = 1 + (128 - canvasSize) / 128 * 0.35;
  return baseRatio * boost;
}

function lerpChannel(a: number, b: number, t: number): number {
  return Math.round(a + (b - a) * t);
}

function lerpColor(
  from: readonly [number, number, number],
  to: readonly [number, number, number],
  t: number,
): [number, number, number] {
  return [
    lerpChannel(from[0], to[0], t),
    lerpChannel(from[1], to[1], t),
    lerpChannel(from[2], to[2], t),
  ];
}

function clamp01(v: number): number {
  return v < 0 ? 0 : v > 1 ? 1 : v;
}

export function EmbryLogo({
  size = 128,
  state: stateProp,
  thinking,
  audioLevel,
  nvis = false,
  distance: distanceProp,
  className,
  'aria-label': ariaLabel,
}: EmbryLogoProps) {
  const resolvedState: EmbryState = stateProp ?? (thinking ? 'thinking' : 'idle');
  const distanceScale = DISTANCE_SCALE[distanceProp ?? 'mid'] ?? 1.0;
  const isHudMode = distanceProp === 'hud';

  const canvasRef = useRef<HTMLCanvasElement>(null);
  const simRef = useRef<Simulation<ParticleNode, never> | null>(null);
  const nodesRef = useRef<ParticleNode[]>([]);
  const animatingRef = useRef(false);
  const rafRef = useRef<number>(0);
  const stateStartRef = useRef<number>(0);
  const lastFrameRef = useRef<number>(0);

  const prevStateRef = useRef<EmbryState>(resolvedState);
  const colorTransitionStartRef = useRef<number>(0);
  const prevColorsRef = useRef<StateColor | null>(null);

  const ringEmergeStartRef = useRef<number>(0);
  const prevHadRingRef = useRef(false);

  const reducedMotionRef = useRef(false);
  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return;
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)');
    reducedMotionRef.current = mq.matches;
    const handler = (e: MediaQueryListEvent) => { reducedMotionRef.current = e.matches; };
    mq.addEventListener('change', handler);
    return () => mq.removeEventListener('change', handler);
  }, []);

  const s = size;
  const dpr = typeof window !== 'undefined' ? window.devicePixelRatio || 1 : 1;
  const pxScale = s / 1024;

  const bg = nvis ? BG_NVIS : BG;
  const nvisAlphaScale = nvis ? 0.7 : 1.0;
  const colorPalette = nvis ? STATE_COLORS_NVIS : STATE_COLORS;

  const sampled = useMemo(() => sampleParticles(s), [s]);
  const stars = useMemo(() => particleData.stars, []);

  const getFrameColors = useCallback((now: number) => {
    const target = colorPalette[resolvedState];
    const prev = prevColorsRef.current;
    if (!prev || colorTransitionStartRef.current === 0) {
      return { particle: [...target.particle] as [number, number, number], glow: [...target.glow] as [number, number, number], glowAlpha: target.glowAlpha };
    }
    const elapsed = now - colorTransitionStartRef.current;
    const t = clamp01(elapsed / COLOR_TRANSITION_MS);
    if (t >= 1) {
      prevColorsRef.current = null;
      colorTransitionStartRef.current = 0;
      return { particle: [...target.particle] as [number, number, number], glow: [...target.glow] as [number, number, number], glowAlpha: target.glowAlpha };
    }
    return {
      particle: lerpColor(prev.particle, target.particle, t),
      glow: lerpColor(prev.glow, target.glow, t),
      glowAlpha: prev.glowAlpha + (target.glowAlpha - prev.glowAlpha) * t,
    };
  }, [resolvedState, colorPalette]);

  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const now = performance.now();
    const w = s * dpr;
    ctx.clearRect(0, 0, w, w);

    // BACKGROUND: Circular as per Embry-OS design system
    const cx = 0.5 * w;
    const cy = 0.5 * w;
    const backgroundRadius = 0.5 * w;
    
    ctx.beginPath();
    ctx.arc(cx, cy, backgroundRadius, 0, Math.PI * 2);
    ctx.fillStyle = `rgb(${bg[0]},${bg[1]},${bg[2]})`;
    ctx.fill();
    ctx.save();
    ctx.clip(); // Ensure everything stays within the circle

    for (const star of stars) {
      const sr = Math.max(star.size * pxScale * dpr, 0.5 * dpr);
      ctx.globalAlpha = star.alpha * nvisAlphaScale;
      ctx.fillStyle = nvis ? '#88cc88' : '#ffffff';
      ctx.beginPath();
      ctx.arc(star.x * w, star.y * w, sr, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.globalAlpha = 1;

    const colors = getFrameColors(now);

    const adjustedRatio = letterSizeForCanvas(FONT.sizeRatio, s);
    const letterSize = adjustedRatio * s * dpr;
    const glowR = letterSize * 0.7;

    const cfg = STATE_CONFIGS[resolvedState];
    let glowAlpha = colors.glowAlpha;
    if (resolvedState !== 'idle' && stateStartRef.current > 0 && !isHudMode) {
      const elapsed = (now - stateStartRef.current) / 1000;
      const range = cfg.breathHz > 0 ? 0.07 : 0.03;
      glowAlpha = colors.glowAlpha + range * Math.sin(elapsed * Math.PI * cfg.breathHz);
    }
    glowAlpha *= nvisAlphaScale;

    const glow = ctx.createRadialGradient(cx, cy, 0, cx, cy, glowR);
    glow.addColorStop(0, `rgba(${colors.glow[0]},${colors.glow[1]},${colors.glow[2]},${glowAlpha})`);
    glow.addColorStop(1, `rgba(${colors.glow[0]},${colors.glow[1]},${colors.glow[2]},0)`);
    ctx.fillStyle = glow;
    ctx.beginPath();
    ctx.arc(cx, cy, glowR, 0, Math.PI * 2);
    ctx.fill();

    const ringCfg = STATE_RING_CONFIGS[resolvedState];
    const orbitR = ((RING.innerR + RING.outerR) / 2) * s;

    if (ringCfg) {
      const elapsed = (stateStartRef.current > 0 && !isHudMode)
        ? (now - stateStartRef.current) / 1000 * distanceScale
        : 0;

      const emergeT = ringEmergeStartRef.current > 0
        ? clamp01((now - ringEmergeStartRef.current) / RING_EMERGE_MS)
        : 1;
      const emergeEased = 1 - Math.pow(1 - emergeT, 3);

      const scaledPulseAmp = (ringCfg.pulseAmp ?? 0) * pxScale;
      const pulseOffset = (ringCfg.pulseHz ?? 0) > 0
        ? scaledPulseAmp * Math.sin(elapsed * Math.PI * 2 * (ringCfg.pulseHz ?? 0))
        : 0;

      const synthContract = resolvedState === 'synthesizing'
        ? 1 - 0.50 * (0.5 + 0.5 * Math.sin(elapsed * Math.PI * 2 / 3))
        : 1;

      const ringR = (orbitR * synthContract + pulseOffset) * emergeEased;

      if (emergeEased > 0.01) {
        const sizeScale = Math.max(1, s / 128);
        const nvisRingScale = nvis ? 1.5 : 1.0;
        const ringAlpha = Math.min(1, ringCfg.alpha * emergeEased * nvisRingScale);
        ctx.strokeStyle = `rgba(${colors.particle[0]},${colors.particle[1]},${colors.particle[2]},${ringAlpha})`;
        ctx.lineWidth = Math.max(2 * dpr, ringCfg.width * sizeScale * nvisRingScale * dpr);

        if (ringCfg.dashPattern) {
          ctx.setLineDash(ringCfg.dashPattern.map(d => d * dpr));
          const circumference = 2 * Math.PI * ringR * dpr;
          ctx.lineDashOffset = -(elapsed * (ringCfg.rotateSpeed ?? 0) / (2 * Math.PI) * circumference);
        } else {
          ctx.setLineDash([]);
        }

        ctx.beginPath();
        ctx.arc(cx, cy, ringR * dpr, 0, Math.PI * 2);
        ctx.stroke();
        ctx.setLineDash([]);

        if (ringCfg.rippleCount && ringCfg.rippleCount > 0) {
          for (let r = 0; r < ringCfg.rippleCount; r++) {
            const phase = ((elapsed * 1.2 + r * (1 / ringCfg.rippleCount)) % 1);
            const rippleR = orbitR + phase * orbitR * 0.6;
            const rippleAlpha = ringCfg.alpha * 0.6 * (1 - phase * phase) * emergeEased * nvisRingScale;
            ctx.strokeStyle = `rgba(${colors.particle[0]},${colors.particle[1]},${colors.particle[2]},${rippleAlpha})`;
            ctx.lineWidth = Math.max(1.5 * dpr, 2.5 * sizeScale * dpr);
            ctx.beginPath();
            ctx.arc(cx, cy, rippleR * dpr, 0, Math.PI * 2);
            ctx.stroke();
          }
        }
      }
    }

    const nodes = nodesRef.current;
    const isActive = resolvedState !== 'idle';
    const sparkEvery = cfg.sparkEvery;

    for (let i = 0; i < nodes.length; i++) {
      const node = nodes[i];
      const pr = Math.max(node.size * pxScale * dpr, 0.5 * dpr);
      ctx.globalAlpha = node.alpha * nvisAlphaScale;

      if (isActive && sparkEvery > 0 && !nvis && i % sparkEvery === 0) {
        const spark = lerpColor(colors.particle, [255, 255, 255], 0.3);
        ctx.fillStyle = `rgb(${spark[0]},${spark[1]},${spark[2]})`;
        ctx.globalAlpha = Math.min(1, node.alpha * 1.3) * nvisAlphaScale;
      } else {
        ctx.fillStyle = `rgb(${colors.particle[0]},${colors.particle[1]},${colors.particle[2]})`;
      }

      ctx.beginPath();
      ctx.arc((node.x ?? node.restX) * dpr, (node.y ?? node.restY) * dpr, pr, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.globalAlpha = 1;

    ctx.fillStyle = `rgb(${colors.glow[0]},${colors.glow[1]},${colors.glow[2]})`;
    ctx.font = `${FONT.weight} ${letterSize}px '${FONT.family}', 'Nunito', sans-serif`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(FONT.letter, cx, cy);

    ctx.restore();
  }, [s, dpr, pxScale, stars, bg, nvisAlphaScale, nvis, resolvedState, getFrameColors, distanceScale, isHudMode]);

  useEffect(() => {
    const nodes: ParticleNode[] = sampled.map((p, i) => ({
      x: p.x * s,
      y: p.y * s,
      restX: p.x * s,
      restY: p.y * s,
      size: p.size,
      alpha: p.alpha,
      group: i % 5 < 2 ? 0 : 1,
    }));
    nodesRef.current = nodes;

    const centerX = 0.5 * s;
    const centerY = 0.5 * s;
    const orbitR = ((RING.innerR + RING.outerR) / 2) * s;

    const sim = forceSimulation<ParticleNode>(nodes)
      .alphaDecay(0.005)
      .velocityDecay(0.4)
      .force('radial', forceRadial<ParticleNode>(orbitR, centerX, centerY).strength(0.06))
      .force('charge', forceManyBody<ParticleNode>().strength(-0.15).distanceMax(s * 0.1))
      .force('center', forceCenter(centerX, centerY).strength(0.01))
      .on('tick', () => {
        if (animatingRef.current) draw();
      })
      .stop();

    simRef.current = sim;

    if (typeof document !== 'undefined' && document.fonts) {
      document.fonts.load(`${FONT.weight} 48px "${FONT.family}"`).then(() => draw());
    } else {
      draw();
    }

    return () => {
      cancelAnimationFrame(rafRef.current);
      sim.stop();
    };
  }, [s, sampled, draw]);

  useEffect(() => {
    const sim = simRef.current;
    if (!sim) return;

    const nodes = nodesRef.current;
    const centerX = 0.5 * s;
    const centerY = 0.5 * s;
    const currentOrbitR = ((RING.innerR + RING.outerR) / 2) * s;
    const cfg = STATE_CONFIGS[resolvedState];
    const now = performance.now();

    if (prevStateRef.current !== resolvedState) {
      prevColorsRef.current = { ...colorPalette[prevStateRef.current] };
      colorTransitionStartRef.current = now;

      const hadRing = prevHadRingRef.current;
      const willHaveRing = STATE_RING_CONFIGS[resolvedState] !== null;
      if (!hadRing && willHaveRing) {
        ringEmergeStartRef.current = now;
      }
      prevHadRingRef.current = willHaveRing;
      prevStateRef.current = resolvedState;
    }

    if (resolvedState === 'idle') {
      sim.stop();
      stateStartRef.current = now;
      animatingRef.current = true;
      lastFrameRef.current = now;

      const returnToRest = () => {
        if (!animatingRef.current) return;
        const frameNow = performance.now();
        const dt = Math.min((frameNow - lastFrameRef.current) / 1000, 0.05);
        lastFrameRef.current = frameNow;

        const lerpRate = 1 - Math.exp(-5 * dt);
        const elapsed = (frameNow - stateStartRef.current) / 1000;
        const breathFactor = 1 + cfg.breathAmp * Math.sin(elapsed * Math.PI * 2 * cfg.breathHz);

        for (const node of nodes) {
          const targetX = node.restX + (node.restX - centerX) * (breathFactor - 1);
          const targetY = node.restY + (node.restY - centerY) * (breathFactor - 1);
          const dx = targetX - (node.x ?? node.restX);
          const dy = targetY - (node.y ?? node.restY);
          if (Math.abs(dx) > 0.3 || Math.abs(dy) > 0.3) {
            node.x = (node.x ?? node.restX) + dx * lerpRate;
            node.y = (node.y ?? node.restY) + dy * lerpRate;
          } else {
            node.x = targetX;
            node.y = targetY;
          }
        }
        draw();
        rafRef.current = requestAnimationFrame(returnToRest);
      };
      returnToRest();

      return () => {
        animatingRef.current = false;
        cancelAnimationFrame(rafRef.current);
      };
    }

    if (reducedMotionRef.current || isHudMode) {
      sim.stop();
      animatingRef.current = true;
      stateStartRef.current = now;

      for (const node of nodes) {
        const dx = node.restX - centerX;
        const dy = node.restY - centerY;
        const dist = Math.sqrt(dx * dx + dy * dy);
        if (dist > 0) {
          const targetR = currentOrbitR * cfg.radiusMul;
          node.x = centerX + (dx / dist) * targetR;
          node.y = centerY + (dy / dist) * targetR;
        }
      }

      const colorLoop = () => {
        if (!animatingRef.current) return;
        draw();
        rafRef.current = requestAnimationFrame(colorLoop);
      };
      colorLoop();

      return () => {
        animatingRef.current = false;
        cancelAnimationFrame(rafRef.current);
      };
    }

    animatingRef.current = true;
    stateStartRef.current = now;
    lastFrameRef.current = now;

    if (cfg.dualRing) {
      sim.force('radial', null);
      sim.force('radial-inner', forceRadial<ParticleNode>(
        currentOrbitR * 0.6,
        centerX,
        centerY,
      ).strength((d: ParticleNode) => d.group === 0 ? 0.10 : 0));
      sim.force('radial-outer', forceRadial<ParticleNode>(
        currentOrbitR * 1.2,
        centerX,
        centerY,
      ).strength((d: ParticleNode) => d.group === 1 ? 0.10 : 0));
    } else {
      sim.force('radial-inner', null);
      sim.force('radial-outer', null);
      sim.force('radial', forceRadial<ParticleNode>(
        currentOrbitR * cfg.radiusMul,
        centerX,
        centerY,
      ).strength(0.06));
    }

    sim.force('charge', forceManyBody<ParticleNode>().strength(cfg.charge).distanceMax(s * 0.1));
    sim.alpha(1.0).restart();

    const animLoop = () => {
      if (!animatingRef.current) return;
      const frameNow = performance.now();
      const elapsed = (frameNow - stateStartRef.current) / 1000;

      if (cfg.dualRing) {
        const speed = 0.3;
        for (const node of nodes) {
          const dx = (node.x ?? node.restX) - centerX;
          const dy = (node.y ?? node.restY) - centerY;
          const dist = Math.sqrt(dx * dx + dy * dy);
          if (dist > 1) {
            const nx = dx / dist;
            const ny = dy / dist;
            const dir = node.group === 0 ? 1 : -1;
            node.vx = (node.vx ?? 0) + (-ny * speed * dir) * 0.02;
            node.vy = (node.vy ?? 0) + (nx * speed * dir) * 0.02;
          }
        }
      }

      if (cfg.pulseOut) {
        const al = audioLevel ?? 0.5;
        const pulseR = currentOrbitR * cfg.radiusMul + currentOrbitR * cfg.breathAmp * al * Math.sin(elapsed * Math.PI * 2 * cfg.breathHz);
        const radialForce = sim.force('radial') as ReturnType<typeof forceRadial<ParticleNode>> | null;
        if (radialForce) {
          radialForce.radius(pulseR);
        }
      }

      if (resolvedState === 'listening') {
        const breathR = currentOrbitR * cfg.radiusMul + currentOrbitR * cfg.breathAmp * Math.sin(elapsed * Math.PI * 2 * cfg.breathHz);
        const radialForce = sim.force('radial') as ReturnType<typeof forceRadial<ParticleNode>> | null;
        if (radialForce) {
          radialForce.radius(breathR);
        }
      }

      rafRef.current = requestAnimationFrame(animLoop);
    };
    animLoop();

    return () => {
      animatingRef.current = false;
      cancelAnimationFrame(rafRef.current);
      sim.stop();
      sim.force('radial-inner', null);
      sim.force('radial-outer', null);
    };
  }, [resolvedState, s, draw, audioLevel, colorPalette, isHudMode, distanceScale]);

  return (
    <canvas
      ref={canvasRef}
      width={s * dpr}
      height={s * dpr}
      className={className}
      role="img"
      aria-label={ariaLabel ?? ARIA_LABELS[resolvedState]}
      style={{
        width: s,
        height: s,
        borderRadius: '50%',
      }}
    />
  );
}
