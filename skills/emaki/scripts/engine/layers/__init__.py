"""Layer primitives. Project-specific modules in <project>/engine_ext/ are loaded by
engine.load_extensions() and can register new layers/fx with the same interface."""
from .text import Text, TextOnPath, DynamicText, parse_markup, plain, layout_text, SCRAMBLE_GLYPHS
from .fill import Fill, Solid, Linear, Radial, Conic, Noise, Pattern, Background
from .shape import (Shape, Rect, Ellipse, Polygon, Star, Line, Arc, PathShape, Morph, svg_path,
                    polyline_path, trim_path, svg_shapes, to_path)
from .repeat import Repeater, Grid, vstack, hstack, order_delays
from .particles import Particles
from .image import Image, Svg
from .data import Counter, BarChart, LineChart, Donut, load_csv, load_json, nice_max, fmt_number
from .ui import Card, Button, Chip, Window, Phone, Cursor, Toggle, Input, Toast, Avatar, Icon, ICONS
from .kinetic import Comet, GridPlane, Wire3D, Waveform, KineticWords, Flash
from .shape import path_point, glow_dot
from .light import KeyLight, Glass
