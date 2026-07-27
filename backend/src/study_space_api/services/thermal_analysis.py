from __future__ import annotations

import math
from collections import deque

from ..schemas import (
    ThermalAnalysisResponse,
    ThermalDetectionBox,
    ThermalPreviewResponse,
)

MIN_REGION_PIXELS = 4
MIN_THRESHOLD = 0.65


def analyze_thermal_preview(
    preview: ThermalPreviewResponse,
    *,
    model_people_count: int | None = None,
    observation_people_count: int | None = None,
) -> ThermalAnalysisResponse:
    """Find anonymous connected hot regions in a normalized 32 x 24 preview."""

    count, source = _preferred_count(
        model_people_count=model_people_count,
        observation_people_count=observation_people_count,
        thermal_region_count=None,
    )
    if (
        not preview.available
        or preview.values is None
        or preview.width is None
        or preview.height is None
        or len(preview.values) != preview.width * preview.height
    ):
        return ThermalAnalysisResponse(
            available=False,
            method="thermal_connected_regions",
            estimated_people_count=count,
            count_source=source,
        )

    values = preview.values
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / len(values)
    threshold = min(0.9, max(MIN_THRESHOLD, mean + 1.5 * math.sqrt(variance)))
    regions = _connected_regions(values, preview.width, preview.height, threshold)
    boxes = [
        _region_box(region, values, preview.width, preview.height)
        for region in regions
        if len(region) >= MIN_REGION_PIXELS
    ]
    count, source = _preferred_count(
        model_people_count=model_people_count,
        observation_people_count=observation_people_count,
        thermal_region_count=len(boxes),
    )
    return ThermalAnalysisResponse(
        available=True,
        method="thermal_connected_regions",
        threshold=round(threshold, 4),
        detected_region_count=len(boxes),
        estimated_people_count=count,
        count_source=source,
        boxes=boxes,
    )


def _connected_regions(
    values: list[float],
    width: int,
    height: int,
    threshold: float,
) -> list[list[int]]:
    hot = {index for index, value in enumerate(values) if value >= threshold}
    regions: list[list[int]] = []
    while hot:
        start = hot.pop()
        queue = deque([start])
        region = [start]
        while queue:
            index = queue.popleft()
            x = index % width
            y = index // width
            neighbours = []
            if x > 0:
                neighbours.append(index - 1)
            if x + 1 < width:
                neighbours.append(index + 1)
            if y > 0:
                neighbours.append(index - width)
            if y + 1 < height:
                neighbours.append(index + width)
            for neighbour in neighbours:
                if neighbour in hot:
                    hot.remove(neighbour)
                    queue.append(neighbour)
                    region.append(neighbour)
        regions.append(region)
    return regions


def _region_box(
    region: list[int],
    values: list[float],
    frame_width: int,
    frame_height: int,
) -> ThermalDetectionBox:
    xs = [index % frame_width for index in region]
    ys = [index // frame_width for index in region]
    left, right = min(xs), max(xs)
    top, bottom = min(ys), max(ys)
    peak = max(values[index] for index in region)
    confidence = sum(values[index] for index in region) / len(region)
    return ThermalDetectionBox(
        x=left / frame_width,
        y=top / frame_height,
        width=(right - left + 1) / frame_width,
        height=(bottom - top + 1) / frame_height,
        confidence=round(confidence, 4),
        peak_intensity=round(peak, 4),
    )


def _preferred_count(
    *,
    model_people_count: int | None,
    observation_people_count: int | None,
    thermal_region_count: int | None,
) -> tuple[int | None, str]:
    if model_people_count is not None:
        return max(0, model_people_count), "people_count_model"
    if thermal_region_count is not None:
        return thermal_region_count, "thermal_regions"
    if observation_people_count is not None:
        return max(0, observation_people_count), "room_observation"
    return None, "unavailable"
