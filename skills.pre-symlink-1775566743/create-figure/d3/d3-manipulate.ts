/**
 * D3 Manipulation Protocol — dynamic command execution on live D3 visualizations.
 *
 * This module provides:
 *   1. ManipulationCommand type — structured command format
 *   2. injectManipulationRuntime() — returns JS string to inject into iframe HTML
 *   3. sendManipulation() — postMessage bridge from parent to iframe
 *
 * The runtime listens for postMessage({type: "d3-manipulate", cmd: ...}) in the
 * iframe and dispatches to per-chart-family handlers.
 *
 * Supported actions per family:
 *   NETWORK:      zoom_to, pan, highlight, focus, expand, collapse, filter, reset
 *   HIERARCHY:    zoom_to, drill_down, drill_up, highlight, focus, collapse, expand, reset
 *   FLOW:         highlight_path, zoom_to, filter, reset
 *   BAR/LINE/AREA: zoom_x, zoom_y, highlight, filter, brush, reset
 *   PIE/RADIAL:   highlight, explode, filter, reset
 *   DISTRIBUTION: zoom_x, highlight, brush, reset
 *   ALL:          reset, zoom_in, zoom_out, pan, highlight, filter
 */

// --- Command types ---

export type ManipulationAction =
  | "zoom_in"
  | "zoom_out"
  | "zoom_to"
  | "pan"
  | "highlight"
  | "highlight_related"
  | "highlight_path"
  | "focus"
  | "expand"
  | "collapse"
  | "drill_down"
  | "drill_up"
  | "filter"
  | "explode"
  | "brush"
  | "reset";

export interface ManipulationCommand {
  action: ManipulationAction;
  target?: string;             // node id, label, series name, slice label
  params?: Record<string, unknown>; // scale, duration, direction, color, etc.
}

export interface ManipulationMessage {
  type: "d3-manipulate";
  commands: ManipulationCommand[];
  vizFamily?: string;          // hint: "network", "hierarchy", "flow", "bar", etc.
}

// --- postMessage bridge ---

export function sendManipulation(
  iframeEl: HTMLIFrameElement | null,
  commands: ManipulationCommand[],
  vizFamily?: string,
): void {
  if (!iframeEl?.contentWindow) return;
  const msg: ManipulationMessage = { type: "d3-manipulate", commands, vizFamily };
  iframeEl.contentWindow.postMessage(msg, "*");
}

// --- Injectable runtime ---

/**
 * Returns a <script> block to inject into D3 HTML visualizations.
 * The runtime:
 *   - Listens for postMessage with type "d3-manipulate"
 *   - Finds the root SVG or container element
 *   - Dispatches commands to chart-family-specific handlers
 *   - Logs actions for debugging
 */
export function manipulationRuntimeScript(): string {
  return MANIPULATION_RUNTIME;
}

/**
 * Wraps existing HTML content with the manipulation runtime injected.
 * Inserts the script just before </body> or appends it.
 */
export function injectRuntime(html: string): string {
  const script = `<script>${MANIPULATION_RUNTIME}</script>`;
  if (html.includes("</body>")) {
    return html.replace("</body>", `${script}\n</body>`);
  }
  return html + script;
}

// --- The runtime itself (runs inside iframe) ---

