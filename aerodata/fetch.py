from datetime import datetime, timedelta
import json
import math
import os
import multiprocessing

import geomag
from loguru import logger
import requests


raw_data_lock = multiprocessing.RLock()
CACHE_PATH = ".cache"
MAX_AGE = timedelta(hours=6000)
RUNWAYS_URL = "https://opendata.arcgis.com/api/v3/datasets/4d8fa46181aa470d809776c57a8ab1f6_0/downloads/data?format=geojson&spatialRefId=4326&where=1%3D1"
RUNWAYS_FILENAME = "Runways.geojson"
AIRPORTS_URL = "https://opendata.arcgis.com/api/v3/datasets/e747ab91a11045e8b3f8a3efd093d3b5_0/downloads/data?format=geojson&spatialRefId=4326&where=1%3D1"
AIRPORTS_FILENAME = "Airports.geosjon"
FEATURES_FILENAME = "Features.geojson"
EARTH_CIRCUMFERENCE_FT = 131482560
RUNWAY_WIDTH_TOLERANCE = 0.2  # fraction
RUNWAY_HEADING_TOLERANCE = 30  # degrees
RUNWAY_HEADINGS = {
    "N": 0,
    "NNE": 22.5,
    "NE": 45,
    "ENE": 67.5,
    "E": 90,
    "ESE": 112.5,
    "SE": 135,
    "SSE": 157.5,
    "S": 180,
    "SSW": 202.5,
    "SW": 225,
    "WSW": 247.5,
    "W": 270,
    "WNW": 292.5,
    "NW": 315,
    "NNW": 337.5,
    "ALL": 0,
    "WAY": 180,
}
RECIPROCAL_SUFFIXES = {
    "L": "R",
    "R": "L",
    "W": "E",
    "E": "W",
    "N": "S",
    "S": "N",
    "NE": "SW",
    "SE": "NW",
    "SW": "NE",
    "NW": "SE",
    "NNE": "SSW",
    "ENE": "WSW",
    "ESE": "WNW",
    "SSE": "NNW",
    "SSW": "NNE",
    "WSW": "ENE",
    "WNW": "ESE",
    "NNW": "SSE",
}


def _heading_of(runway_name: str) -> float:
    if runway_name in RUNWAY_HEADINGS:
        return RUNWAY_HEADINGS[runway_name]
    if runway_name[-1] not in "0123456789":
        runway_name = runway_name[0:-1]
    if runway_name in RUNWAY_HEADINGS:
        return RUNWAY_HEADINGS[runway_name]
    if len(runway_name) == 2:
        return float(runway_name) * 10
    elif len(runway_name) == 3:
        return float(runway_name)
    else:
        raise ValueError(f"Could not determine heading of runway `{runway_name}`")


def _reciprocal_runway(runway_name: str) -> str:
    if runway_name in RECIPROCAL_SUFFIXES:
        return RECIPROCAL_SUFFIXES[runway_name]
    if runway_name[-1] not in "0123456789":
        suffix = runway_name[-1]
        if suffix not in RECIPROCAL_SUFFIXES:
            raise ValueError(f"Cannot determine reciprocal suffix for runway `{runway_name}`")
        suffix = RECIPROCAL_SUFFIXES[suffix]
        runway_name = runway_name[0:-1]
    else:
        suffix = ""
    if runway_name in RECIPROCAL_SUFFIXES:
        return RECIPROCAL_SUFFIXES[runway_name] + suffix
    if len(runway_name) == 2:
        heading = int(runway_name) * 10
    elif len(runway_name) == 3:
        heading = int(runway_name)
    else:
        raise ValueError(f"Could not determine reciprocal runway for `{runway_name}`")
    heading = (heading + 180) % 360
    if len(runway_name) == 2:
        return f"{round(heading / 10):02d}{suffix}"
    elif len(runway_name) == 3:
        return f"{heading:03d}{suffix}"
    else:
        raise RuntimeError("Impossible logic reached")


