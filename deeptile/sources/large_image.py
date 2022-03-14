import dask.array as da
import numpy as np
from dask import delayed
from deeptile import utils


def parse(image, image_shape, tiling, overlap, slices):

    tile_size = utils.calculate_tile_size(np.array(image_shape), np.array(tiling), np.array(overlap))
    overlap_size = utils.calculate_overlap_size(tile_size, np.array(overlap))
    tile_size = np.ceil(tile_size)
    overlap_size = np.floor(overlap_size)

    tiles = np.empty(shape=tiling, dtype=object)
    gys = []
    gxs = []
    heights = []
    widths = []

    tile_iterator = image.tileIterator(frame=slices,
                                       tile_size=dict(height=tile_size[0], width=tile_size[1]),
                                       tile_overlap=dict(y=overlap_size[0], x=overlap_size[1]))
    lazy_imread = delayed(imread)
    for tile in tile_iterator:
        delayed_reader = lazy_imread(tile)
        shape = (tile['height'], tile['width'])
        tiles[tile['level_y'], tile['level_x']] = da.from_delayed(delayed_reader, shape=shape, dtype=object)
        gys.append(tile['gy'])
        gxs.append(tile['gx'])
        heights.append(tile['height'])
        widths.append(tile['width'])

    gys = gys[::tiling[1]]
    gxs = gxs[:tiling[1]]
    heights = heights[::tiling[1]]
    widths = widths[:tiling[1]]

    v_tile_indices = np.cumsum((gys, heights), axis=0).T
    h_tile_indices = np.cumsum((gxs, widths), axis=0).T
    tile_indices = (v_tile_indices, h_tile_indices)

    v_border_indices = np.mean(v_tile_indices.ravel()[1:-1].reshape(-1, 2), axis=1)
    v_border_indices = np.rint(v_border_indices).astype(int)
    v_border_indices = np.concatenate(([0], v_border_indices, [image_shape[0]]))
    h_border_indices = np.mean(h_tile_indices.ravel()[1:-1].reshape(-1, 2), axis=1)
    h_border_indices = np.rint(h_border_indices).astype(int)
    h_border_indices = np.concatenate(([0], h_border_indices, [image_shape[1]]))
    border_indices = (v_border_indices, h_border_indices)

    return tiles, tile_indices, border_indices


def imread(tile_dict):

    tile = tile_dict['tile'][:, :, 0]
    tile_dict.release()

    return tile
