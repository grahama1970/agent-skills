/**
 * BboxAnnotator — vanilla JS bounding-box annotation on a canvas overlay.
 *
 * Features:
 *   - Draw mode: click-drag creates a labeled rectangle
 *   - Select mode: click existing box → dashed highlight
 *   - Delete: Del/Backspace removes selected box (tracked for response)
 *   - Undo: Ctrl+Z / Cmd+Z reverts last action
 *   - Label toolbar: configurable buttons with colors, 1-9 keyboard shortcuts
 *   - Pre-annotations: loaded from window._bboxData[qid], rendered as colored boxes
 *   - Response output: writes to global `responses[qid]` for form submission
 *   - Coordinate system: image-natural-pixel space (Python handles PDF conversion)
 *   - Touch support: touchstart/touchmove/touchend mapped to same draw/select logic
 */

class BboxAnnotator {
    constructor(qid) {
        this.qid = qid;
        this.canvas = document.getElementById('bbox-canvas-' + qid);
        this.img = document.getElementById('bbox-img-' + qid);
        this.container = document.getElementById('bbox-container-' + qid);

        if (!this.canvas || !this.img) return;

        this.ctx = this.canvas.getContext('2d');
        this.annotations = [];
        this.deletedAnnotations = [];  // Fix #1: track deleted pre-annotations
        this.undoStack = [];           // Fix #5: undo history
        this.selectedIndex = -1;
        this.drawing = false;
        this.startX = 0;
        this.startY = 0;
        this.currentX = 0;
        this.currentY = 0;

        // Current label (first label by default)
        const data = (window._bboxData || {})[qid] || {};
        this.labels = data.labels || [
            { name: 'Table', color: '#22c55e' },
            { name: 'Section', color: '#3b82f6' },
            { name: 'Figure', color: '#f59e0b' },
            { name: 'Delete', color: '#ef4444' },
        ];
        this.renderDpi = data.renderDpi || 150;
        this.pageNum = data.pageNum || 0;
        this.currentLabel = this.labels[0].name;
        this.currentColor = this.labels[0].color;

        // Load pre-annotations
        if (data.preAnnotations && data.preAnnotations.length > 0) {
            this.annotations = data.preAnnotations.map(function(ann) {
                var label = this._findLabel(ann.type || 'Table');
                return {
                    type: ann.type || 'Table',
                    bbox: ann.bbox.slice(),
                    page: ann.page || 0,
                    color: label ? label.color : '#22c55e',
                    action: 'keep',
                };
            }.bind(this));
        }

        this._initCanvas();
        this._bindEvents();
        this._render();
        this._updateAnnotationList();
        this._updateResponse();
    }

    _findLabel(name) {
        for (var i = 0; i < this.labels.length; i++) {
            if (this.labels[i].name === name) return this.labels[i];
        }
        return null;
    }

    _initCanvas() {
        var self = this;
        // Wait for image to load, then size the canvas
        if (this.img.complete) {
            this._sizeCanvas();
        } else {
            this.img.onload = function() { self._sizeCanvas(); };
        }
    }

    _sizeCanvas() {
        // Canvas matches displayed image size
        var rect = this.img.getBoundingClientRect();
        this.canvas.width = rect.width;
        this.canvas.height = rect.height;
        this.displayWidth = rect.width;
        this.displayHeight = rect.height;
        this.naturalWidth = this.img.naturalWidth;
        this.naturalHeight = this.img.naturalHeight;
        this.scaleX = this.naturalWidth / this.displayWidth;
        this.scaleY = this.naturalHeight / this.displayHeight;
        this._render();
    }

    _bindEvents() {
        var self = this;

        // Mouse events on canvas
        this.canvas.addEventListener('mousedown', function(e) { self._onMouseDown(e); });
        this.canvas.addEventListener('mousemove', function(e) { self._onMouseMove(e); });
        this.canvas.addEventListener('mouseup', function(e) { self._onMouseUp(e); });

        // Fix #6: Touch events on canvas
        this.canvas.addEventListener('touchstart', function(e) { self._onTouchStart(e); }, { passive: false });
        this.canvas.addEventListener('touchmove', function(e) { self._onTouchMove(e); }, { passive: false });
        this.canvas.addEventListener('touchend', function(e) { self._onTouchEnd(e); }, { passive: false });

        // Keyboard events (delegated from document, filtered by active pane)
        document.addEventListener('keydown', function(e) { self._onKeyDown(e); });

        // Resize observer
        if (window.ResizeObserver) {
            new ResizeObserver(function() { self._sizeCanvas(); }).observe(self.container);
        }
    }

