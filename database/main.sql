/*
 Navicat Premium Dump SQL

 Source Server         : mineru
 Source Server Type    : SQLite
 Source Server Version : 3045000 (3.45.0)
 Source Schema         : main

 Target Server Type    : SQLite
 Target Server Version : 3045000 (3.45.0)
 File Encoding         : 65001

 Date: 18/06/2025 11:25:00
*/

PRAGMA foreign_keys = false;

-- ----------------------------
-- Table structure for active_tasks
-- ----------------------------
DROP TABLE IF EXISTS "active_tasks";
CREATE TABLE "active_tasks" (
  "task_id" TEXT NOT NULL,
  "start_time" TEXT DEFAULT CURRENT_TIMESTAMP,
  "queued_time" TEXT,
  "status" TEXT NOT NULL,
  PRIMARY KEY ("task_id"),
  FOREIGN KEY ("task_id") REFERENCES "tasks" ("task_id") ON DELETE NO ACTION ON UPDATE NO ACTION
);

-- ----------------------------
-- Table structure for sqlite_sequence
-- ----------------------------
DROP TABLE IF EXISTS "sqlite_sequence";
CREATE TABLE sqlite_sequence(name,seq);

-- ----------------------------
-- Table structure for tasks
-- ----------------------------
DROP TABLE IF EXISTS "tasks";
CREATE TABLE "tasks" (
  "id" INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
  "task_id" text NOT NULL,
  "bucket_name" TEXT,
  "object_key" TEXT NOT NULL,
  "output_bucket" TEXT,
  "ocr_enabled" integer NOT NULL DEFAULT 0,
  "table_enabled" integer NOT NULL DEFAULT 0,
  "ocr_lang" TEXT,
  "output_info" TEXT DEFAULT '',
  "create_time" text NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "finish_time" text DEFAULT '',
  CONSTRAINT "unique_task_id" UNIQUE ("task_id") ON CONFLICT REPLACE
);

-- ----------------------------
-- Auto increment value for tasks
-- ----------------------------

-- ----------------------------
-- Indexes structure for table tasks
-- ----------------------------
CREATE INDEX "main"."index_task_id"
ON "tasks" (
  "task_id" ASC
);

PRAGMA foreign_keys = true;
