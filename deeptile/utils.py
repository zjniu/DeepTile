import numpy as np


def calculate_tiling(axis_size, tile_size, overlap_size):

    tiling = (axis_size - overlap_size) / (tile_size - overlap_size)
    tiling = np.ceil(tiling).astype(int)

    return tiling


def calculate_overlap_size(tile_size, overlap):

    overlap_size = tile_size * overlap
    overlap_size = np.rint(overlap_size).astype(int)

    return overlap_size


def calculate_indices_1d(axis_size, tile_size, overlap):

    overlap_size = calculate_overlap_size(tile_size, overlap)
    tiling = calculate_tiling(axis_size, tile_size, overlap_size)

    li = np.arange(tiling) * (tile_size - overlap_size)
    ri = np.append(li[:-1] + tile_size, axis_size)
    tile_indices = np.stack((li, ri), axis=1)

    border_indices = np.arange(1, tiling) * (tile_size - overlap_size) + round(0.5 * overlap_size)
    border_indices = np.hstack([0, border_indices, axis_size])

    return tiling, tile_indices, border_indices


def calculate_indices(image_shape, tile_size, overlap):

    v_tiling, v_tile_indices, v_border_indices = calculate_indices_1d(image_shape[-2], tile_size[0], overlap[0])
    h_tiling, h_tile_indices, h_border_indices = calculate_indices_1d(image_shape[-1], tile_size[1], overlap[1])

    tiling = (v_tiling, h_tiling)
    tile_indices = (v_tile_indices, h_tile_indices)
    border_indices = (v_border_indices, h_border_indices)

    return tiling, tile_indices, border_indices


def get_nonempty_indices(tiles):

    nonempty_indices = []

    for index, tile in np.ndenumerate(tiles):
        if tile is not None:
            nonempty_indices.append(index)

    nonempty_indices = tuple(nonempty_indices)

    return nonempty_indices


def calculate_scaled_indices(tiles, rounding=True):

    profile = tiles.profile
    tile_size = tiles[profile.nonempty_indices[0]].shape[-2:]
    profile_tile_size = profile.tile_size
    profile_image_shape = profile.dt.image_shape
    scales = (tile_size[0] / profile_tile_size[0], tile_size[1] / profile_tile_size[1])
    image_shape = (round(profile_image_shape[-2] * scales[0]), round(profile_image_shape[-1] * scales[1]))
    scales = (image_shape[0] / profile_image_shape[-2], image_shape[1] / profile_image_shape[-1])

    profile_tile_indices = profile.tile_indices
    profile_border_indices = profile.border_indices
    tile_indices = (profile_tile_indices[0] * scales[0], profile_tile_indices[1] * scales[1])
    border_indices = (profile_border_indices[0] * scales[0], profile_border_indices[1] * scales[1])

    if rounding:
        tile_indices = (np.rint(tile_indices[0]).astype(int), np.rint(tile_indices[1]).astype(int))
        border_indices = (np.rint(border_indices[0]).astype(int), np.rint(border_indices[1]).astype(int))

    return image_shape, tile_indices, border_indices


def calculate_stitch_indices(profile, tile_indices, border_indices):

    stitch_indices = {}

    for n_i, n_j in profile.nonempty_indices:

        i_image = border_indices[0][n_i:n_i + 2]
        j_image = border_indices[1][n_j:n_j + 2]
        i = i_image - tile_indices[0][n_i, 0]
        j = j_image - tile_indices[1][n_j, 0]
        stitch_indices[(n_i, n_j)] = (i_image, j_image, i, j)

    return stitch_indices


def axis_slice(ary, axis, start, end, step=1):

    return ary[(slice(None),) * (axis % ary.ndim) + (slice(start, end, step),)]


def array_split(ary, indices, axis):

    sub_arys = [axis_slice(ary, axis, *i) for i in indices]

    return sub_arys


def array_split_2d(ary, indices):

    sub_arys = array_split(ary, indices[0], -2)
    sub_arys = [array_split(sub_ary, indices[1], -1) for sub_ary in sub_arys]

    return sub_arys


def array_pad(ary, padding, axis=0):

    pad_width = [(0, 0)] * ary.ndim
    pad_width[axis] = (0, padding)

    return np.pad(ary, pad_width)


def cast_list_to_array(lst):

    ary = np.empty(shape=(len(lst), len(lst[0])), dtype=object)

    for i, sublst in enumerate(lst):
        for j, subary in enumerate(sublst):
            ary[i, j] = subary

    return ary


def pad_tiles(tiles, tile_size, tile_indices):

    tile_padding = (tile_size[0] - (tile_indices[0][-1, 1] - tile_indices[0][-1, 0]),
                    tile_size[1] - (tile_indices[1][-1, 1] - tile_indices[1][-1, 0]))

    if tile_padding[0] > 0:
        for i, tile in enumerate(tiles[-1]):
            tiles[-1, i] = array_pad(tile, tile_padding[0], -2)

    if tile_padding[1] > 0:
        for i, tile in enumerate(tiles[:, -1]):
            tiles[i, -1] = array_pad(tile, tile_padding[1], -1)

    return tiles


def update_tiles(tiles, index, tile, batch_axis, output_type):

    if output_type == 'tiled_image':

        if batch_axis is None:
            tiles[index] = tile
        else:
            current_tile = tiles[index]
            if isinstance(current_tile, np.ndarray):
                tiles[index] = np.concatenate((current_tile, np.expand_dims(tile, batch_axis)), batch_axis)
            else:
                tiles[index] = np.expand_dims(tile, batch_axis)

    if output_type == 'tiled_coords':

        current_tile = tiles[index]
        if isinstance(current_tile, np.ndarray):
            new_tile = np.empty((1, ), dtype=object)
            new_tile[0] = tile
            tiles[index] = np.concatenate((current_tile, new_tile), 0)
        else:
            new_tile = np.empty((1, ), dtype=object)
            new_tile[0] = tile
            tiles[index] = new_tile

    return tiles
