// Validate a generated build_project.jsx against a mock of the After Effects object model.
// Usage: node validate.js <build_project.jsx> [aeVersion]
// What it proves: the script runs end to end, every matchName it touches is one the mock knows,
// keyframes/eases/values have valid shapes and ranges, referenced files exist, and every
// expression compiles and evaluates without errors at sample times.
// What it cannot prove: real AE behaviour. The matchName list is maintained by hand.
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const jsxPath = path.resolve(process.argv[2]);
const AEV = parseFloat(process.argv[3] || "24.0");
const issues = [];
const stats = { comps: 0, layers: 0, keys: 0, expressions: 0, exprEvals: 0, effects: 0, footage: 0 };
function fail(msg) { throw new Error(msg); }
function warn(msg) { issues.push(msg); }

// ------------------------------------------------------------------------- enums
const KeyframeInterpolationType = { LINEAR: 6612, BEZIER: 6613, HOLD: 6614 };
const ParagraphJustification = { LEFT_JUSTIFY: 7413, CENTER_JUSTIFY: 7415, RIGHT_JUSTIFY: 7414 };
const BlendingMode = {}; ["NORMAL","MULTIPLY","SCREEN","OVERLAY","ADD","DARKEN","LIGHTEN","COLOR_DODGE","COLOR_BURN","SOFT_LIGHT","HARD_LIGHT","DIFFERENCE","EXCLUSION","HUE","SATURATION","COLOR","LUMINOSITY"].forEach((k, i) => BlendingMode[k] = 5000 + i);
const AutoOrientType = { NO_AUTO_ORIENT: 4212, ALONG_PATH: 4213, CAMERA_OR_POINT_OF_INTEREST: 4214, CHARACTERS_TOWARD_CAMERA: 4215 };
const TrackMatteType = { ALPHA: 5012, ALPHA_INVERTED: 5013, LUMA: 5014, LUMA_INVERTED: 5015, NO_TRACK_MATTE: 5016 };
const MaskMode = { NONE: 6812, ADD: 6813, SUBTRACT: 6814, INTERSECT: 6815 };
const PropertyValueType = { NO_VALUE: 0, ThreeD_SPATIAL: 1, ThreeD: 2, TwoD_SPATIAL: 3, TwoD: 4, OneD: 5, COLOR: 6, CUSTOM_VALUE: 7, MARKER: 8, LAYER_INDEX: 9, MASK_INDEX: 10, SHAPE: 11, TEXT_DOCUMENT: 12 };

class KeyframeEase { constructor(speed, influence) {
  if (!isFinite(speed)) fail("KeyframeEase speed not finite: " + speed);
  if (!(influence >= 0.1 - 1e-9 && influence <= 100 + 1e-9)) fail("KeyframeEase influence out of [0.1,100]: " + influence);
  this.speed = speed; this.influence = influence; } }
class Shape { constructor() { this.vertices = []; this.inTangents = []; this.outTangents = []; this.closed = true; } }
class MarkerValue { constructor(c) { this.comment = c; } }
class TextDocument { constructor(t) { this.text = t; this.font = "ArialMT"; this.fontSize = 36; this.fillColor = [1,1,1]; this.applyFill = true; this.applyStroke = false; this.tracking = 0; this.leading = 0; this.autoLeading = true; this.justification = ParagraphJustification.LEFT_JUSTIFY; }
  resetCharStyle() {} resetParagraphStyle() {} }
class FileM { constructor(p) { this.fsName = path.resolve(p); }
  get exists() { return fs.existsSync(this.fsName); }
  get parent() { return new FileM(path.dirname(this.fsName)); } }
class ImportOptions { constructor(f) { if (!(f instanceof FileM)) fail("ImportOptions needs a File"); this.file = f; } }

// ------------------------------------------------------------------------- properties
function isNumArr(v, n) { return Array.isArray(v) && v.every(x => typeof x === "number" && isFinite(x)) && (n === undefined || n.includes(v.length)); }

