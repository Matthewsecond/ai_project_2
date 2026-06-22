-- ============================================================================
--  app_schema.sql — Slovak app-pipeline tables for Jobs Intelligence AI
-- ============================================================================
--  The app pipeline (saved jobs, candidate profiles, employer catalogue,
--  guided-builder targets, audit trail, feedback) lives in the shared
--  `Jobs_Intelligence_AI` schema. Austria and Slovakia use the SAME schema but
--  SEPARATE tables, kept apart by a per-country table prefix so candidates never
--  mix (config.TABLE_PREFIX → "" for Austria, "sk_" for Slovakia):
--
--      Austria        Slovakia
--      ----------     -------------------
--      candidate            sk_candidate
--      candidate_saved_job  sk_candidate_saved_job
--      company              sk_company
--      candidate_company    sk_candidate_company
--      target_candidate     sk_target_candidate
--      audit_log            sk_audit_log
--      feedback             sk_feedback
--
--  `users` (login) is intentionally NOT split — it is shared across both markets.
--
--  This script creates the Slovak (sk_*) tables as exact structural copies of the
--  Austrian ones (CREATE TABLE ... LIKE copies columns + indexes) and re-adds the
--  foreign keys (LIKE does not copy FKs). It is idempotent-ish: the CREATEs use
--  IF NOT EXISTS, but the ALTER ... ADD CONSTRAINT lines will error if the FK
--  already exists — skip them on a re-run.
--
--  Already applied to the live DB via the MySQL MCP on 2026-06-10; kept here as
--  the source of record / for rebuilding the SK tables elsewhere.
--
--  Run:
--      mysql -h <host> -P <port> -u <user> -p Jobs_Intelligence_AI < sql/app_schema.sql
-- ============================================================================

USE `Jobs_Intelligence_AI`;

-- ── Structural copies (columns + indexes; FKs added below) ───────────────────
CREATE TABLE IF NOT EXISTS `sk_candidate`            LIKE `candidate`;
CREATE TABLE IF NOT EXISTS `sk_company`              LIKE `company`;
CREATE TABLE IF NOT EXISTS `sk_candidate_saved_job`  LIKE `candidate_saved_job`;
CREATE TABLE IF NOT EXISTS `sk_candidate_company`    LIKE `candidate_company`;
CREATE TABLE IF NOT EXISTS `sk_target_candidate`     LIKE `target_candidate`;
CREATE TABLE IF NOT EXISTS `sk_audit_log`            LIKE `audit_log`;
CREATE TABLE IF NOT EXISTS `sk_feedback`             LIKE `feedback`;

-- ── Foreign keys (mirror the Austrian rules) ─────────────────────────────────
--  candidate erasure cascades to a candidate's saved jobs and company links;
--  the company catalogue row itself is never deleted by the app.
ALTER TABLE `sk_candidate_saved_job`
    ADD CONSTRAINT `fk_sk_saved_candidate`
        FOREIGN KEY (`candidate_id`) REFERENCES `sk_candidate` (`candidate_id`)
        ON DELETE CASCADE ON UPDATE CASCADE;

ALTER TABLE `sk_candidate_company`
    ADD CONSTRAINT `fk_sk_cc_candidate`
        FOREIGN KEY (`candidate_id`) REFERENCES `sk_candidate` (`candidate_id`)
        ON DELETE CASCADE ON UPDATE NO ACTION;

ALTER TABLE `sk_candidate_company`
    ADD CONSTRAINT `fk_sk_cc_company`
        FOREIGN KEY (`company_id`) REFERENCES `sk_company` (`company_id`)
        ON DELETE CASCADE ON UPDATE NO ACTION;