const MANIPULATION_RUNTIME = `
(function() {
  'use strict';

  // --- State ---
  var currentZoom = null;  // d3.ZoomTransform
  var highlightedNodes = new Set();
  var svg = null;
  var container = null;
  var zoomBehavior = null;

  // --- Init: find SVG and set up zoom ---
  function init() {
    svg = document.querySelector('svg');
    if (!svg) {
      // Try again after a short delay (D3 may not have rendered yet)
      setTimeout(init, 200);
      return;
    }
    container = svg.querySelector('g') || svg;

    // Install zoom behavior if d3 is available
    if (typeof d3 !== 'undefined' && d3.zoom) {
      zoomBehavior = d3.zoom()
        .scaleExtent([0.1, 20])
        .on('zoom', function(event) {
          currentZoom = event.transform;
          // Apply to the first <g> child or create wrapper
          var g = svg.querySelector('g.zoom-layer');
          if (!g) {
            g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
            g.classList.add('zoom-layer');
            // Move all children into zoom layer
            while (svg.firstChild && svg.firstChild !== g) {
              g.appendChild(svg.firstChild);
            }
            svg.appendChild(g);
          }
          g.setAttribute('transform', event.transform.toString());
        });

      d3.select(svg).call(zoomBehavior);
      currentZoom = d3.zoomIdentity;
    }

    console.log('[d3-manipulate] Runtime initialized, svg found');
  }

  // --- Command handlers ---

  var handlers = {
    zoom_in: function(cmd) {
      if (!zoomBehavior || !svg) return;
      var scale = (cmd.params && cmd.params.scale) || 1.5;
      d3.select(svg).transition().duration(500)
        .call(zoomBehavior.scaleBy, scale);
    },

    zoom_out: function(cmd) {
      if (!zoomBehavior || !svg) return;
      var scale = (cmd.params && cmd.params.scale) || 0.67;
      d3.select(svg).transition().duration(500)
        .call(zoomBehavior.scaleBy, scale);
    },

    zoom_to: function(cmd) {
      if (!svg) return;
      var target = findElement(cmd.target);
      if (!target) { console.warn('[d3-manipulate] target not found:', cmd.target); return; }

      if (zoomBehavior) {
        var bbox = target.getBBox();
        var svgRect = svg.getBoundingClientRect();
        var scale = Math.min(svgRect.width / (bbox.width * 1.5), svgRect.height / (bbox.height * 1.5), 5);
        var tx = svgRect.width / 2 - (bbox.x + bbox.width / 2) * scale;
        var ty = svgRect.height / 2 - (bbox.y + bbox.height / 2) * scale;
        d3.select(svg).transition().duration(750).ease(d3.easeCubicInOut)
          .call(zoomBehavior.transform, d3.zoomIdentity.translate(tx, ty).scale(scale));
      }
    },

    pan: function(cmd) {
      if (!zoomBehavior || !svg) return;
      var dx = (cmd.params && cmd.params.dx) || 0;
      var dy = (cmd.params && cmd.params.dy) || 0;
      d3.select(svg).transition().duration(300)
        .call(zoomBehavior.translateBy, dx, dy);
    },

    highlight: function(cmd) {
      if (!svg) return;
      // Reset previous highlights
      svg.querySelectorAll('.d3m-highlighted').forEach(function(el) {
        el.classList.remove('d3m-highlighted');
        el.style.removeProperty('stroke');
        el.style.removeProperty('stroke-width');
        el.style.removeProperty('filter');
      });
      svg.querySelectorAll('.d3m-dimmed').forEach(function(el) {
        el.classList.remove('d3m-dimmed');
        el.style.removeProperty('opacity');
      });

      if (!cmd.target) return;

      var targets = findElements(cmd.target);
      if (targets.length === 0) { console.warn('[d3-manipulate] no targets for highlight:', cmd.target); return; }

      // Dim everything else
      var allElements = svg.querySelectorAll('rect, circle, path, line, ellipse, text, g.node');
      allElements.forEach(function(el) {
        if (!targets.includes(el) && !isChildOf(el, targets)) {
          el.classList.add('d3m-dimmed');
          el.style.opacity = '0.15';
        }
      });

      // Highlight targets
      targets.forEach(function(el) {
        el.classList.add('d3m-highlighted');
        var color = (cmd.params && cmd.params.color) || '#FFD700';
        el.style.stroke = color;
        el.style.strokeWidth = '3px';
        el.style.filter = 'drop-shadow(0 0 6px ' + color + ')';
      });
    },

    highlight_related: function(cmd) {
      if (!svg || !cmd.target) return;
      var target = findElement(cmd.target);
      if (!target) return;

      // For network graphs: find connected edges and nodes
      var related = findRelated(target, cmd.target);
      var allTargets = [target].concat(related);

      handlers.highlight({ target: null }); // clear first
      // Dim everything
      var allElements = svg.querySelectorAll('rect, circle, path, line, ellipse, g.node');
      allElements.forEach(function(el) {
        if (!allTargets.includes(el) && !isChildOf(el, allTargets)) {
          el.classList.add('d3m-dimmed');
          el.style.opacity = '0.15';
        }
      });
      allTargets.forEach(function(el) {
        el.classList.add('d3m-highlighted');
        el.style.stroke = '#FFD700';
        el.style.strokeWidth = '3px';
        el.style.filter = 'drop-shadow(0 0 6px #FFD700)';
      });
    },

    highlight_path: function(cmd) {
      // For sankey/flow: highlight a specific path through the diagram
      if (!svg || !cmd.target) return;
      handlers.highlight({ target: null }); // clear

      var pathParts = cmd.target.split(/\\s*(?:->|→|to)\\s*/i);
      var allElements = svg.querySelectorAll('rect, circle, path, line, g.node, g.link');
      allElements.forEach(function(el) { el.style.opacity = '0.1'; });

      pathParts.forEach(function(part) {
        var found = findElements(part.trim());
        found.forEach(function(el) {
          el.style.opacity = '1';
          el.style.stroke = '#FFD700';
          el.style.strokeWidth = '3px';
        });
      });
    },

    focus: function(cmd) {
      // Combine zoom_to + highlight
      handlers.highlight(cmd);
      handlers.zoom_to(cmd);
    },

    expand: function(cmd) {
      // For hierarchy: expand a collapsed node
      if (!svg || !cmd.target) return;
      var target = findElement(cmd.target);
      if (!target) return;
      // Toggle visibility of children
      var children = target.querySelectorAll(':scope > g, :scope > circle, :scope > rect');
      children.forEach(function(el) {
        el.style.display = '';
        el.style.opacity = '1';
      });
      // Also dispatch custom event for D3 tree layouts that listen
      target.dispatchEvent(new CustomEvent('d3m-expand', { bubbles: true, detail: { target: cmd.target } }));
    },

    collapse: function(cmd) {
      if (!svg || !cmd.target) return;
      var target = findElement(cmd.target);
      if (!target) return;
      var children = target.querySelectorAll(':scope > g');
      children.forEach(function(el) {
        el.style.display = 'none';
      });
      target.dispatchEvent(new CustomEvent('d3m-collapse', { bubbles: true, detail: { target: cmd.target } }));
    },

    drill_down: function(cmd) {
      // For treemap/sunburst: zoom into a subtree
      handlers.zoom_to(cmd);
      // Dispatch event for D3 hierarchy handlers
      if (svg) {
        svg.dispatchEvent(new CustomEvent('d3m-drill-down', { bubbles: true, detail: { target: cmd.target } }));
      }
    },

    drill_up: function(cmd) {
      if (svg) {
        svg.dispatchEvent(new CustomEvent('d3m-drill-up', { bubbles: true, detail: {} }));
      }
      handlers.reset({});
    },

    filter: function(cmd) {
      if (!svg || !cmd.target) return;
      // Hide elements NOT matching the filter
      var matching = findElements(cmd.target);
      var allViz = svg.querySelectorAll('rect, circle, path.data, g.node, g.bar, g.slice, g.arc');
      allViz.forEach(function(el) {
        if (!matching.includes(el) && !isChildOf(el, matching)) {
          el.style.transition = 'opacity 0.3s';
          el.style.opacity = '0';
          setTimeout(function() { el.style.display = 'none'; }, 300);
        }
      });
    },

    explode: function(cmd) {
      // For pie/donut: pull out a slice
      if (!svg || !cmd.target) return;
      var slice = findElement(cmd.target);
      if (!slice) return;
      var path = slice.tagName === 'path' ? slice : slice.querySelector('path');
      if (!path) return;
      // Compute centroid direction and offset
      var bbox = path.getBBox();
      var cx = bbox.x + bbox.width / 2;
      var cy = bbox.y + bbox.height / 2;
      var dist = 15;
      var angle = Math.atan2(cy, cx);
      var tx = Math.cos(angle) * dist;
      var ty = Math.sin(angle) * dist;
      path.style.transition = 'transform 0.5s ease-out';
      path.style.transform = 'translate(' + tx + 'px, ' + ty + 'px)';
    },

    brush: function(cmd) {
      // Visual indicator — actual brush requires d3.brush() wiring
      if (!svg) return;
      console.log('[d3-manipulate] brush requested for:', cmd.target || 'all');
      svg.dispatchEvent(new CustomEvent('d3m-brush', { bubbles: true, detail: cmd }));
    },

    reset: function() {
      if (!svg) return;
      // Clear all highlights
      svg.querySelectorAll('.d3m-highlighted, .d3m-dimmed').forEach(function(el) {
        el.classList.remove('d3m-highlighted', 'd3m-dimmed');
        el.style.removeProperty('opacity');
        el.style.removeProperty('stroke');
        el.style.removeProperty('stroke-width');
        el.style.removeProperty('filter');
        el.style.removeProperty('display');
        el.style.removeProperty('transform');
      });
      // Reset zoom
      if (zoomBehavior) {
        d3.select(svg).transition().duration(500)
          .call(zoomBehavior.transform, d3.zoomIdentity);
      }
      // Show all hidden elements
      svg.querySelectorAll('[style*="display: none"]').forEach(function(el) {
        el.style.removeProperty('display');
        el.style.opacity = '1';
      });
    }
  };

  // --- Element finding ---

  function findElement(target) {
    if (!target || !svg) return null;
    var t = target.toLowerCase().trim();

    // By data-id attribute
    var byId = svg.querySelector('[data-id="' + CSS.escape(t) + '"]')
             || svg.querySelector('[data-id="' + CSS.escape(target) + '"]');
    if (byId) return byId;

    // By data-label attribute
    var byLabel = svg.querySelector('[data-label="' + CSS.escape(target) + '"]');
    if (byLabel) return byLabel;

    // By id attribute
    var byElemId = svg.querySelector('#' + CSS.escape(target))
                || svg.querySelector('#' + CSS.escape(t.replace(/\\s+/g, '-')));
    if (byElemId) return byElemId;

    // By text content in <text> elements, then find parent group
    var texts = svg.querySelectorAll('text');
    for (var i = 0; i < texts.length; i++) {
      var textContent = (texts[i].textContent || '').toLowerCase().trim();
      if (textContent === t || textContent.includes(t)) {
        // Return the parent g or the text's associated shape
        var parent = texts[i].closest('g.node, g.bar, g.slice, g.arc, g.link, g');
        return parent || texts[i];
      }
    }

    // By title element
    var titles = svg.querySelectorAll('title');
    for (var j = 0; j < titles.length; j++) {
      if ((titles[j].textContent || '').toLowerCase().includes(t)) {
        return titles[j].parentElement;
      }
    }

    return null;
  }

  function findElements(target) {
    if (!target || !svg) return [];
    var t = target.toLowerCase().trim();
    var results = [];

    // Multi-target: "A, B, C" or "A and B"
    var parts = target.split(/\\s*[,;&]\\s*|\\s+and\\s+/i);
    if (parts.length > 1) {
      parts.forEach(function(part) {
        var el = findElement(part.trim());
        if (el) results.push(el);
      });
      return results;
    }

    var el = findElement(target);
    if (el) results.push(el);
    return results;
  }

  function findRelated(targetEl, targetName) {
    // For network/force graphs: find edges connected to this node
    var related = [];
    if (!svg) return related;

    var t = (targetName || '').toLowerCase().trim();

    // Find links/edges that reference this node
    svg.querySelectorAll('line, path.link, g.link path, g.edge path').forEach(function(el) {
      var source = (el.getAttribute('data-source') || '').toLowerCase();
      var target = (el.getAttribute('data-target') || '').toLowerCase();
      if (source === t || target === t || source.includes(t) || target.includes(t)) {
        related.push(el);
        // Also find the other endpoint node
        var otherName = source === t || source.includes(t) ? target : source;
        var otherNode = findElement(otherName);
        if (otherNode) related.push(otherNode);
      }
    });

    return related;
  }

  function isChildOf(el, parents) {
    for (var i = 0; i < parents.length; i++) {
      if (parents[i].contains(el)) return true;
    }
    return false;
  }

  // --- Message listener ---
  window.addEventListener('message', function(event) {
    if (!event.data || event.data.type !== 'd3-manipulate') return;

    var msg = event.data;
    console.log('[d3-manipulate] Received commands:', msg.commands);

    if (!svg) init(); // re-init if needed

    (msg.commands || []).forEach(function(cmd) {
      var handler = handlers[cmd.action];
      if (handler) {
        try {
          handler(cmd);
        } catch (err) {
          console.error('[d3-manipulate] Error executing ' + cmd.action + ':', err);
        }
      } else {
        console.warn('[d3-manipulate] Unknown action:', cmd.action);
      }
    });

    // ACK back to parent
    if (event.source) {
      event.source.postMessage({
        type: 'd3-manipulate-ack',
        executed: (msg.commands || []).map(function(c) { return c.action; })
      }, '*');
    }
  });

  // --- Expose global for in-page D3 code to hook into ---
  window.d3Manipulate = function(cmd) {
    var handler = handlers[cmd.action];
    if (handler) handler(cmd);
  };

  window.d3ManipulateHandlers = handlers;

  // --- CSS for highlights ---
  var style = document.createElement('style');
  style.textContent = [
    '.d3m-highlighted { transition: all 0.3s ease-out; }',
    '.d3m-dimmed { transition: opacity 0.3s ease-out; pointer-events: none; }',
    'svg { cursor: grab; }',
    'svg:active { cursor: grabbing; }'
  ].join('\\n');
  document.head.appendChild(style);

  // Auto-init
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
`;
