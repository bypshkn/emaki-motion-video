// ---------------------------------------------------------------------------------------------
// Emaki AE runtime (ExtendScript, ES3). Builds the project described by DATA.
// ---------------------------------------------------------------------------------------------
(function () {
    var D = DATA;
    var MAIN = D.meta.name;
    var VERSION = parseFloat(app.version);
    var NOTES = [];
    var BASE = (new File($.fileName)).parent;
    var CTRL_REF = 'comp("' + MAIN + '").layer("CONTROLS")';
    var footageCache = {};
    var comps = {};
    var folders = {};

    function each(a, f) { if (!a) return; for (var i = 0; i < a.length; i++) f(a[i], i); }

    function interp(s) {
        if (s === "HOLD") return KeyframeInterpolationType.HOLD;
        if (s === "BEZIER") return KeyframeInterpolationType.BEZIER;
        return KeyframeInterpolationType.LINEAR;
    }

    function toShape(c) {
        var s = new Shape();
        s.vertices = c.v; s.inTangents = c.i; s.outTangents = c.o; s.closed = c.c;
        return s;
    }

    function easeArr(e, n) {
        var out = [];
        for (var d = 0; d < n; d++) {
            if (e && e[d]) out.push(new KeyframeEase(e[d][0], Math.max(0.1, Math.min(100, e[d][1]))));
            else out.push(new KeyframeEase(0, 33.33));
        }
        return out;
    }

    function easeDims(p, v) {
        // spatial and 1-D properties take one KeyframeEase; non-spatial multi-D take one per dimension
        if (p.propertyValueType === PropertyValueType.TwoD_SPATIAL || p.propertyValueType === PropertyValueType.ThreeD_SPATIAL) return 1;
        if (v instanceof Array) return v.length;
        return 1;
    }

    function applyK(p, k, conv) {
        if (!k || !p) return;
        conv = conv || function (v) { return v; };
        if (k.k) {
            var rows = k.k, i;
            for (i = 0; i < rows.length; i++) p.setValueAtTime(rows[i].t, conv(rows[i].v));
            for (i = 0; i < rows.length; i++) {
                var idx = p.nearestKeyIndex(rows[i].t);
                var r = rows[i];
                var n = easeDims(p, conv(r.v));
                p.setInterpolationTypeAtKey(idx, interp(r["in"]), interp(r.out));
                if (r.ie || r.oe) {
                    // colour/path properties may want a single ease; fall back if AE rejects n
                    try { p.setTemporalEaseAtKey(idx, easeArr(r.ie, n), easeArr(r.oe, n)); }
                    catch (eErr) { p.setTemporalEaseAtKey(idx, easeArr(r.ie, 1), easeArr(r.oe, 1)); }
                }
            }
        } else if (k.v !== undefined && k.v !== null) {
            p.setValue(conv(k.v));
        }
        if (k.expr) p.expression = k.expr;
    }

    function cubicEase(p, t0, t1, v0, v1, cp) {
        // two keys with a CSS-style cubic-bezier between them
        p.setValueAtTime(t0, v0);
        p.setValueAtTime(t1, v1);
        var i0 = p.nearestKeyIndex(t0), i1 = p.nearestKeyIndex(t1);
        var T = t1 - t0, dims = (v0 instanceof Array) ? v0.length : 1;
        var x1 = Math.max(cp[0], 0.001), y1 = cp[1], x2 = Math.min(cp[2], 0.999), y2 = cp[3];
        var oe = [], ie = [];
        for (var d = 0; d < dims; d++) {
            var dv = (dims > 1 ? v1[d] - v0[d] : v1 - v0) / T;
            oe.push(new KeyframeEase(y1 / x1 * dv, Math.max(0.1, x1 * 100)));
            ie.push(new KeyframeEase((1 - y2) / (1 - x2) * dv, Math.max(0.1, (1 - x2) * 100)));
        }
        var nd = easeDims(p, v0);
        if (nd === 1 && dims > 1) { oe = [oe[0]]; ie = [ie[0]]; }
        p.setInterpolationTypeAtKey(i0, KeyframeInterpolationType.LINEAR, KeyframeInterpolationType.BEZIER);
        p.setInterpolationTypeAtKey(i1, KeyframeInterpolationType.BEZIER, KeyframeInterpolationType.LINEAR);
        p.setTemporalEaseAtKey(i0, easeArr(null, nd), oe);
        p.setTemporalEaseAtKey(i1, ie, easeArr(null, nd));
    }

    function addEffect(layer, matchName, name) {
        var fx = layer.property("ADBE Effect Parade").addProperty(matchName);
        if (name) fx.name = name;
        return fx;
    }

    function ctrl(name, kind) {
        return CTRL_REF + '.effect("' + name + '")("' + (kind || "Slider") + '")';
    }

    function footage(rel) {
        if (footageCache[rel]) return footageCache[rel];
        var f = new File(BASE.fsName + "/" + rel);
        if (!f.exists) throw new Error("missing file next to the script: " + rel);
        var it = app.project.importFile(new ImportOptions(f));
        it.parentFolder = rel.indexOf("Audio/") === 0 ? folders.audio : folders.assets;
        footageCache[rel] = it;
        return it;
    }

    function addComp(name, w, h, dur, folder) {
        var c = app.project.items.addComp(name, w, h, 1, Math.max(dur, 1 / D.meta.fps), D.meta.fps);
        c.parentFolder = folder;
        c.bgColor = D.meta.bg;
        if (D.meta.motion_blur) { c.motionBlur = true; c.shutterAngle = D.meta.motion_blur.shutter || 180; }
        comps[name] = c;
        return c;
    }

    // ---- transform -----------------------------------------------------------------------
    function applyTransform(l, tr, is3d) {
        if (!tr) return;
        var T = l.property("ADBE Transform Group");
        if (is3d) l.threeDLayer = true;
        var pos = T.property("ADBE Position");
        pos.dimensionsSeparated = true;
        applyK(T.property("ADBE Position_0"), tr.x);
        applyK(T.property("ADBE Position_1"), tr.y);
        if (is3d && tr.z) applyK(T.property("ADBE Position_2"), tr.z);
        var a = tr.anchor;
        T.property("ADBE Anchor Point").setValue(is3d ? [a[0], a[1], 0] : [a[0], a[1]]);
        applyK(T.property("ADBE Scale"), tr.scale, function (v) { return is3d ? v : [v[0], v[1]]; });
        applyK(T.property("ADBE Rotate Z"), tr.rotation);
        applyK(T.property("ADBE Opacity"), tr.opacity);
        if (tr.rx || tr.ry) {
            l.threeDLayer = true;
            if (tr.rx) applyK(T.property("ADBE Rotate X"), tr.rx);
            if (tr.ry) applyK(T.property("ADBE Rotate Y"), tr.ry);
        }
    }

    function applyCommon(l, d) {
        l.name = d.name;
        if (d.label) l.label = d.label;
        if (d.blend && BlendingMode[d.blend] !== undefined) l.blendingMode = BlendingMode[d.blend];
        if (d.motion_blur) l.motionBlur = true;
        if (d.start_time !== undefined && d.start_time !== null) l.startTime = d.start_time;
        if (d["in"] !== undefined && d["in"] !== null && d["in"] > 0) l.inPoint = d["in"];
        if (d.out !== undefined && d.out !== null) l.outPoint = d.out;
        applyTransform(l, d.tr, d.three_d);
        each(d.fx, function (f) { layerFx(l, f); });
        if (d.mask) {
            var m = l.property("ADBE Mask Parade").addProperty("ADBE Mask Atom");
            m.maskMode = MaskMode.ADD;
            var sh = d.mask.shift || [0, 0];
            applyK(m.property("ADBE Mask Shape"), d.mask.path, function (v) {
                var c = v[0];
                var vv = [];
                for (var i = 0; i < c.v.length; i++) vv.push([c.v[i][0] - sh[0], c.v[i][1] - sh[1]]);
                return toShape({v: vv, i: c.i, o: c.o, c: c.c});
            });
        }
    }

    function layerFx(l, f) {
        var fx;
        if (f.type === "blur") {
            fx = addEffect(l, "ADBE Gaussian Blur 2", "Blur");
            applyK(fx.property(1), f.sigma);
        } else if (f.type === "shadow") {
            fx = addEffect(l, "ADBE Drop Shadow", "Shadow");
            fx.property(1).setValue(f.color);
            fx.property(2).setValue(f.opacity * 2.55);
            fx.property(3).setValue(f.direction);
            fx.property(4).setValue(f.distance);
            fx.property(5).setValue(f.softness);
        } else if (f.type === "glow") {
            fx = addEffect(l, "ADBE Glo2", "Glow");
            fx.property(3).setValue(f.radius);
            fx.property(4).setValue(f.intensity);
        } else if (f.type === "smear") {
            fx = addEffect(l, "ADBE Motion Blur", "Smear");
            fx.property(1).expression = "var v = transform.position.velocity; radiansToDegrees(Math.atan2(v[0], -v[1]));";
            fx.property(2).expression = "Math.min(" + f.max + ", length(transform.position.velocity) * " + f.k + " * 2.4);";
        } else if (f.type === "ramp") {
            fx = addEffect(l, "ADBE Ramp", "Gradient");
            fx.property(1).setValue(f.start);
            fx.property(2).setValue(f.start_color);
            fx.property(3).setValue(f.end);
            fx.property(4).setValue(f.end_color);
            fx.property(5).setValue(f.shape);
        }
    }

    // ---- layer builders --------------------------------------------------------------------
    function buildText(comp, d) {
        var l = comp.layers.addText(d.text);
        var srcProp = l.property("ADBE Text Properties").property("ADBE Text Document");
        var td = srcProp.value;
        td.resetCharStyle();
        td.font = d.font;
        td.fontSize = d.size;
        td.applyFill = true;
        td.fillColor = d.fill;
        td.tracking = Math.round(d.tracking);
        td.autoLeading = false;
        td.leading = d.leading;
        td.justification = d.just === "CENTER" ? ParagraphJustification.CENTER_JUSTIFY :
            (d.just === "RIGHT" ? ParagraphJustification.RIGHT_JUSTIFY : ParagraphJustification.LEFT_JUSTIFY);
        if (d.stroke) { td.applyStroke = true; td.strokeColor = d.stroke.color; td.strokeWidth = d.stroke.width; td.strokeOverFill = false; }
        else td.applyStroke = false;
        srcProp.setValue(td);
        if (d.source_expr) srcProp.expression = d.source_expr;
        applyCommon(l, d);
        if (d.scale_ctrl) {
            var sc = l.property("ADBE Transform Group").property("ADBE Scale");
            var base = sc.expression ? "" : "";
            sc.expression = "var s = " + ctrl("Text Scale") + "/100; var v = value; v.length > 2 ? [v[0]*s, v[1]*s, v[2]] : [v[0]*s, v[1]*s];";
        }
        var anyChar = false;
        each(d.animators, function (a) { addAnimator(l, a); if (a.anchor_group) anyChar = true; });
        if (anyChar) {
            var mo = l.property("ADBE Text Properties").property("ADBE Text More Options");
            mo.property("ADBE Text Anchor Point Option").setValue(1);
            mo.property("ADBE Text Anchor Point Align").setValue([0, -50]);
        }
        if (d.text_path) {
            var m = l.property("ADBE Mask Parade").addProperty("ADBE Mask Atom");
            m.maskMode = MaskMode.NONE;
            m.property("ADBE Mask Shape").setValue(toShape(d.text_path.shape[0]));
            var po = l.property("ADBE Text Properties").property("ADBE Text Path Options");
            po.property("ADBE Text Path").setValue(1);
        }
        return l;
    }

    function addAnimator(l, a) {
        var anims = l.property("ADBE Text Properties").property("ADBE Text Animators");
        var an = anims.addProperty("ADBE Text Animator");
        an.name = a.name;
        var props = an.property("ADBE Text Animator Properties");
        var P = a.props;
        if (P.opacity !== undefined) props.addProperty("ADBE Text Opacity").setValue(P.opacity);
        if (P.position) props.addProperty("ADBE Text Position 3D").setValue(P.position);
        if (P.scale) props.addProperty("ADBE Text Scale 3D").setValue(P.scale);
        if (P.rotation !== undefined) props.addProperty("ADBE Text Rotation").setValue(P.rotation);
        if (P.blur) props.addProperty("ADBE Text Blur").setValue(P.blur);
        if (P.tracking !== undefined) props.addProperty("ADBE Text Tracking Amount").setValue(P.tracking);
        if (P.fill) {
            var fc = props.addProperty("ADBE Text Fill Color");
            fc.setValue(P.fill);
            if (a.accent) fc.expression = ctrl("Accent Color", "Color");
        }
        if (P.char_offset !== undefined) {
            var co = props.addProperty("ADBE Text Character Offset");
            co.setValue(P.char_offset);
            if (a.char_offset_expr) co.expression = a.char_offset_expr;
        }
        var sels = an.property("ADBE Text Selectors");
        if (a.range) {
            var rs = sels.addProperty("ADBE Text Selector");
            rs.property("ADBE Text Range Advanced").property("ADBE Text Range Units").setValue(2);
            rs.property("ADBE Text Index Start").setValue(a.range[0]);
            rs.property("ADBE Text Index End").setValue(a.range[1]);
        } else {
            var es = sels.addProperty("ADBE Text Expressible Selector");
            es.property("ADBE Text Range Type2").setValue(a.based_on || 1);
            es.property("ADBE Text Expressible Amount").expression = a.amount_expr;
        }
    }

    function buildCursor(comp, d, textLayer) {
        var c = d.cursor;
        var l = comp.layers.addShape();
        l.name = d.name + " · Cursor";
        l.label = 2;
        var g = l.property("ADBE Root Vectors Group").addProperty("ADBE Vector Group");
        var r = g.property("ADBE Vectors Group").addProperty("ADBE Vector Shape - Rect");
        r.property("ADBE Vector Rect Size").setValue([c.w, c.h]);
        r.property("ADBE Vector Rect Position").setValue([c.w / 2, c.dy + c.h / 2]);
        var f = g.property("ADBE Vectors Group").addProperty("ADBE Vector Graphic - Fill");
        f.property("ADBE Vector Fill Color").setValue(c.color);
        l.parent = textLayer;
        var T = l.property("ADBE Transform Group");
        T.property("ADBE Anchor Point").setValue([0, 0]);
        T.property("ADBE Scale").setValue([100, 100]);
        T.property("ADBE Rotate Z").setValue(0);
        var pos = T.property("ADBE Position");
        for (var i = 0; i < c.keys.length; i++) pos.setValueAtTime(c.keys[i][0], c.keys[i][1]);
        for (i = 1; i <= pos.numKeys; i++) pos.setInterpolationTypeAtKey(i, KeyframeInterpolationType.HOLD, KeyframeInterpolationType.HOLD);
        T.property("ADBE Opacity").expression = c.blink;
        l.inPoint = Math.max(0, c.t0);
        return l;
    }

    function buildHighlight(comp, d, h, textLayer, k) {
        var l = comp.layers.addShape();
        l.name = d.name + " · Highlight " + (k + 1);
        l.label = 8;
        l.parent = textLayer;
        var LT = l.property("ADBE Transform Group");
        LT.property("ADBE Position").setValue([0, 0]);
        LT.property("ADBE Anchor Point").setValue([0, 0]);
        LT.property("ADBE Scale").setValue([100, 100]);
        LT.property("ADBE Rotate Z").setValue(0);
        for (var i = 0; i < h.rects.length; i++) {
            var R = h.rects[i];
            var g = l.property("ADBE Root Vectors Group").addProperty("ADBE Vector Group");
            var r = g.property("ADBE Vectors Group").addProperty("ADBE Vector Shape - Rect");
            r.property("ADBE Vector Rect Size").setValue([R[2], R[3]]);
            r.property("ADBE Vector Rect Position").setValue([R[0] + R[2] / 2, R[1] + R[3] / 2]);
            var f = g.property("ADBE Vectors Group").addProperty("ADBE Vector Graphic - Fill");
            f.property("ADBE Vector Fill Color").setValue(h.color);
            f.property("ADBE Vector Fill Opacity").setValue(h.opacity);
            var gt = g.property("ADBE Vector Transform Group");
            gt.property("ADBE Vector Anchor").setValue([R[0], 0]);
            gt.property("ADBE Vector Position").setValue([R[0], 0]);
            applyK(gt.property("ADBE Vector Scale"), h.k, function (v) { return [v[0], v[1]]; });
        }
        return l;
    }

    function addGeo(gc, geo) {
        each(geo, function (it) {
            if (it.type === "rect") {
                var r = gc.addProperty("ADBE Vector Shape - Rect");
                applyK(r.property("ADBE Vector Rect Size"), it.size);
                applyK(r.property("ADBE Vector Rect Roundness"), it.radius);
            } else if (it.type === "ellipse") {
                var e = gc.addProperty("ADBE Vector Shape - Ellipse");
                applyK(e.property("ADBE Vector Ellipse Size"), it.size);
            } else if (it.type === "star") {
                var s = gc.addProperty("ADBE Vector Shape - Star");
                s.property("ADBE Vector Star Type").setValue(it.kind);
                s.property("ADBE Vector Star Points").setValue(it.points);
                applyK(s.property("ADBE Vector Star Outer Radius"), it.outer);
                if (it.inner) applyK(s.property("ADBE Vector Star Inner Radius"), it.inner);
            } else if (it.type === "path") {
                var k = it.shapes[0];
                var nContours = k.k ? k.k[0].v.length : k.v.length;
                for (var c = 0; c < nContours; c++) {
                    var pg = gc.addProperty("ADBE Vector Shape - Group");
                    pg.name = "Path " + (c + 1);
                    (function (ci) {
                        applyK(pg.property("ADBE Vector Shape"), k, function (v) { return toShape(v[ci]); });
                    })(c);
                }
            }
        });
    }

    function buildShape(comp, d) {
        var l = comp.layers.addShape();
        var root = l.property("ADBE Root Vectors Group");
        each(d.groups, function (G) {
            var g = root.addProperty("ADBE Vector Group");
            g.name = G.name;
            var gc = g.property("ADBE Vectors Group");
            addGeo(gc, G.geo);
            if (G.trim) {
                var tr = gc.addProperty("ADBE Vector Filter - Trim");
                tr.name = "Trim Paths 1";
                applyK(tr.property("ADBE Vector Trim Start"), G.trim.start);
                applyK(tr.property("ADBE Vector Trim End"), G.trim.end);
                applyK(tr.property("ADBE Vector Trim Offset"), G.trim.offset);
                tr.property("ADBE Vector Trim Type").setValue(G.trim.mode);
            }
            if (G.stroke) {
                var st = gc.addProperty("ADBE Vector Graphic - Stroke");
                applyK(st.property("ADBE Vector Stroke Color"), G.stroke.color);
                st.property("ADBE Vector Stroke Opacity").setValue(G.stroke.opacity);
                applyK(st.property("ADBE Vector Stroke Width"), G.stroke.width);
                st.property("ADBE Vector Stroke Line Cap").setValue(G.stroke.cap);
                st.property("ADBE Vector Stroke Line Join").setValue(G.stroke.join);
                if (G.stroke.accent) st.property("ADBE Vector Stroke Color").expression = ctrl("Accent Color", "Color");
                if (G.stroke.dash) {
                    var ds = st.property("ADBE Vector Stroke Dashes");
                    ds.addProperty("ADBE Vector Stroke Dash 1").setValue(G.stroke.dash[0]);
                    ds.addProperty("ADBE Vector Stroke Gap 1").setValue(G.stroke.dash[1]);
                }
            }
            if (G.fill) {
                var f = gc.addProperty("ADBE Vector Graphic - Fill");
                applyK(f.property("ADBE Vector Fill Color"), G.fill.color);
                f.property("ADBE Vector Fill Opacity").setValue(G.fill.opacity);
                if (G.fill.accent) f.property("ADBE Vector Fill Color").expression = ctrl("Accent Color", "Color");
            }
        });
        applyCommon(l, d);
        return l;
    }

    function buildLayer(comp, d) {
        var l;
        if (d.kind === "text") {
            l = buildText(comp, d);
            if (d.cursor) buildCursor(comp, d, l);
            each(d.highlights, function (h, k) { var hl = buildHighlight(comp, d, h, l, k); hl.moveAfter(l); });
        } else if (d.kind === "shape" || d.kind === "matte") {
            l = buildShape(comp, d);
            if (d.hidden_matte) l.enabled = false;
        } else if (d.kind === "solid") {
            var sz = d.size || [comp.width, comp.height];
            l = comp.layers.addSolid(d.color || [1, 1, 1], d.name, sz[0], sz[1], 1, comp.duration);
            applyCommon(l, d);
        } else if (d.kind === "image") {
            l = comp.layers.add(footage(d.file));
            applyCommon(l, d);
            var sc = l.property("ADBE Transform Group").property("ADBE Scale");
            if (!sc.numKeys) sc.setValue([d.fit_scale[0], d.fit_scale[1]]);
        } else if (d.kind === "baked") {
            l = comp.layers.add(footage(d.file));
            l.name = d.name; l.label = d.label;
            l.startTime = d.start_time || 0;
        } else if (d.kind === "precomp") {
            l = comp.layers.add(comps[d.source]);
            applyCommon(l, d);
            if (d.collapse) l.collapseTransformation = true;
        } else {
            NOTES.push("skipped layer " + d.name + " (" + d.kind + ")");
            return null;
        }
        if (d.hidden_matte && l) l.enabled = false;
        if (d.matte) {
            var m = comp.layer(d.matte.layer);
            if (VERSION >= 23 && l.setTrackMatte) {
                l.setTrackMatte(m, TrackMatteType[d.matte.type]);
            } else {
                m.moveBefore(l);
                l.trackMatteType = TrackMatteType[d.matte.type];
            }
            m.enabled = false;
        }
        return l;
    }

    function fillComp(comp, layers) {
        each(layers, function (d) { buildLayer(comp, d); });
    }

    function buildCamera(comp, cam) {
        var z = comp.layers.addNull(comp.duration);
        z.name = "CAMERA ZOOM";
        z.enabled = false;
        var sl = addEffect(z, "ADBE Slider Control", "Zoom");
        applyK(sl.property(1), cam.zoom);
        var c = comp.layers.addCamera("Camera", [comp.width / 2, comp.height / 2]);
        c.property("ADBE Camera Options Group").property("ADBE Camera Zoom").setValue(cam.focal);
        var T = c.property("ADBE Transform Group");
        T.property("ADBE Position").dimensionsSeparated = true;
        applyK(T.property("ADBE Position_0"), cam.x);
        applyK(T.property("ADBE Position_1"), cam.y);
        var tx = addEffect(z, "ADBE Slider Control", "Tilt X");
        applyK(tx.property(1), cam.tilt_x);
        var ty = addEffect(z, "ADBE Slider Control", "Tilt Y");
        applyK(ty.property(1), cam.tilt_y);
        // orbit: the camera sits at target + Ry(tilt_y) Rx(tilt_x) (0, 0, -D), D = focal / zoom
        var head = 'var c = thisComp.layer("CAMERA ZOOM"); var D = ' + cam.focal + ' / Math.max(0.01, c.effect("Zoom")("Slider"));' +
                   ' var a = degreesToRadians(c.effect("Tilt Y")("Slider")); var b = degreesToRadians(c.effect("Tilt X")("Slider"));';
        var px = T.property("ADBE Position_0"), py = T.property("ADBE Position_1");
        var ex = px.expression ? px.expression.replace(/ v;\s*$/, " ") : "var v = value; ";
        var ey = py.expression ? py.expression.replace(/ v;\s*$/, " ") : "var v = value; ";
        px.expression = ex + head + " v + D * Math.sin(a) * Math.cos(b);";
        py.expression = ey + head + " v - D * Math.sin(b);";
        T.property("ADBE Position_2").expression = head + " -D * Math.cos(a) * Math.cos(b);";
        T.property("ADBE Anchor Point").expression = 'var c = thisComp.layer("CAMERA ZOOM"); var D = 0; [' +
            '(function(){ var p = transform.xPosition; ' + head + ' return p - D * Math.sin(a) * Math.cos(b); })(), ' +
            '(function(){ var p = transform.yPosition; ' + head + ' return p + D * Math.sin(b); })(), 0]';
        applyK(T.property("ADBE Rotate Z"), cam.rotation);
        c.label = 4;
    }

    // ---- transitions -----------------------------------------------------------------------
    var DIRV = {left: [-1, 0], right: [1, 0], up: [0, -1], down: [0, 1]};

    function posKeys(l, t0, t1, a, b, cp) {
        var T = l.property("ADBE Transform Group");
        T.property("ADBE Position").dimensionsSeparated = true;
        cubicEase(T.property("ADBE Position_0"), t0, t1, a[0], b[0], cp);
        cubicEase(T.property("ADBE Position_1"), t0, t1, a[1], b[1], cp);
    }

    function transition(main, sceneLayers, tr) {
        var A = sceneLayers[tr.from], B = sceneLayers[tr.to];
        var t0 = tr.t0, t1 = tr.t0 + tr.dur, mid = (t0 + t1) / 2, cp = tr.ease, P = tr.params;
        var W = main.width, H = main.height, C = [W / 2, H / 2];
        var dv = DIRV[P.direction || "left"] || [-1, 0];
        if (tr.type === "fade") {
            cubicEase(B.property("ADBE Transform Group").property("ADBE Opacity"), t0, t1, 0, 100, cp);
        } else if (tr.type === "push" || tr.type === "slide") {
            var par = tr.type === "slide" ? (P.parallax || 0.25) : 1;
            posKeys(A, t0, t1, C, [C[0] + dv[0] * W * par, C[1] + dv[1] * H * par], cp);
            posKeys(B, t0, t1, [C[0] - dv[0] * W, C[1] - dv[1] * H], C, cp);
        } else if (tr.type === "wipe") {
            var fx = addEffect(B, "ADBE Linear Wipe", "Wipe In");
            var ang = {right: 270, left: 90, down: 0, up: 180}[P.direction || "right"];
            fx.property(2).setValue(ang);
            fx.property(3).setValue((P.softness || 0) * W);
            cubicEase(fx.property(1), t0, t1, 100, 0, cp);
        } else if (tr.type === "iris") {
            var m = B.property("ADBE Mask Parade").addProperty("ADBE Mask Atom");
            var c = P.center, R = Math.sqrt(W * W + H * H);
            var circ = function (r) {
                var k = 0.5523 * r;
                return toShape({v: [[c[0], c[1] - r], [c[0] + r, c[1]], [c[0], c[1] + r], [c[0] - r, c[1]]],
                    i: [[-k, 0], [0, -k], [k, 0], [0, k]], o: [[k, 0], [0, k], [-k, 0], [0, -k]], c: true});
            };
            m.property("ADBE Mask Shape").setValueAtTime(t0, circ(0.5));
            m.property("ADBE Mask Shape").setValueAtTime(t1, circ(R));
        } else if (tr.type === "zoom") {
            var a = P.amount || 0.35;
            var TA = A.property("ADBE Transform Group"), TB = B.property("ADBE Transform Group");
            cubicEase(TA.property("ADBE Scale"), t0, t1, [100, 100], [100 * (1 + a), 100 * (1 + a)], cp);
            cubicEase(TA.property("ADBE Opacity"), t0, t1, 100, 0, cp);
            cubicEase(TB.property("ADBE Scale"), t0, t1, [100 * (1 - 0.4 * a), 100 * (1 - 0.4 * a)], [100, 100], cp);
            cubicEase(TB.property("ADBE Opacity"), t0, t1, 0, 100, cp);
        } else if (tr.type === "blur") {
            var bA = addEffect(A, "ADBE Gaussian Blur 2", "Transition Blur");
            cubicEase(bA.property(1), t0, mid, 0, (P.sigma || 30) * 2.4, cp);
            var bB = addEffect(B, "ADBE Gaussian Blur 2", "Transition Blur");
            cubicEase(bB.property(1), mid, t1, (P.sigma || 30) * 2.4, 0, cp);
            cubicEase(B.property("ADBE Transform Group").property("ADBE Opacity"), t0, t1, 0, 100, cp);
        } else if (tr.type === "dip") {
            var s = main.layers.addSolid(P.color, "Dip " + tr.to, W, H, 1, main.duration);
            s.inPoint = t0; s.outPoint = t1; s.label = 12;
            var op = s.property("ADBE Transform Group").property("ADBE Opacity");
            cubicEase(op, t0, mid, 0, 100, cp);
            op.setValueAtTime(t1, 0);
            A.outPoint = mid; B.inPoint = mid;
        } else if (tr.type === "shape_wipe") {
            var band = Math.sqrt(W * W + H * H) * 1.2;
            var sl = main.layers.addShape();
            sl.name = "Shape Wipe " + tr.to; sl.label = 8;
            var g = sl.property("ADBE Root Vectors Group").addProperty("ADBE Vector Group");
            var r = g.property("ADBE Vectors Group").addProperty("ADBE Vector Shape - Rect");
            r.property("ADBE Vector Rect Size").setValue([band, band * 2]);
            var f = g.property("ADBE Vectors Group").addProperty("ADBE Vector Graphic - Fill");
            f.property("ADBE Vector Fill Color").setValue(P.color);
            var T = sl.property("ADBE Transform Group");
            T.property("ADBE Rotate Z").setValue(P.angle || -12);
            var x0 = P.direction === "left" ? W + band : -band, x1 = P.direction === "left" ? -band : W + band;
            posKeys(sl, t0, t1, [x0, H / 2], [x1, H / 2], cp);
            sl.inPoint = t0; sl.outPoint = t1;
            A.outPoint = mid; B.inPoint = mid;
        } else if (tr.type === "whip") {
            posKeys(A, t0, t1, C, [C[0] + dv[0] * W, C[1] + dv[1] * H], cp);
            posKeys(B, t0, t1, [C[0] - dv[0] * W, C[1] - dv[1] * H], C, cp);
            each([A, B], function (L) {
                var mb = addEffect(L, "ADBE Motion Blur", "Whip Smear");
                mb.property(1).setValue(dv[0] !== 0 ? 90 : 0);
                mb.property(2).setValueAtTime(t0, 0);
                mb.property(2).setValueAtTime(mid, (P.blur || 90) * 2.4);
                mb.property(2).setValueAtTime(t1, 0);
            });
        } else if (tr.type === "flash") {
            var fl = main.layers.addSolid(P.color || [1, 1, 1], "Flash " + tr.to, W, H, 1, main.duration);
            fl.inPoint = t0; fl.outPoint = t1; fl.label = 12;
            var fo = fl.property("ADBE Transform Group").property("ADBE Opacity");
            fo.setValueAtTime(t0, 0); fo.setValueAtTime(mid, 100); fo.setValueAtTime(t1, 0);
            A.outPoint = mid; B.inPoint = mid;
        } else if (tr.type === "scale_through") {
            var am = (P.amount || 2.2) * 100;
            cubicEase(A.property("ADBE Transform Group").property("ADBE Scale"), t0, mid, [100, 100], [am, am], [0.7, 0, 0.84, 0]);
            cubicEase(B.property("ADBE Transform Group").property("ADBE Scale"), mid, t1, [125, 125], [100, 100], [0.16, 1, 0.3, 1]);
            A.outPoint = mid; B.inPoint = mid;
        } else if (tr.type === "glitch" || tr.type === "cut") {
            A.outPoint = mid; B.inPoint = mid;
        }
    }

    // ---- post fx ---------------------------------------------------------------------------
    function postFx(main, p) {
        var W = main.width, H = main.height;
        if (p.type === "scanlines") {
            var sl = main.layers.addShape();
            sl.name = "FX · Scanlines"; sl.label = 5;
            var g = sl.property("ADBE Root Vectors Group").addProperty("ADBE Vector Group");
            var gc = g.property("ADBE Vectors Group");
            var r = gc.addProperty("ADBE Vector Shape - Rect");
            r.property("ADBE Vector Rect Size").setValue([W, Math.max(1, p.period * 0.4)]);
            r.property("ADBE Vector Rect Position").setValue([W / 2, 0]);
            var f = gc.addProperty("ADBE Vector Graphic - Fill");
            f.property("ADBE Vector Fill Color").setValue([0, 0, 0]);
            var rp = gc.addProperty("ADBE Vector Filter - Repeater");
            rp.property("ADBE Vector Repeater Copies").setValue(Math.ceil(H / p.period) + 1);
            rp.property("ADBE Vector Repeater Transform").property("ADBE Vector Repeater Position").setValue([0, p.period]);
            sl.blendingMode = BlendingMode.MULTIPLY;
            var op = sl.property("ADBE Transform Group").property("ADBE Opacity");
            op.setValue(p.strength);
            op.expression = "value * " + ctrl("FX Intensity") + "/100";
            return;
        }
        var adj = main.layers.addSolid([1, 1, 1], "FX · " + p.type, W, H, 1, main.duration);
        adj.adjustmentLayer = true;
        adj.label = 5;
        var fx;
        if (p.type === "noise") {
            fx = addEffect(adj, "ADBE Noise", "Grain");
            fx.property(1).setValue(p.amount);
            fx.property(1).expression = "value * " + ctrl("FX Intensity") + "/100";
        } else if (p.type === "vignette") {
            fx = addEffect(adj, "CC Vignette", "Vignette");
            fx.property(1).setValue(p.amount);
            fx.property(1).expression = "value * " + ctrl("FX Intensity") + "/100";
        } else if (p.type === "glow") {
            fx = addEffect(adj, "ADBE Glo2", "Bloom");
            fx.property(2).setValue(p.threshold);
            fx.property(3).setValue(p.radius);
            fx.property(4).setValue(p.intensity);
            fx.property(4).expression = "value * " + ctrl("FX Intensity") + "/100";
        } else if (p.type === "grade") {
            fx = addEffect(adj, "ADBE HUE SATURATION", "Grade Saturation");
            fx.property(4).setValue(p.saturation);
            var bc = addEffect(adj, "ADBE Brightness & Contrast 2", "Grade Contrast");
            bc.property(2).setValue(p.contrast);
        }
    }

    function checkFonts() {
        var miss = [];
        if (app.fonts && app.fonts.getFontsByPostScriptName) {
            for (var i = 0; i < D.fonts.length; i++) {
                var r = app.fonts.getFontsByPostScriptName(D.fonts[i]);
                if (!r || r.length === 0) miss.push(D.fonts[i]);
            }
        } else {
            NOTES.push("Font check needs AE 24.0+. Verify these fonts are installed: " + D.fonts.join(", "));
        }
        if (miss.length) {
            if (!confirm("Missing fonts:\n" + miss.join("\n") + "\n\nInstall them and run again, or continue with substitutes?\nContinue?"))
                throw new Error("cancelled: missing fonts");
            NOTES.push("Missing fonts (substituted): " + miss.join(", "));
        }
    }

    // ---- main ------------------------------------------------------------------------------
    function build() {
        if (VERSION + 0.001 < D.meta.target) NOTES.push("This AE (" + app.version + ") is older than the target " + D.meta.target);
        checkFonts();
        if (!app.project) app.newProject();
        var items = app.project.items;
        folders.comps = items.addFolder("Comps");
        folders.pre = items.addFolder("Precomps");
        folders.audio = items.addFolder("Audio");
        folders.assets = items.addFolder("Assets");
        var M = D.meta;
        var i;
        for (i = 0; i < D.precomps.length; i++) addComp(D.precomps[i].name, D.precomps[i].w, D.precomps[i].h, D.precomps[i].dur, folders.pre);
        for (i = 0; i < D.scenes.length; i++) addComp(D.scenes[i].name, D.scenes[i].w, D.scenes[i].h, D.scenes[i].dur, folders.pre);
        var main = addComp(MAIN, M.W, M.H, M.dur, folders.comps);
        // CONTROLS first: expressions in every comp reference it
        var ctl = main.layers.addNull(M.dur);
        ctl.name = "CONTROLS";
        ctl.label = 1;
        addEffect(ctl, "ADBE Slider Control", "Speed").property(1).setValue(100);
        addEffect(ctl, "ADBE Slider Control", "FX Intensity").property(1).setValue(100);
        addEffect(ctl, "ADBE Color Control", "Accent Color").property(1).setValue(D.controls.accent);
        addEffect(ctl, "ADBE Slider Control", "Text Scale").property(1).setValue(100);
        // precomps are filled deepest-first (they were collected children-first)
        for (i = 0; i < D.precomps.length; i++) fillComp(comps[D.precomps[i].name], D.precomps[i].layers);
        var sceneLayers = [];
        for (i = 0; i < D.scenes.length; i++) {
            var S = D.scenes[i], sc = comps[S.name];
            fillComp(sc, S.layers);
            if (S.camera) buildCamera(sc, S.camera);
            if (S.motion_blur) { sc.motionBlur = true; }
            var L = main.layers.add(sc);
            L.startTime = S.t0;
            L.name = S.name;
            L.label = 15;
            if (S.motion_blur) L.motionBlur = true;
            L.timeRemapEnabled = true;
            L.property("ADBE Time Remapping").expression = "(time - inPoint) * " + ctrl("Speed") + "/100";
            sceneLayers.push(L);
        }
        each(D.transitions, function (tr) { transition(main, sceneLayers, tr); });
        fillComp(main, D.overlay);
        each(D.baked_windows, function (b) {
            var bl = main.layers.add(footage("Assets/" + b.file));
            bl.startTime = b.t0; bl.name = "[BAKED] " + b.why; bl.label = 11;
        });
        each(D.post, function (p) { postFx(main, p); });
        if (D.audio.voice) { var av = main.layers.add(footage(D.audio.voice)); av.name = "Voice"; av.label = 6; }
        if (D.audio.music) { var am = main.layers.add(footage(D.audio.music)); am.name = "Music"; am.label = 6; }
        if (D.audio.sfx) { var as = main.layers.add(footage(D.audio.sfx)); as.name = "SFX"; as.label = 6; }
        if (D.audio.mix) { footage(D.audio.mix); }
        each(D.markers, function (m) {
            main.markerProperty.setValueAtTime(m.t, new MarkerValue(m.kind + (m.accent ? " (accent)" : "")));
        });
        ctl.moveToBeginning();
        main.openInViewer();
        var msg = "Emaki: built '" + MAIN + "' (" + D.scenes.length + " scenes).";
        if (NOTES.length) msg += "\n\nNotes:\n- " + NOTES.join("\n- ");
        alert(msg);
    }

    app.beginUndoGroup("Emaki build");
    try {
        build();
    } catch (e) {
        alert("Emaki build error: " + e.toString() + (e.line ? " (line " + e.line + ")" : ""));
        throw e;
    } finally {
        app.endUndoGroup();
    }
})();
