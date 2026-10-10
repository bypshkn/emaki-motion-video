"""Repeaters, grids and layout helpers. All produce ordinary child layers, so they render
in Python and export to After Effects as regular layers."""
import math
import random

from ..core import Group, Layer


class Repeater(Group):
    """`count` copies from factory(i) with cumulative offset/rotation/scale and opacity ramp.
    Copy i is time-shifted by i*stagger (its animations start later)."""
    kind = "repeater"

    def __init__(self, factory, count, offset=(0, 0), rotate=0.0, scale=1.0, opacity_end=1.0,
                 stagger=0.0, **kw):
        super().__init__(**kw)
        for i in range(count):
            lay = factory(i)
            x, y = lay.position.rest()
            lay.position.set((x + offset[0] * i, y + offset[1] * i))
            lay.rotation.set(lay.rotation.rest() + rotate * i)
            s = scale ** i
            sx, sy = lay.scale.rest()
            lay.scale.set((sx * s, sy * s))
            if count > 1 and opacity_end != 1.0:
                lay.opacity.set(lay.opacity.rest() * (1 + (opacity_end - 1) * i / (count - 1)))
            self.add(Group(lay, offset=i * stagger, name=f"{self.name} #{i + 1}") if stagger else lay)


def order_delays(rows, cols, order="row", step=0.05, seed=3):
    """Delay per (i, j) for staggered grids: row|col|diagonal|center|edges|random."""
    d = {}
    cx, cy = (cols - 1) / 2, (rows - 1) / 2
    cells = [(i, j) for i in range(rows) for j in range(cols)]
    if order == "random":
        r = random.Random(seed)
        perm = cells[:]
        r.shuffle(perm)
        return {c: k * step for k, c in enumerate(perm)}
    for i, j in cells:
        if order == "row":
            k = i * cols + j
        elif order == "col":
            k = j * rows + i
        elif order == "diagonal":
            k = i + j
        elif order == "center":
            k = math.hypot(i - cy, j - cx)
        elif order == "edges":
            k = max(cx, cy) - math.hypot(i - cy, j - cx)
        else:
            raise ValueError(order)
        d[(i, j)] = k * step
    return d


class Grid(Group):
    """rows x cols cells; factory(i, j, k, delay, (x, y)) -> Layer placed at the cell center."""
    kind = "grid"

    def __init__(self, rows, cols, cell, factory, gap=(0, 0), order="row", step=0.05, origin=(0, 0), **kw):
        super().__init__(**kw)
        cw, ch = cell
        delays = order_delays(rows, cols, order, step)
        k = 0
        for i in range(rows):
            for j in range(cols):
                x = origin[0] + j * (cw + gap[0]) + cw / 2
                y = origin[1] + i * (ch + gap[1]) + ch / 2
                lay = factory(i, j, k, delays[(i, j)], (x, y))
                if lay is not None:
                    if lay.position.rest() == (0.0, 0.0) and not lay.position.keys:
                        lay.position.set((x, y))
                    self.add(lay)
                k += 1


def vstack(layers, x, y, gap=0.0, align="left"):
    """Place layers top-to-bottom starting at (x, y). Uses each layer's local bounds.
    Returns the y after the last layer."""
    cy = y
    for l in layers:
        b = l.local_bounds(0.0) or (0, 0, 0, 0)
        ax, ay = l.anchor.rest()
        top = b[1] - ay
        if hasattr(l, "L"):        # text: stack by cap-top/baseline box
            top = -ay
            h = l.L.height
        else:
            h = b[3] - b[1]
        w = b[2] - b[0]
        px = x
        if align == "center":
            px = x - (w / 2 + b[0] - ax)
        l.position.set((px, cy - top))
        cy += h + gap
    return cy


def hstack(layers, x, y, gap=0.0):
    cx = x
    for l in layers:
        b = l.local_bounds(0.0) or (0, 0, 0, 0)
        ax, ay = l.anchor.rest()
        l.position.set((cx - (b[0] - ax), y))
        cx += (b[2] - b[0]) + gap
    return cx
