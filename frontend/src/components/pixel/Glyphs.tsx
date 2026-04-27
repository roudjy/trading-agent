/**
 * Pixel-art glyphs rendered as inline SVG.
 * Ported from the Claude Design handoff (`project/components/glyphs.jsx`)
 * — re-typed for TS, no `window.QRE_GLYPHS` global. Geometry is original
 * pixel composition; no copyrighted sprites.
 */

import type { CSSProperties, ReactElement } from "react";

interface PixelSVGProps {
  size?: number;
  grid?: number;
  className?: string;
  style?: CSSProperties;
  children?: ReactElement[] | ReactElement;
}

function PixelSVG({ size = 16, grid = 16, children, className = "", style }: PixelSVGProps) {
  return (
    <svg
      className={`glyph ${className}`.trim()}
      width={size}
      height={size}
      viewBox={`0 0 ${grid} ${grid}`}
      style={{ shapeRendering: "crispEdges", ...style }}
      aria-hidden
    >
      {children}
    </svg>
  );
}

type Palette = Record<string, string>;

function pixels(map: string, palette: Palette): ReactElement[] {
  const rows = map.trim().split("\n").map((r) => r.trim());
  const cells: ReactElement[] = [];
  rows.forEach((row, y) => {
    [...row].forEach((ch, x) => {
      if (ch === "." || ch === " ") return;
      const fill = palette[ch] ?? "currentColor";
      cells.push(<rect key={`${x}-${y}`} x={x} y={y} width={1} height={1} fill={fill} />);
    });
  });
  return cells;
}

interface GlyphProps {
  size?: number;
}

export const Coin = ({ size = 16 }: GlyphProps) => (
  <PixelSVG size={size} grid={8}>
    {pixels(
      `..xxxx..
       .xyyyyx.
       xy.yy.yx
       xy.yy.yx
       xy.yy.yx
       xy.yy.yx
       .xyyyyx.
       ..xxxx..`,
      { x: "var(--coin-dark)", y: "var(--coin)" }
    )}
  </PixelSVG>
);

export const Block = ({ size = 16 }: GlyphProps) => (
  <PixelSVG size={size} grid={8}>
    {pixels(
      `bbbbbbbb
       bccccccb
       bcddddcb
       bcd..dcb
       bcd..dcb
       bcddddcb
       bccccccb
       bbbbbbbb`,
      { b: "var(--ink)", c: "var(--coin)", d: "var(--coin-dark)" }
    )}
  </PixelSVG>
);

export const Brick = ({ size = 16 }: GlyphProps) => (
  <PixelSVG size={size} grid={8}>
    {pixels(
      `rrrkrrrr
       rrrkrrrr
       rrrkrrrr
       kkkkkkkk
       rrrrrkrr
       rrrrrkrr
       rrrrrkrr
       kkkkkkkk`,
      { r: "var(--brick)", k: "var(--brick-dark)" }
    )}
  </PixelSVG>
);

export const Pipe = ({ size = 16 }: GlyphProps) => (
  <PixelSVG size={size} grid={8}>
    {pixels(
      `kggggggk
       gghhhhgg
       gghhhhgg
       kkkkkkkk
       .gghhgg.
       .gghhgg.
       .gghhgg.
       .gghhgg.`,
      { g: "var(--grass)", h: "var(--grass-dark)", k: "var(--ink)" }
    )}
  </PixelSVG>
);

export const Flag = ({ size = 16 }: GlyphProps) => (
  <PixelSVG size={size} grid={8}>
    {pixels(
      `.k......
       .kffff..
       .kfffff.
       .kffff..
       .kfff...
       .k......
       .k......
       .k......`,
      { k: "var(--ink)", f: "var(--brick)" }
    )}
  </PixelSVG>
);

export const Heart = ({ size = 16 }: GlyphProps) => (
  <PixelSVG size={size} grid={8}>
    {pixels(
      `.rr..rr.
       rrrrrrrr
       rrrrrrrr
       rrrrrrrr
       .rrrrrr.
       ..rrrr..
       ...rr...
       ........`,
      { r: "var(--brick)" }
    )}
  </PixelSVG>
);

