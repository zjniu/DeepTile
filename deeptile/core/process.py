from collections.abc import Iterable
from deeptile.core import trees, utils
from deeptile.core.data import Output, Tiled
from functools import partial
import numpy as np


def process_vectorized(func, batch_axis, pad_final_batch, batch_size,
                       args, kwargs, arg_indices, kwarg_indices,
                       job, profile, processed_istree, processed_indices, processed_tiles,
                       batch_indices):

    """ Process tiles using a vectorized function.

    Parameters
    ----------
        func : Callable
            Callable for use in tile processing.
        batch_axis : bool
            Whether to use the first axis to create batches.
        pad_final_batch : bool
            Whether to pad the final batch to the specified ``batch_size``. If ``func_process`` does not support
            batching, this value is ignored.
        batch_size : int
            Number of tiles in each batch. If ``func`` is not vectorized, this value is ignored.
        args : tuple
            Arguments for ``func``.
        kwargs : dict
            Keyword arguments for ``func``.
        arg_indices : list of tuple
            Leaf indices for ``args``.
        kwarg_indices : list of tuple
            Leaf indices for ``kwargs``.
        job : Job
            Job associated with this processing step.
        profile : Profile
            Profile of the input tiles.
        processed_istree : bool
            Whether ``processed_tiles`` is a tree.
        processed_indices : list of tuple
            Leaf indices for ``processed_tiles``.
        processed_tiles
            Array of tiles processed with ``func``.
        batch_indices : tuple of numpy.ndarray
            Batch indices of tiles.

    Returns
    -------
        processed_istree : bool
            Whether ``processed_tiles`` is a tree.
        processed_indices : list of tuple
            Leaf indices for ``processed_tiles``.
        processed_tiles
            Array of tiles processed with ``func``.
    """

    batch_args, batch_kwargs = get_arguments(pad_final_batch, batch_size,
                                             args, kwargs, arg_indices, kwarg_indices, batch_indices)
    processed_batch_tiles = func(*batch_args, **batch_kwargs)

    processed_istree, processed_indices, processed_tiles = \
        initialize_tree(processed_batch_tiles, job, profile.tiling,
                        processed_istree, processed_indices, processed_tiles)

    processed_batch_tiles = trees.tree_apply(processed_batch_tiles, processed_indices, strip_output_wrapper)

    for i_batch, index in enumerate(zip(*batch_indices)):

        processed_tile = trees.tree_apply(processed_batch_tiles, processed_indices, lambda ts: ts[i_batch])

        if processed_istree:
            for processed_index in processed_indices:
                update_tiles(trees.tree_index(processed_tiles, processed_index),
                             trees.tree_index(processed_tile, processed_index),
                             tuple(index[:2]), batch_axis)
        else:
            update_tiles(processed_tiles, processed_tile, tuple(index[:2]), batch_axis)

    return processed_istree, processed_indices, processed_tiles


def process_single(func, batch_axis,
                   args, kwargs, arg_indices, kwarg_indices,
                   job, profile, processed_istree, processed_indices, processed_tiles,
                   index):

    """ Process tiles using a function.

    Parameters
    ----------
        func : Callable
            Callable for use in tile processing.
        batch_axis : bool
            Whether to use the first axis to create batches.
        args : tuple
            Arguments for ``func``.
        kwargs : dict
            Keyword arguments for ``func``.
        arg_indices : list of tuple
            Leaf indices for ``args``.
        kwarg_indices : list of tuple
            Leaf indices for ``kwargs``.
        job : Job
            Job associated with this processing step.
        profile : Profile
            Profile of the input tiles.
        processed_istree : bool
            Whether ``processed_tiles`` is a tree.
        processed_indices : list of tuple
            Leaf indices for ``processed_tiles``.
        processed_tiles
            Array of tiles processed with ``func``.
        index : tuple of int
            Index of a tile.

    Returns
    -------
        processed_istree : bool
            Whether ``processed_tiles`` is a tree.
        processed_indices : list of tuple
            Leaf indices for ``processed_tiles``.
        processed_tiles
            Array of tiles processed with ``func``.
    """

    single_args, single_kwargs = get_arguments(False, 1, args, kwargs, arg_indices, kwarg_indices, index)
    processed_tile = func(*single_args, **single_kwargs)

    processed_istree, processed_indices, processed_tiles = \
        initialize_tree(processed_tile, job, profile.tiling, processed_istree, processed_indices, processed_tiles)

    processed_tile = trees.tree_apply(processed_tile, processed_indices, strip_output_wrapper)

    if processed_istree:
        for processed_index in processed_indices:
            update_tiles(trees.tree_index(processed_tiles, processed_index),
                         trees.tree_index(processed_tile, processed_index),
                         tuple(index[:2]), batch_axis)
    else:
        update_tiles(processed_tiles, processed_tile, tuple(index[:2]), batch_axis)

    return processed_istree, processed_indices, processed_tiles


