-- ============================================================================
--  app_schema_v2.sql — rebuilt app schema for Jobs Intelligence AI (greenfield)
-- ============================================================================
--  Canonical DDL for the reworked `Jobs_Intelligence_AI` app database.
--  Supersedes app_schema.sql (the old sk_-prefix design). See
--  documentation/jobs_intelligence_ai/planning/FRONTEND_DB_REWORK_PLAN.md §3.2.
--
--  Model:
--    * account_company (tenant)  ->  app_user (its staff; role + visibility)
--    * saved_candidates = the ONE normal app-owned table (full candidate record;
--      account_company_id = privacy boundary, owner_id = the employee who owns it)
--    * saved_jobs / saved_companies / saved_contacts = thin junction/reference
--      tables (owner_id + country + the market row's id + a little metadata);
--      saved_jobs also links to a saved_candidate and carries the Won/Lost status
--    * country is a CHAR(2) column ('at' | 'sk'), replacing the old sk_ prefix
--    * jobs / companies / contacts live in the per-country market DBs and are
--      referenced by (country, id) — no cross-DB FK
--    * job_vs_sync / sk_job_vs_sync (vector-store sync) are PRESERVED separately,
--      NOT recreated here
--
--  Decisions baked in: contacts are catalogue-saved (no hand-created contact
--  table for now); saved_jobs.job_id is BIGINT (market jobs.job_id is INT).
--
--  STATUS: NOT YET APPLIED. Backup of the current app DB is in schema
--  `Jobs_Intelligence_AI_prerework`. Cutover (run deliberately, after backup):
--    1) drop the old app tables EXCEPT job_vs_sync / sk_job_vs_sync
--    2) run this script
--    3) seed one account_company + the app_user logins
--    4) adapt + verify the app code, then remove the backup once happy
--
--  Run:
--    mysql -h <host> -P <port> -u <user> -p Jobs_Intelligence_AI < sql/app_schema_v2.sql
-- ============================================================================

USE `Jobs_Intelligence_AI`;

