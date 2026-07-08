def register_blueprints(app):
    # Imported here, not at module load: these blueprints (transitively) import
    # `config`, which resolves COUNTRY at import time. This package is imported
    # as a side effect of `jobs_intelligence_ai.frontend.app` (from __main__.py),
    # which happens before main() applies the --sk/--at CLI flag to the env — an
    # eager import here would permanently cache the wrong country. See app.py's
    # create_app() docstring.
    from .blueprints.search import bp as search_bp
    from .blueprints.saved import bp as saved_bp
    from .blueprints.job_detail import bp as job_detail_bp
    from .blueprints.candidate import bp as candidate_bp
    from .blueprints.company import bp as company_bp
    from .blueprints.feedback import bp as feedback_bp
    from .blueprints.interview import bp as interview_bp

    app.register_blueprint(search_bp)
    app.register_blueprint(saved_bp)
    app.register_blueprint(job_detail_bp)
    app.register_blueprint(candidate_bp)
    app.register_blueprint(company_bp)
    app.register_blueprint(feedback_bp)
    app.register_blueprint(interview_bp)
