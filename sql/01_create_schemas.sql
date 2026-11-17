-- 01_create_schemas.sql
-- Creates the single MySQL schema that holds staging and warehouse
-- tables together, matching the single MYSQL_DATABASE used by
-- docker-compose.yml. Idempotent: safe to run against an existing
-- database, and safe to run twice.

CREATE DATABASE IF NOT EXISTS flight_dw
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE flight_dw;
