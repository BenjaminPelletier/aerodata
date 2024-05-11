from gevent import monkey
from requests import HTTPError

monkey.patch_all()

import flask

from aerodata.fetch import get_features
from aerodata.query import AerodromeQueryParams, select_features

webapp = flask.Flask(__name__)


@webapp.route("/aerodromes")
def get_aerodromes():
    try:
        query_params = AerodromeQueryParams.from_dict(flask.request.args)
    except ValueError as e:
        return f"Error parsing query parameters: {str(e)}", 400

    try:
        features = get_features()
    except HTTPError as e:
        return f"Error fetching features from source: {str(e)}", 500
    except ValueError as e:
        return f"Error processing source data: {str(e)}", 500

    try:
        feature_collection = select_features(features, query_params)
    except ValueError as e:
        return f"Error selecting features: {str(e)}", 400

    return flask.jsonify(feature_collection)


@webapp.route("/status")
def status():
    return "Ok\n"
