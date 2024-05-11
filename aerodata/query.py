from __future__ import annotations
from dataclasses import dataclass
from typing import Optional


@dataclass
class AerodromeQueryParams(object):
    page_token: Optional[str]
    page_size: int
    exclude_runways: bool
    exclude_helipads: bool
    exclude_aerodromes: bool
    latA: float
    latB: float
    lngA: float
    lngB: float
    lng_wrap_180: bool
    aerodrome_identifiers: set[str]
    countries: set[str]

    @staticmethod
    def from_dict(params: dict) -> AerodromeQueryParams:
        kwargs = dict()
        kwargs["page_token"] = params.get("page_token", None)
        kwargs["page_size"] = int(params.get("page_size", 0))
        if kwargs["page_size"] < 0:
            raise ValueError("Invalid page_size")
        kwargs["exclude_runways"] = params.get("exclude_runways", "false").lower() == "true"
        kwargs["exclude_helipads"] = params.get("exclude_helipads", "false").lower() == "true"
        kwargs["exclude_aerodromes"] = params.get("exclude_aerodromes", "false").lower() == "true"

        bounding_box = params.get("bounding_box", None)
        if bounding_box:
            coords = [float(c) for c in bounding_box.split(",")]
            if len(coords) != 4:
                raise ValueError(f"Expecting exactly 4 coordinates for bounding_box, found {len(coords)}")
            kwargs["latA"] = min(coords[0], coords[2])
            kwargs["latB"] = max(coords[0], coords[2])
            if kwargs["latA"] < -90 or kwargs["latB"] > 90 or kwargs["latA"] == kwargs["latB"]:
                raise ValueError("Invalid latitude range; latitudes must be different and fall within [-90, 90]")
            lngA = min(coords[1], coords[3]) % 360
            lngB = max(coords[1], coords[3]) % 360
            if lngA == lngB:
                raise ValueError("Invalid longitude range; longitudes must be different")
            if lngB - lngA > 180:
                kwargs["lng_wrap_180"] = True
                t = lngA
                lngA = lngB
                lngB = t - 360
            else:
                kwargs["lng_wrap_180"] = False
            kwargs["lngA"] = lngA
            kwargs["lngB"] = lngB
        else:
            kwargs["latA"] = -90
            kwargs["latB"] = 90
            kwargs["lngA"] = 0
            kwargs["lngB"] = 360
            kwargs["lng_wrap_180"] = False

        if "aerodrome_identifiers" in params and params.get("aerodrome_identifiers").strip():
            kwargs["aerodrome_identifiers"] = set(a.strip() for a in params.get("aerodrome_identifiers").split(","))
        else:
            kwargs["aerodrome_identifiers"] = set()

        if "countries" in params and params.get("countries").strip():
            kwargs["countries"] = {c.strip() for c in params.get("countries").split(",")}
        else:
            kwargs["countries"] = set()

        return AerodromeQueryParams(**kwargs)


def select_features(all_features: dict, query: AerodromeQueryParams) -> dict:
    """Filter the provided features and return a FeatureCollection with selected features.

    Args:
        all_features: Entire set of features that could be returned.
        query: Query parameters indicating which features to select.

    Returns: GeoJSON FeatureCollection compliant with the API.

    Raises:
        * ValueError when page_token is invalid
    """
    features = []

    for feature in all_features:
        if query.exclude_aerodromes and feature["properties"]["aerodrome_element_type"] == "Aerodrome":
            continue
        if query.exclude_helipads and feature["properties"]["aerodrome_element_type"] == "Helipad":
            continue
        if query.exclude_runways and feature["properties"]["aerodrome_element_type"] == "Runway":
            continue

        if feature["geometry"]["type"] == "Point":
            coords = [feature["geometry"]["coordinates"]]
        elif feature["geometry"]["type"] == "LineString":
            coords = feature["geometry"]["coordinates"]
        else:
            raise NotImplementedError()
        skip = False
        for coord in coords:
            lng = coord[0]
            lat = coord[1]
            lng = (lng % 360) - (180 if query.lng_wrap_180 else 0)
            if not (query.latA <= lat <= query.latB) or not (query.lngA <= lng <= query.lngB):
                skip = True
                break
        if skip:
            continue

        if query.aerodrome_identifiers:
            if feature["properties"]["aerodrome_identifier"] not in query.aerodrome_identifiers:
                continue

        if query.countries and "USA" not in query.countries:
            continue

        features.append(feature)

    if query.page_token:
        skip = int(query.page_token)
        if skip >= len(features):
            raise ValueError("Invalid page_token")
        features = features[skip:]
    else:
        skip = 0

    if query.page_size and len(features) > query.page_size:
        page_token = skip + query.page_size
        features = features[0:query.page_size]
    else:
        page_token = None

    feature_collection = {
        "type": "FeatureCollection",
        "features": features,
    }
    if page_token:
        feature_collection["metadata"] = {
            "next_page_token": str(page_token)
        }

    return feature_collection
