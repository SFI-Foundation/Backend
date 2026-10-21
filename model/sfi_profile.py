"""Optional nonprofit interests; existing user columns and roles stay unchanged."""
from __init__ import db


def empty_interests():
    return {
        'causes': [],
        'participation': [],
        'skills': '',
        'volunteering': None,
        'availability': '',
    }


class SfiProfile(db.Model):
    __tablename__ = 'sfi_profiles'

    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), primary_key=True)
    causes = db.Column(db.JSON, nullable=False, default=list)
    participation = db.Column(db.JSON, nullable=False, default=list)
    skills = db.Column(db.String(500), nullable=False, default='')
    volunteering = db.Column(db.Boolean, nullable=True)
    availability = db.Column(db.String(40), nullable=False, default='')

    user = db.relationship('User', backref=db.backref(
        'sfi_profile', uselist=False, cascade='all, delete-orphan'))

    def read(self):
        return {key: getattr(self, key) for key in empty_interests()}
