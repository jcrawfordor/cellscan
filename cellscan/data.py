from peewee import *

# Just stick it wherever... this data is all ephemeral and only needs to persist until the next
# upload. However, right now we keep all data (even data we know has been uploaded) so that old
# data can be recovered from the sensor if there's some failure of the collection server.
db = SqliteDatabase('datastore.sqlite')

class Cellsite(Model):
    lat = FloatField()
    lon = FloatField()
    alt = FloatField()
    time = DateTimeField()
    # Just storing cell data as strings, which is perhaps kind of lazy, but allows us to keep
    # everything as it is on the sensor and deal with bad values on the server end (where we can
    # retry processing data and such).
    rx = CharField()
    mcc = CharField()
    mnc = CharField()
    lac = CharField()
    gen = CharField()
    cellid = CharField()
    # Keep track of what's been submitted.
    uploaded = BooleanField(default=False)

    class Meta:
        database = db

class Location(Model):
    # Not in use yet, intent is to separately store GPX tracks in the future which could be useful
    # for determining when cell sites go away (sensor is near previous location but does not report
    # the cell)
    time = DateTimeField()
    lat = FloatField()
    lon = FloatField()
    alt = FloatField()
    # Keep track of what's been submitted.
    uploaded = BooleanField(default=False)

    class Meta:
        database = db

def saveCellSite(info):
    obj = Cellsite(**info)
    obj.save()