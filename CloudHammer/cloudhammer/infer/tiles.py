from __future__ import annotations

from dataclasses import dataclass

from cloudhammer.contracts.detections import xyxy_to_xywh


@dataclass(frozen=True)
class Tile:
    index: int
    x: int
    y: int
    width: int
    height: int

    @property
    def bbox(self) -> tuple[int, int, int, int]:
        return (self.x, self.y, self.width, self.height)


def _starts(length: int, tile_size: int, stride: int) -> list[int]:
    if length <= tile_size:
        return [0]
    starts = list(range(0, max(1, length - tile_size + 1), stride))
    last = length - tile_size
    if starts[-1] != last:
        starts.append(last)
    return starts


def generate_tiles(width: int, height: int, tile_size: int, overlap: int) -> list[Tile]:
    if tile_size <= 0:
        raise ValueError("tile_size must be positive")
    if overlap < 0 or overlap >= tile_size:
        raise ValueError("tile_overlap must be >= 0 and < tile_size")
    stride = tile_size - overlap
    tiles: list[Tile] = []
    idx = 0
    for y in _starts(height, tile_size, stride):
        for x in _starts(width, tile_size, stride):
            tiles.append(Tile(index=idx, x=x, y=y, width=min(tile_size, width - x), height=min(tile_size, height - y)))
            idx += 1
    return tiles


def tile_xyxy_to_page_xywh(tile: Tile, box_xyxy: tuple[float, float, float, float]) -> list[float]:
    x0, y0, x1, y1 = box_xyxy
    return xyxy_to_xywh((x0 + tile.x, y0 + tile.y, x1 + tile.x, y1 + tile.y))