class Property {
  constructor(name, spec, owner) {
    this.matchName = name; this.name = name; this.spec = spec; this.owner = owner;
    this.keys = []; this._value = spec.def !== undefined ? spec.def : 0; this._expr = ""; this.propertyType = 6212;
    this.dims = spec.dims || 1;
    this.propertyValueType = spec.kind === "shape" ? PropertyValueType.SHAPE : spec.kind === "textdoc" ? PropertyValueType.TEXT_DOCUMENT :
      spec.kind === "color" ? PropertyValueType.COLOR : spec.spatial ? (this.dims === 3 ? PropertyValueType.ThreeD_SPATIAL : PropertyValueType.TwoD_SPATIAL) :
      this.dims === 1 ? PropertyValueType.OneD : this.dims === 2 ? PropertyValueType.TwoD : PropertyValueType.ThreeD;
    this.dimensionsSeparated = false;
  }
  check(v) {
    const s = this.spec, where = this.path();
    if (s.kind === "shape") { if (!(v instanceof Shape)) fail(where + ": expected Shape");
      const n = v.vertices.length; if (!n || v.inTangents.length !== n || v.outTangents.length !== n) fail(where + ": Shape arrays mismatch");
      [v.vertices, v.inTangents, v.outTangents].forEach(a => a.forEach(p => { if (!isNumArr(p, [2])) fail(where + ": bad vertex " + JSON.stringify(p)); })); return; }
    if (s.kind === "textdoc") { if (!(v instanceof TextDocument)) fail(where + ": expected TextDocument"); return; }
    if (s.kind === "marker") { if (!(v instanceof MarkerValue)) fail(where + ": expected MarkerValue"); return; }
    if (s.kind === "color") { if (!isNumArr(v, [3, 4]) || v.some(x => x < -1e-6 || x > 1 + 1e-6)) fail(where + ": bad color " + JSON.stringify(v)); return; }
    if (this.dims === 1) { if (typeof v !== "number" || !isFinite(v)) fail(where + ": expected number, got " + JSON.stringify(v));
      if (s.min !== undefined && v < s.min - 1e-6) fail(where + ": " + v + " < min " + s.min);
      if (s.max !== undefined && v > s.max + 1e-6) fail(where + ": " + v + " > max " + s.max); return; }
    const ok = s.spatial || s.dims === 3 ? [2, 3] : [this.dims];
    if (!isNumArr(v, ok)) fail(where + ": expected " + ok.join("/") + "-D array, got " + JSON.stringify(v));
  }
  path() { let p = this.matchName, o = this.owner; while (o && o.matchName) { p = o.matchName + " > " + p; o = o.owner; } return p; }
  get value() { return this._value; }
  get numKeys() { return this.keys.length; }
  setValue(v) { if (this.spec.readonly) fail(this.path() + " is read-only"); if (this.keys.length) fail(this.path() + ": setValue on keyframed property"); this.check(v); this._value = v; }
  setValueAtTime(t, v) {
    if (!this.spec.anim && this.spec.anim !== undefined) fail(this.path() + " cannot be keyframed");
    if (!isFinite(t) || t < -1e-6) fail(this.path() + ": bad key time " + t);
    this.check(v);
    const i = this.keys.findIndex(k => Math.abs(k.t - t) < 1e-6);
    const k = { t, v, inT: KeyframeInterpolationType.BEZIER, outT: KeyframeInterpolationType.BEZIER, ie: null, oe: null };
    if (i >= 0) this.keys[i] = k; else { this.keys.push(k); this.keys.sort((a, b) => a.t - b.t); }
    stats.keys++;
  }
  nearestKeyIndex(t) { if (!this.keys.length) fail(this.path() + ": nearestKeyIndex without keys"); let b = 0;
    this.keys.forEach((k, i) => { if (Math.abs(k.t - t) < Math.abs(this.keys[b].t - t)) b = i; }); return b + 1; }
  key(i) { if (i < 1 || i > this.keys.length) fail(this.path() + ": key index " + i); return { time: this.keys[i - 1].t, value: this.keys[i - 1].v }; }
  setInterpolationTypeAtKey(i, a, b) { if (i < 1 || i > this.keys.length) fail(this.path() + ": interp key index " + i);
    const vals = Object.values(KeyframeInterpolationType); if (!vals.includes(a) || !vals.includes(b === undefined ? a : b)) fail(this.path() + ": bad interpolation type");
    this.keys[i - 1].inT = a; this.keys[i - 1].outT = b === undefined ? a : b; }
  setTemporalEaseAtKey(i, inE, outE) { if (i < 1 || i > this.keys.length) fail(this.path() + ": ease key index " + i);
    const want = (this.propertyValueType === PropertyValueType.TwoD_SPATIAL || this.propertyValueType === PropertyValueType.ThreeD_SPATIAL || this.dims === 1 || this.spec.kind === "shape" || this.spec.kind === "color") ? [1] : [this.dims, 2, 3];
    [inE, outE].forEach(a => { if (!Array.isArray(a) || !want.includes(a.length) || !a.every(e => e instanceof KeyframeEase)) fail(this.path() + ": ease array length " + (a && a.length) + ", expected " + want.join("/")); });
    this.keys[i - 1].ie = inE; this.keys[i - 1].oe = outE; }
  set expression(code) {
    if (!this.spec.anim && this.spec.anim !== undefined && this.spec.kind !== "textdoc") fail(this.path() + " cannot take an expression");
    try { new Function(code); } catch (e) { fail(this.path() + ": expression syntax error: " + e.message + "\n" + code.slice(0, 300)); }
    this._expr = code; stats.expressions++; EXPRS.push(this);
  }
  get expression() { return this._expr; }
  valueAtTime(t) { if (!this.keys.length) return this._value; if (t <= this.keys[0].t) return this.keys[0].v;
    const L = this.keys[this.keys.length - 1]; if (t >= L.t) return L.v;
    for (let i = 1; i < this.keys.length; i++) { const a = this.keys[i - 1], b = this.keys[i]; if (t < b.t) { const u = (t - a.t) / (b.t - a.t);
      if (typeof a.v === "number") return a.v + (b.v - a.v) * u; if (Array.isArray(a.v)) return a.v.map((x, j) => x + (b.v[j] - x) * u); return a.v; } } return L.v; }
}

