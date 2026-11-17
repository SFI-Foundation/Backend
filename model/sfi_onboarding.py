"""Optional self-reported preferences, never an authorization source."""
from __init__ import db


MULTI_CHOICES = {
    'involvement': ('manufacturer', 'driver', 'race_team', 'sanctioning_body',
                    'technical_inspector', 'distributor', 'event_organizer',
                    'engineer', 'sfi_staff', 'enthusiast', 'other', 'prefer_not_to_answer'),
    'visit_reasons': ('find_specification', 'technical_specifications', 'safety_equipment',
                      'find_manufacturer', 'certification_requirements', 'safety_standards',
                      'manufacturer_participation', 'sanctioning_resources', 'product_compliance',
                      'safety_updates', 'education', 'other'),
    'disciplines': ('drag_racing', 'oval_racing', 'road_racing', 'off_road', 'karting',
                    'motorcycle', 'other', 'not_applicable'),
    'resources': ('specification_search', 'specification_documents', 'manufacturer_directory',
                  'safety_equipment', 'technical_updates', 'certification_compliance',
                  'education', 'safety_news', 'events'),
    'update_interests': ('specification_updates', 'technical_announcements', 'manufacturer_program',
                         'safety_education', 'foundation_news', 'volunteering_events'),
}
GOALS = ('find_specification', 'research_equipment', 'certification_requirements',
         'manufacturer_information', 'technical_resources', 'about_sfi', 'exploring')
TEXT_LIMITS = {'organization_name': 200, 'organization_website': 500,
               'job_title': 120, 'additional_notes': 500}


def empty_preferences():
    return {**{key: [] for key in MULTI_CHOICES},
            **{key: '' for key in TEXT_LIMITS}, 'primary_goal': None}


class SfiOnboarding(db.Model):
    __tablename__ = 'sfi_onboarding_preferences'

    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), primary_key=True)
    # A validated JSON document permits additive optional fields without altering
    # legacy profile columns. Always assign a fresh document for ORM tracking.
    answers = db.Column(db.JSON, nullable=False, default=empty_preferences)
    user = db.relationship('User', backref=db.backref(
        'sfi_onboarding', uselist=False, cascade='all, delete-orphan'))

    def read(self):
        return {**empty_preferences(), **self.answers}