-- ── Tenant + users ──────────────────────────────────────────────────────────
CREATE TABLE `account_company` (              -- the firm whose staff log in
  `id`          BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `name`        VARCHAR(255)    NOT NULL,
  `created_at`  DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `app_user` (                     -- a person who logs in; one company
  `id`                 BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `account_company_id` BIGINT UNSIGNED NOT NULL,
  `username`           VARCHAR(128)    NOT NULL,
  `password_hash`      VARCHAR(255)    NOT NULL,
  `display_name`       VARCHAR(255)    NOT NULL DEFAULT '',
  `email`              VARCHAR(255)    NULL,
  `role`               ENUM('admin','member') NOT NULL DEFAULT 'member',
  `visibility`         ENUM('own','all')      NOT NULL DEFAULT 'all',
  `created_at`         DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_user_username` (`username`),
  KEY `ix_user_company` (`account_company_id`),
  CONSTRAINT `fk_user_company` FOREIGN KEY (`account_company_id`) REFERENCES `account_company` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ── Candidate record (normal table — full data, app-owned) ───────────────────
CREATE TABLE `saved_candidates` (             -- staff-created; company-owned, user-tracked
  `id`                 BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `account_company_id` BIGINT UNSIGNED NOT NULL,           -- privacy boundary
  `owner_id`           BIGINT UNSIGNED NOT NULL,           -- the employee who owns it
  `country`            CHAR(2)         NOT NULL,           -- 'at' | 'sk'
  `full_name`          VARCHAR(255)    NOT NULL,
  `email`              VARCHAR(255)    NULL,
  `phone`              VARCHAR(64)     NULL,
  `linkedin`           VARCHAR(512)    NULL,
  `headline`           VARCHAR(512)    NULL,
  `location`           VARCHAR(255)    NULL,
  `seniority`          VARCHAR(32)     NULL,
  `years_experience`   INT             NULL,
  `industry`           VARCHAR(255)    NULL,
  `current_company`    VARCHAR(255)    NULL,
  `status`             VARCHAR(32)     NOT NULL DEFAULT 'New',   -- candidate hiring status
  `source`             ENUM('cv_upload','manual','imported') NOT NULL DEFAULT 'cv_upload',
  `is_template`        TINYINT(1)      NOT NULL DEFAULT 0,
  `skills`             JSON NULL,  `experiences`    JSON NULL,  `education` JSON NULL,
  `certifications`     JSON NULL,  `top_skills`     JSON NULL,  `strengths` JSON NULL,
  `ai_summary`         TEXT NULL,  `raw_profile`    JSON NULL,
  `enriched_at`        DATETIME NULL, `ai_model`    VARCHAR(64) NULL,
  `created_at`         DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at`         DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `ix_cand_company` (`account_company_id`),
  KEY `ix_cand_owner`   (`owner_id`),
  KEY `ix_cand_country` (`country`),
  CONSTRAINT `fk_cand_company` FOREIGN KEY (`account_company_id`) REFERENCES `account_company` (`id`),
  CONSTRAINT `fk_cand_owner`   FOREIGN KEY (`owner_id`)           REFERENCES `app_user` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ── User-owned saved references (thin junctions into the market catalogue) ────
CREATE TABLE `saved_jobs` (                   -- a job shortlisted FOR a saved candidate
  `id`                 BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `account_company_id` BIGINT UNSIGNED NOT NULL,
  `owner_id`           BIGINT UNSIGNED NOT NULL,           -- who saved/owns it
  `saved_candidate_id` BIGINT UNSIGNED NOT NULL,           -- which candidate it's for
  `country`            CHAR(2)         NOT NULL,           -- which market the job is from
  `job_id`             BIGINT UNSIGNED NOT NULL,           -- logical ref -> <country DB>.jobs (no cross-DB FK)
  `status`             ENUM('new','in_progress','proposal_sent','won','lost') NOT NULL DEFAULT 'new',
  `score`              DECIMAL(5,4)    NULL,
  `grade`              CHAR(1)         NULL,
  `job_snapshot`       JSON            NULL,               -- job fields at save time
  `notes`              TEXT            NULL,
  `saved_at`           DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_saved_jobs` (`saved_candidate_id`, `country`, `job_id`),
  KEY `ix_sj_owner` (`owner_id`),
  KEY `ix_sj_company` (`account_company_id`),
  CONSTRAINT `fk_sj_company`   FOREIGN KEY (`account_company_id`) REFERENCES `account_company` (`id`),
  CONSTRAINT `fk_sj_owner`     FOREIGN KEY (`owner_id`)           REFERENCES `app_user` (`id`),
  CONSTRAINT `fk_sj_candidate` FOREIGN KEY (`saved_candidate_id`) REFERENCES `saved_candidates` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `saved_companies` (              -- a target company a user bookmarked
  `id`                 BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `account_company_id` BIGINT UNSIGNED NOT NULL,
  `owner_id`           BIGINT UNSIGNED NOT NULL,
  `country`            CHAR(2)         NOT NULL,
  `target_company_id`  BIGINT UNSIGNED NOT NULL,           -- logical ref -> <country DB>.companies
  `notes`              TEXT            NULL,
  `saved_at`           DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_saved_companies` (`owner_id`, `country`, `target_company_id`),
  KEY `ix_sco_company` (`account_company_id`),
  CONSTRAINT `fk_sco_company` FOREIGN KEY (`account_company_id`) REFERENCES `account_company` (`id`),
  CONSTRAINT `fk_sco_owner`   FOREIGN KEY (`owner_id`)           REFERENCES `app_user` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `saved_contacts` (               -- a contact (person at a company) a user bookmarked
  `id`                 BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `account_company_id` BIGINT UNSIGNED NOT NULL,
  `owner_id`           BIGINT UNSIGNED NOT NULL,
  `country`            CHAR(2)         NOT NULL,
  `contact_id`         BIGINT UNSIGNED NOT NULL,           -- logical ref -> <country DB>.contacts
  `notes`              TEXT            NULL,
  `saved_at`           DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_saved_contacts` (`owner_id`, `country`, `contact_id`),
  KEY `ix_sct_company` (`account_company_id`),
  CONSTRAINT `fk_sct_company` FOREIGN KEY (`account_company_id`) REFERENCES `account_company` (`id`),
  CONSTRAINT `fk_sct_owner`   FOREIGN KEY (`owner_id`)           REFERENCES `app_user` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ── Cross-cutting ─────────────────────────────────────────────────────────────
CREATE TABLE `audit_log` (
  `id`                 BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `account_company_id` BIGINT UNSIGNED NULL,
  `user_id`            BIGINT UNSIGNED NULL,               -- the actor
  `action`             VARCHAR(64)     NOT NULL,
  `entity_type`        VARCHAR(64)     NULL,               -- 'saved_candidate' | 'saved_job' | ...
  `entity_id`          BIGINT UNSIGNED NULL,
  `detail`             TEXT            NULL,
  `created_at`         DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `ix_audit_company` (`account_company_id`),
  KEY `ix_audit_created` (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `feedback` (
  `id`                 BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `account_company_id` BIGINT UNSIGNED NULL,
  `user_id`            BIGINT UNSIGNED NULL,
  `message`            TEXT            NOT NULL,
  `context`            VARCHAR(64)     NULL,
  `created_at`         DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `ix_feedback_created` (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