const EXPRS = [];
const ALLCOMPS = [];
// permissive stand-in for AE objects reached through expressions (content(), path, effect()...)
function deep() {
  const f = function () { return deep(); };
  return new Proxy(f, { get(t, k) {
      if (k === Symbol.toPrimitive || k === "valueOf") return () => 0.5;
      if (k === "length") return 2;
      if (k === "toString") return () => "0.5";
      return deep(); }, apply() { return deep(); } });
}
function layerRef(comp, n) {
  if (!comp._layers.find(x => x.name === n)) fail("expression references missing layer '" + n + "' in comp '" + comp.name + "'");
  return deep();
}

// schema: group children (fixed) and addable children
const P1 = (o = {}) => Object.assign({ dims: 1, anim: true }, o);
const P2 = (o = {}) => Object.assign({ dims: 2, anim: true }, o);
const P3 = (o = {}) => Object.assign({ dims: 3, anim: true }, o);
const COL = (o = {}) => Object.assign({ kind: "color", dims: 3, anim: true, def: [1, 1, 1] }, o);
const SHP = { kind: "shape", anim: true };

const GROUPS = {
  transform: { "ADBE Anchor Point": P3({ spatial: true, def: [0, 0, 0] }), "ADBE Position": P3({ spatial: true, def: [0, 0, 0], separable: true }),
    "ADBE Position_0": P1({ sep: true }), "ADBE Position_1": P1({ sep: true }), "ADBE Position_2": P1({ sep: true }),
    "ADBE Scale": P3({ def: [100, 100, 100] }), "ADBE Rotate Z": P1(), "ADBE Rotate X": P1(), "ADBE Rotate Y": P1(),
    "ADBE Opacity": P1({ min: 0, max: 100, def: 100 }) },
  textProps: { "ADBE Text Document": { kind: "textdoc", anim: true }, "ADBE Text Animators": "@textAnimators", "ADBE Text More Options": "@moreOptions", "ADBE Text Path Options": "@pathOptions" },
  moreOptions: { "ADBE Text Anchor Point Option": P1({ anim: false, min: 1, max: 4 }), "ADBE Text Anchor Point Align": P2() },
  pathOptions: { "ADBE Text Path": P1({ anim: false }) },
  textAnimator: { "ADBE Text Animator Properties": "@animProps", "ADBE Text Selectors": "@selectors" },
  rangeSelector: { "ADBE Text Index Start": P1(), "ADBE Text Index End": P1(), "ADBE Text Percent Start": P1(), "ADBE Text Percent End": P1(), "ADBE Text Range Advanced": "@rangeAdv" },
  rangeAdv: { "ADBE Text Range Units": P1({ anim: false, min: 1, max: 2 }), "ADBE Text Range Type2": P1({ anim: false, min: 1, max: 4 }) },
  exprSelector: { "ADBE Text Range Type2": P1({ anim: false, min: 1, max: 4 }), "ADBE Text Expressible Amount": P3() },
  vectorGroup: { "ADBE Vectors Group": "@vectors", "ADBE Vector Transform Group": "@vectorTransform" },
  vectorTransform: { "ADBE Vector Anchor": P2(), "ADBE Vector Position": P2(), "ADBE Vector Scale": P2({ def: [100, 100] }), "ADBE Vector Rotation": P1(), "ADBE Vector Group Opacity": P1({ min: 0, max: 100 }) },
  rect: { "ADBE Vector Rect Size": P2({ def: [100, 100] }), "ADBE Vector Rect Position": P2(), "ADBE Vector Rect Roundness": P1({ min: 0 }) },
  ellipse: { "ADBE Vector Ellipse Size": P2(), "ADBE Vector Ellipse Position": P2() },
  star: { "ADBE Vector Star Type": P1({ anim: false, min: 1, max: 2 }), "ADBE Vector Star Points": P1({ min: 3 }), "ADBE Vector Star Outer Radius": P1({ min: 0 }), "ADBE Vector Star Inner Radius": P1({ min: 0 }), "ADBE Vector Star Rotation": P1() },
  pathShape: { "ADBE Vector Shape": SHP },
  trim: { "ADBE Vector Trim Start": P1({ min: 0, max: 100 }), "ADBE Vector Trim End": P1({ min: 0, max: 100 }), "ADBE Vector Trim Offset": P1(), "ADBE Vector Trim Type": P1({ anim: false, min: 1, max: 2 }) },
  repeater: { "ADBE Vector Repeater Copies": P1({ min: 0 }), "ADBE Vector Repeater Transform": "@repTransform" },
  repTransform: { "ADBE Vector Repeater Position": P2(), "ADBE Vector Repeater Scale": P2() },
  stroke: { "ADBE Vector Stroke Color": COL(), "ADBE Vector Stroke Opacity": P1({ min: 0, max: 100 }), "ADBE Vector Stroke Width": P1({ min: 0 }),
    "ADBE Vector Stroke Line Cap": P1({ anim: false, min: 1, max: 3 }), "ADBE Vector Stroke Line Join": P1({ anim: false, min: 1, max: 3 }), "ADBE Vector Stroke Dashes": "@dashes" },
  fill: { "ADBE Vector Fill Color": COL(), "ADBE Vector Fill Opacity": P1({ min: 0, max: 100 }) },
  maskAtom: { "ADBE Mask Shape": SHP, "ADBE Mask Feather": P2(), "ADBE Mask Opacity": P1() },
  cameraOpts: { "ADBE Camera Zoom": P1({ min: 1 }) },
};
const ADDABLE = {
  textAnimators: { "ADBE Text Animator": "textAnimator" },
  animProps: { "ADBE Text Opacity": P1({ min: 0, max: 100 }), "ADBE Text Position 3D": P3(), "ADBE Text Scale 3D": P3(), "ADBE Text Rotation": P1(),
    "ADBE Text Blur": P2(), "ADBE Text Tracking Amount": P1(), "ADBE Text Fill Color": COL(), "ADBE Text Character Offset": P1() },
  selectors: { "ADBE Text Selector": "rangeSelector", "ADBE Text Expressible Selector": "exprSelector" },
  vectors: { "ADBE Vector Group": "vectorGroup", "ADBE Vector Shape - Rect": "rect", "ADBE Vector Shape - Ellipse": "ellipse", "ADBE Vector Shape - Star": "star",
    "ADBE Vector Shape - Group": "pathShape", "ADBE Vector Filter - Trim": "trim", "ADBE Vector Filter - Repeater": "repeater",
    "ADBE Vector Graphic - Stroke": "stroke", "ADBE Vector Graphic - Fill": "fill" },
  rootVectors: { "ADBE Vector Group": "vectorGroup" },
  dashes: { "ADBE Vector Stroke Dash 1": P1({ min: 0 }), "ADBE Vector Stroke Gap 1": P1({ min: 0 }), "ADBE Vector Stroke Offset": P1() },
  masks: { "ADBE Mask Atom": "maskAtom" },
  effects: { // effect matchName -> params (by index)
    "ADBE Gaussian Blur 2": [P1({ min: 0 }), P1({ anim: false }), P1({ anim: false })],
    "ADBE Drop Shadow": [COL(), P1({ min: 0, max: 255 }), P1(), P1({ min: 0 }), P1({ min: 0 }), P1({ anim: false })],
    "ADBE Glo2": [P1({ anim: false }), P1({ min: 0, max: 100 }), P1({ min: 0 }), P1({ min: 0 }), P1(), P1(), COL(), COL(), P1(), P1()],
    "ADBE Ramp": [P2(), COL(), P2(), COL(), P1({ anim: false, min: 1, max: 2 }), P1(), P1()],
    "ADBE Noise": [P1({ min: 0, max: 100 }), P1({ anim: false }), P1({ anim: false })],
    "CC Vignette": [P1(), P1(), P2(), P1()],
    "ADBE Linear Wipe": [P1({ min: 0, max: 100 }), P1(), P1({ min: 0 })],
    "ADBE Motion Blur": [P1(), P1({ min: 0 })],
    "ADBE Slider Control": [P1()],
    "ADBE Color Control": [COL()],
    "ADBE HUE SATURATION": [P1(), P1(), P1(), P1({ min: -100, max: 100 }), P1(), P1(), P1(), P1(), P1(), P1()],
    "ADBE Brightness & Contrast 2": [P1(), P1({ min: -100, max: 100 }), P1({ anim: false })],
  },
};

