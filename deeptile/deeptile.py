import numpy as np
from deeptile import backends, utils
from pathlib import Path
from skimage import measure


class DeepTile:

    def __init__(self, image):

        if isinstance(image, np.ndarray):
            self.image = image
        elif Path(image).is_file():
            if image.endswith('.nd2'):
                self.image, self.nd2_metadata = utils.read_nd2(image)
            elif image.endswith(('.tif', '.tiff')):
                from tifffile import imread
                self.image = imread(image)
        else:
            raise ValueError("Invalid image.")

        if isinstance(self.image, np.ndarray):
            self.image_type = 'array'
        else:
            self.image_type = 'nd2'

        self.n_blocks = None
        self.overlap = None
        self.algorithm = None
        self.model_parameters = None
        self.eval_parameters = None
        self.app = None

        self.image_shape = None
        self.mask_shape = None
        self.tile_indices = None
        self.border_indices = None
        self.stitch_indices = None

    def configure(self, n_blocks=(2, 2), overlap=(0.1, 0.1), algorithm='cellori',
                  model_parameters=None, eval_parameters=None):

        if self.image_type == 'array':
            self.n_blocks = n_blocks
        self.overlap = overlap
        self.algorithm = algorithm

        if model_parameters is None:
            self.model_parameters = dict()
        else:
            self.model_parameters = model_parameters

        if eval_parameters is None:
            self.eval_parameters = dict()
        else:
            self.eval_parameters = eval_parameters

        self.app = backends.create_app(self.algorithm)

    def segment_image(self, slices=(slice(None))):

        masks, tiles = self._segment_image(slices)
        self.stitch_indices = self._calculate_stitch_indices(tiles)
        mask = self._stitch_masks(masks)

        return mask, masks, tiles

    def get_tiles(self, slices=(slice(None))):

        tiles = None
        if self.image_type == 'array':
            image = self.image[slices]
            self.image_shape = image.shape
            self.tile_indices, self.border_indices = \
                utils.calculate_indices_2d(self.image_shape, self.n_blocks, self.overlap)
            tiles = np.empty(shape=self.n_blocks, dtype=object)
            tiles[:] = utils.array_split_2d(image, self.tile_indices)
        elif self.image_type == 'nd2':
            tiles, self.overlap, self.image_shape = utils.parse_nd2(self.image, self.nd2_metadata, self.overlap,
                                                                    slices)
            self.n_blocks = tiles.shape
            self.tile_indices, self.border_indices = utils.calculate_indices_2d(self.image_shape, self.n_blocks,
                                                                                self.overlap)

        return tiles

    def stitch_nd2(self, slices=(slice(None))):

        tiles = self.get_tiles(slices)
        self.stitch_indices = self._calculate_stitch_indices(tiles)
        image = self._stitch_nd2(tiles)

        return image, tiles

    def _segment_image(self, slices=(slice(None))):

        tiles = self.get_tiles(slices)
        masks = np.zeros_like(tiles)
        self.mask_shape = None

        for index, tile in np.ndenumerate(tiles):

            if tile is None:
                mask = None
            else:
                tile = tile.reshape(-1, *tile.shape[-2:])
                mask, self.mask_shape = backends.segment_tile(tile, self.app, self.model_parameters,
                                                              self.eval_parameters, self.image_shape, self.mask_shape)

            masks[index] = mask

        return masks, tiles

    def _stitch_nd2(self, tiles):

        stitched_image = np.zeros(self.image_shape)

        for (n_i, n_j), (i_image, j_image, i, j) in self.stitch_indices.items():

            tile = tiles[n_i, n_j]
            tile_crop = tile[..., i[0]:i[1], j[0]:j[1]]
            stitched_image[..., i_image[0]:i_image[1], j_image[0]:j_image[1]] = tile_crop

        return stitched_image

    def _stitch_masks(self, masks):

        mask_flat_shape = (np.prod(self.mask_shape[:-2], dtype=int), *self.mask_shape[-2:])
        stitched_mask = np.zeros(mask_flat_shape, dtype=int)

        for z in range(mask_flat_shape[0]):

            total_count = 0

            for (n_i, n_j), (i_image, j_image, i, j) in self.stitch_indices.items():

                i_clear = i[(0 < i_image) & (i_image < self.mask_shape[-2])]
                j_clear = j[(0 < j_image) & (j_image < self.mask_shape[-1])]
                mask = utils.clear_border(masks[n_i, n_j][z].copy(), i_clear, j_clear)

                mask_crop = mask[i[0]:i[1], j[0]:j[1]]
                mask_crop = measure.label(mask_crop)
                count = mask_crop.max()
                mask_crop[mask_crop > 0] += total_count
                total_count += count
                stitched_mask[z, i_image[0]:i_image[1], j_image[0]:j_image[1]] = mask_crop

            border_cells = self._find_border_cells(masks, z)

            for (n_i, n_j), cells in border_cells.items():

                mask = masks[n_i, n_j][z]
                regions = measure.regionprops(mask)

                for cell in cells:

                    mask_crop = regions[cell - 1].image
                    s = regions[cell - 1].slice
                    s_image = (slice(s[0].start + self.tile_indices[0][n_i, 0],
                                     s[0].stop + self.tile_indices[0][n_i, 0]),
                               slice(s[1].start + self.tile_indices[1][n_j, 0],
                                     s[1].stop + self.tile_indices[1][n_j, 0]))
                    image_crop = stitched_mask[z][s_image]

                    if not np.any(mask_crop & (image_crop > 0)):
                        image_crop[mask_crop] = total_count + 1
                        total_count += 1

            stitched_mask[z] = measure.label(stitched_mask[z])

        stitched_mask = stitched_mask.reshape(self.mask_shape)

        return stitched_mask

    def _find_border_cells(self, masks, z):

        tile_indices_flat = (self.tile_indices[0].flatten(), self.tile_indices[1].flatten())
        border_cells = dict()

        for axis in range(2):

            if axis == 1:
                masks = masks.T

            for n_i in range(self.n_blocks[axis]):

                i_image = self.border_indices[axis][n_i:n_i + 2]
                i = i_image - self.tile_indices[axis][n_i, 0]

                for n_j in range(self.n_blocks[1 - axis] - 1):

                    j_image = np.flip(tile_indices_flat[1 - axis][2 * n_j + 1:2 * n_j + 3])
                    offset = self.tile_indices[1 - axis][n_j:n_j + 2, 0]
                    j = j_image - offset.reshape(2, 1)
                    border_index = self.border_indices[1 - axis][n_j + 1] - j_image[0]

                    position_l, position_r = None, None

                    mask_l_all = masks[n_i, n_j]
                    if mask_l_all is not None:
                        mask_l_all = mask_l_all[z]
                        if axis == 1:
                            mask_l_all = mask_l_all.T
                            position_l = (n_j, n_i)
                        elif axis == 0:
                            position_l = (n_i, n_j)
                        border_cells = self._scan_border(border_cells, mask_l_all, (i, j[0]), position_l, border_index)

                    mask_r_all = masks[n_i, n_j + 1]
                    if mask_r_all is not None:
                        mask_r_all = mask_r_all[z]
                        if axis == 1:
                            mask_r_all = mask_r_all.T
                            position_r = (n_j + 1, n_i)
                        elif axis == 0:
                            position_r = (n_i, n_j + 1)
                        border_cells = self._scan_border(border_cells, mask_r_all, (i, j[1]), position_r, border_index)

        return border_cells

    @staticmethod
    def _scan_border(all_border_cells, mask_all, position, position_adjacent, border_index):

        if mask_all is not None:

            i, j = position
            mask = mask_all[i[0]:i[1], j[0]:j[1]]
            border = mask[:, border_index]
            cells = np.unique(border)
            cells = cells[cells > 0]

            if len(cells) > 0:
                border_cells = all_border_cells.get(position_adjacent, set())
                border_cells.update(cells)
                all_border_cells[position_adjacent] = border_cells

        return all_border_cells

    def _calculate_stitch_indices(self, tiles):

        stitch_indices = dict()

        for (n_i, n_j), tile in np.ndenumerate(tiles):

            if tile is not None:
                i_image = self.border_indices[0][n_i:n_i + 2]
                j_image = self.border_indices[1][n_j:n_j + 2]
                i = i_image - self.tile_indices[0][n_i, 0]
                j = j_image - self.tile_indices[1][n_j, 0]
                stitch_indices[(n_i, n_j)] = (i_image, j_image, i, j)

        return stitch_indices
