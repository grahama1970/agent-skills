import QtQuick
import "."

// Embry force-ring particle animation — port of EmbryThinkingIcon.tsx to QML Canvas2D
// Driven by embryState: idle/listening/thinking/synthesizing/speaking
// ~200 sampled particles at 256px, 60fps timer, Canvas.Threaded rendering

Item {
    id: root

    required property string embryState        // "idle", "listening", etc.
    required property string particleDataJson  // JSON array of {x,y,size,alpha}
    required property string starsJson
    required property string ringJson
    required property string fontJson
    required property string stateConfigsJson
    required property string ringConfigsJson
    required property string stateColorsJson

    property bool reduceMotion: false
    property real audioLevel: 0.5

    implicitWidth: 256
    implicitHeight: 256

    Accessible.name: {
        var labels = {
            "idle": "Embry is idle",
            "listening": "Embry is listening",
            "thinking": "Embry is thinking",
            "synthesizing": "Embry is synthesizing a response",
            "speaking": "Embry is speaking"
        };
        return labels[embryState] || "Embry";
    }
    Accessible.role: Accessible.Graphic

    // ── Internal state ───────────────────────────────────────
    QtObject {
        id: internal

        property var particles: []
        property var stars: []
        property var ring: ({innerR: 0.195, outerR: 0.273})
        property var font: ({family: "Varela Round", weight: 400, letter: "e", sizeRatio: 0.293})
        property var stateConfigs: ({})
        property var ringConfigs: ({})
        property var stateColors: ({})

        // Animation state
        property string prevState: "idle"
        property real stateStartTime: 0
        property real colorTransitionStart: 0
        property var prevColors: null
        property real ringEmergeStart: 0
        property bool prevHadRing: false

        // Particle positions (mutable arrays of x, y per particle)
        property var px: []
        property var py: []
        property var pgroup: []

        function initParticles() {
            if (particles.length === 0) return;
            var n = particles.length;
            var _px = new Array(n);
            var _py = new Array(n);
            var _pg = new Array(n);
            var s = canvas.width;
            for (var i = 0; i < n; i++) {
                _px[i] = particles[i].x * s;
                _py[i] = particles[i].y * s;
                _pg[i] = (i % 5 < 2) ? 0 : 1;  // 40% inner, 60% outer
            }
            px = _px;
            py = _py;
            pgroup = _pg;
        }
    }

    // ── Parse JSON when data arrives ─────────────────────────
    onParticleDataJsonChanged: {
        if (particleDataJson) {
            internal.particles = JSON.parse(particleDataJson);
            internal.initParticles();
        }
    }
    onStarsJsonChanged: {
        if (starsJson) internal.stars = JSON.parse(starsJson);
    }
    onRingJsonChanged: {
        if (ringJson) internal.ring = JSON.parse(ringJson);
    }
    onFontJsonChanged: {
        if (fontJson) internal.font = JSON.parse(fontJson);
    }
    onStateConfigsJsonChanged: {
        if (stateConfigsJson) internal.stateConfigs = JSON.parse(stateConfigsJson);
    }
    onRingConfigsJsonChanged: {
        if (ringConfigsJson) internal.ringConfigs = JSON.parse(ringConfigsJson);
    }
    onStateColorsJsonChanged: {
        if (stateColorsJson) internal.stateColors = JSON.parse(stateColorsJson);
    }

    // ── State transitions ────────────────────────────────────
    onEmbryStateChanged: {
        var now = Date.now();
        var prev = internal.prevState;
        if (prev !== embryState) {
            // Color transition
            var prevCol = internal.stateColors[prev];
            if (prevCol) {
                internal.prevColors = {
                    particle: prevCol.particle.slice(),
                    glow: prevCol.glow.slice(),
                    glowAlpha: prevCol.glowAlpha
                };
            }
            internal.colorTransitionStart = now;

            // Ring emergence
            var hadRing = internal.prevHadRing;
            var willHaveRing = internal.ringConfigs[embryState] !== null && internal.ringConfigs[embryState] !== undefined;
            if (!hadRing && willHaveRing) {
                internal.ringEmergeStart = now;
            } else if (!willHaveRing) {
                internal.ringEmergeStart = 0;
            }
            internal.prevHadRing = willHaveRing;
            internal.prevState = embryState;
            internal.stateStartTime = now;
        }
    }

    // ── Helper functions ─────────────────────────────────────
    function lerpChannel(a, b, t) {
        return Math.round(a + (b - a) * t);
    }
    function lerpColor(from, to, t) {
        return [lerpChannel(from[0], to[0], t),
                lerpChannel(from[1], to[1], t),
                lerpChannel(from[2], to[2], t)];
    }
    function clamp01(v) { return v < 0 ? 0 : v > 1 ? 1 : v; }

    function getFrameColors(now) {
        var target = internal.stateColors[embryState];
        if (!target) return {particle: [0,200,180], glow: [212,175,55], glowAlpha: 0.18};

        var prev = internal.prevColors;
        if (!prev || internal.colorTransitionStart === 0) {
            return {particle: target.particle.slice(), glow: target.glow.slice(), glowAlpha: target.glowAlpha};
        }
        var elapsed = now - internal.colorTransitionStart;
        var t = clamp01(elapsed / 300);  // COLOR_TRANSITION_MS
        if (t >= 1) {
            internal.prevColors = null;
            internal.colorTransitionStart = 0;
            return {particle: target.particle.slice(), glow: target.glow.slice(), glowAlpha: target.glowAlpha};
        }
        return {
            particle: lerpColor(prev.particle, target.particle, t),
            glow: lerpColor(prev.glow, target.glow, t),
            glowAlpha: prev.glowAlpha + (target.glowAlpha - prev.glowAlpha) * t
        };
    }

    // ── Physics step ─────────────────────────────────────────
    function physicsStep(dt) {
        var cfg = internal.stateConfigs[embryState];
        if (!cfg || internal.particles.length === 0) return;

        var s = canvas.width;
        var cx = s * 0.5;
        var cy = s * 0.5;
        var orbitR = ((internal.ring.innerR + internal.ring.outerR) / 2) * s;
        var elapsed = (Date.now() - internal.stateStartTime) / 1000;
        var n = internal.px.length;

        // Make mutable copies
        var _px = internal.px;
        var _py = internal.py;
        var _pg = internal.pgroup;

        for (var i = 0; i < n; i++) {
            var dx = _px[i] - cx;
            var dy = _py[i] - cy;
            var dist = Math.sqrt(dx * dx + dy * dy);
            if (dist < 0.5) continue;

            var nx = dx / dist;
            var ny = dy / dist;

            // Target radius
            var targetR;
            if (cfg.dualRing) {
                targetR = (_pg[i] === 0) ? orbitR * 0.6 : orbitR * 1.2;
            } else if (cfg.pulseOut) {
                var al = root.audioLevel;
                targetR = orbitR * cfg.radiusMul + orbitR * cfg.breathAmp * al * Math.sin(elapsed * Math.PI * 2 * cfg.breathHz);
            } else if (embryState === "listening") {
                targetR = orbitR * cfg.radiusMul + orbitR * cfg.breathAmp * Math.sin(elapsed * Math.PI * 2 * cfg.breathHz);
            } else if (embryState === "idle") {
                var breathFactor = 1 + cfg.breathAmp * Math.sin(elapsed * Math.PI * 2 * cfg.breathHz);
                var restX = internal.particles[i].x * s;
                var restY = internal.particles[i].y * s;
                // Lerp toward rest position with breathing
                var targetX = restX + (restX - cx) * (breathFactor - 1);
                var targetY = restY + (restY - cy) * (breathFactor - 1);
                var lerpRate = 1 - Math.exp(-5 * dt);
                _px[i] += (targetX - _px[i]) * lerpRate;
                _py[i] += (targetY - _py[i]) * lerpRate;
                continue;
            } else {
                targetR = orbitR * cfg.radiusMul;
            }

            // Radial force toward target
            var radialStrength = 0.06;
            var radialForce = (targetR - dist) * radialStrength;
            var fx = nx * radialForce;
            var fy = ny * radialForce;

            // Tangential force for dual-ring rotation
            if (cfg.dualRing) {
                var dir = (_pg[i] === 0) ? 1 : -1;
                fx += -ny * 0.3 * dir * 0.02;
                fy += nx * 0.3 * dir * 0.02;
            }

            // Repulsion (simplified charge)
            fx += nx * cfg.charge * 0.01;
            fy += ny * cfg.charge * 0.01;

            // Center pull
            fx += (cx - _px[i]) * 0.0001;
            fy += (cy - _py[i]) * 0.0001;

            // Apply with velocity decay
            _px[i] += fx * s * dt;
            _py[i] += fy * s * dt;
        }
        internal.px = _px;
        internal.py = _py;
    }

    // ── Canvas ───────────────────────────────────────────────
    Canvas {
        id: canvas
        anchors.fill: parent
        renderStrategy: Canvas.Threaded
        renderTarget: Canvas.FramebufferObject

        onPaint: {
            var ctx = getContext("2d");
            if (!ctx) return;

            var w = width;
            var h = height;
            var now = Date.now();
            var pxScale = w / 1024;

            // Background
            var r = w * 0.08;
            ctx.clearRect(0, 0, w, h);
            ctx.beginPath();
            ctx.roundedRect(0, 0, w, h, r, r);
            ctx.fillStyle = "rgb(14,14,28)";
            ctx.fill();
            ctx.save();
            ctx.clip();

            // Stars
            var stars = internal.stars;
            for (var si = 0; si < stars.length; si++) {
                var star = stars[si];
                var sr = Math.max(star.size * pxScale, 0.5);
                ctx.globalAlpha = star.alpha;
                ctx.fillStyle = "#ffffff";
                ctx.beginPath();
                ctx.arc(star.x * w, star.y * h, sr, 0, Math.PI * 2);
                ctx.fill();
            }
            ctx.globalAlpha = 1;

            // Colors
            var colors = getFrameColors(now);
            var cfg = internal.stateConfigs[embryState];
            if (!cfg) { ctx.restore(); return; }

            // Center glow
            var cx = w * 0.5;
            var cy = h * 0.5;
            var fontData = internal.font;
            var letterSize = fontData.sizeRatio * w;
            var glowR = letterSize * 0.7;
            var glowAlpha = colors.glowAlpha;

            if (embryState !== "idle" && internal.stateStartTime > 0 && !root.reduceMotion) {
                var elapsed = (now - internal.stateStartTime) / 1000;
                var range = cfg.breathHz > 0 ? 0.07 : 0.03;
                glowAlpha = colors.glowAlpha + range * Math.sin(elapsed * Math.PI * cfg.breathHz);
            }

            var glow = ctx.createRadialGradient(cx, cy, 0, cx, cy, glowR);
            glow.addColorStop(0, "rgba(" + colors.glow[0] + "," + colors.glow[1] + "," + colors.glow[2] + "," + glowAlpha + ")");
            glow.addColorStop(1, "rgba(" + colors.glow[0] + "," + colors.glow[1] + "," + colors.glow[2] + ",0)");
            ctx.fillStyle = glow;
            ctx.beginPath();
            ctx.arc(cx, cy, glowR, 0, Math.PI * 2);
            ctx.fill();

            // ── Force Ring ───────────────────────────────────
            var ringCfg = internal.ringConfigs[embryState];
            var orbitR = ((internal.ring.innerR + internal.ring.outerR) / 2) * w;

            if (ringCfg) {
                var rElapsed = (internal.stateStartTime > 0 && !root.reduceMotion)
                    ? (now - internal.stateStartTime) / 1000 : 0;

                // Emergence
                var emergeT = internal.ringEmergeStart > 0
                    ? clamp01((now - internal.ringEmergeStart) / 250) : 1;
                var emergeEased = 1 - Math.pow(1 - emergeT, 3);

                // Breathing
                var scaledPulseAmp = (ringCfg.pulseAmp || 0) * pxScale;
                var pulseOffset = (ringCfg.pulseHz || 0) > 0
                    ? scaledPulseAmp * Math.sin(rElapsed * Math.PI * 2 * (ringCfg.pulseHz || 0)) : 0;

                // Synth contraction
                var synthContract = (embryState === "synthesizing")
                    ? 1 - 0.50 * (0.5 + 0.5 * Math.sin(rElapsed * Math.PI * 2 / 3)) : 1;

                var ringR = (orbitR * synthContract + pulseOffset) * emergeEased;

                if (emergeEased > 0.01) {
                    var sizeScale = Math.max(1, w / 128);
                    var ringAlpha = Math.min(1, ringCfg.alpha * emergeEased);
                    ctx.strokeStyle = "rgba(" + colors.particle[0] + "," + colors.particle[1] + "," + colors.particle[2] + "," + ringAlpha + ")";
                    ctx.lineWidth = Math.max(2, ringCfg.width * sizeScale);

                    if (ringCfg.dashPattern && ringCfg.dashPattern.length > 0) {
                        ctx.setLineDash(ringCfg.dashPattern);
                        var circumference = 2 * Math.PI * ringR;
                        ctx.lineDashOffset = -(rElapsed * (ringCfg.rotateSpeed || 0) / (2 * Math.PI) * circumference);
                    } else {
                        ctx.setLineDash([]);
                    }

                    ctx.beginPath();
                    ctx.arc(cx, cy, ringR, 0, Math.PI * 2);
                    ctx.stroke();
                    ctx.setLineDash([]);

                    // Speaking ripples
                    if (ringCfg.rippleCount && ringCfg.rippleCount > 0) {
                        for (var ri = 0; ri < ringCfg.rippleCount; ri++) {
                            var phase = ((rElapsed * 1.2 + ri * (1 / ringCfg.rippleCount)) % 1);
                            var rippleR = orbitR + phase * orbitR * 0.6;
                            var rippleAlpha = ringCfg.alpha * 0.6 * (1 - phase * phase) * emergeEased;
                            ctx.strokeStyle = "rgba(" + colors.particle[0] + "," + colors.particle[1] + "," + colors.particle[2] + "," + rippleAlpha + ")";
                            ctx.lineWidth = Math.max(1.5, 2.5 * sizeScale);
                            ctx.beginPath();
                            ctx.arc(cx, cy, rippleR, 0, Math.PI * 2);
                            ctx.stroke();
                        }
                    }
                }
            }

            // ── Particles ────────────────────────────────────
            var particles = internal.particles;
            var _px = internal.px;
            var _py = internal.py;
            var isActive = embryState !== "idle";

            for (var pi = 0; pi < particles.length && pi < _px.length; pi++) {
                var p = particles[pi];
                var pr = Math.max(p.size * pxScale, 0.5);
                ctx.globalAlpha = p.alpha;

                // Sparks
                if (isActive && cfg.sparkEvery > 0 && pi % cfg.sparkEvery === 0) {
                    var spark = lerpColor(colors.particle, [255, 255, 255], 0.3);
                    ctx.fillStyle = "rgb(" + spark[0] + "," + spark[1] + "," + spark[2] + ")";
                    ctx.globalAlpha = Math.min(1, p.alpha * 1.3);
                } else {
                    ctx.fillStyle = "rgb(" + colors.particle[0] + "," + colors.particle[1] + "," + colors.particle[2] + ")";
                }

                ctx.beginPath();
                ctx.arc(_px[pi], _py[pi], pr, 0, Math.PI * 2);
                ctx.fill();
            }
            ctx.globalAlpha = 1;

            // ── Letter 'e' ───────────────────────────────────
            ctx.fillStyle = "rgb(" + colors.glow[0] + "," + colors.glow[1] + "," + colors.glow[2] + ")";
            ctx.font = fontData.weight + " " + letterSize + "px '" + fontData.family + "', 'Nunito', sans-serif";
            ctx.textAlign = "center";
            ctx.textBaseline = "middle";
            ctx.fillText(fontData.letter, cx, cy);

            ctx.restore();
        }
    }

    // ── Animation Timer ──────────────────────────────────────
    Timer {
        id: animTimer
        interval: 16  // ~60fps
        running: !root.reduceMotion
        repeat: true
        onTriggered: {
            physicsStep(0.016);
            canvas.requestPaint();
        }
    }

    // State badge below canvas
    Rectangle {
        id: stateBadge
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.top: parent.bottom
        anchors.topMargin: EmbryStyle.layout.space2
        width: stateLabel.implicitWidth + EmbryStyle.layout.badgePadding * 2
        height: EmbryStyle.layout.badgeHeight
        radius: EmbryStyle.layout.badgeRadius
        color: EmbryStyle.colors.badge

        Text {
            id: stateLabel
            anchors.centerIn: parent
            text: root.embryState
            font.pixelSize: EmbryStyle.text.sm
            font.weight: EmbryStyle.text.weightMedium
            color: {
                var stateCol = internal.stateColors[root.embryState];
                if (stateCol) {
                    return Qt.rgba(stateCol.particle[0]/255,
                                   stateCol.particle[1]/255,
                                   stateCol.particle[2]/255, 1);
                }
                return EmbryStyle.colors.textSecondary;
            }
            font.capitalization: Font.AllUppercase
        }
    }
}