    _getCanvasCoords(e) {
        var rect = this.canvas.getBoundingClientRect();
        return {
            x: e.clientX - rect.left,
            y: e.clientY - rect.top,
        };
    }

    _getTouchCoords(e) {
        var touch = e.touches[0] || e.changedTouches[0];
        var rect = this.canvas.getBoundingClientRect();
        return {
            x: touch.clientX - rect.left,
            y: touch.clientY - rect.top,
        };
    }

    // Convert display coords to image-natural coords
    _toNatural(x, y) {
        return {
            x: x * this.scaleX,
            y: y * this.scaleY,
        };
    }

    // Convert image-natural coords to display coords
    _toDisplay(x, y) {
        return {
            x: x / this.scaleX,
            y: y / this.scaleY,
        };
    }

    _onMouseDown(e) {
        if (e.button !== 0) return;
        var pos = this._getCanvasCoords(e);
        this._handlePointerDown(pos);
    }

    _onMouseMove(e) {
        var pos = this._getCanvasCoords(e);

        // Fix #2: Cursor feedback for hover over existing boxes
        if (!this.drawing) {
            var hit = this._hitTest(pos.x, pos.y);
            this.canvas.style.cursor = hit >= 0 ? 'pointer' : 'crosshair';
            return;
        }

        this.currentX = pos.x;
        this.currentY = pos.y;
        this._render();
        // Draw preview rectangle
        this._drawRect(
            this.startX, this.startY,
            this.currentX - this.startX, this.currentY - this.startY,
            this.currentColor, true
        );
    }

    _onMouseUp(e) {
        var pos = this._getCanvasCoords(e);
        this._handlePointerUp(pos);
    }

    // Fix #6: Touch event handlers
    _onTouchStart(e) {
        e.preventDefault();
        var pos = this._getTouchCoords(e);
        this._handlePointerDown(pos);
    }

    _onTouchMove(e) {
        e.preventDefault();
        if (!this.drawing) return;
        var pos = this._getTouchCoords(e);
        this.currentX = pos.x;
        this.currentY = pos.y;
        this._render();
        this._drawRect(
            this.startX, this.startY,
            this.currentX - this.startX, this.currentY - this.startY,
            this.currentColor, true
        );
    }

    _onTouchEnd(e) {
        e.preventDefault();
        var pos = this._getTouchCoords(e);
        this._handlePointerUp(pos);
    }

    // Shared pointer logic for mouse and touch
    _handlePointerDown(pos) {
        // Check if clicking on an existing box (select mode)
        var hitIdx = this._hitTest(pos.x, pos.y);
        if (hitIdx >= 0) {
            this.selectedIndex = hitIdx;
            this.drawing = false;
            this._render();
            this._updateAnnotationList();
            return;
        }

        // Start drawing
        this.drawing = true;
        this.startX = pos.x;
        this.startY = pos.y;
        this.currentX = pos.x;
        this.currentY = pos.y;
        this.selectedIndex = -1;
    }

    _handlePointerUp(pos) {
        if (!this.drawing) return;
        this.drawing = false;

        var x0 = Math.min(this.startX, pos.x);
        var y0 = Math.min(this.startY, pos.y);
        var x1 = Math.max(this.startX, pos.x);
        var y1 = Math.max(this.startY, pos.y);

        // Minimum size check (at least 10px)
        if (x1 - x0 < 10 || y1 - y0 < 10) {
            this._render();
            return;
        }

        // Convert to natural pixel coords
        var topLeft = this._toNatural(x0, y0);
        var bottomRight = this._toNatural(x1, y1);

        var newAnn = {
            type: this.currentLabel,
            bbox: [topLeft.x, topLeft.y, bottomRight.x, bottomRight.y],
            page: this.pageNum,
            color: this.currentColor,
            action: 'add',
        };
        this.annotations.push(newAnn);

        // Fix #5: Push undo entry
        this.undoStack.push({ type: 'add', index: this.annotations.length - 1 });

        this.selectedIndex = this.annotations.length - 1;
        this._render();
        this._updateAnnotationList();
        this._updateResponse();
    }

    _onKeyDown(e) {
        // Only handle if our pane is active
        var pane = document.getElementById('pane-' + this.qid);
        if (!pane || !pane.classList.contains('active')) return;
        if (document.activeElement && document.activeElement.tagName === 'INPUT') return;

        // Fix #5: Undo with Ctrl+Z / Cmd+Z
        if ((e.ctrlKey || e.metaKey) && e.key === 'z') {
            e.preventDefault();
            this._undo();
            return;
        }

        // Delete selected annotation
        if ((e.key === 'Delete' || e.key === 'Backspace') && this.selectedIndex >= 0) {
            e.preventDefault();
            this._deleteAnnotation(this.selectedIndex);
            return;
        }

        // 1-9 to switch labels
        var num = parseInt(e.key);
        if (num >= 1 && num <= 9 && num <= this.labels.length) {
            e.preventDefault();
            var label = this.labels[num - 1];
            this.setLabel(label.name, label.color);
            return;
        }
    }

