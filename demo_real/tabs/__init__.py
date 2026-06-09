from .search import bp as search_bp
from .chat import bp as chat_bp
from .saved import bp as saved_bp
from .radar import bp as radar_bp
from .analytics import bp as analytics_bp
from .job_detail import bp as job_detail_bp
from .candidate import bp as candidate_bp
from .company import bp as company_bp
from .guided import bp as guided_bp
from .feedback import bp as feedback_bp


def register_blueprints(app):
    app.register_blueprint(search_bp)
    app.register_blueprint(chat_bp)
    app.register_blueprint(saved_bp)
    app.register_blueprint(radar_bp)
    app.register_blueprint(analytics_bp)
    app.register_blueprint(job_detail_bp)
    app.register_blueprint(candidate_bp)
    app.register_blueprint(company_bp)
    app.register_blueprint(guided_bp)
    app.register_blueprint(feedback_bp)