class PropertyGroup {
  constructor(name, kind, owner) { this.matchName = name; this.name = name; this.kind = kind; this.owner = owner; this.kids = {}; this.list = []; this.propertyType = 6213; }
  property(n) {
    if (typeof n === "number") { if (n < 1 || n > this.list.length) fail(this.matchName + ".property(" + n + ") out of range (" + this.list.length + ")"); return this.list[n - 1]; }
    if (this.kids[n]) return this.kids[n];
    const named = this.list.find(c => c.name === n); if (named) return named;
    const g = GROUPS[this.kind];
    if (!g || !(n in g)) fail("unknown property '" + n + "' in " + this.matchName + " (" + this.kind + ")");
    const spec = g[n];
    if (n.startsWith("ADBE Position_")) { const pos = this.property("ADBE Position"); if (!pos.dimensionsSeparated) fail(n + " requires dimensionsSeparated"); }
    const c = typeof spec === "string" ? (spec.startsWith("@") ? new PropertyGroup(n, spec.slice(1), this) : null) : new Property(n, spec, this);
    this.kids[n] = c; this.list.push(c); return c;
  }
  addProperty(n) {
    const a = ADDABLE[this.kind]; if (!a || !(n in a)) fail("cannot addProperty('" + n + "') to " + this.matchName + " (" + this.kind + ")");
    const spec = a[n]; let c;
    if (this.kind === "effects") { c = new PropertyGroup(n, "effect", this); c.list = spec.map((s, i) => new Property(n + "-" + String(i + 1).padStart(4, "0"), s, c)); stats.effects++; }
    else if (typeof spec === "string") { c = new PropertyGroup(n, spec, this); if (spec === "maskAtom") c.maskMode = MaskMode.ADD; }
    else c = new Property(n, spec, this);
    this.list.push(c); return c;
  }
  get numProperties() { return this.list.length; }
}