def _flatten(coords: list[tuple[float, float]]) -> list[tuple[float, float]]:
    lat0 = sum(c[1] for c in coords) / len(coords)
    lng0 = sum(c[0] for c in coords) / len(coords)
    coslat = math.cos(math.radians(lat0))
    flattened = []
    for coord in coords:
        flattened.append((
            (coord[0] - lng0) * EARTH_CIRCUMFERENCE_FT * coslat / 360,
            (coord[1] - lat0) * EARTH_CIRCUMFERENCE_FT / 360
        ))
    return flattened


def _unflatten(xy: list[tuple[float, float]], lat0: float, lng0: float) -> list[tuple[float, float]]:
    coslat = math.cos(math.radians(lat0))
    unflattened = []
    for coord in xy:
        unflattened.append((
            lng0 + coord[0] * 360 / (EARTH_CIRCUMFERENCE_FT * coslat),
            lat0 + coord[1] * 360 / EARTH_CIRCUMFERENCE_FT
        ))
    return unflattened


def _angular_distance(a1_deg: float, a2_deg: float) -> float:
    candidates = [a2_deg - a1_deg, a2_deg + 360 - a1_deg, a2_deg - 360 - a1_deg]
    return min(abs(c) for c in candidates)


def get_features() -> list[dict]:
    """Get Features in API format.

    When necessary, download the source data for runways and airports to cache files.

    When necessary, regenerate features cache file.  Otherwise, read featuers from cache file.

    Returns: List of GeoJSON Features compliant with the API.

    Raises:
        * HTTPError for non-successful retrieval status
        * ValueError when decoding JSON
    """
    with raw_data_lock:
        if not os.path.exists(CACHE_PATH):
            os.makedirs(CACHE_PATH)

        features_path = os.path.join(CACHE_PATH, FEATURES_FILENAME)

        runways_path = os.path.join(CACHE_PATH, RUNWAYS_FILENAME)
        if not os.path.exists(runways_path) or (datetime.utcnow() - datetime.fromtimestamp(os.path.getmtime(runways_path))) > MAX_AGE:
            logger.debug(f"Downloading {RUNWAYS_FILENAME}")
            resp = requests.get(RUNWAYS_URL)
            resp.raise_for_status()
            runways = resp.json()
            with open(runways_path, "w") as f:
                json.dump(runways, f)
            if os.path.exists(features_path):
                os.remove(features_path)
        else:
            with open(runways_path, "r") as f:
                runways = json.load(f)

        airports_path = os.path.join(CACHE_PATH, AIRPORTS_FILENAME)
        if not os.path.exists(airports_path) or (datetime.utcnow() - datetime.fromtimestamp(os.path.getmtime(airports_path))) > MAX_AGE:
            logger.debug(f"Downloading {AIRPORTS_FILENAME}")
            resp = requests.get(AIRPORTS_URL)
            resp.raise_for_status()
            airports = resp.json()
            with open(airports_path, "w") as f:
                json.dump(airports, f)
            if os.path.exists(features_path):
                os.remove(features_path)
        else:
            with open(airports_path, "r") as f:
                airports = json.load(f)

        if os.path.exists(features_path):
            # Use cached Features.geojson
            with open(features_path, "r") as f:
                features = json.load(f)
        else:
            # Features.geojson isn't present; generate it from airports + runways
            features = []

            # Process airports
            for airport in airports["features"]:
                if not airport["properties"]["IDENT"]:
                    ap_id = airport["properties"]["GLOBAL_ID"]
                else:
                    ap_id = "K" + airport["properties"]["IDENT"]
                airport["id"] = ap_id
                features.append({
                    "type": "Feature",
                    "geometry": airport["geometry"],
                    "properties": {
                        "aerodrome_element_type": "Aerodrome",
                        "aerodrome_identifier": ap_id,
                        "country": "USA",
                        "name": airport["properties"]["NAME"],
                    }
                })

            # Process runways
            airports_by_id = {ap["properties"]["GLOBAL_ID"]: ap for ap in airports["features"]}
            for runway in runways["features"]:
                airport = airports_by_id[runway["properties"]["AIRPORT_ID"]]
                coords = runway["geometry"]["coordinates"][0]
                lng0 = min(c[0] for c in coords)
                lng1 = max(c[0] for c in coords)
                lat0 = min(c[1] for c in coords)
                lat1 = max(c[1] for c in coords)
                bad_coords = lng0 > -0.5 and lng1 < 0.5 and lat0 > -0.001 and lat1 < 0.001

                name = runway["properties"]["DESIGNATOR"]
                width = runway["properties"]["WIDTH"]
                length = runway["properties"]["LENGTH"]
                ident = airport['properties']['IDENT']

                if "-" in name and name[0] not in "HB":
                    name = name.replace("-", "/")

                if ((not name[0] in "HB") and ("/" in name or length > 800)) or name == "W":
                    # This is a runway

                    names = name.split("/")
                    if len(names) == 1:
                        # Reciprocal runway is simply missing
                        names.append(_reciprocal_runway(names[0]))
                        runway["properties"]["DESIGNATOR"] = "/".join(names)

                    if all((n[-1] == "X") for n in names):
                        # This runway doesn't exist any more
                        logger.warning(f"Omitting non-existent runway `{name}` at {ident} with {length} ft length")
                        continue

                    if not bad_coords:
                        # Find the runway endpoints from the provided geometry
                        xy = _flatten(coords)
                        seg_length = []
                        for i in range(4):
                            dx = xy[i + 1][0] - xy[i][0]
                            dy = xy[i + 1][1] - xy[i][1]
                            seg_length.append(math.sqrt(dx * dx + dy * dy))
                        if seg_length[0] + seg_length[2] < seg_length[1] + seg_length[3]:
                            end1 = ((coords[0][0] + coords[1][0]) / 2, (coords[0][1] + coords[1][1]) / 2)
                            end2 = ((coords[2][0] + coords[3][0]) / 2, (coords[2][1] + coords[3][1]) / 2)
                            width1, length1, width2, length2 = seg_length
                        else:
                            end1 = ((coords[1][0] + coords[2][0]) / 2, (coords[1][1] + coords[2][1]) / 2)
                            end2 = ((coords[0][0] + coords[3][0]) / 2, (coords[0][1] + coords[3][1]) / 2)
                            length1, width1, length2, width2 = seg_length
                        if abs(width / width1 - 1) > RUNWAY_WIDTH_TOLERANCE:
                            logger.warning(f"Runway {name} at {ident} is listed as {width} ft wide, but end 1 is {width1} ft wide")
                        if abs(width / width2 - 1) > RUNWAY_WIDTH_TOLERANCE:
                            logger.warning(f"Runway {name} at {ident} is listed as {width} ft wide, but end 2 is {width2} ft wide")
                        if abs(length / length1 - 1) > RUNWAY_WIDTH_TOLERANCE:
                            logger.warning(f"Runway {name} at {ident} is listed as {length} ft long, but side 1 is {length1} ft long")
                        if abs(length / length2 - 1) > RUNWAY_WIDTH_TOLERANCE:
                            logger.warning(f"Runway {name} at {ident} is listed as {length} ft long, but side 2 is {length2} ft long")

                        xy = _flatten([end1, end2])
                        mag_dec = geomag.declination(end1[1], end1[0])
                        heading12 = math.degrees(math.atan2(xy[1][0] - xy[0][0], xy[1][1] - xy[0][1])) - mag_dec
                        heading21 = (heading12 + 180) % 360

                        headings = [_heading_of(n) for n in names]

                        if len(names) == 2:
                            if _angular_distance(headings[0], heading12) + _angular_distance(headings[1], heading21) > _angular_distance(headings[0], heading21) + _angular_distance(headings[1], heading12):
                                t = end2
                                end2 = end1
                                end1 = t
                                t = heading12
                                heading12 = heading21
                                heading21 = t

                            if _angular_distance(headings[0], heading12) > RUNWAY_HEADING_TOLERANCE:
                                logger.warning(f"Runway {names[0]} (of {name}) at {ident} has actual heading of {heading12 % 360}")
                            if _angular_distance(headings[1], heading21) > RUNWAY_HEADING_TOLERANCE:
                                logger.warning(f"Runway {names[1]} (of {name}) at {ident} has actual heading of {heading21 % 360}")
                        else:
                            raise NotImplementedError()

                        geo = {
                            "type": "LineString",
                            "coordinates": [end1, end2],
                        }
                        approx = False
                    else:
                        # Estimate runway endpoints from airport center and heading
                        if length == 0:
                            raise ValueError(f"Runway `{name}` at {ident} with zero length has bad coordinates")
                        if width == 0:
                            raise ValueError(f"Runway `{name}` at {ident} with zero width has bad coordinates")
                        if length < 500:
                            logger.warning(f"Short runway `{name}` {length} ft long at {ident} has bad coordinates")

                        ap_coords = airport["geometry"]["coordinates"]
                        mag_dec = geomag.declination(ap_coords[1], ap_coords[0])
                        heading = math.radians(_heading_of(name.split("/")[0]) + mag_dec)
                        xy = [
                            (-length / 2 * math.sin(heading), -length / 2 * math.cos(heading)),
                            (length / 2 * math.sin(heading), length / 2 * math.cos(heading)),
                        ]
                        coords = _unflatten(xy, ap_coords[1], ap_coords[0])
                        geo = {
                            "type": "LineString",
                            "coordinates": coords
                        }
                        approx = True
                    features.append({
                        "type": "Feature",
                        "geometry": geo,
                        "properties": {
                            "aerodrome_element_type": "Runway",
                            "aerodrome_identifier": airports_by_id[runway["properties"]["AIRPORT_ID"]]["id"],
                            "runway_surface_identifier": runway["properties"]["GLOBAL_ID"],
                            "runway_width": width,
                            "runways": [
                                {
                                    "runway_identifier": names[0],
                                    "approach_end": 0,
                                    "threshold_displacement": 0,
                                },
                                {
                                    "runway_identifier": names[1],
                                    "approach_end": 1,
                                    "threshold_displacement": 0,
                                }
                            ],
                            "approximate": approx,
                        }
                    })
                else:
                    # This is not a runway

                    if name.startswith("H") or length == 0:
                        # Treat this as a helipad
                        if length == 0:
                            logger.warning(f"Found zero-length runway/helipad {name} at {ident}")
                        if length > 2000 or width > 500:
                            logger.warning(f"Found huge {length}x{width} ft helipad {name} at {ident}")
                        if not bad_coords:
                            geo = {
                                "type": "Point",
                                "coordinates": [
                                    sum(c[0] for c in coords[0:-1]) / (len(coords) - 1),
                                    sum(c[1] for c in coords[0:-1]) / (len(coords) - 1)
                                ],
                            }
                            approx = False
                        else:
                            # Use the airport location for the helipad
                            geo = airport["geometry"]
                            approx = True
                        features.append({
                            "type": "Feature",
                            "geometry": geo,
                            "properties": {
                                "aerodrome_element_type": "Helipad",
                                "aerodrome_identifier": airports_by_id[runway["properties"]["AIRPORT_ID"]]["id"],
                                "helipad_identifier": runway["properties"]["GLOBAL_ID"],
                                "approximate": approx,
                            }
                        })
                    elif name[0] == "B":
                        # This is probably a balloon port
                        logger.warning(f"Removing balloon port `{name}` at {ident}")
                        continue  # TODO: keep/show this feature
                    else:
                        raise NotImplementedError(f"Unrecognized {length}x{width} ft runway `{name}` at {ident}")

            with open(features_path, "w") as f:
                json.dump(features, f)

    return features
