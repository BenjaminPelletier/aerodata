import multiprocessing

from gevent import monkey
monkey.patch_all()

import flask

from aerodata.fetch import get_features
from aerodata.query import AerodromeQueryParams, select_features

webapp = flask.Flask(__name__)


lock = multiprocessing.RLock()


@webapp.route("/aerodromes")
def get_aerodromes():
    try:
        query = AerodromeQueryParams.from_dict(flask.request.args)
    except ValueError as e:
        return f"Error parsing query parameters: {str(e)}"

    features = get_features()
    feature_collection = select_features(features, query)

    return flask.jsonify(feature_collection)


@webapp.route("/status")
def status():
    return "Ok"
