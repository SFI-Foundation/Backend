"""Non-sensitive presentation preferences, independent of onboarding answers."""
from __init__ import db


class SfiSettings(db.Model):
    __tablename__ = 'sfi_account_settings'
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), primary_key=True)
    revision = db.Column(db.Integer, nullable=False, default=1)
    preferences = db.Column(db.JSON, nullable=False, default=dict)
    user = db.relationship('User', backref=db.backref('website_settings', uselist=False, cascade='all, delete-orphan'))
