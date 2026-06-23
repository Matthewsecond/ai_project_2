from .blueprints.search import bp as search_bp
from .blueprints.saved import bp as saved_bp
from .blueprints.radar import bp as radar_bp
from .blueprints.analytics import bp as analytics_bp
from .blueprints.job_detail import bp as job_detail_bp
from .blueprints.candidate import bp as candidate_bp
from .blueprints.company import bp as company_bp
from .blueprints.guided import bp as guided_bp
from .blueprints.feedback import bp as feedback_bp
from .blueprints.cluster import bp as cluster_bp
from .blueprints.interview import bp as interview_bp


def register_blueprints(app):
    app.register_blueprint(search_bp)
    app.register_blueprint(saved_bp)
    app.register_blueprint(radar_bp)
    app.register_blueprint(analytics_bp)
    app.register_blueprint(job_detail_bp)
    app.register_blueprint(candidate_bp)
    app.register_blueprint(company_bp)
    app.register_blueprint(guided_bp)
    app.register_blueprint(feedback_bp)
    app.register_blueprint(cluster_bp)
    app.register_blueprint(interview_bp)
