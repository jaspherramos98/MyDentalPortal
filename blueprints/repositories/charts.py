# File: MyDentalPortal/blueprints/repositories/charts.py
# Dental-chart storage plumbing ONLY. The chart's data *shape* and save/load
# *logic* stay in blueprints/routes/charts.py (SACRED); this module just holds
# the raw mongo.db reads/writes so the route doesn't query the driver directly.

from datetime import datetime

from bson.objectid import ObjectId

from extensions import mongo


def get_by_patient(patient_id):
    """The patient's dental chart document, or None."""
    return mongo.db.dental_charts.find_one({'patient_id': ObjectId(patient_id)})


def insert(chart_data):
    """Insert a chart document and return the stored copy."""
    result = mongo.db.dental_charts.insert_one(chart_data)
    return mongo.db.dental_charts.find_one({'_id': result.inserted_id})


def upsert(patient_id, data, actor_id):
    """Upsert the chart for a patient, stamping updated_at/updated_by.

    `data` is the caller-sanitised payload (read-only fields already stripped
    in the route — that logic is part of the SACRED save flow and stays there).
    """
    mongo.db.dental_charts.update_one(
        {'patient_id': ObjectId(patient_id)},
        {'$set': {
            **data,
            'updated_at': datetime.utcnow(),
            'updated_by': actor_id,
        }},
        upsert=True,
    )
