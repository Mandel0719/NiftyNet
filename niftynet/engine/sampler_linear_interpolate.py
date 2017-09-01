# -*- coding: utf-8 -*-
"""
Generating samples by linearly combining two input images
"""
from __future__ import absolute_import, print_function, division

import numpy as np
import tensorflow as tf

from niftynet.engine.image_window import ImageWindow, N_SPATIAL
from niftynet.engine.image_window_buffer import InputBatchQueueRunner
from niftynet.layer.base_layer import Layer


class LinearInterpolateSampler(Layer, InputBatchQueueRunner):
    """
    This class reads two feature vectors from files (often generated
    by running feature extractors on images in advance)
    and returns n linear combinations of the vectors.
    The coefficients are generated by
    np.linspace(0, 1, n_interpolations)
    """

    def __init__(self,
                 reader,
                 data_param,
                 batch_size=10,
                 n_interpolations=10,
                 queue_length=10):
        self.n_interpolations = n_interpolations
        self.reader = reader
        Layer.__init__(self, name='input_buffer')
        InputBatchQueueRunner.__init__(
            self,
            capacity=max(batch_size * 4, queue_length),
            shuffle=False)
        tf.logging.info('reading size of preprocessed images')
        self.window = ImageWindow.from_data_reader_properties(
            self.reader.input_sources,
            self.reader.shapes,
            self.reader.tf_dtypes,
            data_param)
        # only try to use the first spatial shape available
        image_spatial_shape = self.reader.shapes.values()[0][:3]
        self.window.set_spatial_shape(image_spatial_shape)

        tf.logging.info('initialised window instance')
        self._create_queue_and_ops(self.window,
                                   enqueue_size=self.n_interpolations,
                                   dequeue_size=batch_size)
        tf.logging.info("initialised sampler output {} "
                        " [-1 for dynamic size]".format(self.window.shapes))

        assert not self.window.has_dynamic_shapes, \
            "dynamic shapes not supported, please specify " \
            "spatial_window_size = (1, 1, 1)"

    def layer_op(self, *args, **kwargs):
        """
        This function first reads two vectors, and interpolates them
        with self.n_interpolations mixing coefficients
        Location coordinates are set to np.ones for all the vectors
        """
        while True:
            image_id_x, data_x, _ = self.reader(idx=None, shuffle=False)
            image_id_y, data_y, _ = self.reader(idx=None, shuffle=True)
            if not data_x or not data_y:
                break
            if image_id_x == image_id_y:
                continue
            embedding_x = data_x[self.window.names[0]]
            embedding_y = data_y[self.window.names[0]]

            steps = np.linspace(0, 1, self.n_interpolations)
            output_vectors = []
            for (idx, mixture) in enumerate(steps):
                output_vector = \
                    embedding_x * mixture + embedding_y * (1 - mixture)
                output_vector = output_vector[np.newaxis, ...]
                output_vectors.append(output_vector)
            output_vectors = np.concatenate(output_vectors, axis=0)
            coordinates = np.ones(
                (self.n_interpolations, N_SPATIAL * 2 + 1), dtype=np.int32)
            coordinates[:, 0] = image_id_x
            coordinates[:, 1] = image_id_y

            output_dict = {}
            for name in self.window.names:
                coordinates_key = self.window.coordinates_placeholder(name)
                image_data_key = self.window.image_data_placeholder(name)
                output_dict[coordinates_key] = coordinates
                output_dict[image_data_key] = output_vectors
            yield output_dict
