-- ============================================================================
--  app_schema_v2.sql — app schema for Jobs Intelligence AI
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
--      tables (owner_id + country + the market row's id + snapshot metadata);
--      saved_jobs also links to a saved_candidate and carries the sales-pipeline
--      status (canonical codes: new / in_progress / proposal_sent / won / lost)
--    * country is a CHAR(2) column ('at' | 'sk'), replacing the old sk_ prefix
--    * jobs / companies / contacts live in the per-country market DBs and are
--      referenced by (country, id) — no cross-DB FK
--    * job_vs_sync / sk_job_vs_sync (vector-store sync) are PRESERVED separately,
--      NOT recreated here
--
--  STATUS: MIRROR OF LIVE — regenerated from SHOW CREATE TABLE on 2026-07-02,
--  the day the cutover completed: the old tables (candidate, sk_candidate,
--  candidate_saved_job, sk_candidate_saved_job, candidate_company,
--  sk_candidate_company, company, sk_company, target_candidate,
--  sk_target_candidate, users, sk_feedback, sk_audit_log) were DROPPED after
--  checksum-verifying them against the backup schema
--  `Jobs_Intelligence_AI_prerework` (which retains a full pre-rework copy).
--  Seeded: account_company id=1 'Acme Recruitment' + 3 app_user
--  logins (admin / Monika2 / hr_manager).
--
--  Run only against a fresh/empty DB:
--    mysql -h <host> -P <port> -u <user> -p Jobs_Intelligence_AI < data/sql/app_schema_v2.sql
-- ============================================================================

USE `Jobs_Intelligence_AI`;

CREATE TABLE `account_company` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `name` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `app_user` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `account_company_id` bigint unsigned NOT NULL,
  `username` varchar(128) COLLATE utf8mb4_unicode_ci NOT NULL,
  `password_hash` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `display_name` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '',
  `email` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `role` enum('admin','member') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'member',
  `visibility` enum('own','all') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'all',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_user_username` (`username`),
  KEY `ix_user_company` (`account_company_id`),
  CONSTRAINT `fk_user_company` FOREIGN KEY (`account_company_id`) REFERENCES `account_company` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `saved_candidates` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `account_company_id` bigint unsigned NOT NULL,
  `owner_id` bigint unsigned NOT NULL,
  `country` char(2) COLLATE utf8mb4_unicode_ci NOT NULL,
  `full_name` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `email` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `phone` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `linkedin` varchar(512) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `headline` varchar(512) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `title` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `experience_years` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `location` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `languages` varchar(512) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `salary_expectation` varchar(128) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `availability` varchar(128) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `summary` text COLLATE utf8mb4_unicode_ci,
  `seniority` varchar(32) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `years_experience` int DEFAULT NULL,
  `industry` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `current_company` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `role_category` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `education_level` varchar(128) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `management_experience` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `profile_pic_url` varchar(1024) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `public_identifier` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `follower_count` int DEFAULT NULL,
  `status` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'New',
  `source` enum('cv_upload','manual','imported') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'cv_upload',
  `is_template` tinyint(1) NOT NULL DEFAULT '0',
  `skills` json DEFAULT NULL,
  `experiences` json DEFAULT NULL,
  `education` json DEFAULT NULL,
  `certifications` json DEFAULT NULL,
  `top_skills` json DEFAULT NULL,
  `specializations` json DEFAULT NULL,
  `strengths` json DEFAULT NULL,
  `raw_profile` json DEFAULT NULL,
  `estimated_salary_min` int DEFAULT NULL,
  `estimated_salary_max` int DEFAULT NULL,
  `ai_summary` text COLLATE utf8mb4_unicode_ci,
  `ai_model` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `enriched_at` datetime DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `ix_cand_company` (`account_company_id`),
  KEY `ix_cand_owner` (`owner_id`),
  KEY `ix_cand_country` (`country`),
  KEY `ix_cand_name` (`full_name`),
  CONSTRAINT `fk_cand_company` FOREIGN KEY (`account_company_id`) REFERENCES `account_company` (`id`),
  CONSTRAINT `fk_cand_owner` FOREIGN KEY (`owner_id`) REFERENCES `app_user` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `saved_jobs` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `account_company_id` bigint unsigned NOT NULL,
  `owner_id` bigint unsigned NOT NULL,
  `saved_candidate_id` bigint unsigned NOT NULL,
  `country` char(2) COLLATE utf8mb4_unicode_ci NOT NULL,
  `job_id` bigint unsigned NOT NULL,
  `status` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'new',
  `score` decimal(5,4) DEFAULT NULL,
  `grade` char(1) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `job_snapshot` json DEFAULT NULL,
  `notes` text COLLATE utf8mb4_unicode_ci,
  `extras` json DEFAULT NULL,
  `saved_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_saved_jobs` (`saved_candidate_id`,`country`,`job_id`),
  KEY `ix_sj_owner` (`owner_id`),
  KEY `ix_sj_company` (`account_company_id`),
  CONSTRAINT `fk_sj_candidate` FOREIGN KEY (`saved_candidate_id`) REFERENCES `saved_candidates` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_sj_company` FOREIGN KEY (`account_company_id`) REFERENCES `account_company` (`id`),
  CONSTRAINT `fk_sj_owner` FOREIGN KEY (`owner_id`) REFERENCES `app_user` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `saved_companies` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `account_company_id` bigint unsigned NOT NULL,
  `owner_id` bigint unsigned NOT NULL,
  `country` char(2) COLLATE utf8mb4_unicode_ci NOT NULL,
  `target_company_id` bigint unsigned NOT NULL,
  `snapshot` json DEFAULT NULL,
  `notes` text COLLATE utf8mb4_unicode_ci,
  `saved_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_saved_companies` (`owner_id`,`country`,`target_company_id`),
  KEY `ix_sco_company` (`account_company_id`),
  CONSTRAINT `fk_sco_company` FOREIGN KEY (`account_company_id`) REFERENCES `account_company` (`id`),
  CONSTRAINT `fk_sco_owner` FOREIGN KEY (`owner_id`) REFERENCES `app_user` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `saved_contacts` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `account_company_id` bigint unsigned NOT NULL,
  `owner_id` bigint unsigned NOT NULL,
  `country` char(2) COLLATE utf8mb4_unicode_ci NOT NULL,
  `contact_id` bigint unsigned NOT NULL,
  `snapshot` json DEFAULT NULL,
  `notes` text COLLATE utf8mb4_unicode_ci,
  `saved_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_saved_contacts` (`owner_id`,`country`,`contact_id`),
  KEY `ix_sct_company` (`account_company_id`),
  CONSTRAINT `fk_sct_company` FOREIGN KEY (`account_company_id`) REFERENCES `account_company` (`id`),
  CONSTRAINT `fk_sct_owner` FOREIGN KEY (`owner_id`) REFERENCES `app_user` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `audit_log` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `account_company_id` bigint unsigned DEFAULT NULL,
  `user_id` bigint unsigned DEFAULT NULL,
  `actor` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `action` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `entity_type` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `entity_id` bigint unsigned DEFAULT NULL,
  `candidate_id` bigint unsigned DEFAULT NULL,
  `detail` text COLLATE utf8mb4_unicode_ci,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_audit_candidate` (`candidate_id`),
  KEY `idx_audit_created` (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `feedback` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `account_company_id` bigint unsigned DEFAULT NULL,
  `user_id` bigint unsigned DEFAULT NULL,
  `message` text COLLATE utf8mb4_unicode_ci NOT NULL,
  `context` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_by` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_feedback_created` (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