// ------------------------------------------------------------------------- layers / comps
class Layer {
  constructor(comp, type, name) { this.comp = comp; this.type = type; this._name = name || type; this.label = 0; this.enabled = true; this.startTime = 0; this.inPoint = 0; this.outPoint = comp.duration;
    this.threeDLayer = false; this.autoOrient = AutoOrientType.NO_AUTO_ORIENT; this.blendingMode = BlendingMode.NORMAL; this.motionBlur = false; this.collapseTransformation = false; this.adjustmentLayer = false; this.parent = null;
    this.root = new PropertyGroup("layer", "root", null); this.root.layer = this;
    this.groups = { "ADBE Transform Group": new PropertyGroup("ADBE Transform Group", "transform", this.root), "ADBE Effect Parade": new PropertyGroup("ADBE Effect Parade", "effects", this.root),
      "ADBE Mask Parade": new PropertyGroup("ADBE Mask Parade", "masks", this.root) };
    if (type === "text") this.groups["ADBE Text Properties"] = new PropertyGroup("ADBE Text Properties", "textProps", this.root);
    if (type === "shape") this.groups["ADBE Root Vectors Group"] = new PropertyGroup("ADBE Root Vectors Group", "rootVectors", this.root);
    if (type === "camera") { this.groups["ADBE Camera Options Group"] = new PropertyGroup("ADBE Camera Options Group", "cameraOpts", this.root); delete this.groups["ADBE Effect Parade"]; }
    stats.layers++;
    if (type === "precomp") this._tr = new Property("ADBE Time Remapping", P1(), this.root);
    if (AEV >= 23) this.setTrackMatte = (m, t) => { if (!(m instanceof Layer)) fail("setTrackMatte needs a layer"); if (!Object.values(TrackMatteType).includes(t)) fail("bad TrackMatteType " + t); this.matte = m; };
  }
  get name() { return this._name; } set name(v) { if (typeof v !== "string" || !v.length) fail("bad layer name"); if (v.length > 255) warn("layer name > 255 chars"); this._name = v; }
  set label(v) { if (!(v >= 0 && v <= 16)) fail("label out of range: " + v); this._label = v; } get label() { return this._label; }
  property(n) {
    if (n === "ADBE Time Remapping") { if (!this._tr) fail("time remap only on precomp/footage layers"); if (!this.timeRemapEnabled) fail("enable timeRemap first"); return this._tr; }
    if (!this.groups[n]) fail("layer '" + this._name + "' (" + this.type + ") has no '" + n + "'"); return this.groups[n];
  }
  moveBefore(l) { this.comp._move(this, l, 0); } moveAfter(l) { this.comp._move(this, l, 1); } moveToBeginning() { this.comp._move(this, null, -1); }
  set trackMatteType(v) { if (!Object.values(TrackMatteType).includes(v)) fail("bad trackMatteType"); this._tmt = v; }
}

