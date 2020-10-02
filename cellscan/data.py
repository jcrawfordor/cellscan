from peewee import *

db = SqliteDatabase('datastore.sqlite')

class Cellsite(Model):
    lat = FloatField()
    lon = FloatField()
    alt = FloatField()
    # Just storing everything as a string, which is perhaps kind of lazy, but allows us to keep
    # everything as it is on the sensor and deal with bad values on the server end (where we can
    # retry processing data and such)
    rx = CharField()
    mcc = CharField()
    mnc = CharField()
    lac = CharField()
    gen = CharField()
    cellid = CharField()
    uploaded = BooleanField(default=False)

    class Meta:
        database = db

class Location(Model):
    time = DateTimeField()
    lat = FloatField()
    lon = FloatField()
    alt = FloatField()
    uploaded = BooleanField(default=False)

    class Meta:
        database = db

def saveCellSite(info):
    obj = Cellsite(**info)
    obj.save()