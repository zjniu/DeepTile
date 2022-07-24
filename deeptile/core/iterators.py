import numpy as np
from functools import cached_property


class Iterator:

    """ Base Iterator class that mimics the indexing behavior of numpy.ndarray.

    Parameters
    ----------
        tiles : Tiled
            Array of tiles.
    """

    def __init__(self, tiles):

        self.dt = tiles.dt
        self.profile = tiles.profile
        self.tiles = tiles
        self.otype = None

    def __getitem__(self, index):

        """ Placeholder __getitem__ method.

        Parameters
        ----------
            index : tuple of int
                Array index.

        Raises
        ------
            NotImplementedError
                If no __getitem__ method has been set.
        """

        raise NotImplementedError("No __getitem__ method has been set.")

    @cached_property
    def nonempty_tiles(self):

        """ Get a list of nonempty tiles.

        Returns
        -------
            nonempty_tiles : list
                List of nonempty tiles.
        """

        nonempty_indices = self.profile.nonempty_indices
        nonempty_tiles = [self[nonempty_index] for nonempty_index in nonempty_indices]

        return nonempty_tiles


class IndicesIterator(Iterator):

    """ Iterator subclass for array indices.

    Parameters
    ----------
        tiles : Tiled
            Array of tiles.
    """

    def __init__(self, tiles):

        super().__init__(tiles)
        self.otype = 'index_iterator'

    def __getitem__(self, index):

        """ Get array index.

        Parameters
        ----------
            index : tuple of int
                Array index.

        Returns
        -------
            index : tuple of int
                Array index.
        """

        return index


class TileIndicesIterator(Iterator):

    """ Iterator subclass for tile indices.

    Parameters
    ----------
        tiles : Tiled
            Array of tiles.
    """

    def __init__(self, tiles):

        super().__init__(tiles)
        self.otype = 'tile_index_iterator'

    def __getitem__(self, index):

        """ Get tile index.

        Parameters
        ----------
            index : tuple of int
                Array index.

        Returns
        -------
            tile_index : numpy.ndarray
                Tile index.
        """

        i, j = index
        tile_indices = self.tiles.tile_indices

        tile_index = np.stack((tile_indices[0][i], tile_indices[1][j]))

        return tile_index


class BorderIndicesIterator(Iterator):

    """ Iterator subclass for border indices.

    Parameters
    ----------
        tiles : Tiled
            Array of tiles.
    """

    def __init__(self, tiles):

        super().__init__(tiles)
        self.otype = 'border_index_iterator'

    def __getitem__(self, index):

        """ Get border index.

        Parameters
        ----------
            index : tuple of int
                Array index.

        Returns
        -------
            border_index : numpy.ndarray
                Border index.
        """

        i, j = index
        border_indices = self.tiles.border_indices

        border_index = np.stack((border_indices[0][i:i + 2], border_indices[1][j:j + 2]))

        return border_index


class StitchIndicesIterator(Iterator):

    """ Iterator subclass for stitch indices.

    Parameters
    ----------
        tiles : Tiled
            Array of tiles.
    """

    def __init__(self, tiles):

        super().__init__(tiles)
        self.otype = 'stitch_index_iterator'

    def __getitem__(self, index):

        """ Get stitch index.

        Parameters
        ----------
            index : tuple of int
                Array index.

        Returns
        -------
            stitch_index : tuple of int
                Stitch index.
        """

        tile_indices_iterator = self.tiles.tile_indices_iterator
        border_indices_iterator = self.tiles.border_indices_iterator

        index_image = border_indices_iterator[index]
        index_tile = index_image - tile_indices_iterator[index][:, 0:1]
        stitch_index = (*index_image, *index_tile)

        return stitch_index