export const Star = ({ size = 16 }: GlyphProps) => (
  <PixelSVG size={size} grid={8}>
    {pixels(
      `...kk...
       ...yy...
       .kyyyyk.
       yyyyyyyy
       .yyyyyy.
       .yy..yy.
       .y....y.
       ........`,
      { y: "var(--coin)", k: "var(--coin-dark)" }
    )}
  </PixelSVG>
);

export const Chip = ({ size = 16 }: GlyphProps) => (
  <PixelSVG size={size} grid={8}>
    {pixels(
      `.kkkkkk.
       kssssssk
       ksiiiisk
       ksi..isk
       ksi..isk
       ksiiiisk
       kssssssk
       .kkkkkk.`,
      { k: "var(--ink)", s: "var(--info)", i: "var(--coin)" }
    )}
  </PixelSVG>
);

export const Cloud = ({ size = 16 }: GlyphProps) => (
  <PixelSVG size={size} grid={16}>
    {pixels(
      `................
       ................
       .....wwww.......
       ....wwwwww......
       ...wwwwwwww.....
       ..wwwwwwwwww....
       .wwwwwwwwwwww...
       .wwwwwwwwwwwww..
       .wwwwwwwwwwwww..
       ..wwwwwwwwwww...
       ................
       ................
       ................
       ................
       ................
       ................`,
      { w: "var(--panel)" }
    )}
  </PixelSVG>
);

export const Skull = ({ size = 16 }: GlyphProps) => (
  <PixelSVG size={size} grid={8}>
    {pixels(
      `.kkkkkk.
       kwwwwwwk
       kw.kk.wk
       kwwkkwwk
       .kwwwwk.
       ..k.k.k.
       .k.k.k..
       ........`,
      { k: "var(--ink)", w: "var(--panel)" }
    )}
  </PixelSVG>
);

export const Check = ({ size = 16 }: GlyphProps) => (
  <PixelSVG size={size} grid={8}>
    {pixels(
      `.......g
       ......gg
       g....gg.
       gg..gg..
       .gggg...
       ..gg....
       ........
       ........`,
      { g: "var(--grass)" }
    )}
  </PixelSVG>
);

export const XMark = ({ size = 16 }: GlyphProps) => (
  <PixelSVG size={size} grid={8}>
    {pixels(
      `rr....rr
       rrr..rrr
       .rrrrrr.
       ..rrrr..
       ..rrrr..
       .rrrrrr.
       rrr..rrr
       rr....rr`,
      { r: "var(--brick)" }
    )}
  </PixelSVG>
);

export const Warn = ({ size = 16 }: GlyphProps) => (
  <PixelSVG size={size} grid={8}>
    {pixels(
      `...kk...
       ..kyyk..
       ..kyyk..
       .kyykyk.
       .kyykyk.
       kyyyyyyk
       kyyykyyk
       kkkkkkkk`,
      { k: "var(--ink)", y: "var(--coin)" }
    )}
  </PixelSVG>
);

interface DotProps {
  color?: string;
  size?: number;
}

export const Dot = ({ color = "var(--grass)", size = 10 }: DotProps) => (
  <span
    className="glyph"
    style={{
      width: size,
      height: size,
      display: "inline-block",
      background: color,
      boxShadow:
        "0 -2px 0 0 var(--ink), 0 2px 0 0 var(--ink), -2px 0 0 0 var(--ink), 2px 0 0 0 var(--ink)",
    }}
  />
);

interface ArrowProps {
  size?: number;
  dir?: "right" | "down";
}

export const Arrow = ({ size = 12, dir = "right" }: ArrowProps) => {
  const map: Record<string, string> = {
    right: `.k......
            .kk.....
            .kkk....
            .kkkk...
            .kkkk...
            .kkk....
            .kk.....
            .k......`,
    down: `........
           ........
           kkkkkkkk
           .kkkkkk.
           ..kkkk..
           ...kk...
           ........
           ........`,
  };
  return (
    <PixelSVG size={size} grid={8}>
      {pixels(map[dir], { k: "currentColor" })}
    </PixelSVG>
  );
};

export const Bars = ({ size = 14 }: GlyphProps) => (
  <PixelSVG size={size} grid={8}>
    {pixels(
      `kkkkkkkk
       ........
       kkkkkk..
       ........
       kkkkkkkk
       ........
       kkkk....
       ........`,
      { k: "currentColor" }
    )}
  </PixelSVG>
);