    _hitTest(x, y) {
        // Check in reverse order (top-most drawn last)
        for (var i = this.annotations.length - 1; i >= 0; i--) {
            var ann = this.annotations[i];
            var tl = this._toDisplay(ann.bbox[0], ann.bbox[1]);
            var br = this._toDisplay(ann.bbox[2], ann.bbox[3]);
            if (x >= tl.x && x <= br.x && y >= tl.y && y <= br.y) {
                return i;
            }
        }
        return -1;
    }

    _render() {
        if (!this.ctx) return;
        this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);

        for (var i = 0; i < this.annotations.length; i++) {
            var ann = this.annotations[i];
            var tl = this._toDisplay(ann.bbox[0], ann.bbox[1]);
            var br = this._toDisplay(ann.bbox[2], ann.bbox[3]);
            var w = br.x - tl.x;
            var h = br.y - tl.y;
            var isSelected = (i === this.selectedIndex);

            this._drawRect(tl.x, tl.y, w, h, ann.color, false, isSelected);

            // Draw label text
            this.ctx.font = '12px sans-serif';
            this.ctx.fillStyle = ann.color;
            var labelText = ann.type;
            var textWidth = this.ctx.measureText(labelText).width;

            // Background for label
            this.ctx.fillStyle = 'rgba(0,0,0,0.6)';
            this.ctx.fillRect(tl.x, tl.y - 16, textWidth + 8, 16);

            this.ctx.fillStyle = 'white';
            this.ctx.fillText(labelText, tl.x + 4, tl.y - 4);
        }
    }

    _drawRect(x, y, w, h, color, isPreview, isSelected) {
        this.ctx.strokeStyle = color;
        this.ctx.lineWidth = isSelected ? 3 : 2;

        if (isPreview) {
            this.ctx.setLineDash([6, 3]);
            this.ctx.globalAlpha = 0.7;
        } else if (isSelected) {
            this.ctx.setLineDash([6, 3]);
            this.ctx.globalAlpha = 1.0;
        } else {
            this.ctx.setLineDash([]);
            this.ctx.globalAlpha = 1.0;
        }

        this.ctx.strokeRect(x, y, w, h);

        // Semi-transparent fill
        this.ctx.globalAlpha = isSelected ? 0.15 : 0.08;
        this.ctx.fillStyle = color;
        this.ctx.fillRect(x, y, w, h);

        // Reset
        this.ctx.globalAlpha = 1.0;
        this.ctx.setLineDash([]);
    }

    // Fix #1: Track deleted pre-annotations instead of losing them
    _deleteAnnotation(index) {
        if (index < 0 || index >= this.annotations.length) return;

        var removed = this.annotations[index];

        // If it was a pre-annotation, track it in deletedAnnotations for the response
        if (removed.action === 'keep') {
            var deleted = {
                type: removed.type,
                bbox: removed.bbox.slice(),
                page: removed.page,
                color: removed.color,
                action: 'delete',
            };
            this.deletedAnnotations.push(deleted);
        }

        this.annotations.splice(index, 1);

        // Fix #5: Push undo entry
        this.undoStack.push({ type: 'delete', annotation: removed, index: index });

        this.selectedIndex = -1;
        this._render();
        this._updateAnnotationList();
        this._updateResponse();
    }

    // Fix #5: Undo last action
    _undo() {
        if (this.undoStack.length === 0) return;
        var entry = this.undoStack.pop();

        if (entry.type === 'add') {
            // Undo an add: remove the last-added annotation
            var idx = entry.index;
            if (idx >= 0 && idx < this.annotations.length) {
                this.annotations.splice(idx, 1);
            }
        } else if (entry.type === 'delete') {
            // Undo a delete: restore the annotation at its original position
            var ann = entry.annotation;
            var restoreIdx = Math.min(entry.index, this.annotations.length);
            this.annotations.splice(restoreIdx, 0, ann);

            // If it was a deleted pre-annotation, remove from deletedAnnotations
            if (ann.action === 'keep') {
                for (var i = this.deletedAnnotations.length - 1; i >= 0; i--) {
                    var d = this.deletedAnnotations[i];
                    if (d.bbox[0] === ann.bbox[0] && d.bbox[1] === ann.bbox[1] &&
                        d.bbox[2] === ann.bbox[2] && d.bbox[3] === ann.bbox[3] &&
                        d.type === ann.type) {
                        this.deletedAnnotations.splice(i, 1);
                        break;
                    }
                }
            }
        }

        this.selectedIndex = -1;
        this._render();
        this._updateAnnotationList();
        this._updateResponse();
    }

    _updateAnnotationList() {
        var list = document.getElementById('bbox-ann-list-' + this.qid);
        if (!list) return;

        var totalCount = this.annotations.length + this.deletedAnnotations.length;
        var header = '<div class="bbox-ann-header">Annotations (' + this.annotations.length;
        if (this.deletedAnnotations.length > 0) {
            header += ', ' + this.deletedAnnotations.length + ' deleted';
        }
        header += ')</div>';
        var items = '';

        for (var i = 0; i < this.annotations.length; i++) {
            var ann = this.annotations[i];
            var selectedClass = (i === this.selectedIndex) ? ' selected' : '';
            var bbox = ann.bbox;
            items += '<div class="bbox-ann-item' + selectedClass + '" data-idx="' + i + '" ' +
                'onclick="window._bboxAnnotators[\'' + this.qid + '\'].selectAnnotation(' + i + ')">' +
                '<span class="bbox-ann-type" style="color:' + ann.color + '">' + ann.type + '</span> ' +
                '<span class="bbox-ann-coords">[' +
                Math.round(bbox[0]) + ', ' + Math.round(bbox[1]) + ', ' +
                Math.round(bbox[2]) + ', ' + Math.round(bbox[3]) + ']</span>' +
                '<button class="bbox-ann-delete" onclick="event.stopPropagation(); ' +
                'window._bboxAnnotators[\'' + this.qid + '\'].deleteAnnotation(' + i + ')" ' +
                'title="Delete">x</button>' +
                '</div>';
        }

        list.innerHTML = header + items;
    }

    // Fix #1: Include deleted pre-annotations in response so server knows what was removed
    _updateResponse() {
        // Write to global responses object for form submission
        if (typeof responses === 'undefined') return;

        var result = [];

        // Active annotations (kept + newly added)
        for (var i = 0; i < this.annotations.length; i++) {
            var ann = this.annotations[i];
            result.push({
                action: ann.action,
                type: ann.type,
                bbox: ann.bbox.map(Math.round),
                page: ann.page,
            });
        }

        // Deleted pre-annotations (action='delete') — so server knows what was removed
        for (var j = 0; j < this.deletedAnnotations.length; j++) {
            var del = this.deletedAnnotations[j];
            result.push({
                action: 'delete',
                type: del.type,
                bbox: del.bbox.map(Math.round),
                page: del.page,
            });
        }

        responses[this.qid] = {
            decision: 'override',
            value: 'bbox_annotations',
            annotations: result,
            render_dpi: this.renderDpi,
        };

        // Update tab completion
        if (typeof updateTabCompletion === 'function') {
            updateTabCompletion(this.qid);
        }
    }

    // Public API

    setLabel(name, color) {
        this.currentLabel = name;
        this.currentColor = color;

        // Update toolbar button state
        var toolbar = document.getElementById('bbox-toolbar-' + this.qid);
        if (toolbar) {
            var btns = toolbar.querySelectorAll('.bbox-label-btn');
            btns.forEach(function(btn) {
                btn.classList.toggle('active', btn.dataset.label === name);
            });
        }
    }

    selectAnnotation(index) {
        this.selectedIndex = index;
        this._render();
        this._updateAnnotationList();
    }

    deleteAnnotation(index) {
        this._deleteAnnotation(index);
    }
}

// Global storage for annotator instances
window._bboxAnnotators = window._bboxAnnotators || {};

// Global helper called from label toolbar buttons
function setBboxLabel(qid, name, color) {
    var annotator = window._bboxAnnotators[qid];
    if (annotator) annotator.setLabel(name, color);
}

// Global helper called from annotation list delete buttons
function deleteBboxAnnotation(qid, index) {
    var annotator = window._bboxAnnotators[qid];
    if (annotator) annotator.deleteAnnotation(index);
}

// Initialize annotators when DOM is ready or when pane becomes active
function initBboxAnnotators() {
    var data = window._bboxData || {};
    for (var qid in data) {
        if (!window._bboxAnnotators[qid]) {
            var canvas = document.getElementById('bbox-canvas-' + qid);
            if (canvas) {
                window._bboxAnnotators[qid] = new BboxAnnotator(qid);
            }
        }
    }
}

// Hook into DOMContentLoaded
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initBboxAnnotators);
} else {
    // DOM already loaded, init immediately (but with a small delay for image loading)
    setTimeout(initBboxAnnotators, 100);
}
