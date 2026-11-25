"""Adapted from PlaceNav's Bayesian querier (see LICENSE.PlaceNav).

Original filter: https://github.com/mingu6/ProbFiltersVPR/blob/master/src/models/TopologicalFilter.py
The filter receives descriptors directly instead of loading a ROS/HDF5 pipeline.
"""

import math

import numpy as np


def unit_descriptors(values):
    values = np.asarray(values, dtype=np.float64)
    if values.ndim not in (1, 2) or not values.size or not np.isfinite(values).all():
        raise ValueError("Descriptor phải là vector hoặc ma trận hữu hạn, không rỗng.")
    norms = np.linalg.norm(values, axis=-1, keepdims=True)
    if not np.isfinite(norms).all() or (norms < 1e-8).any():
        raise ValueError("Descriptor không được có norm bằng 0 hoặc vô hạn.")
    return values / norms


class PlaceRecognitionTopologicalFilter:
    def __init__(self, descriptors, delta=10, window_lower=-1, window_upper=2):
        self.descriptors = unit_descriptors(descriptors)
        if self.descriptors.ndim != 2:
            raise ValueError("Database phải có shape [số node, chiều descriptor].")
        if not math.isfinite(delta) or delta <= 1:
            raise ValueError("delta phải hữu hạn và lớn hơn 1.")
        if (not isinstance(window_lower, int) or not isinstance(window_upper, int)
                or window_lower >= window_upper or window_lower >= len(self.descriptors)):
            raise ValueError("Cửa sổ transition không hợp lệ cho map này.")
        self.delta = delta
        self.window_lower = window_lower
        self.transition = np.ones(window_upper - window_lower)
        self.belief = None
        self.lambda1 = 0.0

    def _distances(self, descriptor):
        descriptor = unit_descriptors(descriptor)
        if descriptor.shape != (self.descriptors.shape[1],):
            raise ValueError("Chiều descriptor query không khớp database.")
        similarities = np.clip(self.descriptors.dot(descriptor), -1.0, 1.0)
        return np.sqrt(2.0 - 2.0 * similarities)

    def _update_belief(self, prior, distances):
        # Log weights avoid underflow when a query is far from every map image.
        with np.errstate(divide="ignore"):
            log_weights = np.log(prior) - self.lambda1 * distances
        maximum = log_weights.max()
        if not np.isfinite(maximum):
            raise ValueError("Bayesian filter không còn xác suất hợp lệ.")
        weights = np.exp(log_weights - maximum)
        self.belief = weights / weights.sum()

    def initialize_model(self, descriptor):
        distances = self._distances(descriptor)
        low, high = np.quantile(distances, [0.025, 0.975])
        spread = high - low
        # Equal distances contain no evidence, including a map with a single node.
        self.lambda1 = math.log(self.delta) / spread if spread > 1e-6 else 0.0
        self._update_belief(np.ones(len(distances)), distances)

    def match(self, descriptor):
        if self.belief is None or self.lambda1 == 0.0:
            self.initialize_model(descriptor)
        else:
            distances = self._distances(descriptor)
            padding = len(self.transition) - 1
            belief_pad = np.pad(self.belief, padding, mode="symmetric")
            convolution = np.convolve(belief_pad, self.transition, mode="valid")
            lower = self.window_lower
            prior = np.zeros_like(self.belief)
            if lower < 0:
                prior[:] = convolution[abs(lower):len(self.belief) + abs(lower)]
            else:
                prior[lower:] = convolution[:len(self.belief) - lower]
            self._update_belief(prior, distances)
        node = int(np.argmax(self.belief))
        return node, float(self.belief[node])
