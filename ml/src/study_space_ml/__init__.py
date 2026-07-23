"""Edge ML bridge for the privacy-preserving study space advisor."""

from .predictor import EdgePredictor, predict_window

__all__ = ["EdgePredictor", "predict_window"]
__version__ = "0.1.0"