def get_arguments(pad_final_batch, batch_size, args, kwargs, arg_indices, kwarg_indices, batch_indices):

    """ Replace Tiled arguments with a single tile or batch of tiles.

    Parameters
    ----------
        pad_final_batch : bool
            Whether to pad the final batch to the specified ``batch_size``. If ``func_process`` does not support
            batching, this value is ignored.
        batch_size : int
            Number of tiles in each batch. If ``func`` is not vectorized, this value is ignored.
        args : tuple
            Arguments for ``func``.
        kwargs : dict
            Keyword arguments for ``func``.
        arg_indices : list of tuple
            Leaf indices for ``args``.
        kwarg_indices : list of tuple
            Leaf indices for ``kwargs``.
        batch_indices : tuple of numpy.ndarray
            Batch indices of tiles.

    Returns
    -------
        args : tuple
            Arguments for ``func`` with Tiled objects replaced.
        kwargs : dict
            Keyword arguments for ``func`` with Tiled objects replaced.
    """

    partial_create_batch = partial(create_batch,
                                   pad_final_batch=pad_final_batch, batch_size=batch_size, batch_indices=batch_indices)
    args = trees.tree_apply(args, arg_indices, partial_create_batch)
    kwargs = trees.tree_apply(kwargs, kwarg_indices, partial_create_batch)

    return args, kwargs


def create_batch(tiles, pad_final_batch, batch_size, batch_indices):

    """ Create a batch of tiles from a Tiled object.

    Parameters
    ----------
        tiles : Tiled
            Array of tiles.
        pad_final_batch : bool
            Whether to pad the final batch to the specified ``batch_size``. If ``func_process`` does not support
            batching, this value is ignored.
        batch_size : int
            Number of tiles in each batch. If ``func`` is not vectorized, this value is ignored.
        batch_indices : tuple of numpy.ndarray
            Batch indices of tiles.

    Returns
    -------
        batch_tiles
            Batch of tiles.
    """

    if len(batch_indices) == 2:
        batch_tiles = tiles[batch_indices]
    else:
        if isinstance(batch_indices[0], Iterable):
            batch_tiles = [tiles[batch_index[:2]][batch_index[2]] for batch_index in zip(*batch_indices)]
            batch_tiles = utils.cast_list_to_array(batch_tiles)
        else:
            batch_tiles = tiles[batch_indices[:2]][batch_indices[2]]

    if isinstance(batch_tiles, (list, Tiled)) and tiles.metadata['stackable']:
        batch_tiles = np.stack(batch_tiles)
        if pad_final_batch and (batch_tiles[0].shape[0] < batch_size):
            batch_tiles = utils.array_pad(batch_tiles, batch_size - batch_tiles.shape[0], 0)

    return batch_tiles


def initialize_tree(processed_tile, job, tiling, processed_istree, processed_indices, processed_tiles):

    """ Initialize a tree of Tiled objects.

    Parameters
    ----------
        processed_tile
            Processed tile.
        job : Job
            Job associated with this processing step.
        tiling : tuple of int
            Number of tiles in each dimension.
        processed_istree : bool
            Whether ``processed_tiles`` is a tree.
        processed_indices : list of tuple
            Leaf indices for ``processed_tiles``.
        processed_tiles
            Array of tiles processed with ``func``.

    Returns
    -------
        processed_istree : bool
            Whether ``processed_tiles`` is a tree.
        processed_indices : list of tuple
            Leaf indices for ``processed_tiles``.
        processed_tiles
            Array of tiles processed with ``func``.
    """

    if processed_istree is None:
        processed_istree, _, processed_indices = trees.tree_scan(processed_tile)
        processed_tiles = trees.tree_apply(processed_tile, processed_indices,
                                           partial(initialize_tiles, job=job, tiling=tiling))

    return processed_istree, processed_indices, processed_tiles


def initialize_tiles(processed_tile, job, tiling):

    """ Initialize a Tiled object.

    Parameters
    ----------
        processed_tile
            Processed tile.
        job : Job
            Job associated with this processing step.
        tiling : tuple of int
            Number of tiles in each dimension.

    Returns
    -------
        processed_tiles : Tiled
            Array of tiles.
    """

    processed_tiles = np.empty(tiling, dtype=object)

    if isinstance(processed_tile, Output):
        processed_tiles = Tiled(processed_tiles, job, **processed_tile.metadata)
    else:
        processed_tiles = Tiled(processed_tiles, job)

    return processed_tiles


def strip_output_wrapper(processed_tile):

    """ Strip Output wrapper from a processed tile.

    Parameters
    ----------
        processed_tile
            Processed tile.

    Returns
    -------
        processed_tile
            Processed tile stripped of Output wrapper.

    """

    if isinstance(processed_tile, Output):
        processed_tile = processed_tile.output

    return processed_tile


def update_tiles(processed_tiles, processed_tile, index, batch_axis):

    """ Update a Tiled object.

    Parameters
    ----------
        processed_tiles
            Array of tiles.
        processed_tile
            Processed tile.
        index : tuple of int
            Index of a tile.
        batch_axis : bool
            Whether to use the first axis to create batches.
    """

    if batch_axis:

        current_tile = processed_tiles[index]

        if current_tile is None:
            processed_tiles[index] = processed_tile[None]
        else:
            processed_tiles[index] = np.concatenate((current_tile, processed_tile[None]), 0)

    else:

        processed_tiles[index] = processed_tile


def check_compatability(tiles):

    """ Check if the given tiles are compatible.

    Parameters
    ----------
        tiles : list of Tiled
            Array of tiles.

    Raises
    ------
        ValueError
            If no tiles are given.
        ValueError
            If tiles do not all share a common profile.
        ValueError
            If tiles do not all share a common mask.
    """

    if len(tiles) == 0:
        raise ValueError("no tiles are given.")

    profile = None
    mask = None
    for i, ts in enumerate(tiles):

        if profile is None:
            profile = ts.profile
        else:
            if ts.profile is not profile:
                raise ValueError(f'tiles must all share a common profile.')

        if mask is None:
            mask = ts.mask
        else:
            if np.any(ts.mask != mask):
                raise ValueError(f'tiles must all share a common mask.')