class Item { constructor(name) { this.name = name; this.parentFolder = null; } }
class CompItem extends Item {
  constructor(name, w, h, par, dur, fps) { super(name);
    if (!(w >= 4 && w <= 30000 && h >= 4 && h <= 30000)) fail("comp size out of range: " + w + "x" + h);
    if (!(dur > 0 && dur <= 10800)) fail("comp duration invalid: " + dur);
    if (!(fps > 0 && fps <= 999)) fail("comp fps invalid: " + fps);
    this.width = w; this.height = h; this.pixelAspect = par; this.duration = dur; this.frameRate = fps; this._layers = []; this.bgColor = [0, 0, 0]; this.motionBlur = false; this.shutterAngle = 180;
    this.markerProperty = new Property("ADBE Marker", { kind: "marker", anim: true }, null);
    const self = this;
    this.layers = {
      addText(t) { if (typeof t !== "string") fail("addText needs a string"); const l = new Layer(self, "text"); const td = l.groups["ADBE Text Properties"].property("ADBE Text Document"); td._value = new TextDocument(t); l._name = t.slice(0, 30) || "Text"; return self._push(l); },
      addShape() { return self._push(new Layer(self, "shape", "Shape Layer")); },
      addSolid(c, n, w, h, par, d) { if (!isNumArr(c, [3])) fail("addSolid color"); if (!(w >= 1 && h >= 1)) fail("addSolid size"); return self._push(new Layer(self, "solid", n)); },
      addNull(d) { return self._push(new Layer(self, "null", "Null")); },
      addCamera(n, c) { if (!isNumArr(c, [2])) fail("addCamera center"); return self._push(new Layer(self, "camera", n)); },
      add(item) { if (!(item instanceof Item)) fail("layers.add needs an item"); if (item === self) fail("comp cannot contain itself"); return self._push(new Layer(self, item instanceof CompItem ? "precomp" : "footage", item.name)); },
    };
    stats.comps++;
    ALLCOMPS.push(this);
  }
  _push(l) { this._layers.unshift(l); return l; }
  _move(l, ref, mode) { const a = this._layers; a.splice(a.indexOf(l), 1); if (mode < 0) a.unshift(l); else { const i = a.indexOf(ref); if (i < 0) fail("move reference not in comp"); a.splice(i + mode, 0, l); } }
  layer(n) { const l = this._layers.find(x => x.name === n); if (!l) fail("comp '" + this.name + "' has no layer '" + n + "'"); return l; }
  get numLayers() { return this._layers.length; }
  openInViewer() {}
}
class FolderItem extends Item {}
class FootageItem extends Item {}

const project = {
  items: { addFolder(n) { return new FolderItem(n); }, addComp(n, w, h, par, d, f) { return new CompItem(n, w, h, par, d, f); } },
  importFile(opts) { if (!(opts instanceof ImportOptions)) fail("importFile needs ImportOptions"); if (!opts.file.exists) fail("import: file missing " + opts.file.fsName); stats.footage++; return new FootageItem(path.basename(opts.file.fsName)); },
};
const appM = { version: AEV.toFixed(1) + ".0x1", project, beginUndoGroup() {}, endUndoGroup() {}, newProject() { return project; } };
if (AEV >= 24) appM.fonts = { getFontsByPostScriptName(n) { return [{ postScriptName: n }]; } };

const sandbox = { app: appM, $: { fileName: jsxPath, writeln: (s) => {} }, File: FileM, ImportOptions, Shape, KeyframeEase, MarkerValue, TextDocument,
  KeyframeInterpolationType, ParagraphJustification, BlendingMode, TrackMatteType, MaskMode, PropertyValueType, AutoOrientType,
  alert: (m) => { sandbox.__alerts.push(String(m)); }, confirm: () => true, __alerts: [] };
vm.createContext(sandbox);

// ------------------------------------------------------------------------- expression evaluation
function evalExpressions() {
  const helpers = {
    add: (a, b) => Array.isArray(a) ? a.map((x, i) => x + b[i]) : a + b, sub: (a, b) => Array.isArray(a) ? a.map((x, i) => x - b[i]) : a - b,
    mul: (a, k) => Array.isArray(a) ? a.map(x => x * k) : a * k, clamp: (v, a, b) => Math.max(a, Math.min(b, v)),
    seedRandom: () => {}, random: (a, b) => (b === undefined ? (a || 1) * 0.5 : a + (b - a) * 0.5), wiggle: function (f, a) { return this.value; },
  };
  EXPRS.forEach(p => {
    const lay = (() => { let o = p.owner; while (o && !o.layer) o = o.owner; return o ? o.layer : null; })();
    const comp = lay ? lay.comp : null;
    const dur = comp ? comp.duration : 10;
    [0, dur * 0.25, dur * 0.5, dur * 0.9].forEach(t => {
      const ctx = Object.assign({}, helpers, Math, {
        Math, time: t, value: p.valueAtTime(t), textIndex: 3, textTotal: 10, inPoint: 0, numKeys: p.keys.length,
        key: (i) => p.key(i), thisComp: { layer: (n) => layerRef(comp, n) },
        comp: (n) => { const c = ALLCOMPS.find(x => x.name === n); if (!c) fail("expression references missing comp '" + n + "'"); return { layer: (m) => layerRef(c, m) }; },
        transform: { xPosition: 0, yPosition: 0, position: { velocity: [120, -40] } },
        degreesToRadians: (d) => d * Math.PI / 180, radiansToDegrees: (r) => r * 180 / Math.PI,
        length: (a, b) => Array.isArray(a) ? Math.hypot(...a) : Math.abs(a - (b || 0)),
        effect: () => () => 1, thisLayer: {}, wiggle: () => p.valueAtTime(t),
      });
      ctx.value = p.spec.kind === "textdoc" ? "text" : ctx.value;
      try {
        const fn = new Function("ctx", "with (ctx) { return eval(" + JSON.stringify(p._expr) + "); }");
        const r = fn(ctx);
        stats.exprEvals++;
        if (p.spec.kind === "textdoc") { if (typeof r !== "string") fail("source text expression must return a string: " + p.path()); }
        else if (p.matchName === "ADBE Text Expressible Amount") { if (!isNumArr(r, [3])) fail("expressible amount must return [a,a,a]: " + JSON.stringify(r)); }
        else if (typeof r === "function") { /* value derived from a referenced AE object (stubbed) */ }
        else if (typeof r === "number") { if (!isFinite(r)) fail("expression returned " + r + " at " + p.path()); }
        else if (Array.isArray(r)) { if (!r.every(x => isFinite(x))) fail("expression returned non-finite array at " + p.path()); }
        else if (r === undefined) fail("expression returned undefined at " + p.path());
      } catch (e) { fail("expression runtime error at " + p.path() + " t=" + t.toFixed(2) + ": " + e.message); }
    });
  });
}

try {
  const code = fs.readFileSync(jsxPath, "utf8");
  vm.runInContext(code, sandbox, { filename: path.basename(jsxPath) });
  evalExpressions();
  const fatal = sandbox.__alerts.filter(a => a.indexOf("build error") >= 0);
  if (fatal.length) throw new Error(fatal.join("\n"));
  console.log("[mock-ae] OK for AE " + AEV + ": " + JSON.stringify(stats));
  sandbox.__alerts.forEach(a => console.log("[mock-ae] alert: " + a.replace(/\n/g, " | ").slice(0, 600)));
  issues.forEach(i => console.log("[mock-ae] warn: " + i));
  process.exit(0);
} catch (e) {
  console.log("[mock-ae] FAIL: " + e.message);
  if (e.stack) console.log(e.stack.split("\n").slice(0, 6).join("\n"));
  process.exit(1);
}
